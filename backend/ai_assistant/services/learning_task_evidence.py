"""Recheck task provenance; a model rubric grade remains a model judgement."""
import math
from rest_framework.exceptions import PermissionDenied, ValidationError
from users.feature_access import has_learning_feature
from quizzes.models import ExamQuestionResult
from quizzes.services.question_normalizer import normalize_objective_answer, normalize_options
from ai_assistant.models import ProjectLearningEvent
from .bayesian_evidence import ALGORITHM_VERSION
from .learning_tasks import _hash, task_result_snapshot, task_label_source, task_question_hash, task_prompt_hash


def verified_task_events(project, version_id):
    events = ProjectLearningEvent.objects.filter(project=project, kind='assessment',
        content__version_id=version_id).order_by('created_at', 'pk')
    valid, excluded, repeated = [], 0, 0
    seen = set()
    if not has_learning_feature(project.user, 'quiz.exam'):
        return {'events': [], 'excluded_provenance': events.count(), 'repeated_questions': 0}
    for event in events:
        check = event.content
        result = ExamQuestionResult.objects.select_related('exam__learning_task__project', 'question__knowledge_point').filter(
            pk=check.get('result_id'), exam__user_id=project.user_id, status='graded',
            exam__learning_task__project=project, exam__learning_task__knowledge_version_id=version_id).first()
        if not result:
            excluded += 1
            continue
        task = result.exam.learning_task
        try:
            snapshot = task_result_snapshot(task, result)
            label_source = task_label_source(task, result)
        except (PermissionDenied, ValidationError):
            excluded += 1
            continue
        if (not result.graded_at or task.created_at > result.exam.created_at
                or result.graded_at < result.exam.created_at or not result.max_score
                or not math.isfinite(result.score) or not 0 <= result.score <= result.max_score
                or result.max_score != snapshot['max_score']):
            excluded += 1
            continue
        success = result.score / result.max_score >= .6
        if label_source == 'objective_answer_key':
            options = normalize_options(snapshot['options'])
            answer = normalize_objective_answer(result.user_answer, options)
            correct = normalize_objective_answer(snapshot['correct_answer'], options)
            success = bool(answer and answer == correct)
            if (not correct or not options.get(correct) or result.score != (snapshot['max_score'] if success else 0)
                    or result.max_score != snapshot['max_score']):
                excluded += 1
                continue
        expected = {
            'task_id': str(task.pk), 'result_id': result.pk, 'version_id': version_id,
            'node_id': task.node_id, 'stage_id': task.stage_id, 'mode': task.mode,
            'assistance': task.assistance, 'outcome': 'success' if success else 'failure',
            'score': result.score, 'max_score': result.max_score,
            'label_source': label_source, 'algorithm': ALGORITHM_VERSION,
            'question_hash': task_question_hash(snapshot), 'answer_hash': _hash(result.user_answer.strip()),
        }
        if any(check.get(key) != value for key, value in expected.items()):
            excluded += 1
            continue
        valid.append((event, task, result))
    unique = []
    for event, task, result in sorted(valid, key=lambda row: (row[2].graded_at, row[2].pk)):
        snapshot = task.question_snapshot['0' if task.definition else str(result.question_id)]
        keys = {(task.node_id, 'hash', event.content['question_hash']), (task.node_id, 'prompt', task_prompt_hash(snapshot))}
        if result.question_id is not None:
            keys.add((task.node_id, 'id', result.question_id))
        if seen.intersection(keys):
            repeated += 1
            continue
        seen.update(keys)
        unique.append((event, task, result))
    return {'events': unique, 'excluded_provenance': excluded, 'repeated_questions': repeated}


def formal_observations(project, version_id):
    verified = verified_task_events(project, version_id)
    rows = []
    for event, task, result in verified['events']:
        snapshot = task.question_snapshot['0' if task.definition else str(result.question_id)]
        objective = event.content['label_source'] == 'objective_answer_key'
        rows.append({**event.content, 'event_id': event.pk, 'task_at': task.created_at.isoformat(),
            'at': result.graded_at.isoformat(), 'evidence_type': 'formal', 'question': snapshot['text'],
            'quote': result.user_answer, 'reason': result.feedback or '参照冻结标准给出的本次评价。',
            'rubric': '单选题按标准答案确定性判分。' if objective else snapshot.get('grading_points') or '模型按任务标准评价，未独立复核。',
            'source': result.user_answer, 'conversation_id': None, 'message_id': None, 'exam_id': result.exam_id})
    return rows, verified
