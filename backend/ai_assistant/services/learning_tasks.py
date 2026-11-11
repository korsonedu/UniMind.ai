"""Project tasks reuse formal exams; only persisted graded results become evidence."""
import hashlib
import json
import logging

from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied, ValidationError

from ai_assistant.models import ProjectLearning, ProjectLearningEvent, ProjectLearningTask
from core.utils import get_content_institution_id
from quizzes.models import Question, UserQuestionStatus
from quizzes.services.practice_results import exam_result_payload, question_snapshot
from quizzes.services.question_normalizer import normalize_objective_answer, normalize_options
from users.feature_access import has_learning_feature

logger = logging.getLogger(__name__)
ASSISTANCE = ['independent', 'hint', 'guided', 'unknown']


class TaskInput(serializers.Serializer):
    version_id = serializers.IntegerField(min_value=1)
    node_id = serializers.CharField(max_length=60)
    stage_id = serializers.CharField(max_length=60)
    title = serializers.CharField(max_length=200)
    instructions = serializers.CharField(max_length=8000)
    question_ids = serializers.ListField(child=serializers.IntegerField(min_value=1), min_length=1, max_length=10)
    mode = serializers.ChoiceField(choices=['apply', 'transfer'])


def _hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


def assessment_snapshot(question):
    return question_snapshot(question) | {'max_score': question.get_max_score(), 'rubric': question.rubric,
                                         'institution_id': question.institution_id}


def _validate_path(project, version_id, node_id, stage_id):
    state = get_object_or_404(ProjectLearning.objects.select_for_update(), project=project)
    path = state.plan.get('knowledge_path') or {}
    stage = next((item for item in state.plan.get('stages', []) if item['id'] == stage_id), None)
    if (state.status != 'active' or path.get('version_id') != version_id or not stage
            or node_id not in stage.get('knowledge_nodes', [])):
        raise ValidationError('任务需要对应当前生效计划的知识版本与学习阶段。')
    from .learning_knowledge import owned_version
    version = owned_version(project, version_id)
    if node_id not in {node['id'] for node in version.snapshot['nodes']}:
        raise ValidationError('知识节点不在该版本中。')
    return version


@transaction.atomic
def create_task(project, arguments):
    if not has_learning_feature(project.user, 'quiz.exam'):
        raise PermissionDenied('当前账号尚未开放习题训练。')
    serializer = TaskInput(data=arguments)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data
    version = _validate_path(project, data.pop('version_id'), data['node_id'], data['stage_id'])
    ids = data['question_ids']
    if len(ids) != len(set(ids)):
        raise ValidationError('任务题目不能重复。')
    questions = {q.pk: q for q in Question.objects.select_for_update().filter(
        pk__in=ids, institution_id=get_content_institution_id()).order_by('pk')}
    if len(questions) != len(ids):
        raise ValidationError('题目不存在或不在当前内容范围。')
    snapshots = {}
    for pk in ids:
        question = questions[pk]
        options = normalize_options(question.options)
        answer = normalize_objective_answer(question.correct_answer, options)
        if question.q_type != 'objective' or not question.text.strip() or sum(bool(value) for value in options.values()) < 2 or not options.get(answer):
            raise ValidationError('当前任务只接受有明确标准答案与选项的客观题。')
        snapshots[str(pk)] = assessment_snapshot(question)
    return ProjectLearningTask.objects.create(project=project, knowledge_version=version,
                                              question_snapshot=snapshots, **data)


def validate_task_submission(user, task_id, submission_id, questions_data, assistance):
    """Called under the exam submit transaction, before binding an attempt."""
    task = get_object_or_404(ProjectLearningTask.objects.select_for_update().select_related('project'),
                            pk=task_id, project__user=user)
    if str(task.pk) != str(submission_id):
        raise ValidationError('任务与本次提交编号不一致。')
    if [int(item['question_id']) for item in questions_data] != task.question_ids:
        raise ValidationError('请按原顺序提交任务内全部题目。')
    if not task.exam_id:
        _validate_path(task.project, task.knowledge_version_id, task.node_id, task.stage_id)
    elif task.assistance != assistance:
        raise ValidationError('已提交任务不能更换辅助情况。')
    from quizzes.ai_workflow import validate_exam_answers
    questions = validate_exam_answers(user, questions_data, lock=True)
    for question in questions.values():
        validate_task_question(task, question)
    return task, questions


def validate_task_question(task, question):
    if assessment_snapshot(question) != task.question_snapshot.get(str(question.pk)):
        raise ValidationError('任务题目已变化，请重新创建任务。')


def sync_task_result(result):
    if result.status != 'graded':
        return
    task = ProjectLearningTask.objects.filter(exam_id=result.exam_id).first()
    if not task:
        return
    snapshot = task.question_snapshot.get(str(result.question_id))
    if not snapshot or snapshot['q_type'] != 'objective':
        return
    content = {
        'task_id': str(task.pk), 'result_id': result.pk, 'version_id': task.knowledge_version_id,
        'node_id': task.node_id, 'stage_id': task.stage_id, 'mode': task.mode, 'assistance': task.assistance,
        'outcome': 'success' if result.score == result.max_score else 'failure',
        'score': result.score, 'max_score': result.max_score,
        'label_source': 'objective_answer_key', 'algorithm': 'bep-0.1',
        'question_hash': _hash(snapshot), 'answer_hash': _hash(result.user_answer.strip()),
    }
    ProjectLearningEvent.objects.get_or_create(
        request_key=hashlib.sha256(f'exam_result:{result.pk}'.encode()).hexdigest(),
        defaults={'project': task.project, 'kind': 'assessment', 'content': content},
    )


def sync_exam_task_result(result_id):
    """Best effort after commit; task GET retries a failed projection."""
    from quizzes.models import ExamQuestionResult
    try:
        result = ExamQuestionResult.objects.get(pk=result_id)
        sync_task_result(result)
    except Exception:
        logger.exception('Learning task result sync failed for result=%s', result_id)


def task_data(task):
    authorized = has_learning_feature(task.project.user, 'quiz.exam')
    available = authorized and Question.objects.filter(pk__in=task.question_ids, institution_id=get_content_institution_id()).count() == len(task.question_ids)
    exam = task.exam if task.exam_id else None
    result = exam_result_payload(exam, include_results=False) if exam and authorized else None
    if exam:
        for item in exam.results.filter(status='graded'):
            sync_exam_task_result(item.pk)
    questions = []
    for pk in task.question_ids if available else []:
        snapshot = task.question_snapshot[str(pk)]
        questions.append({'id': pk, **{key: snapshot[key] for key in
            ('q_type', 'subjective_type', 'options', 'difficulty_level')}, 'text': snapshot['text']})
    due = UserQuestionStatus.objects.filter(user_id=task.project.user_id, question_id__in=task.question_ids,
        reps__gt=0).order_by('next_review_at').values_list('next_review_at', flat=True).first() if exam and authorized else None
    status = ('processing' if exam.status in ('pending', 'grading') else exam.status) if exam else 'ready'
    return {
        'id': str(task.pk), 'learning_task_id': str(task.pk), 'practice_id': str(task.pk),
        'project_id': task.project_id, 'version_id': task.knowledge_version_id,
        'node_id': task.node_id, 'stage_id': task.stage_id, 'title': task.title,
        'instructions': task.instructions, 'mode': task.mode, 'assistance': task.assistance,
        'status': status if available else 'unavailable',
        'unavailable_reason': '' if available else ('任务题目已删除或不在当前内容范围，请重新安排任务。' if authorized else '当前账号尚未开放习题训练。'),
        'exam_id': task.exam_id, 'created_at': task.created_at, 'review_due_at': due,
        'summary': result, 'payload': {'practice_id': str(task.pk), 'title': task.title, 'questions': questions},
    }
