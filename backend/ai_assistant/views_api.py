"""
ai_assistant/views_api.py — Grading API + Memory API (Phase 5).

Endpoints:
    POST /api/grading/grade/   — 判分
    GET  /api/memory/profile/  — 用户画像
    GET  /api/memory/due/      — 到期待复习题
    GET  /api/memory/stats/    — 学习统计
"""

import logging

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from ai_service import AIService
from ai_assistant.services.grading_engine import GradingEngine
from ai_assistant.services.memory_system import MemorySystem
from quizzes.models import Question
from users.models import User

logger = logging.getLogger(__name__)


def _resolve_user(request):
    """Resolve target user from request. Admins may pass user_id query param."""
    user_id = request.query_params.get('user_id')
    if user_id:
        from users.permissions import is_platform_admin, is_institution_admin
        if not (is_platform_admin(request.user) or is_institution_admin(request.user)):
            return None, Response({'error': '无权查询其他用户'}, status=403)
        try:
            target = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return None, Response({'error': '用户不存在'}, status=404)
        # institution admin can only query users in same institution
        if is_institution_admin(request.user) and not is_platform_admin(request.user):
            if target.institution_id != request.user.institution_id:
                return None, Response({'error': '无权查询其他机构用户'}, status=403)
        return target, None
    return request.user, None


# ── Grading API ────────────────────────────────────────────────────────

@api_view(['POST'])
@permission_classes([IsAuthenticated])
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
        question = Question.objects.get(id=question_id)
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
    except Exception as exc:
        logger.exception("Grading failed for question_id=%s", question_id)
        return Response({'error': f'判分失败: {str(exc)}'}, status=500)

    return Response(result)


# ── Memory API ─────────────────────────────────────────────────────────

@api_view(['GET'])
@permission_classes([IsAuthenticated])
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
            institution=getattr(user, 'institution', None),
        )
    except Exception as exc:
        logger.exception("Profile query failed for user_id=%s", user.id)
        return Response({'error': f'查询画像失败: {str(exc)}'}, status=500)

    return Response(profile)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
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
            institution=getattr(user, 'institution', None),
        )
    except Exception as exc:
        logger.exception("Due reviews query failed for user_id=%s", user.id)
        return Response({'error': f'查询失败: {str(exc)}'}, status=500)

    return Response(due_data)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
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
            institution=getattr(user, 'institution', None),
        )
    except Exception as exc:
        logger.exception("Stats query failed for user_id=%s", user.id)
        return Response({'error': f'查询统计失败: {str(exc)}'}, status=500)

    return Response(stats)
