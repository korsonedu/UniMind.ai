"""Versioned decisions for the first ULR teaching flow."""
from core.utils import get_content_institution_id
from quizzes.models import Question
from users.feature_access import has_learning_feature
from ..models import AIChatMessage, ProjectLearning, TaskMemoryFrame
from . import rsi_policy
from .dsh_cards import build_tool_card
from .learning_task_evidence import verified_task_events
from .learning_tasks import available_project_tasks
from .project_learning import assert_learning_turn, current_project
from .ulr_capabilities import create_recheck


def selected_task(user, chat_context, current):
    """Resolve the selected or previously resumed task inside the owned project."""
    activity = current.metadata.get('learning_activity') or {}
    previous = AIChatMessage.objects.filter(user=user, bot=current.bot, conversation_id=current.conversation_id,
        role='assistant', metadata__engine='ulr').order_by('-pk').values_list('metadata', flat=True).first()
    prior_task = (previous or {}).get('ulr_task_id')
    task_id = activity.get('task', {}).get('id') if activity else prior_task
    if task_id and has_learning_feature(user, 'quiz.exam'):
        project, _ = current_project(user, chat_context)
        return available_project_tasks(project).select_related('exam', 'project').filter(pk=task_id).first()
    return None


def supports_objective_evidence(user, task):
    if not task or len(task.question_ids) != 1:
        return False
    snapshot = task.question_snapshot.get(str(task.question_ids[0]), {})
    return (snapshot.get('q_type') == 'objective' and bool(snapshot.get('kp_id'))
            and snapshot.get('institution_id') == get_content_institution_id(user)
            and Question.objects.filter(pk=task.question_ids[0], institution_id=snapshot['institution_id']).exists())


def record_decision(user, chat_context, current, task_id):
    """Commit only alongside the successful turn. Formal answers use the existing grading ledger."""
    task = selected_task(user, chat_context, current)
    if not supports_objective_evidence(user, task) or str(task.pk) != task_id:
        return {}, None
    state = ProjectLearning.objects.select_for_update().get(project=task.project)
    if (not state.planning_enabled or state.status != 'active' or task.stage_id != state.current_stage
            or task.knowledge_version_id != (state.plan.get('knowledge_path') or {}).get('version_id')):
        return {}, None
    assert_learning_turn(task.project, current)
    rows = verified_task_events(task.project, task.knowledge_version_id)['events']
    evidence = next((event.content for event, source, _ in rows if source.pk == task.pk), None)
    if not evidence:
        if not task.exam_id and task.purpose != 'recheck' and ('提示' in current.content or 'hint' in current.content.casefold().split()):
            return {'action': 'respond_to_hint_request', 'presentation': 'unknown'}, None
        return {}, None
    if task.purpose == 'recheck':
        offer = AIChatMessage.objects.filter(user=user, bot=current.bot, role='assistant',
            metadata__ulr_teaching__recheck_task_id=str(task.pk), metadata__ulr_teaching__action='offer_recheck'
        ).order_by('pk').values_list('metadata', flat=True).first()
        linked = {key: offer['ulr_teaching'][key] for key in ('strategy', 'source_result_id')} if offer else {}
        return {'action': 'record_recheck_result', 'result_id': evidence['result_id'],
            'assistance': evidence['assistance'], 'outcome': evidence['outcome'], **linked}, None
    if evidence['assistance'] != 'hint' or evidence['outcome'] != 'success':
        return {}, None

    previous = AIChatMessage.objects.filter(user=user, bot=current.bot, role='assistant',
        metadata__ulr_teaching__source_result_id=evidence['result_id'],
        metadata__ulr_teaching__action__in=('wait', 'no_question', 'offer_recheck', 'already_submitted'),
    ).order_by('-pk').values_list('metadata', flat=True).first()
    prior = previous['ulr_teaching'] if previous else None
    frame_id, program_digest = None, ''
    if not prior:
        frame_id = current.metadata.get('sdtm_frame_id') or (
            current.metadata.get('learning_snapshot') or {}).get('memory_frame_id')
        program_digest = current.metadata.get('sdtm_program_digest') or ''
        frames = TaskMemoryFrame.objects.filter(memory__project=task.project, memory__owner=user)
        frame = frames.filter(pk=frame_id).values_list('pk', 'program__digest').first() if frame_id else None
        if not frame:
            frame = frames.order_by('-revision').values_list('pk', 'program__digest').first()
        if frame:
            frame_id, program_digest = frame
    strategy, log = rsi_policy.select_recheck_timing(task.project, task, current,
        source_result_id=evidence['result_id'], prior_decision=prior,
        sdtm_frame_id=frame_id, sdtm_program_digest=program_digest)
    remaining = max(0, prior['remaining_turns'] - 1) if prior else rsi_policy.RECHECK_DELAYS[strategy]
    decision = {'strategy': strategy, 'source_result_id': evidence['result_id'], 'remaining_turns': remaining}
    if log and rsi_policy.policy_mode(task.project_id) != 'off':
        decision.update(decision_id=log.pk, selection_mode=log.selection_mode, propensity=log.propensity)
    recheck = task.followup_tasks.filter(purpose='recheck').order_by('created_at', 'pk').first()
    if recheck is None and remaining:
        return {**decision, 'action': 'wait'}, None
    if recheck is None:
        recheck = create_recheck(task)
    if recheck is None:
        return {**decision, 'action': 'no_question'}, None
    if recheck.exam_id:
        return {**decision, 'action': 'already_submitted', 'recheck_task_id': str(recheck.pk)}, None
    href = f'/xiaoyu?project={task.project_id}&learning_task={recheck.pk}'
    card = build_tool_card('manage_learning_tasks', {'title': recheck.title, 'href': href})
    return {**decision, 'action': 'offer_recheck', 'recheck_task_id': str(recheck.pk), 'presentation': 'unknown'}, card
