import logging
from typing import Any, Dict, List

from django.db import connection, transaction
from django.db.models import Count, F, Q, Sum
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from core.utils import apply_institution_filter, get_content_institution_id

from quizzes.utils import safe_int

from ai_service import AIService
from notifications.models import Notification
from quizzes.memorix.service import MemorixService
from quizzes.models import ExamQuestionResult, Question, QuizExam, UserQuestionStatus
from quizzes.services.exam_grading_state import grading_lock_key
from quizzes.services.practice_results import validate_grading_question
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


def _grade_answer(question: Question, user_answer: Any, *, objective_only=False, language='zh-CN', ulr=False) -> Dict[str, Any]:
    max_score = question.get_max_score()
    correct_answer = question.correct_answer
    if question.q_type == 'objective':
        options = AIService.normalize_options(question.options)
        user_answer = AIService.normalize_objective_answer(user_answer, options)
        correct_answer = AIService.normalize_objective_answer(correct_answer, options)
    if objective_only and question.q_type == 'objective':
        correct = bool(user_answer and user_answer == correct_answer)
        grade_data = {'score': max_score if correct else 0, 'feedback': ('Your answer matches the reference answer.' if correct else 'Your answer does not match the reference answer.') if language == 'en' else ('作答与标准答案一致。' if correct else '作答与标准答案不一致。'),
                      'analysis': question.ai_answer or '', 'memorix_rating': 4 if correct else 1}
    else:
        grade_data = AIService.grade_question(
            language=language,
            question_text=question.text,
            user_answer=user_answer,
            correct_answer=correct_answer,
            q_type=question.q_type,
            max_score=max_score,
            grading_points=question.grading_points,
            options=question.options,
            rubric=question.rubric,
            subjective_type=_subjective_type_label(question),
            **({'ulr': True} if ulr else {}),
        )

    score_val = _clamp_score(float(grade_data.get('score', 0)), max_score)

    # 客观题以标准答案比对为准，避免模型漂移
    if question.q_type == 'objective':
        user_choice = AIService.normalize_objective_answer(user_answer)
        correct_choice = AIService.normalize_objective_answer(correct_answer)
        score_val = float(max_score if user_choice and user_choice == correct_choice else 0)

    normalized_score = score_val / max_score if max_score > 0 else 0
    memorix_rating = safe_int(grade_data.get('memorix_rating', 2), 2)
    memorix_rating = min(4, max(1, memorix_rating))

    return {
        'score': score_val,
        'max_score': max_score,
        'feedback': grade_data.get('feedback', '已评阅'),
        'analysis': grade_data.get('analysis', question.ai_answer or ''),
        'error_analysis': grade_data.get('error_analysis') or {},
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


def _exam_counts(exam_id: int) -> Dict[str, Any]:
    return ExamQuestionResult.objects.filter(exam_id=exam_id).aggregate(
        graded=Count('id', filter=Q(status='graded')),
        failed=Count('id', filter=Q(status='failed')),
        pending=Count('id', filter=Q(status='pending')),
        score=Sum('score', filter=Q(status='graded')),
        max_score=Sum('max_score', filter=Q(status='graded')),
    )


def _refresh_exam_counts(exam_id: int) -> None:
    counts = _exam_counts(exam_id)
    QuizExam.objects.filter(pk=exam_id, status='grading').update(
        graded_count=counts['graded'] or 0,
        failed_count=counts['failed'] or 0,
        total_score=counts['score'] or 0,
        max_score=counts['max_score'] or 0,
    )


def _mark_item_failed(item_id: int, message: str) -> None:
    with transaction.atomic():
        item = ExamQuestionResult.objects.select_for_update().filter(pk=item_id).first()
        if not item or item.status != 'pending':
            return
        item.status = 'failed'
        item.attempts += 1
        item.graded_at = timezone.now()
        item.error_metadata = {'error': str(message)[:1000]}
        item.save(update_fields=['status', 'attempts', 'graded_at', 'error_metadata'])
        _refresh_exam_counts(item.exam_id)


def _fail_pending_items(exam_id: int, message: str) -> None:
    with transaction.atomic():
        items = list(ExamQuestionResult.objects.select_for_update().filter(
            exam_id=exam_id, status='pending',
        ))
        for item in items:
            item.status = 'failed'
            item.attempts += 1
            item.graded_at = timezone.now()
            item.error_metadata = {'error': str(message)[:1000]}
        if items:
            ExamQuestionResult.objects.bulk_update(
                items, ['status', 'attempts', 'graded_at', 'error_metadata'], batch_size=200,
            )
        _refresh_exam_counts(exam_id)


def _create_exam_notification(exam: QuizExam) -> None:
    if exam.status == 'completed':
        title = '练习批改完成'
        rate = exam.total_score / exam.max_score * 100 if exam.max_score else 0
        content = f'得分：{exam.total_score}/{exam.max_score}，正确率 {round(rate, 1)}%。点击查看逐题复盘。'
    elif exam.status == 'partial':
        title = '练习部分完成'
        content = f'还有 {exam.failed_count} 题未完成，已完成 {exam.graded_count}/{exam.total_questions} 题。点击查看。'
    else:
        title = '练习批改未完成'
        content = '批改服务暂不可用，请稍后重试。'
    if exam.ui_language == 'en':
        title = {'completed': 'Practice grading complete', 'partial': 'Practice partly graded'}.get(exam.status, 'Practice grading incomplete')
        content = (f'Score: {exam.total_score}/{exam.max_score}. Open your question review.' if exam.status == 'completed'
                   else f'Graded {exam.graded_count}/{exam.total_questions} questions. Open the results to retry unfinished questions.')
    Notification.objects.create(
        recipient_id=exam.user_id,
        ntype='practice_result',
        title=title,
        content=content,
        link=f'/tests/results/{exam.id}',
    )


def _finalize_exam(user_id: int, exam_id: int) -> None:
    with transaction.atomic():
        exam = QuizExam.objects.select_for_update().filter(id=exam_id, user_id=user_id).first()
        if not exam:
            return
        if exam.status in ('completed', 'partial', 'failed') and exam.grading_completed_at and exam.notified_at:
            return
        counts = _exam_counts(exam.id)
        if counts['pending']:
            return

        graded_items = list(ExamQuestionResult.objects.filter(
            exam_id=exam.id, status='graded',
        ).select_related('question'))
        total_score = counts['score'] or 0
        max_score = counts['max_score'] or 0
        failed = counts['failed'] or 0
        if not graded_items and failed:
            exam.status = 'failed'
            exam.summary = 'Grading did not finish. Try again later.' if exam.ui_language == 'en' else '批改未完成，请稍后重试。'
        elif not graded_items and not failed:
            exam.status = 'failed'
            exam.summary = 'This practice has no gradable questions.' if exam.ui_language == 'en' else '本次练习没有可批改的题目。'
        elif failed:
            exam.status = 'partial'
            exam.summary = f'Grading incomplete: {len(graded_items)}/{exam.total_questions} questions completed.' if exam.ui_language == 'en' else f'部分题目未完成，已完成 {len(graded_items)} / {exam.total_questions or len(graded_items) + failed} 题。'
        else:
            exam.status = 'completed'
            exam.summary = ''

        exam.total_questions = exam.total_questions or (len(graded_items) + failed)
        exam.graded_count = len(graded_items)
        exam.failed_count = failed
        exam.total_score = round(total_score, 1)
        exam.max_score = round(max_score, 1)
        exam.grading_completed_at = timezone.now()
        update_fields = [
            'status', 'summary', 'total_questions', 'graded_count', 'failed_count',
            'total_score', 'max_score', 'grading_completed_at',
        ]

        exam.last_error = f'{failed} 道题未完成' if failed else ''
        update_fields.append('last_error')
        notify = exam.notified_at is None
        if notify:
            exam.notified_at = timezone.now()
            update_fields.append('notified_at')
        exam.save(update_fields=update_fields)
        if notify:
            _create_exam_notification(exam)


def run_exam_grading(user_id: int, exam_id: int, questions_data: List[Dict[str, Any]] = None):
    # PostgreSQL releases this lock when the worker connection closes. No transaction spans a model call.
    if connection.vendor != 'postgresql':
        return _run_exam_grading(user_id, exam_id)
    key = grading_lock_key(user_id, exam_id)
    with connection.cursor() as cursor:
        cursor.execute('SELECT pg_try_advisory_lock(%s)', [key])
        if not cursor.fetchone()[0]:
            # A retry can be enqueued as the previous run finishes releasing its lock.
            if not QuizExam.objects.filter(pk=exam_id, user_id=user_id, status='grading', started_at__isnull=True).exists():
                return
            cursor.execute('SELECT pg_advisory_lock(%s)', [key])
    try:
        return _run_exam_grading(user_id, exam_id)
    finally:
        with connection.cursor() as cursor:
            cursor.execute('SELECT pg_advisory_unlock(%s)', [key])


def _run_exam_grading(user_id: int, exam_id: int):
    from ai_assistant.services.ulr_config import ulr_enabled

    user = User.objects.filter(id=user_id).first()
    if not user or not user.is_active or not has_learning_feature(user, 'quiz.exam'):
        return
    with transaction.atomic():
        exam = QuizExam.objects.select_for_update().filter(id=exam_id, user_id=user_id).first()
        if not exam or exam.status not in ('pending', 'grading'):
            return
        native_worker = ulr_enabled()
        exam.requires_ulr = (exam.requires_ulr or native_worker
                             or exam.results.filter(question_snapshot__has_key='ulr_practice_version').exists())
        exam.status = 'grading'
        exam.started_at = timezone.now()
        exam.save(update_fields=['status', 'started_at', 'requires_ulr'])
    force_ulr = exam.requires_ulr and not native_worker

    from ai_assistant.models import ProjectLearningTask
    from ai_assistant.services.learning_tasks import validate_task_question, sync_exam_task_result, task_result_snapshot, personal_question
    learning_task = ProjectLearningTask.objects.select_related('project__user').filter(exam_id=exam_id).first()
    personal_task = bool(learning_task and learning_task.definition)
    try:
        scope = None if personal_task else get_content_institution_id(user)
    except PermissionDenied as exc:
        _fail_pending_items(exam_id, str(exc))
        _finalize_exam(user_id, exam_id)
        return

    items = list(ExamQuestionResult.objects.filter(exam_id=exam_id, status='pending').order_by('position', 'id'))
    if not items:
        _finalize_exam(user_id, exam_id)
        return

    for item in items:
        snapshot = item.question_snapshot or {}
        practice_card = 'ulr_practice_version' in snapshot
        versioned = practice_card or 'ulr_grading_version' in snapshot
        try:
            if personal_task:
                task_result_snapshot(learning_task, item)
                question = personal_question(learning_task.definition)
            else:
                if get_content_institution_id(user) != scope:
                    raise ValidationError('内容范围已变更')
                question = Question.objects.select_related('knowledge_point').filter(
                    pk=item.question_id, institution_id=scope,
                ).first()
                if not question:
                    raise ValidationError('题目不存在或不在当前内容范围')
                if learning_task:
                    validate_task_question(learning_task, question)
                elif versioned:
                    validate_grading_question(question, snapshot, scope)
            if (learning_task or practice_card) and question.q_type == 'objective':
                graded = _grade_answer(question, item.user_answer or '', objective_only=True, language=exam.ui_language)
                if practice_card:
                    graded['analysis'] = item.question_snapshot['ai_answer']
            else:
                graded = _grade_answer(question, item.user_answer or '', language=exam.ui_language,
                                       **({'ulr': True} if force_ulr else {}))
        except Exception as exc:
            logger.exception('Exam item grading failed: exam_id=%s item_id=%s', exam_id, item.pk)
            _mark_item_failed(item.pk, str(exc))
            continue

        try:
            with transaction.atomic():
                # Do not select_related('question') here: question is nullable,
                # and PostgreSQL rejects FOR UPDATE on the nullable side of an outer join.
                locked = ExamQuestionResult.objects.select_for_update().filter(pk=item.pk).first()
                if not locked or locked.status != 'pending':
                    continue
                if personal_task:
                    task_result_snapshot(learning_task, locked)
                    question = personal_question(learning_task.definition)
                else:
                    question = Question.objects.select_related('knowledge_point').filter(
                        pk=locked.question_id, institution_id=scope,
                    ).first()
                    if not question or get_content_institution_id(user) != scope:
                        raise ValidationError('题目或内容范围已变更')
                    if learning_task:
                        task_result_snapshot(learning_task, locked)
                    elif versioned:
                        validate_grading_question(question, locked.question_snapshot, scope)
                    _apply_memorix_status(
                        user, question, graded['normalized_score'], graded['memorix_rating'],
                    )
                error = graded.get('error_analysis') or {}
                locked.score = graded['score']
                locked.max_score = graded['max_score']
                locked.feedback = graded['feedback']
                locked.analysis = graded['analysis']
                locked.is_correct = graded['is_correct']
                locked.error_type = error.get('type', '') if isinstance(error, dict) else ''
                locked.error_metadata = {
                    key: error.get(key, '')
                    for key in ('reasoning', 'suggested_focus')
                } if isinstance(error, dict) and error else {}
                locked.status = 'graded'
                locked.attempts += 1
                locked.graded_at = timezone.now()
                locked.save(update_fields=[
                    'score', 'max_score', 'feedback', 'analysis', 'is_correct',
                    'error_type', 'error_metadata', 'status', 'attempts', 'graded_at',
                ])
                if learning_task:
                    transaction.on_commit(lambda result_id=locked.pk: sync_exam_task_result(result_id), robust=True)
                _refresh_exam_counts(exam_id)
                transaction.on_commit(
                    lambda q=question, s=graded['score']: _queue_experience_verification(user_id, q, s)
                )
        except Exception as exc:
            logger.exception('Exam item commit failed: exam_id=%s item_id=%s', exam_id, item.pk)
            _mark_item_failed(item.pk, str(exc))

    _finalize_exam(user_id, exam_id)


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
