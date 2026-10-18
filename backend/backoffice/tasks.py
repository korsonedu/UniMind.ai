"""Short-poll teaching jobs, discovered by Celery's installed-app autodiscovery."""
import logging
from datetime import timedelta
from types import SimpleNamespace

from celery import shared_task
from django.db import transaction
from django.utils import timezone

from ai_assistant.models import AIChatMessage, Bot, Conversation
from quizzes.models import ContentPipelineTask, KnowledgePoint
from .common import content_institution

logger = logging.getLogger(__name__)


def expire_stale_teaching_tasks(queryset):
    # Hard limit is 960s; allow a minute for the worker to finish recording failure.
    return queryset.filter(
        status='running', started_at__lt=timezone.now() - timedelta(seconds=1020),
        payload__kind__in=['quick', 'arc', 'bulk', 'chat', 'report'],
    ).update(status='failed', error_message='任务处理超时或工作进程已退出，请重试。',
             finished_at=timezone.now(), updated_at=timezone.now())


@shared_task(name='backoffice.run_teaching_task', soft_time_limit=900, time_limit=960)
def run_teaching_task(task_id):
    expire_stale_teaching_tasks(ContentPipelineTask.objects.filter(pk=task_id))
    # The status claim makes duplicate broker delivery harmless.
    with transaction.atomic():
        task = ContentPipelineTask.objects.select_for_update().select_related('created_by').get(pk=task_id)
        if task.status != 'pending':
            return
        task.status = 'running'
        task.started_at = timezone.now()
        task.save(update_fields=['status', 'started_at', 'updated_at'])
    try:
        from .teaching import student_detail, validate_kps
        scope = content_institution(required=True)
        if task.institution_id != (scope.pk if scope else None):
            raise ValueError('任务内容归属已变更，请重新提交。')
        from users.permissions import is_platform_admin
        if not is_platform_admin(task.created_by):
            raise ValueError('管理员账号已停用。')
        args = task.payload
        kind = args.get('kind')
        if kind in ['quick', 'arc']:
            ids = validate_kps(args.get('kp_ids'))
            kps = list(KnowledgePoint.objects.filter(institution=scope, pk__in=ids))
            count_per_kp = max(1, -(-args.get('count', 5)//len(kps)))
            if kind == 'arc':
                from quizzes.services.adversarial_pipeline import _execute_pipeline
                _execute_pipeline(task, kps, count_per_kp, difficulty=args.get('difficulty', 'normal'),
                    types=args.get('types'), institution=scope, strict_scope=True, review_only=True)
                return
            from quizzes.services.adversarial_pipeline import _author_generate
            questions = _author_generate(kps, q_per_kp=count_per_kp, difficulty=args.get('difficulty', 'normal'), types=args.get('types'))[:args.get('count', 5)]
            if not questions:
                raise ValueError('生成未返回有效题目。')
            for question in questions:
                validate_kps([question.get('kp_id')])
            task.result = {'questions': questions}
            task.status = 'review'
        elif kind == 'bulk':
            from quizzes.services.bulk_pipeline import _execute_bulk_pipeline, DEFAULT_DIFFICULTY_DIST, DEFAULT_TYPE_DIST
            _execute_bulk_pipeline(task, args['subject'], args.get('count', 500),
                args.get('difficulty_dist') or DEFAULT_DIFFICULTY_DIST,
                args.get('type_dist') or DEFAULT_TYPE_DIST, kp_code=args.get('kp_code') or None,
                institution=scope, institution_only=True, strict_scope=True, review_only=True)
            return
        elif kind == 'report':
            task.result = student_detail(SimpleNamespace(user=task.created_by), args)
            task.status = 'completed'
        elif kind == 'chat':
            run_chat(task)
        else:
            raise ValueError('此任务没有可执行的处理器。')
        task.progress = 100
        task.finished_at = timezone.now()
        task.save(update_fields=['result', 'status', 'progress', 'finished_at', 'updated_at'])
    except Exception:
        logger.exception('Teaching task failed: %s', task.pk)
        # Keep provider messages and traceback out of the browser.
        ContentPipelineTask.objects.filter(pk=task.pk).update(status='failed',
            error_message='任务执行失败，请核对参数后重试；详细原因已记录在服务日志。', finished_at=timezone.now())


def run_chat(task):
    from ai_engine.service import AIEngine
    from ai_assistant.bot_registry import get_bot_profile
    from ai_assistant.services.chat_service import AssistantChatService
    from ai_assistant.services.tool_executor import set_permitted_tools
    from .teaching_executor import TeachingExecutor
    args = task.payload
    user = task.created_by
    bot = Bot.objects.get(pk=args['bot_id'], bot_type='exam_generator', is_active=True)
    conversation = Conversation.objects.get(user=user, bot=bot, conversation_id=args['conversation_id'])
    history = list(AIChatMessage.objects.filter(user=user, bot=bot, conversation_id=conversation.conversation_id).order_by('-timestamp', '-id')[:30])
    executor = TeachingExecutor(user)
    tools = get_bot_profile('exam_generator').tools_factory()
    # Models cannot invoke a legacy handler even if they invent its name.
    tools = [item for item in tools if item['function']['name'] != 'save_questions_to_bank']
    set_permitted_tools(executor, tools)
    executor._allowed_tool_names = {item['function']['name'] for item in tools}
    prompt = AssistantChatService._build_agent_system_prompt(bot, '', '', executor.institution)
    messages = [{'role': 'system', 'content': prompt + '\n所有通知、精修启动和题目入库均需管理员在界面明确确认。不得声称已发送或已入库。'}]
    messages.extend({'role': row.role, 'content': row.content} for row in reversed(history) if row.role in ['user', 'assistant'])
    messages.append({'role': 'user', 'content': args['message']})

    def progress(step):
        payload = dict(task.payload)
        payload['status_text'] = str(step.get('label') or step.get('name') or '正在处理')[:250]
        ContentPipelineTask.objects.filter(pk=task.pk).update(payload=payload)
        task.payload = payload

    executor.on_step = progress
    response = AIEngine.call_ai_with_tools(messages=messages, tools=tools, tool_executor=executor,
        tool_choice='auto', temperature=0.6, max_tokens=2500, operation='assistant.chat.exam_generator', max_tool_rounds=8)
    content = response['choices'][0]['message']['content'] or ''
    visuals = executor.pop_pending_visuals()
    if not content.strip() and (executor.generated_batches or visuals):
        content = '结果已整理，请查看下方内容；题目须审核确认后入库。'
    if not content.strip() or response['choices'][0].get('finish_reason') in ('length', 'tool_limit'):
        raise ValueError('对话未返回完整答复。')
    metadata = {'questions': executor.generated_batches, 'confirmations': executor.confirmations,
        'visuals': visuals, 'task_id': task.pk}
    with transaction.atomic():
        AIChatMessage.objects.create(user=user, bot=bot, conversation_id=conversation.conversation_id, role='user', content=args['message'])
        AIChatMessage.objects.create(user=user, bot=bot, conversation_id=conversation.conversation_id, role='assistant', content=content, metadata=metadata)
        Conversation.objects.filter(pk=conversation.pk).update(updated_at=timezone.now())
    task.result = {'content': content, **metadata}
    task.status = 'review' if executor.generated_batches else 'completed'
