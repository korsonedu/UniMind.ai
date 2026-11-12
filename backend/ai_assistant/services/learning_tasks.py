"""Owned learning tasks reuse formal exams and frozen grading definitions."""
import hashlib
import json
import logging

from django.db import transaction
from django.contrib.auth import get_user_model
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


class DefinitionInput(serializers.Serializer):
    prompt = serializers.CharField(min_length=5, max_length=8000)
    response_type = serializers.ChoiceField(choices=['explanation', 'calculation', 'reasoning', 'case', 'code'])
    criteria = serializers.ListField(child=serializers.CharField(max_length=500), min_length=1, max_length=8)
    reference_answer = serializers.CharField(max_length=8000, required=False, allow_blank=True, default='')
    sources = serializers.ListField(child=serializers.CharField(max_length=60), max_length=10, default=list)


class TaskInput(serializers.Serializer):
    version_id = serializers.IntegerField(min_value=1, required=False, allow_null=True)
    node_id = serializers.CharField(max_length=60, required=False, allow_blank=True, default='')
    stage_id = serializers.CharField(max_length=60)
    title = serializers.CharField(max_length=200)
    instructions = serializers.CharField(max_length=8000)
    question_ids = serializers.ListField(child=serializers.IntegerField(min_value=1), max_length=10, default=list)
    definition = DefinitionInput(required=False)
    mode = serializers.ChoiceField(choices=['apply', 'transfer'], default='apply')
    purpose = serializers.ChoiceField(choices=['diagnostic', 'practice', 'recheck'], default='practice')
    source_task_id = serializers.UUIDField(required=False, allow_null=True)
    strategy_use_id = serializers.IntegerField(min_value=1, required=False, allow_null=True)

    def validate(self, data):
        if bool(data['question_ids']) == bool(data.get('definition')):
            raise ValidationError('请选择已有题目或准备一个开放任务，二者只能选一。')
        return data


def _hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


def task_prompt_hash(snapshot):
    return _hash(''.join(snapshot['text'].split()).casefold())


def _current_user(project):
    return get_user_model().objects.filter(pk=project.user_id, is_active=True).first()


def task_question_hash(snapshot):
    return _hash({key: value for key, value in snapshot.items() if key != 'learning_task_id'})


def assessment_snapshot(question):
    return question_snapshot(question) | {'max_score': question.get_max_score(), 'rubric': question.rubric,
                                         'institution_id': question.institution_id}


def personal_question(definition):
    """A grading input only: this Question is never inserted into the shared bank."""
    return Question(text=definition['prompt'], q_type='subjective',
        subjective_type='calculate' if definition['response_type'] == 'calculation' else 'short',
        options=[], correct_answer=definition.get('reference_answer', ''),
        grading_points='\n'.join(definition['criteria']), difficulty_level='normal')


def _personal_snapshot(task):
    return assessment_snapshot(personal_question(task.definition)) | {
        'learning_task_id': str(task.pk), 'source_kind': 'personal_task',
        'response_type': task.definition['response_type'], 'criteria': task.definition['criteria'],
        'sources': task.definition.get('sources', []), 'label_source': 'model_rubric_grade',
    }


def _validate_path(project, version_id, node_id, stage_id):
    state = get_object_or_404(ProjectLearning.objects.select_for_update(), project=project)
    stage = next((item for item in state.plan.get('stages', []) if item['id'] == stage_id), None)
    if state.status != 'active' or not stage:
        raise ValidationError('任务需要对应当前生效计划的学习阶段。')
    path = state.plan.get('knowledge_path') or {}
    if not path:
        if version_id or node_id:
            raise ValidationError('当前计划尚未绑定知识地图，任务不能声明知识版本或节点。')
        return None
    if path.get('version_id') != version_id or node_id not in stage.get('knowledge_nodes', []):
        raise ValidationError('任务需要对应当前生效计划的知识版本与学习阶段。')
    from .learning_knowledge import owned_version
    version = owned_version(project, version_id)
    if node_id not in {node['id'] for node in version.snapshot['nodes']}:
        raise ValidationError('知识节点不在该版本中。')
    return version


@transaction.atomic
def create_task(project, arguments):
    if not has_learning_feature(_current_user(project), 'quiz.exam'):
        raise PermissionDenied('当前账号尚未开放习题训练。')
    serializer = TaskInput(data=arguments)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data
    version = _validate_path(project, data.pop('version_id', None), data['node_id'], data['stage_id'])
    source_id = data.pop('source_task_id', None)
    source = get_object_or_404(ProjectLearningTask, pk=source_id, project=project) if source_id else None
    use_id = data.pop('strategy_use_id', None)
    from .teaching_sidecar import validate_strategy_use
    strategy_use = validate_strategy_use(project, use_id) if use_id else None
    if source and source.knowledge_version_id != (version.pk if version else None):
        raise ValidationError('关联任务的知识版本不同，请按当前计划重新安排，不能自动混用旧证据。')
    if source and data['purpose'] == 'recheck' and source.node_id != data['node_id']:
        raise ValidationError('再次检验应围绕原知识单元；补前置知识请安排学习任务并说明原因。')
    definition = data.get('definition', {})
    if definition:
        resources = {item['id'] for item in ProjectLearning.objects.get(project=project).resources}
        if not set(definition['sources']).issubset(resources):
            raise ValidationError('任务引用必须来自本项目已保存的实际资料。')
        snapshots = {}
    else:
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
            if question.q_type == 'objective':
                options = normalize_options(question.options)
                answer = normalize_objective_answer(question.correct_answer, options)
                valid = sum(bool(value) for value in options.values()) >= 2 and bool(options.get(answer))
            else:
                valid = bool(question.grading_points or question.rubric)
            if not question.text.strip() or not valid:
                raise ValidationError('题目需要明确选项答案或主观评价标准。')
            snapshots[str(pk)] = assessment_snapshot(question)
    if data['purpose'] == 'recheck' and source:
        prompts = {task_prompt_hash(snapshot) for snapshot in snapshots.values()}
        if definition:
            prompts.add(task_prompt_hash({'text': definition['prompt']}))
        if prompts.intersection(task_prompt_hash(snapshot) for snapshot in source.question_snapshot.values()):
            raise ValidationError('再次检验请准备不同的题目，不能重复原任务。')
    task = ProjectLearningTask.objects.create(project=project, knowledge_version=version,
        source_task=source, strategy_use=strategy_use, question_snapshot=snapshots, **data)
    if definition:
        task.question_snapshot = {'0': _personal_snapshot(task)}
        task.save(update_fields=['question_snapshot'])
    return task


def personal_answers(answers):
    if not isinstance(answers, list) or len(answers) != 1 or not isinstance(answers[0], dict) or type(answers[0].get('question_id')) is not int or answers[0]['question_id'] != 0:
        raise ValidationError('开放任务需要提交唯一的原任务答案。')
    answer = serializers.CharField(max_length=20000, trim_whitespace=False).run_validation(answers[0].get('answer'))
    if not answer.strip():
        raise ValidationError('请先提交实际成果。')
    return [{'question_id': 0, 'answer': answer}]


def validate_task_submission(user, task_id, submission_id, questions_data, assistance):
    task = get_object_or_404(ProjectLearningTask.objects.select_for_update().select_related('project'),
                            pk=task_id, project__user=user)
    if str(task.pk) != str(submission_id):
        raise ValidationError('任务与本次提交编号不一致。')
    if not task.exam_id:
        _validate_path(task.project, task.knowledge_version_id, task.node_id, task.stage_id)
    elif task.assistance != assistance:
        raise ValidationError('已提交任务不能更换辅助情况。')
    if task.definition:
        personal_answers(questions_data)
        if task.question_snapshot != {'0': _personal_snapshot(task)}:
            raise ValidationError('任务评价标准已变化，请重新安排任务。')
        return task, {0: personal_question(task.definition)}
    if [int(item['question_id']) for item in questions_data] != task.question_ids:
        raise ValidationError('请按原顺序提交任务内全部题目。')
    from quizzes.ai_workflow import validate_exam_answers
    questions = validate_exam_answers(user, questions_data, lock=True)
    for question in questions.values():
        validate_task_question(task, question)
    return task, questions


def validate_task_question(task, question):
    if assessment_snapshot(question) != task.question_snapshot.get(str(question.pk)):
        raise ValidationError('任务题目已变化，请重新创建任务。')


def task_result_snapshot(task, result):
    """Recheck ownership and frozen content for grading, review and BEP replay."""
    if not has_learning_feature(_current_user(task.project), 'quiz.exam'):
        raise PermissionDenied('当前账号尚未开放习题训练。')
    if (result.exam_id != task.exam_id or result.exam.user_id != task.project.user_id
            or not ProjectLearningTask.objects.filter(pk=task.pk, project__user_id=result.exam.user_id, project__user__is_active=True).exists()):
        raise ValidationError('任务与实际作答归属不一致。')
    if task.definition:
        expected = _personal_snapshot(task)
        if result.question_id is not None or task.question_snapshot != {'0': expected} or result.question_snapshot != expected:
            raise ValidationError('开放任务原始定义或提交快照已变化。')
        return expected
    snapshot = task.question_snapshot.get(str(result.question_id))
    if not snapshot or not result.question or result.question.institution_id != get_content_institution_id():
        raise ValidationError('任务题目已不可核验。')
    validate_task_question(task, result.question)
    if any(result.question_snapshot.get(key) != snapshot.get(key) for key in result.question_snapshot):
        raise ValidationError('原始提交快照已变化。')
    return snapshot


def task_label_source(task, result):
    return 'model_rubric_grade' if task.definition or result.question_snapshot.get('q_type') != 'objective' else 'objective_answer_key'


def sync_task_result(result):
    if result.status != 'graded':
        return
    task = ProjectLearningTask.objects.select_related('project').filter(exam_id=result.exam_id).first()
    if not task:
        return
    snapshot = task_result_snapshot(task, result)
    label_source = task_label_source(task, result)
    content = {
        'task_id': str(task.pk), 'result_id': result.pk, 'version_id': task.knowledge_version_id,
        'node_id': task.node_id, 'stage_id': task.stage_id, 'mode': task.mode, 'assistance': task.assistance,
        'outcome': 'success' if result.max_score > 0 and result.score / result.max_score >= .6 else 'failure',
        'score': result.score, 'max_score': result.max_score,
        'label_source': label_source, 'algorithm': 'bep-0.1',
        'question_hash': task_question_hash(snapshot),
        'answer_hash': _hash(result.user_answer.strip()),
    }
    event, _ = ProjectLearningEvent.objects.get_or_create(
        request_key=hashlib.sha256(f'exam_result:{result.pk}'.encode()).hexdigest(),
        defaults={'project': task.project, 'kind': 'assessment', 'content': content},
    )
    if task.strategy_use_id:
        from .teaching_sidecar import observe, record_task_outcome
        observe(record_task_outcome, task, result, event)


def sync_exam_task_result(result_id):
    from quizzes.models import ExamQuestionResult
    try:
        sync_task_result(ExamQuestionResult.objects.select_related('exam', 'question__knowledge_point').get(pk=result_id))
    except Exception:
        logger.exception('Learning task result sync failed for result=%s', result_id)


def task_data(task):
    authorized = has_learning_feature(_current_user(task.project), 'quiz.exam')
    available = authorized and (bool(task.definition) or Question.objects.filter(
        pk__in=task.question_ids, institution_id=get_content_institution_id()).count() == len(task.question_ids))
    exam = task.exam if task.exam_id else None
    summary = exam_result_payload(exam, include_results=False) if exam and authorized else None
    if exam:
        for item in exam.results.filter(status='graded'):
            sync_exam_task_result(item.pk)
    label_source = 'model_rubric_grade' if task.definition or any(s['q_type'] != 'objective' for s in task.question_snapshot.values()) else 'objective_answer_key'
    if summary:
        summary['label_source'] = label_source
    questions = []
    for pk in ([0] if task.definition else task.question_ids) if available else []:
        snapshot = task.question_snapshot[str(pk)]
        questions.append({'id': pk, **{key: snapshot[key] for key in
            ('q_type', 'subjective_type', 'options', 'difficulty_level')}, 'text': snapshot['text']})
    due = UserQuestionStatus.objects.filter(user_id=task.project.user_id, question_id__in=task.question_ids,
        reps__gt=0).order_by('next_review_at').values_list('next_review_at', flat=True).first() if exam and authorized and not task.definition else None
    status = ('processing' if exam.status in ('pending', 'grading') else exam.status) if exam else 'ready'
    return {
        'id': str(task.pk), 'learning_task_id': str(task.pk), 'practice_id': str(task.pk),
        'project_id': task.project_id, 'version_id': task.knowledge_version_id,
        'node_id': task.node_id, 'stage_id': task.stage_id, 'title': task.title,
        'instructions': task.instructions, 'mode': task.mode, 'assistance': task.assistance,
        'purpose': task.purpose, 'source_task_id': str(task.source_task_id) if task.source_task_id else None,
        **({'strategy_use_id': task.strategy_use_id} if task.strategy_use_id else {}),
        'response_type': task.definition.get('response_type'), 'criteria': task.definition.get('criteria', []),
        'label_source': label_source, 'sources': task.definition.get('sources', []),
        'status': status if available else 'unavailable',
        'unavailable_reason': '' if available else ('任务题目已删除或不在当前内容范围，请重新安排任务。' if authorized else '当前账号尚未开放习题训练。'),
        'exam_id': task.exam_id, 'created_at': task.created_at, 'review_due_at': due,
        'summary': summary, 'payload': {'practice_id': str(task.pk), 'title': task.title, 'questions': questions},
    }
