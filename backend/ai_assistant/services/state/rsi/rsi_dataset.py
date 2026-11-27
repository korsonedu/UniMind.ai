"""L2 State Layer — Freeze project-scoped temporal holdouts and logged S assignments."""
from collections import defaultdict
from datetime import datetime
import math
from uuid import UUID

from django.db.models import Prefetch
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework.exceptions import PermissionDenied, ValidationError

from ai_assistant.models import Conversation, ConversationProject, TaskMemoryFrame, TeachingDecisionLog
from quizzes.models import ExamQuestionResult
from users.feature_access import has_learning_feature
from ai_assistant.services.facts import learning_diagnostics
from ai_assistant.services.facts.learning_tasks import task_label_source, task_prompt_hash, task_result_snapshot
from ai_assistant.services.facts.teaching_sidecar import canonical_hash
from ai_assistant.services.state.prism.prism_memory import accessible
from ai_assistant.services.state.rsi import rsi_evidence

TEMPORAL_SPLIT = 'sdtm_temporal_cutoff:'
DECISION_POINTS = ('recheck_timing', 'method_ranking')
RANDOMIZED_MODES = {'recheck_timing': 'stratified_random', 'method_ranking': 'bounded_exploration'}
EXCLUSIONS = ('no_outcome', 'not_randomized', 'disclosed', 'non_independent', 'repeated',
              'unverified_timing', 'source_unavailable')


def authorize(project):
    current = ConversationProject.objects.select_related('user').filter(
        pk=project.pk, user_id=project.user_id, user__is_active=True).first() if isinstance(project, ConversationProject) else None
    if not current or not all(has_learning_feature(current.user, feature) for feature in ('ai.assistant', 'quiz.exam')):
        raise PermissionDenied('当前项目所有者需要小宇和习题训练权限。')
    return current


def _stamp(value):
    try:
        stamp = parse_datetime(value) if isinstance(value, str) else value
    except ValueError:
        return None
    return stamp if isinstance(stamp, datetime) and timezone.is_aware(stamp) else None


def _cutoff(value):
    if not isinstance(value, datetime) or _stamp(value) is None:
        raise ValidationError('cutoff_at 须含明确时区。')
    return value


def _frame(project, cutoff_at):
    frames = TaskMemoryFrame.objects.filter(memory__project=project, memory__owner_id=project.user_id)
    if cutoff_at is not None:
        frames = frames.filter(occurred_at__lte=cutoff_at)
    return frames.order_by('-occurred_at', '-pk').values_list('pk', 'program__digest').first()


def objective_anchor(task, result):
    if (result.status != 'graded' or not result.graded_at or task_label_source(task, result) != 'objective_answer_key'
            or not all(math.isfinite(value) for value in (result.score, result.max_score)) or result.max_score <= 0):
        return None
    task_result_snapshot(task, result)
    score = min(1.0, max(0.0, result.score / result.max_score))
    return {'expected_score': score, 'expected_independent_support': score >= .6, 'source': 'objective_answer_key'}


def _shadow_split(project, cutoff_at, max_cases, kind):
    pre, holdout, excluded = {}, {}, set()
    for record in rsi_evidence.project_method_evidence(project):
        assigned = _stamp(record['assigned_at'])
        for outcome in record['outcomes']:
            graded = _stamp(outcome['graded_at'])
            if not assigned or not graded or not record['source_available']:
                excluded.add(outcome['task_id'])
                continue
            if assigned <= cutoff_at and graded <= cutoff_at:
                pre[outcome['result_id']] = outcome['outcome']
            elif (assigned > cutoff_at and graded > cutoff_at
                  and outcome['status'] == rsi_evidence.INDEPENDENT and not outcome['reasons']):
                key = (assigned, graded, outcome['task_id'])
                task_outcomes = holdout.setdefault(outcome['task_id'], {})
                task_outcomes[outcome['result_id']] = min(key, task_outcomes.get(outcome['result_id'], key))
            else:
                excluded.add(outcome['task_id'])

    # The shadow runner resolves all graded results for a task. Admit only whole eligible tasks.
    results = ExamQuestionResult.objects.filter(status='graded').order_by('pk')
    tasks = project.learning_tasks.filter(pk__in=holdout.keys() - excluded, exam__user_id=project.user_id)
    tasks = tasks.select_related('exam', 'project__user').prefetch_related(Prefetch('exam__results', queryset=results))
    cases, anchors = [], []
    for task in sorted(tasks, key=lambda task: min(holdout[str(task.pk)].values())):
        eligible = holdout[str(task.pk)]
        graded_results = list(task.exam.results.all())
        if ({result.pk for result in graded_results} != eligible.keys() or task.exam.created_at <= cutoff_at
                or any(not result.graded_at or result.graded_at <= cutoff_at for result in graded_results)):
            continue
        task_id = str(task.pk)
        cases.append({'id': task_id, 'task_id': task_id})
        if kind == 'E' and len(graded_results) == 1 and (anchor := objective_anchor(task, graded_results[0])):
            anchors.append({'case_id': task_id, **anchor})
        if len(cases) == max_cases:
            break
    if not cases:
        raise ValidationError('截止时间之后没有合格的独立作答案例。')
    failed = sum(outcome == 'failure' for outcome in pre.values())
    return cases, anchors, f'截止时已批改的观察结果共 {len(pre)} 条，其中失败 {failed} 条。'


def build_sdtm_shadow_packet(project, *, kind, cutoff_at, baseline_instruction, development_goal='',
                             max_cases=6, max_tokens_per_call=1024, max_calls_per_arm=12):
    project = authorize(project)
    cutoff_at = _cutoff(cutoff_at)
    if kind not in ('G', 'E') or type(max_cases) is not int or not 1 <= max_cases <= 6:
        raise ValidationError('仅支持 G/E，每轮限制 1 至 6 个案例。')
    if (not isinstance(baseline_instruction, str) or not 1 <= len(baseline_instruction) <= 8000
            or not isinstance(development_goal, str) or len(development_goal) > 8000
            or type(max_tokens_per_call) is not int or not 128 <= max_tokens_per_call <= 4096
            or type(max_calls_per_arm) is not int or not 1 <= max_calls_per_arm <= 20):
        raise ValidationError('基线指令、开发目标或模型预算无效。')
    cases, anchors, failure = _shadow_split(project, cutoff_at, max_cases, kind)
    note = 'Development outcomes and holdout assignments/grades are split at the SDTM cutoff.'
    if frame := _frame(project, cutoff_at):
        note += f' sdtm_frame_id={frame[0]} sdtm_program_digest={frame[1]}'
    return {'schema_version': 'rsi-shadow-1',
            'provenance': {'origin': 'observational', 'split_note': f'{TEMPORAL_SPLIT}{cutoff_at.isoformat()}'},
            'development': {'goal': development_goal, 'failure': failure},
            'cases': cases, 'baseline': {'instruction': baseline_instruction}, 'anchors': anchors,
            'budget': {'max_tokens_per_call': max_tokens_per_call, 'max_calls_per_arm': max_calls_per_arm},
            'protocol': {'note': note}}


def verify_sdtm_shadow_split(project, kind, packet):
    split = packet['provenance'].get('split_note')
    if not (packet['provenance']['origin'] == 'observational' and isinstance(split, str) and split.startswith(TEMPORAL_SPLIT)):
        return False
    cutoff_at = _stamp(split.removeprefix(TEMPORAL_SPLIT))
    current = build_sdtm_shadow_packet(project, kind=kind, cutoff_at=cutoff_at,
        baseline_instruction=packet['baseline']['instruction'], development_goal=packet['development']['goal'],
        max_cases=len(packet['cases']), **packet['budget'])
    if any(current[key] != packet.get(key) for key in ('cases', 'development', 'protocol')):
        raise ValidationError('SDTM 留出材料已经变化，请重建评测包。')
    return True


def _outcome_exclusion(outcome):
    reasons = outcome['reasons']
    if 'source_unavailable' in reasons:
        return 'source_unavailable'
    if outcome['disclosed']:
        return 'disclosed'
    if outcome['repeated']:
        return 'repeated'
    if not outcome['timing_verified']:
        return 'unverified_timing'
    if outcome['status'] != rsi_evidence.INDEPENDENT or reasons:
        return 'non_independent'
    return None


def _method_reward(log, records, completed):
    rewards, excluded = {}, set()
    for record in records:
        if not record['source_available'] or record['reply_id'] != log.answer_id:
            excluded.add('source_unavailable')
            continue
        for outcome in record['outcomes']:
            reason = _outcome_exclusion(outcome)
            graded = _stamp(outcome['graded_at'])
            if reason or not graded or graded <= completed:
                excluded.add(reason or 'unverified_timing')
            else:
                rewards[outcome['result_id']] = float(outcome['outcome'] == 'success')
    if rewards:
        return sum(rewards.values()) / len(rewards), None
    return None, next((reason for reason in EXCLUSIONS if reason in excluded), 'no_outcome')


def _recheck_reward(project, log, completed):
    metadata = log.answer.metadata.get('ulr_teaching') or {}
    tasks = project.learning_tasks.filter(purpose='recheck').select_related('exam', 'project__user')
    if log.task_id:
        tasks = tasks.filter(source_task_id=log.task_id)
    if task_id := metadata.get('recheck_task_id'):
        try:
            tasks = tasks.filter(pk=UUID(str(task_id)))
        except ValueError:
            return None, 'source_unavailable'
    elif not log.task_id:
        return None, 'no_outcome'
    task = tasks.order_by('created_at', 'pk').first()
    if task is None or not task.exam_id:
        return None, 'no_outcome'
    if task.exam.user_id != project.user_id:
        return None, 'source_unavailable'
    results = list(task.exam.results.filter(status='graded').select_related('exam', 'question__knowledge_point'))
    if not results:
        return None, 'no_outcome'
    if len(results) != 1:
        return None, 'non_independent'
    result = results[0]
    if (task.created_at < log.created_at or task.exam.created_at <= completed or task.exam.created_at < task.created_at
            or not result.graded_at or result.graded_at < task.exam.created_at):
        return None, 'unverified_timing'
    if str(task.pk) in learning_diagnostics.excluded_tasks(learning_diagnostics.read_sources(project, {str(task.pk)})):
        return None, 'disclosed'
    if task.assistance != 'independent':
        return None, 'non_independent'
    try:
        anchor = objective_anchor(task, result)
    except (PermissionDenied, ValidationError):
        return None, 'source_unavailable'
    if anchor is None:
        return None, 'non_independent'
    prompt = task_prompt_hash(result.question_snapshot)
    prior = ExamQuestionResult.objects.filter(exam__user_id=project.user_id, exam__created_at__lte=task.exam.created_at)
    prior = prior.exclude(exam_id=task.exam_id).values_list('question_id', 'question_snapshot')
    if any((result.question_id is not None and question_id == result.question_id)
           or (snapshot.get('text') and task_prompt_hash(snapshot) == prompt) for question_id, snapshot in prior):
        return None, 'repeated'
    return float(anchor['expected_independent_support']), None


def build_s_replay_dataset(project, *, decision_point, cutoff_at=None, max_records=200):
    project = authorize(project)
    if decision_point not in DECISION_POINTS or type(max_records) is not int or max_records < 1:
        raise ValidationError('决策点或记录上限无效。')
    logs = TeachingDecisionLog.objects.filter(project=project, owner_id=project.user_id,
        decision_point=decision_point, answer__isnull=False).select_related('answer', 'message__bot', 'message__user')
    if cutoff_at is not None:
        logs = logs.filter(created_at__gt=_cutoff(cutoff_at))
    logs = list(logs.order_by('created_at', 'pk')[:max_records])
    rooms = set(Conversation.objects.filter(project=project, user_id=project.user_id).values_list('conversation_id', flat=True))
    records = defaultdict(list)
    if logs and decision_point == 'method_ranking':
        for record in rsi_evidence.project_method_evidence(project):
            records[record['question_id']].append(record)

    excluded_counts, rows = dict.fromkeys(EXCLUSIONS, 0), []
    for log in logs:
        if log.selection_mode != RANDOMIZED_MODES[decision_point]:
            excluded_counts['not_randomized'] += 1
            continue
        reply, message = log.answer, log.message
        turn = reply.metadata.get('learning_turn') or {}
        reply_hash = log.exposure.get('reply_hash')
        if (reply.user_id != project.user_id or message.user_id != project.user_id or reply.role != 'assistant'
                or reply.bot_id != message.bot_id or reply.conversation_id != message.conversation_id
                or message.conversation_id not in rooms or not accessible(message)
                or turn.get('completed') is not True or turn.get('message_id') != message.pk
                or (reply_hash and reply_hash != canonical_hash(reply.content))):
            excluded_counts['source_unavailable'] += 1
            continue
        completed = _stamp(turn.get('completed_at'))
        if not completed or completed < message.timestamp or reply.timestamp < log.created_at:
            excluded_counts['unverified_timing'] += 1
            continue
        completed = max(completed, reply.timestamp)
        if decision_point == 'method_ranking':
            reward, reason = _method_reward(log, records[log.message_id], completed)
        else:
            reward, reason = _recheck_reward(project, log, completed)
        if reason:
            excluded_counts[reason] += 1
            continue
        propensity = log.propensity
        rows.append({'decision_id': log.pk, 'selected_action': log.selected_action,
                     'propensity': propensity if propensity is not None and math.isfinite(propensity) else None,
                     'candidates': log.candidates, 'reward': reward, 'presented': log.exposure.get('presentation') == 'presented',
                     'created_at': log.created_at.isoformat(), 'sdtm_frame_id': log.sdtm_frame_id,
                     'sdtm_program_digest': log.sdtm_program_digest})
    frame = _frame(project, cutoff_at)
    return {'decision_point': decision_point, 'sdtm_frame_id': frame[0] if frame else None,
            'rows': rows, 'excluded_counts': excluded_counts}
