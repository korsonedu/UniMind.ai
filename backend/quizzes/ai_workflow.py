import logging
from typing import Any, Dict, List

from django.db import transaction
from django.db.models import F
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from core.utils import apply_institution_filter, get_content_institution_id

from quizzes.utils import safe_int

from ai_service import AIService
from notifications.models import Notification
from quizzes.memorix.service import MemorixService
from quizzes.models import ExamQuestionResult, Question, QuizExam, UserQuestionStatus
from users.models import User
from users.feature_access import has_learning_feature

logger = logging.getLogger(__name__)


def _clamp_score(score: float, max_score: float) -> float:
    return max(0.0, min(float(max_score or 0), float(score or 0)))


def _subjective_type_label(question: Question) -> str:
    if question.q_type == 'subjective' and question.subjective_type:
        return question.get_subjective_type_display()
    return '客观题'


@transaction.atomic
def _apply_memorix_status(user: User, question: Question, normalized_score: float, memorix_rating: int, review_time=None) -> UserQuestionStatus:
    User.objects.select_for_update().get(pk=user.pk)
    status_obj, _ = UserQuestionStatus.objects.get_or_create(user=user, question=question)
    status_obj = MemorixService.update_status(user_id=user.id, status=status_obj, rating=memorix_rating)

    if normalized_score < 0.6:
        UserQuestionStatus.objects.filter(pk=status_obj.pk).update(wrong_count=F('wrong_count') + 1)
        status_obj.wrong_count = F('wrong_count') + 1
        status_obj.last_correct = False
    else:
        status_obj.last_correct = True

    status_obj.save(update_fields=['last_correct', 'last_review'])
    return status_obj


def _calc_elo_change(user_elo: int, score_ratio: float, difficulty: float) -> int:
    expected_score = 1 / (1 + 10 ** ((difficulty - user_elo) / 400))
    return int(32 * (score_ratio - expected_score))


def _grade_answer(question: Question, user_answer: Any) -> Dict[str, Any]:
    max_score = question.get_max_score()
    grade_data = AIService.grade_question(
        question_text=question.text,
        user_answer=user_answer,
        correct_answer=question.correct_answer,
        q_type=question.q_type,
        max_score=max_score,
        grading_points=question.grading_points,
        options=question.options,
        rubric=question.rubric,
        subjective_type=_subjective_type_label(question),
    )

    score_val = _clamp_score(float(grade_data.get('score', 0)), max_score)

    # 客观题以标准答案比对为准，避免模型漂移
    if question.q_type == 'objective':
        user_choice = AIService.normalize_objective_answer(user_answer)
        correct_choice = AIService.normalize_objective_answer(question.correct_answer)
        score_val = float(max_score if user_choice and user_choice == correct_choice else 0)

    normalized_score = score_val / max_score if max_score > 0 else 0
    memorix_rating = safe_int(grade_data.get('memorix_rating', 2), 2)
    memorix_rating = min(4, max(1, memorix_rating))

    return {
        'score': score_val,
        'max_score': max_score,
        'feedback': grade_data.get('feedback', '已评阅'),
        'analysis': grade_data.get('analysis', question.ai_answer or ''),
        'memorix_rating': memorix_rating,
        'normalized_score': normalized_score,
        'is_correct': normalized_score >= 0.6,
    }


def _queue_experience_verification(user_id, question, score):
    if question.knowledge_point_id:
        def dispatch():
            from ai_assistant.tasks import experience_verify_on_answer
            experience_verify_on_answer.delay(
                user_id=user_id,
                kp_id=question.knowledge_point_id,
                score=score,
                max_score=question.get_max_score(),
            )
        transaction.on_commit(dispatch, robust=True)


def grade_answer_for_user(user: User, question: Question, user_answer: Any, set_last_review: bool = True) -> Dict[str, Any]:
    result = _grade_answer(question, user_answer)
    _apply_memorix_status(user, question, result['normalized_score'], result['memorix_rating'])
    _queue_experience_verification(user.id, question, result['score'])
    return result


def grade_single_question_submission(user: User, question: Question, user_answer: Any) -> Dict[str, Any]:
    result = _grade_answer(question, user_answer)
    with transaction.atomic():
        locked = User.objects.select_for_update().get(id=user.id)
        _apply_memorix_status(locked, question, result['normalized_score'], result['memorix_rating'])
        elo_change = _calc_elo_change(user_elo=locked.elo_score, score_ratio=result['normalized_score'], difficulty=float(question.difficulty or 1000))
        locked.elo_score += elo_change
        locked.save(update_fields=['elo_score'])
        _queue_experience_verification(user.id, question, result['score'])
    result['elo_change'] = elo_change
    return result


def validate_exam_answers(user: User, questions_data, request=None, lock=False):
    if not isinstance(questions_data, list) or not questions_data:
        raise ValidationError({'error': '无有效答题数据'})
    question_ids = []
    for item in questions_data:
        if not isinstance(item, dict):
            raise ValidationError({'error': '答题数据格式错误'})
        q_id = item.get('question_id')
        if isinstance(q_id, bool) or not isinstance(q_id, (int, str)):
            raise ValidationError({'error': '题目 ID 无效'})
        try:
            q_id = int(q_id)
        except ValueError:
            raise ValidationError({'error': '题目 ID 无效'})
        if not 0 < q_id <= 9223372036854775807:
            raise ValidationError({'error': '题目 ID 无效'})
        if item.get('answer') is not None and not isinstance(item['answer'], str):
            raise ValidationError({'error': '答案格式错误'})
        question_ids.append(int(q_id))
    if len(set(question_ids)) != len(question_ids):
        raise ValidationError({'error': '不能重复提交同一道题目'})
    queryset = apply_institution_filter(Question.objects.all(), user, request=request).filter(pk__in=question_ids).order_by('pk')
    if lock:
        queryset = queryset.select_for_update()
    questions = {question.pk: question for question in queryset}
    if len(questions) != len(question_ids):
        raise ValidationError({'error': '题目不存在或不在当前内容范围内'})
    return questions


def run_exam_grading(user_id: int, exam_id: int, questions_data: List[Dict[str, Any]]):
    user = User.objects.filter(id=user_id).first()
    exam = QuizExam.objects.filter(id=exam_id, user_id=user_id).first()
    if not user or not user.is_active or not has_learning_feature(user, 'quiz.exam') or not exam or exam.grading_completed_at:
        return
    # Recheck the current configured boundary before reading answers or grading.
    try:
        scope = get_content_institution_id()
        questions = validate_exam_answers(user, questions_data)
    except (PermissionDenied, ValidationError):
        return
    try:
        graded_answers = [
            (questions[int(item['question_id'])], item.get('answer') or '',
             _grade_answer(questions[int(item['question_id'])], item.get('answer') or ''))
            for item in questions_data
        ]
    except Exception:
        logger.exception('Exam grading failed: exam_id=%s', exam_id)
        with transaction.atomic():
            locked = User.objects.select_for_update().filter(pk=user_id).first()
            if not locked or not locked.is_active or not has_learning_feature(locked, 'quiz.exam'):
                return
            exam = QuizExam.objects.select_for_update().filter(pk=exam_id, user_id=user_id).first()
            if exam and not exam.grading_completed_at:
                exam.summary = '批改服务暂不可用，本次未更新学习记录。'
                exam.save(update_fields=['summary'])
                Notification.objects.create(
                    recipient=user, ntype='system', title='试卷批改未完成',
                    content='批改服务暂不可用，本次未更新学习记录，请稍后重试。',
                    link=f'/tests?action=view_report&exam_id={exam_id}',
                )
        return

    with transaction.atomic():
        locked = User.objects.select_for_update().filter(id=user_id).first()
        if not locked or not locked.is_active or not has_learning_feature(locked, 'quiz.exam'):
            return
        exam = QuizExam.objects.select_for_update().filter(id=exam_id, user_id=user_id).first()
        if not exam or exam.grading_completed_at:
            return
        try:
            if get_content_institution_id() != scope:
                return
            current_questions = validate_exam_answers(locked, questions_data, lock=True)
        except (PermissionDenied, ValidationError):
            return
        total_score = sum(result['score'] for _, _, result in graded_answers)
        max_total_score = sum(result['max_score'] for _, _, result in graded_answers)
        avg_score = total_score / max_total_score if max_total_score > 0 else 0
        avg_difficulty = sum(float(current_questions[q.pk].difficulty or 1000) for q, _, _ in graded_answers) / len(graded_answers)
        for question, user_answer, graded in graded_answers:
            question = current_questions[question.pk]
            _apply_memorix_status(locked, question, graded['normalized_score'], graded['memorix_rating'])
            ExamQuestionResult.objects.create(
                exam=exam, question=question, user_answer=user_answer,
                score=graded['score'], max_score=graded['max_score'],
                feedback=graded['feedback'], analysis=graded['analysis'],
                is_correct=graded['is_correct'],
            )
            _queue_experience_verification(user_id, question, graded['score'])

        elo_change = _calc_elo_change(locked.elo_score, avg_score, avg_difficulty)
        locked.elo_score += elo_change
        locked.save(update_fields=['elo_score'])
        exam.total_score = total_score
        exam.max_score = max_total_score
        exam.elo_change = elo_change
        exam.summary = ''
        exam.grading_completed_at = timezone.now()
        exam.save(update_fields=['total_score', 'max_score', 'elo_change', 'summary', 'grading_completed_at'])
        if len(graded_answers) == 1:
            title = '特训判分完成'
            content = f'该题已完成 AI 判分：{total_score}/{max_total_score}。点击查看详解。'
        else:
            title = '评估完成'
            content = f'得分：{total_score}/{max_total_score}。本次测验平均难度：{int(avg_difficulty)}。'
        Notification.objects.create(
            recipient=locked, ntype='system', title=title, content=content,
            link=f'/tests?action=view_report&exam_id={exam.id}',
        )


def save_confirmed_questions(questions_data: List[Dict[str, Any]], institution=None) -> int:
    created_count = 0

    with transaction.atomic():
        for q_data in questions_data:
            q_type, subjective_type = AIService.normalize_question_type(
                q_data.get('q_type') or q_data.get('type'),
                q_data.get('subjective_type'),
            )

            text = str(q_data.get('question') or q_data.get('text') or '').strip()
            if not text:
                continue

            kp_id = q_data.get('kp_id') or q_data.get('knowledge_point_id')
            try:
                kp_id = int(kp_id) if kp_id is not None else None
            except Exception:
                kp_id = None

            options = AIService.normalize_options(q_data.get('options')) if q_type == 'objective' else {}
            answer = q_data.get('answer') or q_data.get('correct_answer') or ''
            if q_type == 'objective':
                answer = AIService.normalize_objective_answer(answer, options)

            difficulty_level = AIService.normalize_difficulty_level(
                q_data.get('difficulty_level'), q_data.get('difficulty')
            )

            if q_type == 'objective':
                grading_points = '无'
            else:
                grading_points = str(q_data.get('grading_points') or '').strip() or AIService.default_grading_points(subjective_type)

            Question.objects.create(
                knowledge_point_id=kp_id,
                text=text,
                q_type=q_type,
                subjective_type=subjective_type if q_type == 'subjective' else None,
                options=options if q_type == 'objective' else {},
                correct_answer=str(answer).strip(),
                grading_points=grading_points,
                ai_answer='',
                difficulty_level=difficulty_level,
                institution=institution,
            )
            created_count += 1

    return created_count
