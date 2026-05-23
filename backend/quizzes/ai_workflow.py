from typing import Any, Dict, Iterable, List

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from quizzes.utils import safe_int

from ai_service import AIService
from notifications.models import Notification
from quizzes.memorix.service import MemorixService
from quizzes.models import ExamQuestionResult, Question, QuizExam, UserQuestionStatus
from users.models import User


def _clamp_score(score: float, max_score: float) -> float:
    return max(0.0, min(float(max_score or 0), float(score or 0)))


def _subjective_type_label(question: Question) -> str:
    if question.q_type == 'subjective' and question.subjective_type:
        return question.get_subjective_type_display()
    return '客观题'


def _apply_fsrs_status(user: User, question: Question, normalized_score: float, fsrs_rating: int, review_time=None) -> UserQuestionStatus:
    status_obj, _ = UserQuestionStatus.objects.get_or_create(user=user, question=question)
    status_obj = MemorixService.update_status(user_id=user.id, status=status_obj, rating=fsrs_rating)
    if review_time is not None:
        status_obj.last_review = review_time

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


def grade_answer_for_user(user: User, question: Question, user_answer: Any, set_last_review: bool = True) -> Dict[str, Any]:
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
    fsrs_rating = safe_int(grade_data.get('fsrs_rating', 2), 2)
    fsrs_rating = min(4, max(1, fsrs_rating))

    _apply_fsrs_status(
        user=user,
        question=question,
        normalized_score=normalized_score,
        fsrs_rating=fsrs_rating,
        review_time=timezone.now() if set_last_review else None,
    )

    return {
        'score': score_val,
        'max_score': max_score,
        'feedback': grade_data.get('feedback', '已评阅'),
        'analysis': grade_data.get('analysis', question.ai_answer or ''),
        'fsrs_rating': fsrs_rating,
        'normalized_score': normalized_score,
        'is_correct': normalized_score >= 0.6,
    }


def grade_single_question_submission(user: User, question: Question, user_answer: Any) -> Dict[str, Any]:
    result = grade_answer_for_user(user=user, question=question, user_answer=user_answer)

    with transaction.atomic():
        locked = User.objects.select_for_update().get(id=user.id)
        elo_change = _calc_elo_change(user_elo=locked.elo_score, score_ratio=result['normalized_score'], difficulty=float(question.difficulty or 1000))
        locked.elo_score += elo_change
        locked.save(update_fields=['elo_score'])


    result['elo_change'] = elo_change
    return result


def mark_questions_reviewed(user: User, question_ids: Iterable[int], review_time=None):
    now = review_time or timezone.now()
    min_next_review = now + timezone.timedelta(hours=1)
    for q_id in question_ids:
        try:
            status_obj, _ = UserQuestionStatus.objects.get_or_create(user=user, question_id=q_id)
            status_obj.last_review = now
            if status_obj.next_review_at < min_next_review:
                status_obj.next_review_at = min_next_review
                status_obj.save(update_fields=['last_review', 'next_review_at'])
            else:
                status_obj.save(update_fields=['last_review'])
        except Exception:
            continue


def run_exam_grading(user_id: int, exam_id: int, questions_data: List[Dict[str, Any]]):
    user = User.objects.filter(id=user_id).first()
    exam = QuizExam.objects.filter(id=exam_id).first()
    if not user or not exam:
        return

    total_score = 0.0
    max_total_score = 0.0
    total_difficulty = 0.0
    question_count = 0

    for item in questions_data:
        q_id = item.get('question_id')
        user_answer = item.get('answer')

        question = Question.objects.filter(id=q_id).first()
        if not question:
            continue

        max_score = question.get_max_score()
        max_total_score += max_score
        total_difficulty += float(question.difficulty or 1000)
        question_count += 1

        try:
            graded = grade_answer_for_user(user=user, question=question, user_answer=user_answer)
            total_score += graded['score']

            ExamQuestionResult.objects.update_or_create(
                exam=exam,
                question=question,
                defaults={
                    'user_answer': user_answer or '',
                    'score': graded['score'],
                    'max_score': max_score,
                    'feedback': graded['feedback'],
                    'analysis': graded['analysis'],
                    'is_correct': graded['is_correct'],
                },
            )
        except Exception as exc:
            ExamQuestionResult.objects.create(
                exam=exam,
                question=question,
                user_answer=user_answer or '',
                score=0,
                max_score=max_score,
                feedback='评分服务异常',
                analysis=f'错误详情: {str(exc)}',
                is_correct=False,
            )

    avg_score = total_score / max_total_score if max_total_score > 0 else 0
    avg_difficulty = total_difficulty / question_count if question_count > 0 else 1000

    with transaction.atomic():
        locked = User.objects.select_for_update().get(id=user_id)
        elo_change = _calc_elo_change(user_elo=locked.elo_score, score_ratio=avg_score, difficulty=avg_difficulty)
        locked.elo_score += elo_change
        locked.save(update_fields=['elo_score'])


    exam.total_score = total_score
    exam.max_score = max_total_score
    exam.elo_change = elo_change
    exam.save(update_fields=['total_score', 'max_score', 'elo_change'])

    if question_count == 1:
        title = '特训判分完成'
        content = f'该题已完成 AI 判分：{total_score}/{max_total_score}。点击查看详解。'
    else:
        title = '评估完成'
        content = f'得分：{total_score}/{max_total_score}。本次测验平均难度：{int(avg_difficulty)}。'

    Notification.objects.create(
        recipient=user,
        ntype='system',
        title=title,
        content=content,
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
