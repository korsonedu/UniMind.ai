"""A block assessment groups existing project tasks, never a second progress ledger."""
from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework.exceptions import PermissionDenied, ValidationError

from ai_assistant.models import ConversationProject, ProjectLearning, ProjectLearningEvent, ProjectLearningTask
from ai_assistant.services.learning_tasks import create_task, task_data
from ai_assistant.services.ulr_config import standalone_ulr
from .block_study import visible_block_resources, _assignments, _clean_question, _generate_question, _hash, _knowledge_points
from .intake import _bank_question
from quizzes.models import Question


IN_PROGRESS = ('pending', 'running')


def context(user, block, project_id):
    project = get_object_or_404(ConversationProject, pk=project_id, user=user)
    state = get_object_or_404(ProjectLearning, project=project)
    path = state.plan.get('knowledge_path') or {}
    from ai_assistant.services.learning_knowledge import owned_version
    if not path.get('version_id'):
        raise ValidationError('请先将知识块加入当前项目，并在小宇确认学习安排。')
    version = owned_version(project, path['version_id'])
    if state.status != 'active' or version.snapshot.get('builder', {}).get('build_id') != str(block.build_id):
        raise ValidationError('请先在小宇确认当前图谱的学习安排。')
    node = next((node for node in version.snapshot['nodes'] if block.pk in node.get('builder_block_ids', [])), None)
    stage = next((stage for stage in state.plan.get('stages', []) if node and node['id'] in stage.get('knowledge_nodes', [])), None)
    if not node or not stage:
        raise ValidationError('当前学习安排未包含这个知识块，请先加入项目目标。')
    return project, state, version, node, stage


def latest(project, block, version):
    return ProjectLearningEvent.objects.filter(project=project, kind='block_assessment',
        content__block_id=block.pk, content__version_id=version.pk).order_by('-pk').first()


def assessment_data(event):
    if not event:
        return None
    tasks = {str(task.pk): task for task in ProjectLearningTask.objects.filter(project=event.project,
        pk__in=[item['task_id'] for item in event.content['items']]).select_related('project', 'exam')}
    items = [{**item, 'task': task_data(tasks[item['task_id']])} for item in event.content['items'] if item['task_id'] in tasks]
    complete = len(items) == len(event.content['items']) and all(item['task']['status'] == 'completed' for item in items)
    ratios = [item['task']['summary']['total_score'] / item['task']['summary']['max_score'] for item in items
              if item['task']['summary'] and item['task']['summary']['max_score'] and item['task']['status'] == 'completed']
    accuracy = sum(ratios) / len(ratios) if complete and ratios else None
    core = [item for item in items if item['membership_type'] == 'core']
    core_passed = complete and bool(core) and all(item['task']['summary']['total_score'] / item['task']['summary']['max_score'] >= .75 for item in core)
    return {'id': event.pk, 'block_id': event.content['block_id'], 'mode': event.content['mode'], 'items': items,
            'complete': complete, 'accuracy': accuracy, 'passed': bool(core_passed and accuracy is not None and accuracy >= .75)}


def complete_preparation(preparation, assessment):
    ProjectLearningEvent.objects.filter(pk=preparation.pk, content=preparation.content).update(content={
        **preparation.content, 'status': 'completed', 'error': '', 'assessment_id': assessment.pk})


def generate_assessment(preparation, block):
    user = preparation.project.user
    mode, retest = preparation.content['mode'], preparation.content['retest']
    project, state, version, node, stage = context(user, block, preparation.project_id)
    if version.pk != preparation.content['version_id']:
        raise ValidationError('学习安排已变化，请重新打开当前知识块。')
    claim = ProjectLearningEvent.objects.filter(pk=preparation.pk, content=preparation.content)
    previous = latest(project, block, version)
    if previous and not retest:
        return complete_preparation(preparation, previous)
    if previous and not assessment_data(previous)['complete']:
        raise ValidationError('请先完成或恢复当前检测的批改，再安排换题检验。')
    from users.feature_access import has_learning_feature
    if not has_learning_feature(user, 'quiz.exam'):
        raise PermissionDenied('当前账号尚未开放习题训练。')
    assignments = list({row.atom_id: row for row in reversed(_assignments(block))}.values())
    assignments.sort(key=lambda row: (row.membership_type != 'core', row.step.step_index, row.position))
    if not assignments:
        raise ValidationError('当前知识块尚无原子点，无法生成检测。')
    selected = [row for row in assignments if row.membership_type == 'core']
    selected += [row for row in assignments if row.membership_type != 'core'][:max(0, 4 - len(selected))]
    kps = _knowledge_points(user, assignments)
    existing = ProjectLearningTask.objects.filter(project=project, knowledge_version=version, node_id=node['id'])
    seen = {_hash(snapshot['text']) for task in existing for snapshot in task.question_snapshot.values()}
    def visible_urls():
        return {f'/course/{course_id}' if kind == 'course' else url
                for kind, course_id, url in visible_block_resources(user, block).values_list('source_kind', 'course_id', 'url')}

    urls = visible_urls()
    resources = [item for item in state.resources if item['url'] in urls][:5]
    sources = {item['id']: item for item in resources}
    source_urls = {item['url'] for item in resources}
    source_context = '\n'.join(f"{item['title']}（{'摘要或元数据' if item.get('not_web_read') else '已保存摘录'}）：{item['excerpt'][:1000]}" for item in resources)

    def check_sources(current):
        if {item['id']: item for item in current if item['id'] in sources} != sources or not source_urls <= visible_urls():
            raise ValidationError('出题参考资料已变化，请重新准备检测。')

    def before_model_request():
        if not claim.exists():
            raise ValidationError('本轮出题已失效。')
        if sources:
            check_sources(ProjectLearning.objects.values_list('resources', flat=True).get(pk=state.pk))

    prepared = []
    generated = False
    for row, q_type in [(row, 'objective') for row in selected] + ([(selected[0], 'subjective')] if mode == 'challenge' else []):
        item = None
        kp = kps.get(row.atom.name)
        if kp and q_type == 'objective':
            for question in Question.objects.filter(knowledge_point=kp, institution_id=kp.institution_id, q_type=q_type).order_by('pk'):
                bank = _bank_question(question)
                if bank:
                    bank['options'] = {option['key']: option['label'] for option in bank['options']}
                    candidate = _clean_question(bank, q_type)
                    if candidate and _hash(candidate['stem']) not in seen:
                        item = candidate
                        item['question_id'] = question.pk
                        break
        if item is None:
            before_model_request()
            item = _generate_question(row, block, q_type, seen, source_context, before_retry=before_model_request)
            generated = True
        prepared.append((row, item))
        seen.add(_hash(item['stem']))
    with transaction.atomic():
        # Serialize concurrent clicks and recheck that the confirmed path did not change during generation.
        ProjectLearning.objects.select_for_update().get(project=project)
        if not claim.exists():
            return
        _, current_state, current_version, current_node, current_stage = context(user, block, project.pk)
        if current_version.pk != version.pk or current_stage != stage or current_node != node:
            raise ValidationError('学习安排已变化，请重新打开当前知识块。')
        concurrent = latest(project, block, version)
        if concurrent and (not previous or concurrent.pk != previous.pk):
            return complete_preparation(preparation, concurrent)
        if generated and sources:
            check_sources(current_state.resources)
        items = []
        old_items = previous.content['items'] if previous else []
        for row, item in prepared:
            source = next((old['task_id'] for old in old_items if old['atom_id'] == row.atom_id and old['q_type'] == item['q_type']), None)
            args = dict(version_id=version.pk, node_id=node['id'], stage_id=stage['id'],
                title=f'{block.short_title} · {row.atom.name}', instructions=f'本题检查：{row.atom.goal_statement}。请独立作答，并如实记录获得的帮助。',
                purpose='recheck' if source else 'practice', source_task_id=source)
            if item.get('question_id'):
                args['question_ids'] = [item['question_id']]
            else:
                args['definition'] = dict(prompt=item['stem'], response_type='objective' if item['q_type'] == 'objective' else 'calculation' if item['subjective_type'] == 'calculate' else 'reasoning',
                    options=item['options'], reference_answer=item['correct_answer'], criteria=[item['grading_points'] or '按标准答案比对。'], sources=list(sources))
            task = create_task(project, args)
            items.append(dict(task_id=str(task.pk), atom_id=row.atom_id, atom_name=row.atom.name,
                              membership_type=row.membership_type, q_type=item['q_type']))
        event = ProjectLearningEvent.objects.create(project=project, kind='block_assessment', content={
            'build_id': str(block.build_id), 'block_id': block.pk, 'version_id': version.pk, 'node_id': node['id'], 'mode': mode, 'items': items})
        complete_preparation(preparation, event)


def block_assessment(user, block, project_id, *, action='read', mode='objective', retest=False):
    from django.utils import timezone
    from users.feature_access import has_learning_feature
    project, state, version, node, stage = context(user, block, project_id)
    with transaction.atomic():
        ProjectLearning.objects.select_for_update().get(project=project)
        preparation = ProjectLearningEvent.objects.filter(project=project, kind='block_prepare',
            content__block_id=block.pk, content__version_id=version.pk).order_by('-pk').first()
        if preparation and preparation.content['status'] in IN_PROGRESS:
            started = preparation.content.get('started_at', preparation.content.get('queued_at', preparation.created_at.timestamp()))
            if timezone.now().timestamp() - started > 720:
                content = {**preparation.content, 'status': 'failed', 'error': '出题已超时，请重试。',
                           'queue_retryable': preparation.content['status'] == 'pending'}
                if ProjectLearningEvent.objects.filter(pk=preparation.pk, content=preparation.content).update(content=content):
                    preparation.content = content
                else:
                    preparation.refresh_from_db()
        event = latest(project, block, version)
        if action == 'generate' and not (preparation and preparation.content['status'] in IN_PROGRESS) and (not event or retest):
            if not has_learning_feature(user, 'quiz.exam'):
                raise PermissionDenied('当前账号尚未开放习题训练。')
            if event and not assessment_data(event)['complete']:
                raise ValidationError('请先完成或恢复当前检测的批改，再安排换题检验。')
            retry = (preparation and preparation.content.get('queue_retryable')
                     and (preparation.content['mode'], preparation.content['retest']) == (mode, retest))
            native = standalone_ulr()
            if retry and preparation.content.get('requires_ulr') and not native:
                raise ValidationError('本轮出题需要 ULR，请恢复运行配置后重试。')
            queued = {'block_id': block.pk, 'version_id': version.pk, 'mode': mode, 'retest': retest,
                      'status': 'pending', 'error': '', 'queued_at': timezone.now().timestamp(), 'requires_ulr': native}
            if retry:
                preparation.content = queued
                preparation.save(update_fields=['content'])
            else:
                preparation = ProjectLearningEvent.objects.create(project=project, kind='block_prepare', content=queued)
            def dispatch():
                from .tasks import prepare_block_assessment
                try:
                    prepare_block_assessment.delay(preparation.pk)
                except Exception:
                    ProjectLearningEvent.objects.filter(pk=preparation.pk, content=queued).update(content={
                        **queued, 'status': 'failed', 'queue_retryable': True, 'error': '任务暂未能进入出题队列，请重试。'})
            transaction.on_commit(dispatch)
    if not preparation:
        return {'assessment': assessment_data(event), 'preparation': None}
    status = preparation.content['status']
    return {'assessment': assessment_data(event), 'preparation': {'status': 'pending' if status in IN_PROGRESS else status,
                                                                 'error': preparation.content['error']}}
