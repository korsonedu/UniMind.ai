"""Domain capabilities shared by the ULR executor and teaching policies."""
import math
from types import SimpleNamespace

from django.db.models import Q
from rest_framework.exceptions import PermissionDenied, ValidationError

from courses.access import visible_courses
from core.utils import get_content_institution_id
from quizzes.models import ExamQuestionResult, KnowledgePoint, Question
from quizzes.services.practice_results import practice_question_reviews, saved_practice_review_rows
from quizzes.services.question_normalizer import normalize_objective_answer, normalize_options
from ai_assistant.services.dsh_cards import data_card, item
from ai_assistant.services.dsh_service import permitted_tools
from ai_assistant.services.learning_tasks import create_task, task_label_source, task_prompt_hash, task_result_snapshot


def course_tools(user):
    names = {'search_courses', 'search_asr', 'search_knowledge_tree'}
    return [tool for tool in permitted_tools(user) if tool['function']['name'] in names]


def visible_course_ids(user, course_ids, *, project_id=None):
    if not course_ids:
        return set()
    private_ids = set()
    if project_id:
        from .workbench_grounding import is_personal_space
        from courses.access import private_companion_courses
        if is_personal_space(user):
            private_ids = set(private_companion_courses(user, project_id).filter(
                pk__in=course_ids,
            ).values_list('pk', flat=True))
    if public_ids := course_ids - private_ids:
        courses = visible_courses(SimpleNamespace(user=user, query_params={}))
        return private_ids | set(courses.filter(pk__in=public_ids).values_list('pk', flat=True))
    return private_ids


def require_visible_course_sources(user, course_ids, *, project_id=None):
    if visible_course_ids(user, course_ids, project_id=project_id) != course_ids:
        raise PermissionDenied('引用课程已不可访问，请重新提问。')


def _visible_practice_questions(scope, question_ids):
    return Question.objects.filter(pk__in=question_ids, institution_id=scope).filter(
        Q(knowledge_point__isnull=True) | Q(knowledge_point__institution_id=scope))


def require_visible_practice_sources(user, questions, *, point_id=None, lock=False):
    if not questions and point_id is None:
        return
    scope = get_content_institution_id(user)
    visible = _visible_practice_questions(scope, questions)
    rows = None
    if lock:
        rows = {row['id']: row for row in visible.order_by('pk').select_for_update(of=('self',)).values(
            'id', 'knowledge_point_id', 'text', 'q_type', 'subjective_type', 'options')}
        points = {pk: row['knowledge_point_id'] for pk, row in rows.items()}
    else:
        points = dict(visible.values_list('pk', 'knowledge_point_id'))
    if ((point_id is not None and not KnowledgePoint.objects.filter(pk=point_id, institution_id=scope).exists())
            or questions != points):
        raise PermissionDenied('所选知识点或练习题已不可访问，请重新提问。')
    return rows


def _reviewable_practice_questions(user, question_ids):
    if not question_ids:
        return set()
    questions = _visible_practice_questions(get_content_institution_id(user), question_ids)
    visible = set(questions.values_list('pk', flat=True))
    reviews = practice_question_reviews(user, visible)
    return visible - {pk for pk, review in reviews.items() if review['practice_status'] != 'graded'}


def visible_practice_review_sources(user, references):
    if not references:
        return set()
    visible = _reviewable_practice_questions(user, {pk for pk, _ in references})
    results = ExamQuestionResult.objects.filter(exam__user=user, question_id__in=visible,
        pk__in={result_id for _, result_id in references})
    return {(row['question_id'], row['pk']) for row in saved_practice_review_rows(results)} & references


def require_visible_practice_review_sources(user, references):
    if visible_practice_review_sources(user, references) != references:
        raise PermissionDenied('原练习评阅或权限已变化，请重新打开正式成绩。')


PRACTICE_REVIEW_GUIDANCE = (
    '按保存的作答、分数和解析复盘。解析为空时说明已有评分依据，请查看正式成绩。'
    'model_rubric_grade 是模型按评分标准给出的评价，尚未独立复核。'
)


def _practice_review_payload(review):
    question = review['question_snapshot']
    return {'id': review['question_id'], 'text': question['text'][:1200], 'q_type': question['q_type'],
            'subjective_type': question.get('subjective_type') or '', 'options': question.get('options') or [],
            'kp_name': question.get('kp_name') or '', 'user_answer': review['user_answer'][:1000],
            'score': review['score'], 'max_score': review['max_score'], 'feedback': review['feedback'][:500],
            'analysis': review['analysis'][:1200],
            'label_source': 'objective_answer_key' if question['q_type'] == 'objective' else 'model_rubric_grade'}


def _practice_exam_review(user, result, pending_questions):
    results = ExamQuestionResult.objects.filter(exam_id=result['exam_id'], exam__user=user,
        question_id__isnull=False).exclude(question_id__in=pending_questions).order_by('is_correct', 'position', 'pk')
    rows = list(saved_practice_review_rows(results))
    visible = _reviewable_practice_questions(user, {row['question_id'] for row in rows})
    rows = [row for row in rows if row['question_id'] in visible][:3]
    result['reviewed_items'] = [dict(_practice_review_payload(row), position=row['position']) for row in rows]
    result['_ulr_practice_reviews'] = [(row['question_id'], row['pk']) for row in rows]
    result['guidance'] = ('以下最多三道已评阅题，优先错题。' + PRACTICE_REVIEW_GUIDANCE if rows
                          else '当前没有可用于复盘的已保存逐题评阅，请打开正式成绩。')
    return result


def practice_tool_result(user, name, result, pending_questions, *, review_exam=False, include_review=True):
    if name == 'get_recent_practice_result' and review_exam and result.get('has_result'):
        return _practice_exam_review(user, result, pending_questions)
    if result.get('error') or name not in ('lookup_question', 'get_user_wrong_questions'):
        return result
    rows = result.get('questions', []) if name == 'get_user_wrong_questions' else [result]
    question_ids = {row['id'] for row in rows}
    reviews = practice_question_reviews(user, question_ids - pending_questions)
    reviews.update({pk: {'practice_status': 'unsubmitted'} for pk in question_ids & pending_questions})
    if name == 'get_user_wrong_questions':
        for index, row in enumerate(rows):
            if review := reviews.get(row['id']):
                rows[index] = {**{key: row[key] for key in ('id', 'text', 'q_type', 'kp_name', 'wrong_count')},
                               'practice_status': review['practice_status']}
        if reviews:
            result['guidance'] = '有练习状态的题目在评阅前只给概念提示，已有评阅可请学生查看正式成绩。'
        return result
    review = reviews.get(result['id'])
    if not review:
        return result
    status = review['practice_status']
    if status == 'graded':
        if not include_review:
            return {'id': result['id'], 'practice_status': status, 'guidance': '请从正式成绩查看原作答和评阅。'}
        score, maximum = review['score'], review['max_score']
        return dict(_practice_review_payload(review), practice_status=status,
            _ulr_practice_reviews=[(result['id'], review['pk'])],
            visual=data_card('查看原作答与评阅', [item('已评阅得分', f'{score:g}/{maximum:g}')],
                             ('打开正式成绩', f"/tests/results/{review['exam_id']}")),
            guidance=PRACTICE_REVIEW_GUIDANCE)
    fields = ('text', 'q_type', 'subjective_type', 'options', 'kp_name')
    return {'id': result['id'], 'practice_status': status, **{key: result[key] for key in fields},
            'guidance': ('练习尚未正式评阅。只给一个概念提示，具体答案留在评阅结果。'
                         if status == 'awaiting_review' else '引导学生独立思考。只给一个概念提示，请学生从原作答卡提交。')}


def task_review(user, task):
    """Read the student's stored evaluation without treating it as new evidence."""
    exam = task.exam
    if exam.user_id != user.pk:
        return {'status': 'unverified'}
    if exam.status in ('pending', 'grading', 'failed'):
        return {'status': exam.status}
    rows = []
    for result in exam.results.filter(status='graded').select_related('exam', 'question__knowledge_point').order_by('position', 'pk'):
        try:
            snapshot = task_result_snapshot(task, result)
        except (PermissionDenied, ValidationError):
            return {'status': 'unverified'}
        if (not result.graded_at or not result.max_score or not math.isfinite(result.score)
                or result.max_score != snapshot['max_score'] or not 0 <= result.score <= result.max_score):
            return {'status': 'unverified'}
        label_source = task_label_source(task, result)
        if label_source == 'objective_answer_key':
            options = normalize_options(snapshot['options'])
            original = normalize_objective_answer(result.user_answer, options)
            correct = normalize_objective_answer(snapshot['correct_answer'], options)
            if not correct or not options.get(correct) or result.score != (result.max_score if original == correct else 0):
                return {'status': 'unverified'}
        rows.append({
            'result_id': result.pk, 'question_excerpt': snapshot['text'][:240],
            'answer_excerpt': result.user_answer[:500], 'reference_excerpt': snapshot['correct_answer'][:180],
            'rubric_excerpt': snapshot['grading_points'][:180], 'feedback_excerpt': result.feedback[:180],
            'score': result.score, 'max_score': result.max_score, 'label_source': label_source,
        })
    if not rows or (exam.status == 'completed' and len(rows) != exam.total_questions):
        return {'status': 'unverified'}
    return {'status': exam.status, 'task_id': str(task.pk), 'assistance': task.assistance, 'results': rows}


def create_recheck(source):
    snapshot = source.question_snapshot[str(source.question_ids[0])]
    comparable_tasks = source.project.learning_tasks.filter(knowledge_version=source.knowledge_version,
        node_id=source.node_id, exam__isnull=False).values_list('question_snapshot', flat=True)
    used_prompts = {task_prompt_hash(row) for task in comparable_tasks for row in task.values()}
    used_prompts.add(task_prompt_hash(snapshot))
    candidates = Question.objects.filter(knowledge_point_id=snapshot['kp_id'],
        institution_id=snapshot['institution_id'], q_type='objective').exclude(pk__in=source.question_ids).order_by('pk')
    for question in candidates.iterator():
        options = normalize_options(question.options)
        answer = normalize_objective_answer(question.correct_answer, options)
        if (not question.text.strip() or sum(bool(value) for value in options.values()) < 2
                or not options.get(answer) or task_prompt_hash({'text': question.text}) in used_prompts):
            continue
        return create_task(source.project, {
            'version_id': source.knowledge_version_id, 'node_id': source.node_id, 'stage_id': source.stage_id,
            'title': '独立复测', 'instructions': '请独立作答，并如实选择本次是否获得帮助。',
            'question_ids': [question.pk], 'purpose': 'recheck', 'source_task_id': source.pk, 'mode': source.mode,
        })
    return None
