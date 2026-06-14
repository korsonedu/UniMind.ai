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


# ── Practice Session API ─────────────────────────────────────────────────

import uuid as _uuid
from django.core.cache import cache as _cache
from django.utils import timezone as _timezone


@api_view(['POST'])
@permission_classes([IsAuthenticated])
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
    count = int(request.data.get('count', 5))
    count = max(1, min(count, 10))

    user = request.user
    institution = getattr(user, 'institution', None)

    try:
        result = MemorySystem.query_practice_questions(
            user=user,
            kp_name=kp_name,
            subject=subject,
            difficulty=difficulty,
            limit=count,
            institution=institution,
        )
    except Exception as exc:
        logger.exception("Practice start failed for user=%s", user.id)
        return Response({'error': f'抽题失败: {str(exc)}'}, status=500)

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
@permission_classes([IsAuthenticated])
def practice_pre_grade_view(request):
    """
    POST /api/ai/practice/pre-grade/
    Body: { session_id, question_id, answer }

    异步预批改：收到单题答案后立即派发 Celery task 后台批改，
    结果写 Redis (practice:grade:{session_id}:{question_id})。
    submit 时优先读缓存，减少同步等待。
    """
    session_id = (request.data.get('session_id') or '').strip()
    question_id = int(request.data.get('question_id', 0))
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

    # 异步派发 Celery task
    from ai_assistant.tasks import pre_grade_single_question
    pre_grade_single_question.delay(
        session_id=session_id,
        question_id=question_id,
        user_answer=user_answer,
        user_id=request.user.id,
    )

    return Response({'status': 'accepted', 'question_id': question_id})


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def practice_submit_view(request):
    """
    POST /api/ai/practice/submit/
    Body: { session_id, answers: [{question_id, answer}, ...] }
    Returns: { total_score, max_score, correct_rate, time_spent,
               results: [{question_id, is_correct, score, feedback, error_analysis?}],
               kp_breakdown, summary_text }

    优先读 Redis 预批改缓存 (practice:grade:{session_id}:{qid})，
    缓存未命中时同步批改。
    """
    session_id = (request.data.get('session_id') or '').strip()
    answers = request.data.get('answers', [])

    if not session_id:
        return Response({'error': 'session_id 必填'}, status=400)
    if not answers or not isinstance(answers, list):
        return Response({'error': 'answers 必填，且必须为数组'}, status=400)

    # 从 Redis 取 session 验证
    session_key = f'practice:session:{session_id}'
    session_data = _cache.get(session_key)
    if not session_data:
        return Response({'error': '会话已过期或不存在'}, status=404)
    if session_data['user_id'] != request.user.id:
        return Response({'error': '无权访问此会话'}, status=403)

    session_questions = {q['id']: q for q in session_data['questions']}
    valid_question_ids = set(session_questions.keys())

    # 验证 question_ids
    submitted_ids = {int(a.get('question_id', 0)) for a in answers}
    if not submitted_ids.issubset(valid_question_ids):
        return Response({'error': '提交的题目 ID 与 session 不匹配'}, status=400)

    ai = None  # lazy init，只在缓存未命中时创建
    results = []
    total_score = 0.0
    max_score_total = 0.0
    kp_scores: dict = {}  # kp_id → {correct, total}
    cache_hits = 0

    for ans in answers:
        qid = int(ans.get('question_id', 0))
        user_answer = str(ans.get('answer', '')).strip()
        question_entry = session_questions.get(qid, {})

        if not user_answer:
            results.append({
                'question_id': qid,
                'is_correct': False,
                'score': 0,
                'max_score': 10.0,
                'feedback': '未作答',
                'kp_name': question_entry.get('kp_name', ''),
            })
            max_score_total += 10.0
            continue

        try:
            question = Question.objects.get(id=qid)
        except Question.DoesNotExist:
            results.append({
                'question_id': qid,
                'is_correct': False,
                'score': 0,
                'max_score': 10.0,
                'feedback': '题目不存在',
                'kp_name': '',
            })
            max_score_total += 10.0
            continue

        max_q = question.get_max_score()
        kp_id = question.knowledge_point_id
        kp_name = question.knowledge_point.name if question.knowledge_point else ''

        # 优先读 Redis 预批改缓存
        cache_key = f'practice:grade:{session_id}:{qid}'
        cached = _cache.get(cache_key)
        if cached and '_error' not in cached:
            cache_hits += 1
            grade_result = cached
        else:
            # 缓存未命中 → 同步批改
            if ai is None:
                ai = AIService()
            try:
                grade_result = GradingEngine.grade(
                    ai=ai,
                    question_text=question.text or '',
                    user_answer=user_answer,
                    correct_answer=question.correct_answer or '',
                    q_type=question.q_type or 'objective',
                    max_score=max_q,
                    grading_points=question.grading_points,
                    options=question.options,
                    subjective_type=question.subjective_type or '主观题',
                    user=request.user,
                )
            except Exception as exc:
                logger.exception("Grading failed for question_id=%s", qid)
                grade_result = {
                    'score': 0, 'max_score': max_q, 'feedback': f'判分异常: {exc}',
                    'is_correct': False,
                }

        score = float(grade_result.get('score', 0))
        is_correct = grade_result.get('is_correct', score >= max_q * 0.6)
        total_score += score
        max_score_total += max_q

        # 写入记录 + Memorix 更新
        error_analysis = grade_result.get('error_analysis')
        error_type = ''
        error_metadata = {}
        if error_analysis and isinstance(error_analysis, dict):
            error_type = error_analysis.get('type', '')
            error_metadata = {
                'reasoning': error_analysis.get('reasoning', ''),
                'suggested_focus': error_analysis.get('suggested_focus', ''),
                'graded_at': _timezone.now().isoformat(),
            }
            MemorySystem.write_question_status_error(request.user, qid, error_type, error_metadata)

        MemorySystem.write_grading_record(
            user=request.user,
            question_id=qid,
            score=score,
            max_score=max_q,
            is_correct=is_correct,
            error_type=error_type,
            error_metadata=error_metadata,
            feedback=grade_result.get('feedback', ''),
            analysis=grade_result.get('analysis', ''),
        )

        # Memorix 状态更新
        normalized = score / max_q if max_q > 0 else 0
        memorix_rating = int(grade_result.get('memorix_rating', 2))
        memorix_rating = min(4, max(1, memorix_rating))
        from quizzes.ai_workflow import _apply_memorix_status
        _apply_memorix_status(
            user=request.user,
            question=question,
            normalized_score=normalized,
            memorix_rating=memorix_rating,
            review_time=_timezone.now(),
        )

        # 知识点统计
        kp_id = question.knowledge_point_id
        kp_name = question.knowledge_point.name if question.knowledge_point else ''
        if kp_id:
            if kp_id not in kp_scores:
                kp_scores[kp_id] = {'correct': 0, 'total': 0, 'kp_name': kp_name}
            kp_scores[kp_id]['total'] += 1
            if is_correct:
                kp_scores[kp_id]['correct'] += 1

        results.append({
            'question_id': qid,
            'is_correct': is_correct,
            'score': score,
            'max_score': max_q,
            'feedback': grade_result.get('feedback', ''),
            'error_analysis': error_analysis,
            'kp_name': kp_name,
        })

    correct_rate = round(total_score / max_score_total * 100, 1) if max_score_total > 0 else 0
    correct_count = sum(1 for r in results if r['is_correct'])

    # 知识点 breakdown
    kp_breakdown = [
        {
            'kp_id': kp_id,
            'kp_name': info['kp_name'],
            'correct_rate': round(info['correct'] / info['total'] * 100, 1) if info['total'] > 0 else 0,
        }
        for kp_id, info in kp_scores.items()
    ]

    # 生成摘要
    summary_parts = [f'正确率 {correct_rate}%（{correct_count}/{len(results)}）']
    weak_kps = [kp for kp in kp_breakdown if kp['correct_rate'] < 60]
    if weak_kps:
        names = '、'.join(kp['kp_name'] for kp in weak_kps[:3])
        summary_parts.append(f'薄弱知识点：{names}')
    else:
        summary_parts.append('全部知识点掌握良好')

    summary_text = '。'.join(summary_parts) + '。'

    # 清理 session + 预批改缓存
    _cache.delete(session_key)
    for qid in valid_question_ids:
        _cache.delete(f'practice:grade:{session_id}:{qid}')

    return Response({
        'total_score': round(total_score, 1),
        'max_score': round(max_score_total, 1),
        'correct_rate': correct_rate,
        'correct_count': correct_count,
        'total_questions': len(results),
        'cache_hits': cache_hits,
        'results': results,
        'kp_breakdown': kp_breakdown,
        'summary_text': summary_text,
    })


# ── Feedback API ─────────────────────────────────────────────────────────

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def feedback_view(request):
    """
    POST /api/ai/feedback/
    Body: { message_id: int, feedback: bool }
    静默记录用户对 AI 回复的反馈（赞/踩），同步更新 GEPA 轨迹 outcome。
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

    # 同步更新 GEPA 轨迹 outcome（同一 conversation 内最新反馈覆盖）
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
