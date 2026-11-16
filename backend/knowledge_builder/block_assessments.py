"""A block assessment groups existing project tasks, never a second progress ledger."""
from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework.exceptions import PermissionDenied, ValidationError

from ai_assistant.models import ConversationProject, ProjectLearning, ProjectLearningEvent, ProjectLearningTask
from ai_assistant.services.learning_tasks import create_task, task_data
from .block_study import visible_block_resources, _assignments, _clean_question, _generate_question, _hash, _knowledge_points
from .intake import _bank_question
from quizzes.models import Question


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


def generate_assessment(user, block, project_id, *, mode='objective', retest=False):
    project, state, version, node, stage = context(user, block, project_id)
    previous = latest(project, block, version)
    if previous and not retest:
        return {'assessment': assessment_data(previous)}
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
    urls = {f'/course/{row.course_id}' if row.source_kind == 'course' else row.url for row in visible_block_resources(user, block)}
    sources = [item['id'] for item in state.resources if item['url'] in urls][:10]
    prepared = []
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
        item = item or _generate_question(row, block, q_type, seen)
        prepared.append((row, item))
        seen.add(_hash(item['stem']))
    with transaction.atomic():
        # Serialize concurrent clicks and recheck that the confirmed path did not change during generation.
        ProjectLearning.objects.select_for_update().get(project=project)
        _, current, current_version, current_node, current_stage = context(user, block, project_id)
        if current_version.pk != version.pk or current_stage != stage or current_node != node:
            raise ValidationError('学习安排已变化，请重新打开当前知识块。')
        concurrent = latest(project, block, version)
        if concurrent and (not previous or concurrent.pk != previous.pk):
            return {'assessment': assessment_data(concurrent)}
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
                    options=item['options'], reference_answer=item['correct_answer'], criteria=[item['grading_points'] or '按标准答案比对。'], sources=sources)
            task = create_task(project, args)
            items.append(dict(task_id=str(task.pk), atom_id=row.atom_id, atom_name=row.atom.name,
                              membership_type=row.membership_type, q_type=item['q_type']))
        event = ProjectLearningEvent.objects.create(project=project, kind='block_assessment', content={
            'build_id': str(block.build_id), 'block_id': block.pk, 'version_id': version.pk, 'node_id': node['id'], 'mode': mode, 'items': items})
    return {'assessment': assessment_data(event)}


def block_assessment(user, block, project_id, *, action='read', mode='objective', retest=False):
    from django.utils import timezone
    from users.feature_access import has_learning_feature
    project, state, version, node, stage = context(user, block, project_id)
    with transaction.atomic():
        ProjectLearning.objects.select_for_update().get(project=project)
        preparation = ProjectLearningEvent.objects.filter(project=project, kind='block_prepare',
            content__block_id=block.pk, content__version_id=version.pk).order_by('-pk').first()
        if preparation and preparation.content['status'] == 'pending' and (timezone.now() - preparation.created_at).total_seconds() > 720:
            preparation.content.update(status='failed', error='出题已超时，请重试。')
            preparation.save(update_fields=['content'])
        event = latest(project, block, version)
        if action == 'generate' and not (preparation and preparation.content['status'] == 'pending') and (not event or retest):
            if not has_learning_feature(user, 'quiz.exam'):
                raise PermissionDenied('当前账号尚未开放习题训练。')
            if event and not assessment_data(event)['complete']:
                raise ValidationError('请先完成或恢复当前检测的批改，再安排换题检验。')
            preparation = ProjectLearningEvent.objects.create(project=project, kind='block_prepare', content={
                'block_id': block.pk, 'version_id': version.pk, 'mode': mode, 'retest': retest, 'status': 'pending', 'error': ''})
            def dispatch():
                from .tasks import prepare_block_assessment
                try:
                    prepare_block_assessment.delay(preparation.pk)
                except Exception:
                    preparation.content.update(status='failed', error='任务暂未能进入出题队列，请重试。')
                    preparation.save(update_fields=['content'])
            transaction.on_commit(dispatch)
    return {'assessment': assessment_data(event), 'preparation': {'status': preparation.content['status'], 'error': preparation.content['error']} if preparation else None}
