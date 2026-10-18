"""
ai_assistant/views_api.py — Grading API + Memory API + Practice API + Feedback API.

Endpoints:
    POST /api/grading/grade/        — 判分
    GET  /api/memory/profile/       — 用户画像
    GET  /api/memory/due/           — 到期待复习题
    GET  /api/memory/stats/         — 学习统计
    POST /api/ai/practice/start/    — 创建练习会话
    POST /api/ai/practice/submit/   — 提交练习，返回成绩单
    POST /api/ai/feedback/          — AI 回复反馈（赞/踩）
"""

import hashlib
import json
import logging
import math

from django.db import transaction
from rest_framework import serializers
from rest_framework.decorators import api_view, permission_classes
from users.permissions import IsMember
from rest_framework.response import Response

from ai_service import AIService
from ai_assistant.services.grading_engine import GradingEngine
from ai_assistant.services.memory_system import MemorySystem
from ai_assistant.services.practice import practice_grade_cache_key
from quizzes.models import Question, PracticeSubmission, GradingRecord
from users.models import User
from core.utils import get_content_institution, get_content_institution_id

logger = logging.getLogger(__name__)


class PracticeAnswerInput(serializers.Serializer):
    question_id = serializers.IntegerField(min_value=1)
    answer = serializers.CharField(allow_blank=True, default='')


def _resolve_user(request):
    """Resolve target user from request. Admins may pass user_id query param."""
    user_id = request.query_params.get('user_id')
    if user_id:
        from users.permissions import is_platform_admin, is_institution_admin
        if not (is_platform_admin(request.user) or is_institution_admin(request.user)):
            return None, Response({'error': '无权查询其他用户'}, status=403)
        try:
            target = User.objects.get(id=user_id, is_active=True, institution_id=get_content_institution_id())
        except User.DoesNotExist:
            return None, Response({'error': '用户不存在'}, status=404)
        from users.learning import is_course_student
        if not is_course_student(target):
            return None, Response({'error': '该账号不是可访问的课程学员'}, status=403)
        return target, None
    return request.user, None


# ── Grading API ────────────────────────────────────────────────────────

@api_view(['POST'])
@permission_classes([IsMember])
def grade_view(request):
    """
    POST /api/grading/grade/
    Body: {question_id, user_answer}
    Returns: GradingEngine.grade() result
    """
    question_id = request.data.get('question_id')
    user_answer = request.data.get('user_answer')

    if question_id is None or user_answer is None:
        return Response({'error': 'question_id and user_answer are required'}, status=400)

    try:
        question = Question.objects.get(id=question_id, institution_id=get_content_institution_id())
    except Question.DoesNotExist:
        return Response({'error': '题目不存在'}, status=404)

    ai = AIService()
    try:
        result = GradingEngine.grade(
            ai=ai,
            question_text=question.text or '',
            user_answer=user_answer,
            correct_answer=question.correct_answer or '',
            q_type=question.q_type or 'objective',
            max_score=question.get_max_score(),
            grading_points=question.grading_points,
            options=question.options,
            subjective_type=question.subjective_type or '主观题',
        )
    except Exception:
        logger.exception("Grading failed for question_id=%s", question_id)
        return Response({'error': '判分失败，请稍后重试'}, status=500)

    return Response(result)


# ── Memory API ─────────────────────────────────────────────────────────

@api_view(['GET'])
@permission_classes([IsMember])
def profile_view(request):
    """
    GET /api/memory/profile/?user_id=<optional>
    Returns: user profile (learning stats + mastery map + weak points)
    """
    user, error_resp = _resolve_user(request)
    if error_resp:
        return error_resp

    try:
        profile = MemorySystem.query_user_profile(
            user,
            institution=get_content_institution(),
        )
    except Exception:
        logger.exception("Profile query failed for user_id=%s", user.id)
        return Response({'error': '查询画像失败，请稍后重试'}, status=500)

    return Response(profile)


@api_view(['GET'])
@permission_classes([IsMember])
def due_view(request):
    """
    GET /api/memory/due/?user_id=<optional>&limit=20
    Returns: due reviews list
    """
    user, error_resp = _resolve_user(request)
    if error_resp:
        return error_resp

    try:
        limit = int(request.query_params.get('limit', 20))
    except (TypeError, ValueError):
        limit = 20

    try:
        due_data = MemorySystem.query_due_reviews(
            user,
            limit=limit,
            institution=get_content_institution(),
        )
    except Exception:
        logger.exception("Due reviews query failed for user_id=%s", user.id)
        return Response({'error': '查询失败，请稍后重试'}, status=500)

    return Response(due_data)


@api_view(['GET'])
@permission_classes([IsMember])
def stats_view(request):
    """
    GET /api/memory/stats/?user_id=<optional>
    Returns: learning statistics (accuracy, streak, subjects, etc.)
    """
    user, error_resp = _resolve_user(request)
    if error_resp:
        return error_resp

    try:
        stats = MemorySystem.query_learning_stats(
            user,
            institution=get_content_institution(),
        )
    except Exception:
        logger.exception("Stats query failed for user_id=%s", user.id)
        return Response({'error': '查询统计失败，请稍后重试'}, status=500)

    return Response(stats)


# ── Practice Session API ─────────────────────────────────────────────────

import uuid as _uuid
from django.core.cache import cache as _cache
from django.utils import timezone as _timezone


@api_view(['POST'])
@permission_classes([IsMember])
def practice_start_view(request):
    """
    POST /api/ai/practice/start/
    Body: { kp_name?, subject?, difficulty?, count? (default 5) }
    Returns: { session_id, questions, total_time_estimate }

    创建练习会话，从题库抽取题目，存入 Redis（24h TTL）。
    """
    kp_name = (request.data.get('kp_name') or '').strip()
    subject = (request.data.get('subject') or '').strip()
    difficulty = (request.data.get('difficulty') or '').strip()
    count = serializers.IntegerField(min_value=1, max_value=10).run_validation(request.data.get('count', 5))

    user = request.user
    institution = get_content_institution()

    try:
        result = MemorySystem.query_practice_questions(
            user=user,
            kp_name=kp_name,
            subject=subject,
            difficulty=difficulty,
            limit=count,
            institution=institution,
        )
    except Exception:
        logger.exception("Practice start failed for user=%s", user.id)
        return Response({'error': '抽题失败，请稍后重试'}, status=500)

    questions = result.get('questions', [])
    if not questions:
        return Response({'error': '没有匹配的题目'}, status=404)

    session_id = _uuid.uuid4().hex
    session_key = f'practice:session:{session_id}'

    session_data = {
        'user_id': user.id,
        'questions': questions,
        'created_at': _timezone.now().isoformat(),
    }
    _cache.set(session_key, session_data, timeout=86400)  # 24h TTL

    # 估算总时长：每题 90 秒
    total_estimate = len(questions) * 90

    return Response({
        'session_id': session_id,
        'questions': questions,
        'total_questions': len(questions),
        'total_time_estimate': total_estimate,
    })


@api_view(['POST'])
@permission_classes([IsMember])
def practice_pre_grade_view(request):
    """
    POST /api/ai/practice/pre-grade/
    Body: { session_id, question_id, answer }

    异步预批改：收到单题答案后立即派发 Celery task 后台批改，
    结果按会话、题目及答案摘要缓存。
    submit 时优先读缓存，减少同步等待。
    """
    session_id = serializers.UUIDField().run_validation(request.data.get('session_id')).hex
    question_id = serializers.IntegerField(min_value=1).run_validation(request.data.get('question_id'))
    user_answer = str(request.data.get('answer', '')).strip()

    if not session_id or not question_id:
        return Response({'error': 'session_id 和 question_id 必填'}, status=400)
    if not user_answer:
        return Response({'error': 'answer 不能为空'}, status=400)

    # 验证 session 存在且属于当前用户
    session_key = f'practice:session:{session_id}'
    session_data = _cache.get(session_key)
    if not session_data:
        return Response({'error': '会话已过期或不存在'}, status=404)
    if session_data['user_id'] != request.user.id:
        return Response({'error': '无权访问此会话'}, status=403)

    # 验证 question_id 在 session 内
    session_questions = {q['id'] for q in session_data['questions']}
    if question_id not in session_questions:
        return Response({'error': '题目不属于此会话'}, status=400)

    if not Question.objects.filter(id=question_id, institution_id=get_content_institution_id()).exists():
        return Response({'error': '题目不在当前内容范围'}, status=403)

    # 异步派发 Celery task
    from ai_assistant.tasks import pre_grade_single_question
    try:
        pre_grade_single_question.delay(
            session_id=session_id,
            question_id=question_id,
            user_answer=user_answer,
            user_id=request.user.id,
        )
    except Exception:
        logger.exception('Practice pre-grade dispatch failed')
        return Response({'error': '预批改暂不可用，提交时会重新批改'}, status=503)

    return Response({'status': 'accepted', 'question_id': question_id})


@api_view(['POST'])
@permission_classes([IsMember])
def practice_submit_view(request):
    """Grade outside locks, then commit the complete session exactly once."""
    session_id = serializers.UUIDField().run_validation(request.data.get('session_id')).hex
    answer_input = PracticeAnswerInput(data=request.data.get('answers'), many=True, allow_empty=False)
    answer_input.is_valid(raise_exception=True)
    answers = answer_input.validated_data
    ids = [answer['question_id'] for answer in answers]
    if len(ids) != len(set(ids)):
        return Response({'error': '每道题只能提交一次答案'}, status=400)
    answers_hash = hashlib.sha256(json.dumps(
        sorted(answers, key=lambda answer: answer['question_id']), sort_keys=True,
    ).encode()).hexdigest()

    def replay(submission):
        if submission.answers_hash != answers_hash:
            return Response({'error': '此练习已提交，不能更换答案'}, status=409)
        return Response(submission.response)

    prior = PracticeSubmission.objects.filter(user=request.user, session_id=session_id).first()
    if prior:
        return replay(prior)
    session_key = f'practice:session:{session_id}'
    session = _cache.get(session_key)
    if not session:
        prior = PracticeSubmission.objects.filter(user=request.user, session_id=session_id).first()
        if prior:
            return replay(prior)
        return Response({'error': '会话已过期或不存在'}, status=404)
    if session['user_id'] != request.user.id:
        return Response({'error': '无权访问此会话'}, status=403)
    if set(ids) != {question['id'] for question in session['questions']}:
        return Response({'error': '请提交会话内全部题目的答案'}, status=400)
    scope = get_content_institution_id()
    questions = {question.pk: question for question in Question.objects.filter(
        pk__in=ids, institution_id=scope,
    ).select_related('knowledge_point')}
    if len(questions) != len(ids):
        return Response({'error': '题目不存在或已不在当前内容范围'}, status=403)

    ai = None
    graded = []
    results = []
    kp_scores = {}
    cache_hits = 0
    for answer in answers:
        question = questions[answer['question_id']]
        text = answer['answer']
        maximum = question.get_max_score()
        cache_key = practice_grade_cache_key(session_id, question.pk, text)
        if not text:
            grade = {'score': 0, 'feedback': '未作答', 'is_correct': False}
        else:
            grade = _cache.get(cache_key)
            if grade and '_error' not in grade:
                cache_hits += 1
            else:
                try:
                    if ai is None:
                        ai = AIService()
                    grade = GradingEngine.grade(
                        ai=ai, question_text=question.text or '', user_answer=text,
                        correct_answer=question.correct_answer or '', q_type=question.q_type,
                        max_score=maximum, grading_points=question.grading_points,
                        options=question.options, subjective_type=question.subjective_type or '主观题',
                        user=request.user,
                    )
                    _cache.set(cache_key, grade, timeout=1800)
                except Exception:
                    logger.exception('Practice grading failed for question_id=%s', question.pk)
                    return Response({'error': '判分失败，答案已保留，请稍后重新提交'}, status=503)
        try:
            score = float(grade['score'])
            if not math.isfinite(score):
                raise ValueError('Invalid grading score')
            score = max(0.0, min(maximum, score))
            is_correct = score >= maximum * 0.6
            rating = min(4, max(1, int(grade.get('memorix_rating', 3 if is_correct else 1))))
        except (KeyError, TypeError, ValueError):
            return Response({'error': '判分结果无效，请稍后重新提交'}, status=503)
        kp_name = question.knowledge_point.name if question.knowledge_point_id else ''
        results.append({
            'question_id': question.pk, 'is_correct': is_correct, 'score': score,
            'max_score': maximum, 'feedback': grade.get('feedback', ''),
            'error_analysis': grade.get('error_analysis'), 'kp_name': kp_name,
        })
        graded.append((question, text, grade, score, maximum, is_correct, rating))
        if question.knowledge_point_id:
            kp = kp_scores.setdefault(question.knowledge_point_id, {'correct': 0, 'total': 0, 'kp_name': kp_name})
            kp['total'] += 1
            kp['correct'] += int(is_correct)

    total_score = sum(result['score'] for result in results)
    max_score = sum(result['max_score'] for result in results)
    correct_rate = round(total_score / max_score * 100, 1) if max_score else 0
    correct_count = sum(result['is_correct'] for result in results)
    kp_breakdown = [{'kp_id': pk, 'kp_name': value['kp_name'],
                     'correct_rate': round(value['correct'] / value['total'] * 100, 1)}
                    for pk, value in kp_scores.items()]
    summary = [f'正确率 {correct_rate}%（{correct_count}/{len(results)}）']
    weak = [kp['kp_name'] for kp in kp_breakdown if kp['correct_rate'] < 60]
    summary.append('薄弱知识点：' + '、'.join(weak[:3]) if weak else '全部知识点掌握良好')
    response = {
        'total_score': round(total_score, 1), 'max_score': round(max_score, 1),
        'correct_rate': correct_rate, 'correct_count': correct_count,
        'total_questions': len(results), 'cache_hits': cache_hits, 'results': results,
        'kp_breakdown': kp_breakdown, 'summary_text': '。'.join(summary) + '。',
    }
    from quizzes.ai_workflow import _apply_memorix_status
    with transaction.atomic():
        user = User.objects.select_for_update().get(pk=request.user.pk)
        from users.feature_access import has_learning_feature
        if not has_learning_feature(user, 'quiz.exam'):
            return Response({'error': '当前账号已无法提交此练习'}, status=403)
        prior = PracticeSubmission.objects.filter(user=request.user, session_id=session_id).first()
        if prior:
            return replay(prior)
        # The content scope or questions may have changed while the AI was grading.
        current_questions = {question.pk: question for question in Question.objects.select_for_update().filter(
            pk__in=ids, institution_id=scope,
        ).order_by('pk')}
        if get_content_institution_id() != scope or len(current_questions) != len(ids):
            return Response({'error': '题目内容范围已变更，请重新开始练习'}, status=409)
        for question, text, grade, score, maximum, is_correct, rating in graded:
            question = current_questions[question.pk]
            if not text:
                continue
            error = grade.get('error_analysis') or {}
            error_type = error.get('type', '') if isinstance(error, dict) else ''
            metadata = {key: error.get(key, '') for key in ('reasoning', 'suggested_focus')} if isinstance(error, dict) and error else {}
            if metadata:
                metadata['graded_at'] = _timezone.now().isoformat()
            GradingRecord.objects.create(
                user=request.user, question=question, score=score, max_score=maximum,
                is_correct=is_correct, error_type=error_type, error_metadata=metadata,
                feedback=grade.get('feedback', ''), analysis=grade.get('analysis', ''),
            )
            status = _apply_memorix_status(request.user, question, score / maximum if maximum else 0, rating)
            status.error_type, status.error_metadata = error_type, metadata
            status.save(update_fields=['error_type', 'error_metadata'])
        PracticeSubmission.objects.create(user=request.user, session_id=session_id,
                                          answers_hash=answers_hash, response=response)
    # A failed cache cleanup must not turn an already committed submission into a 500.
    try:
        _cache.delete_many([session_key] + [practice_grade_cache_key(session_id, answer['question_id'], answer['answer']) for answer in answers])
    except Exception:
        logger.warning('Practice cache cleanup failed', exc_info=True)
    return Response(response)


# ── Feedback API ─────────────────────────────────────────────────────────

@api_view(['POST'])
@permission_classes([IsMember])
def feedback_view(request):
    """
    POST /api/ai/feedback/
    Body: { message_id: int, feedback: bool }
    静默记录用户对 AI 回复的反馈（赞/踩），同步更新 MUTAR 轨迹 outcome。
    """
    message_id = request.data.get('message_id')
    feedback = request.data.get('feedback')

    if message_id is None or feedback is None:
        return Response({'error': 'message_id and feedback are required'}, status=400)
    if not isinstance(feedback, bool):
        return Response({'error': 'feedback must be true or false'}, status=400)

    from .models import AIChatMessage
    try:
        msg = AIChatMessage.objects.get(id=message_id, user=request.user, role='assistant')
    except AIChatMessage.DoesNotExist:
        return Response({'error': '消息不存在'}, status=404)

    msg.feedback = feedback
    msg.save(update_fields=['feedback'])

    # 同步更新 MUTAR 轨迹 outcome（同一 conversation 内最新反馈覆盖）
    try:
        from .models import AITrajectory
        from django.utils import timezone
        trajectory = AITrajectory.objects.filter(
            conversation_id=msg.conversation_id,
        ).order_by('-created_at').first()
        if trajectory:
            trajectory.outcome = 'success' if feedback else 'failure'
            trajectory.outcome_metrics = {
                **trajectory.outcome_metrics,
                'feedback_source': 'user',
                'feedback_message_id': msg.id,
            }
            trajectory.evaluated_at = timezone.now()
            trajectory.save(update_fields=['outcome', 'outcome_metrics', 'evaluated_at'])
    except Exception:
        logger.warning("Trajectory outcome update failed for msg %s", msg.id, exc_info=True)

    return Response({'status': 'ok'})
