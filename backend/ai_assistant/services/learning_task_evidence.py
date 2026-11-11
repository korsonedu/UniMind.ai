"""Recheck formal task provenance before using a score as knowledge evidence."""
from core.utils import get_content_institution_id
from users.feature_access import has_learning_feature
from quizzes.models import ExamQuestionResult
from quizzes.services.question_normalizer import normalize_objective_answer, normalize_options
from ai_assistant.models import ProjectLearningEvent
from .bayesian_evidence import ALGORITHM_VERSION
from .learning_tasks import _hash, assessment_snapshot


def verified_task_events(project, version_id):
    events = ProjectLearningEvent.objects.filter(project=project, kind='assessment',
        content__version_id=version_id).order_by('created_at', 'pk')
    valid, excluded, repeated = [], 0, 0
    seen = set()
    if not has_learning_feature(project.user, 'quiz.exam'):
        return {'events': [], 'excluded_provenance': events.count(), 'repeated_questions': 0}
    scope = get_content_institution_id()
    for event in events:
        check = event.content
        result = ExamQuestionResult.objects.select_related('exam__learning_task', 'question__knowledge_point').filter(
            pk=check.get('result_id'), exam__user_id=project.user_id, status='graded',
            exam__learning_task__project=project, exam__learning_task__knowledge_version_id=version_id).first()
        if not result:
            excluded += 1
            continue
        task, question = result.exam.learning_task, result.question
        snapshot = task.question_snapshot.get(str(result.question_id))
        if (not question or question.institution_id != scope or not snapshot
                or snapshot != assessment_snapshot(question)
                or any(result.question_snapshot.get(key) != snapshot.get(key) for key in result.question_snapshot)):
            excluded += 1
            continue
        options = normalize_options(snapshot['options'])
        answer = normalize_objective_answer(result.user_answer, options)
        correct = normalize_objective_answer(snapshot['correct_answer'], options)
        success = bool(answer and answer == correct)
        expected = {
            'task_id': str(task.pk), 'result_id': result.pk, 'version_id': version_id,
            'node_id': task.node_id, 'stage_id': task.stage_id, 'mode': task.mode,
            'assistance': task.assistance, 'outcome': 'success' if success else 'failure',
            'score': result.score, 'max_score': result.max_score,
            'label_source': 'objective_answer_key', 'algorithm': ALGORITHM_VERSION,
            'question_hash': _hash(snapshot), 'answer_hash': _hash(result.user_answer.strip()),
        }
        if (check != expected or snapshot['q_type'] != 'objective' or not correct or not options.get(correct)
                or result.score != (snapshot['max_score'] if success else 0)
                or result.max_score != snapshot['max_score'] or not result.graded_at
                or task.created_at > result.exam.created_at or result.graded_at < result.exam.created_at):
            excluded += 1
            continue
        valid.append((event, task, result))
    unique = []
    # A delayed projection must not turn a later repeat into the first observation.
    for event, task, result in sorted(valid, key=lambda row: (row[2].graded_at, row[2].pk)):
        keys = {(task.node_id, 'id', result.question_id), (task.node_id, 'hash', event.content['question_hash'])}
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
        rows.append({**event.content, 'event_id': event.pk, 'task_at': task.created_at.isoformat(),
            'at': result.graded_at.isoformat(), 'evidence_type': 'formal',
            'question': task.question_snapshot[str(result.question_id)]['text'],
            'quote': result.user_answer, 'reason': result.feedback or '按标准答案比对评分。',
            'rubric': '单选题按标准答案确定性判分。', 'source': result.user_answer,
            'conversation_id': None, 'message_id': None, 'exam_id': result.exam_id})
    return rows, verified
