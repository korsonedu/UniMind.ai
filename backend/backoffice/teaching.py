"""Directus teaching operations; all content uses the configured Korson scope."""
import logging
from datetime import timedelta
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers

from ai_assistant.models import AIChatMessage, Bot, Conversation
from quizzes.models import ContentPipelineTask, KnowledgePoint, Question
from quizzes.serializers import ContentPipelineTaskSerializer
from .common import content_institution, identity, paginate

DIFFICULTIES = ['entry', 'easy', 'normal', 'hard', 'extreme']


def scoped(model):
    return model.objects.filter(institution=content_institution(required=True))


def students():
    scope = content_institution(required=True)
    now = timezone.now()
    explicit = Q(course_student_status__is_course_student=True)
    legacy = Q(course_student_status__isnull=True, institution=scope) & (
        Q(is_member=True) & (Q(membership_expires_at__isnull=True) | Q(membership_expires_at__gt=now)) |
        Q(learning_grants__revoked=False, learning_grants__starts_at__lte=now, learning_grants__expires_at__gt=now))
    return get_user_model().objects.filter(explicit | legacy, is_active=True,
        is_superuser=False, is_staff=False).distinct()


def list_students(request, data):
    qs = students().order_by('nickname', 'id')
    if data.get('search'):
        query = str(data['search'])[:200]
        qs = qs.filter(Q(nickname__icontains=query) | Q(username__icontains=query) | Q(email__icontains=query))
    return paginate(qs, data, lambda row: {'id': row.pk, 'name': row.nickname or row.username, 'email': row.email})


def student(data):
    qs = students()
    if data.get('student_id'):
        return get_object_or_404(qs, pk=identity(data, 'student_id'))
    name = str(data.get('student_name') or data.get('name') or '').strip()
    if not name:
        raise serializers.ValidationError('请选择学员。')
    matches = list(qs.filter(Q(nickname__icontains=name) | Q(username__icontains=name))[:2])
    if len(matches) != 1:
        raise serializers.ValidationError('学员未找到或姓名不唯一，请指定学员 ID。')
    return matches[0]


def bot():
    scope = content_institution(required=True)
    item = Bot.objects.filter(bot_type='exam_generator', is_active=True, institution=scope).first()
    if not item:
        item = Bot.objects.filter(bot_type='exam_generator', is_active=True, institution__isnull=True).first()
    if not item:
        raise serializers.ValidationError('请先配置工作台 Bot。')
    return item


def owned_tasks(request):
    qs = scoped(ContentPipelineTask).filter(
        Q(payload__kind__isnull=True) | ~Q(payload__kind__in=['chat', 'restored', 'notification']) |
        Q(created_by=request.user))
    from .tasks import expire_stale_teaching_tasks
    expire_stale_teaching_tasks(qs)
    return qs


def task_object(request, data, lock=False):
    qs = owned_tasks(request)
    if lock:
        qs = qs.select_for_update()
    return get_object_or_404(qs, pk=identity(data))


def task_item(task, detail=False):
    result = dict(ContentPipelineTaskSerializer(task).data)
    if not detail:
        result.pop('result', None)
        result['payload'] = {key: (task.payload or {}).get(key) for key in
            ('kind', 'current_stage', 'status_text', 'conversation_id', 'stages')}
    return result


def list_tasks(request, data):
    qs = owned_tasks(request).order_by('-created_at', '-id')
    if data.get('status'):
        qs = qs.filter(status=serializers.ChoiceField(choices=ContentPipelineTask.STATUS_CHOICES).run_validation(data['status']))
    if data.get('search'):
        qs = qs.filter(title__icontains=str(data['search'])[:200])
    if data.get('task_type'):
        qs = qs.filter(task_type=str(data['task_type']))
    return paginate(qs, data, task_item)


def task_detail(request, data):
    return task_item(task_object(request, data), True)


def metrics(request, data):
    days = serializers.IntegerField(min_value=1, max_value=90).run_validation(data.get('days', 14))
    qs = owned_tasks(request).filter(task_type='ai_generate', created_at__gte=timezone.now()-timedelta(days=days))
    total = qs.count()
    by_status = {row['status']: row['count'] for row in qs.values('status').annotate(count=Count('id'))}
    pipeline_rows = [row.result.get('pipeline', {}) for row in qs if isinstance(row.result, dict) and row.result.get('pipeline')]
    passed = sum(int(row.get('review_passed') or 0) for row in pipeline_rows)
    rejected = sum(int(row.get('review_rejected') or 0) for row in pipeline_rows)
    return {'window_days': days, 'total': total, 'by_status': by_status,
        'completion_rate': round(by_status.get('completed', 0)*100/max(total, 1), 2),
        'pipeline_quality': {'review_passed': passed, 'review_rejected': rejected,
            'schema_ok': sum(row.get('schema_ok') is True for row in pipeline_rows)},
        'top_errors': list(qs.filter(status='failed').values('error_message').annotate(count=Count('id')).order_by('-count')[:5]),
        'daily': list(qs.extra(select={'day': 'date(created_at)'}).values('day').annotate(count=Count('id')).order_by('day'))}


def stats(request, data):
    qs = scoped(Question)
    return {'questions': qs.count(), 'knowledge_points': scoped(KnowledgePoint).filter(level='kp').count(),
        'students': students().count(), 'review_tasks': owned_tasks(request).filter(status='review').count(),
        'by_subject': list(qs.values('knowledge_point__subject').annotate(count=Count('id')).order_by('-count')),
        'by_difficulty': list(qs.values('difficulty_level').annotate(count=Count('id'))),
        'by_type': list(qs.values('q_type').annotate(count=Count('id')))}


def search_knowledge(request, data):
    qs = scoped(KnowledgePoint).filter(name__icontains=str(data.get('query', ''))[:200])
    if data.get('subject'):
        qs = qs.filter(subject=str(data['subject']))
    return paginate(qs.order_by('order', 'id'), data, lambda row: {
        'id': row.pk, 'name': row.name, 'code': row.code, 'level': row.level,
        'subject': row.subject, 'description': row.description})


def browse(request, data):
    from articles.models import Article
    from courses.models import Course
    kind = serializers.ChoiceField(choices=['courses', 'questions', 'articles']).run_validation(data.get('kind'))
    model = {'courses': Course, 'questions': Question, 'articles': Article}[kind]
    qs = scoped(model)
    field = 'text' if kind == 'questions' else 'title'
    if data.get('query'):
        qs = qs.filter(**{field+'__icontains': str(data['query'])[:200]})
    return paginate(qs.order_by('-created_at'), data, lambda row: {'id': row.pk,
        'title': getattr(row, field), 'description': getattr(row, 'description', ''),
        'content': getattr(row, 'content', ''), 'q_type': getattr(row, 'q_type', ''),
        'answer': getattr(row, 'correct_answer', '')})


def student_detail(request, data):
    from users.views import _build_report_data
    item = student(data)
    start = serializers.DateTimeField().run_validation(data['date_from']) if data.get('date_from') else timezone.now()-timedelta(days=30)
    end = serializers.DateTimeField().run_validation(data['date_to']) if data.get('date_to') else timezone.now()
    if start > end:
        raise serializers.ValidationError('开始时间应早于结束时间。')
    return {'student_id': item.pk, 'student_name': item.nickname or item.username,
        'date_from': start.isoformat(), 'date_to': end.isoformat(), 'report': _build_report_data(item, start, end)}


def conversations(request, data):
    qs = Conversation.objects.filter(user=request.user, bot__bot_type='exam_generator')
    return paginate(qs.order_by('-updated_at'), data, lambda row: {
        'id': str(row.conversation_id), 'title': row.title, 'updated_at': row.updated_at})


def history(request, data):
    cid = serializers.UUIDField().run_validation(data.get('conversation_id'))
    get_object_or_404(Conversation, conversation_id=cid, user=request.user, bot__bot_type='exam_generator')
    messages = AIChatMessage.objects.filter(user=request.user, conversation_id=cid, bot__bot_type='exam_generator').order_by('-timestamp', '-id')
    result = paginate(messages, data, lambda row: {'id': row.pk, 'role': row.role, 'content': row.content,
        'metadata': row.metadata, 'timestamp': row.timestamp})
    result['items'].reverse()
    result['tasks'] = [task_item(row, True) for row in scoped(ContentPipelineTask).filter(
        created_by=request.user, payload__conversation_id=str(cid)).order_by('-id')[:20]]
    return result


def locked_actor(request):
    # Serialize retries for one administrator without a new idempotency table.
    get_user_model().objects.select_for_update().get(pk=request.user.pk)


def request_key(data):
    return str(serializers.UUIDField().run_validation(data.get('request_id')))


def create_task(request, data, kind, payload, title):
    locked_actor(request)
    key = request_key(data)
    existing = scoped(ContentPipelineTask).filter(created_by=request.user, request_id=key).first()
    if existing:
        request.backoffice_no_change = True
        return task_item(existing, True)
    task = ContentPipelineTask.objects.create(created_by=request.user, institution=content_institution(required=True),
        task_type='ai_generate' if kind in ['quick', 'arc', 'bulk'] else 'other',
        title=title[:200], status='pending', payload={'kind': kind, **payload}, request_id=key)
    from .tasks import run_teaching_task

    def enqueue():
        try:
            run_teaching_task.delay(task.pk)
        except Exception:
            logging.getLogger(__name__).exception('Teaching task enqueue failed: %s', task.pk)
            ContentPipelineTask.objects.filter(pk=task.pk, status='pending').update(
                status='failed', error_message='任务队列暂不可用，请稍后重试。', finished_at=timezone.now())
    transaction.on_commit(enqueue)
    return task_item(task, True)


def launch(request, data):
    kind = serializers.ChoiceField(choices=['quick', 'arc', 'bulk']).run_validation(data.get('kind', 'quick'))
    payload = {'difficulty': serializers.ChoiceField(choices=DIFFICULTIES).run_validation(data.get('difficulty', 'normal')),
        'count': serializers.IntegerField(min_value=1, max_value=1000 if kind == 'bulk' else 100).run_validation(data.get('count', 5)),
        'types': serializers.ListField(child=serializers.ChoiceField(choices=['objective', 'subjective:noun', 'subjective:short', 'subjective:essay', 'subjective:calculate']), required=False).run_validation(data.get('types', []))}
    if kind == 'bulk':
        payload['subject'] = serializers.CharField(max_length=120).run_validation(data.get('subject'))
        payload['kp_code'] = str(data.get('kp_code') or '')
        payload['difficulty_dist'] = distribution(data.get('difficulty_dist'), DIFFICULTIES)
        payload['type_dist'] = distribution(data.get('type_dist'), ['objective', 'subjective'])
        if not scoped(KnowledgePoint).filter(level='kp', subject=payload['subject']).exists():
            raise serializers.ValidationError('该学科在科晟内容范围内没有考点。')
    else:
        payload['kp_ids'] = validate_kps(data.get('kp_ids'))
    return create_task(request, data, kind, payload, str(data.get('title') or {'quick': '快速出题', 'arc': 'ARC 精修', 'bulk': '批量初始化'}[kind]))


def distribution(value, choices):
    if value is None:
        return {}
    result = serializers.DictField(child=serializers.FloatField(min_value=0)).run_validation(value)
    if not result or set(result)-set(choices) or sum(result.values()) <= 0:
        raise serializers.ValidationError('比例须包含有效分类及正数权重。')
    total = sum(result.values())
    return {key: weight/total for key, weight in result.items()}


def validate_kps(value):
    ids = serializers.ListField(child=serializers.IntegerField(min_value=1), min_length=1, max_length=100).run_validation(value)
    if scoped(KnowledgePoint).filter(pk__in=set(ids), level='kp').count() != len(set(ids)):
        raise serializers.ValidationError('考点不在科晟内容范围内。')
    return list(dict.fromkeys(ids))


def chat(request, data):
    message = serializers.CharField(max_length=16000).run_validation(data.get('message'))
    cid = serializers.UUIDField().run_validation(data.get('conversation_id'))
    selected_bot = bot()
    locked_actor(request)
    existing = Conversation.objects.filter(conversation_id=cid).first()
    if existing and (existing.user_id != request.user.pk or existing.bot.bot_type != 'exam_generator'):
        raise serializers.ValidationError('会话不存在。')
    if not existing:
        Conversation.objects.create(user=request.user, bot=selected_bot, conversation_id=cid, title=message[:120])
    from .tasks import expire_stale_teaching_tasks
    expire_stale_teaching_tasks(scoped(ContentPipelineTask).filter(created_by=request.user, payload__conversation_id=str(cid)))
    active = scoped(ContentPipelineTask).filter(created_by=request.user, payload__conversation_id=str(cid), status__in=['pending', 'running']).exclude(request_id=request_key(data)).exists()
    if active:
        raise serializers.ValidationError('此会话仍有任务正在处理，请稍候。')
    return create_task(request, data, 'chat', {'message': message, 'bot_id': existing.bot_id if existing else selected_bot.pk,
        'conversation_id': str(cid)}, message[:60])


def require_confirmation(data):
    if data.get('confirmed') is not True:
        raise serializers.ValidationError('请先预览并明确确认操作。')


def review(request, data):
    require_confirmation(data)
    task = task_object(request, data, True)
    if task.status in ['completed', 'cancelled']:
        request.backoffice_no_change = True
        return {'id': task.pk, 'status': task.status, 'saved': (task.result or {}).get('saved', 0)}
    if task.status != 'review':
        raise serializers.ValidationError('该任务尚未进入人工审核。')
    action = serializers.ChoiceField(choices=['approve', 'reject']).run_validation(data.get('action'))
    if action == 'approve':
        source = (task.result or {}).get('questions') or []
        indices = serializers.ListField(child=serializers.IntegerField(min_value=0), min_length=1).run_validation(data.get('question_indices'))
        edited = serializers.DictField(child=serializers.DictField()).run_validation(data.get('edited_questions', {}))
        selected = []
        for index in dict.fromkeys(indices):
            if index >= len(source):
                raise serializers.ValidationError('题目序号已失效，请刷新。')
            question = dict(edited.get(str(index), source[index]))
            validate_kps([question.get('kp_id') or question.get('knowledge_point_id')])
            selected.append(question)
        from .quizzes import save_question
        for question in selected:
            points = question.get('grading_points')
            if isinstance(points, list):
                points = '\n'.join(str(point) for point in points)
            save_question(request, {'knowledge_point': question.get('kp_id') or question.get('knowledge_point_id'),
                'text': question.get('question') or question.get('text'),
                'q_type': question.get('q_type', 'objective'),
                'subjective_type': question.get('subjective_type') or None,
                'difficulty_level': question.get('difficulty_level', 'normal'),
                'options': question.get('options'), 'correct_answer': question.get('answer') or question.get('correct_answer'),
                'grading_points': points or '', 'rubric': question.get('rubric'),
                'ai_answer': question.get('explanation') or ''})
        saved = len(selected)
        task.result = {**(task.result or {}), 'saved': saved, 'saved_indices': indices}
    task.status = 'completed' if action == 'approve' else 'cancelled'
    task.finished_at = timezone.now()
    task.save(update_fields=['result', 'status', 'finished_at', 'updated_at'])
    return {'id': task.pk, 'status': task.status, 'saved': (task.result or {}).get('saved', 0)}


def retry(request, data):
    source = task_object(request, data)
    if source.status not in ['failed', 'cancelled']:
        raise serializers.ValidationError('只能重试失败或已取消的任务。')
    payload = source.payload or {}
    kind = payload.get('kind')
    if kind not in ['quick', 'arc', 'bulk', 'chat', 'report']:
        # Legacy ARC/bulk tasks contain enough parameters to rerun the original service.
        kind = 'bulk' if payload.get('subject') and payload.get('total_target') else 'arc' if payload.get('kp_ids') else None
    if not kind:
        raise serializers.ValidationError('该历史任务缺少可执行参数，不能自动重试。')
    clean = {key: value for key, value in payload.items() if key not in ['kind', 'stages', 'current_stage', 'status_text']}
    if kind == 'bulk':
        clean.setdefault('count', clean.get('total_target', 500))
    elif kind in ['quick', 'arc']:
        validate_kps(clean.get('kp_ids'))
        clean.setdefault('count', clean.get('questions_per_kp', 3)*len(clean['kp_ids']))
    return create_task(request, data, kind, clean, '[重试] '+source.title)


def delete_task(request, data):
    require_confirmation(data)
    locked_actor(request)
    qs = owned_tasks(request).select_for_update().filter(pk=identity(data))
    task = qs.first()
    if task and task.status in ['pending', 'running']:
        raise serializers.ValidationError('任务执行中，暂不能删除。')
    if task:
        task.delete()
    else:
        request.backoffice_no_change = True
    return {'id': identity(data), 'deleted': True}


def notification_preview(request, data):
    item = student(data)
    return {'student_id': item.pk, 'recipient': item.nickname or item.username, 'request_id': str(uuid4()),
        'title': serializers.CharField(max_length=200).run_validation(data.get('title', '学习提醒')),
        'content': serializers.CharField(max_length=10000).run_validation(data.get('content'))}


def send_notification(request, data):
    require_confirmation(data)
    locked_actor(request)
    key = request_key(data)
    existing = scoped(ContentPipelineTask).filter(created_by=request.user, request_id=key, payload__kind='notification').first()
    if existing:
        request.backoffice_no_change = True
        return existing.result
    preview = notification_preview(request, data)
    from notifications.models import Notification
    notification = Notification.objects.create(recipient_id=preview['student_id'], title=preview['title'], content=preview['content'], ntype='system', link='/xiaoyu')
    result = {'id': notification.pk, 'recipient': preview['recipient'], 'sent': True}
    ContentPipelineTask.objects.create(created_by=request.user, institution=content_institution(required=True), task_type='other',
        status='completed', title=preview['title'], payload={'kind': 'notification'}, result=result, request_id=key, finished_at=timezone.now())
    return result


def restore_draft(request, data):
    locked_actor(request)
    message = get_object_or_404(AIChatMessage, pk=identity(data, 'message_id'), user=request.user,
        bot__bot_type='exam_generator', role='assistant')
    existing = scoped(ContentPipelineTask).filter(created_by=request.user, payload__source_message_id=message.pk).first()
    if existing:
        request.backoffice_no_change = True
        return task_item(existing, True)
    metadata = message.metadata or {}
    if metadata.get('task_id'):
        original = get_object_or_404(scoped(ContentPipelineTask), pk=metadata['task_id'], created_by=request.user)
        request.backoffice_no_change = True
        return task_item(original, True)
    questions = metadata.get('generated_questions') or metadata.get('questions') or []
    if not isinstance(questions, list) or not questions:
        raise serializers.ValidationError('这条消息没有可恢复的生成题目。')
    for question in questions:
        if not isinstance(question, dict):
            raise serializers.ValidationError('历史题目格式无效。')
        validate_kps([question.get('kp_id') or question.get('knowledge_point_id')])
    item = ContentPipelineTask.objects.create(created_by=request.user, institution=content_institution(required=True),
        task_type='ai_generate', status='review', title='恢复历史生成题目', progress=100,
        payload={'kind': 'restored', 'source_message_id': message.pk, 'conversation_id': str(message.conversation_id)},
        result={'questions': questions}, request_id=request_key(data), finished_at=timezone.now())
    return task_item(item, True)


def notification_config(request, data):
    from users.models_commercial import InstitutionNotificationConfig
    scope = content_institution(required=True)
    if scope is None:
        return {'supported': False, 'configured': False,
            'message': '当前使用全局内容范围；旧通知配置只支持机构归属，尚无对应全局配置。'}
    config = InstitutionNotificationConfig.objects.filter(institution=scope).first()
    return {'supported': True, 'configured': config is not None,
        'enabled': config.enabled if config else False, 'channel': config.channel if config else 'email',
        'due_threshold': config.due_threshold if config else 5}


def save_notification_config(request, data):
    from users.models_commercial import InstitutionNotificationConfig
    scope = content_institution(required=True)
    if scope is None:
        raise serializers.ValidationError('全局内容范围尚无对应的到期提醒配置。')
    locked_actor(request)
    values = {'enabled': serializers.BooleanField().run_validation(data.get('enabled')),
        'channel': serializers.ChoiceField(choices=['email', 'feishu']).run_validation(data.get('channel')),
        'due_threshold': serializers.IntegerField(min_value=1, max_value=100).run_validation(data.get('due_threshold'))}
    config, created = InstitutionNotificationConfig.objects.get_or_create(institution=scope, defaults=values)
    if not created:
        if all(getattr(config, key) == value for key, value in values.items()):
            request.backoffice_no_change = True
        else:
            for key, value in values.items():
                setattr(config, key, value)
            config.save(update_fields=[*values, 'updated_at'])
    return {'id': config.pk, 'supported': True, 'configured': True, **values}


def report(request, data):
    item = student(data)
    return create_task(request, data, 'report', {'student_id': item.pk, 'date_from': data.get('date_from'), 'date_to': data.get('date_to')}, '学情报告：'+(item.nickname or item.username))


READS = {'teaching.stats': stats, 'teaching.knowledge': search_knowledge,
    'teaching.browse': browse, 'teaching.student': student_detail, 'teaching.students': list_students,
    'teaching.conversations': conversations, 'teaching.history': history,
    'teaching.notification.preview': notification_preview, 'teaching.notification.config': notification_config,
    'pipeline.list': list_tasks, 'pipeline.detail': task_detail, 'pipeline.metrics': metrics}
WRITES = {'teaching.chat': chat, 'teaching.generate': launch, 'teaching.report': report,
    'teaching.notification.send': send_notification, 'teaching.notification.config.save': save_notification_config,
    'teaching.restore': restore_draft, 'pipeline.review': review,
    'pipeline.retry': retry, 'pipeline.delete': delete_task}
