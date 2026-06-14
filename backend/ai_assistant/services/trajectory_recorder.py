"""
Trajectory recorder: capture agent conversations for GEPA self-evolution.

Part of xiaoyu self-evolution optimization.
Records conversation trajectories for future GEPA (Genetic-Pareto) optimization.
Uses Celery for async recording to avoid blocking the main thread.
"""

import logging
from typing import Dict, List, Optional
from django.utils import timezone
from ..models import AITrajectory

logger = logging.getLogger(__name__)


def record_trajectory(
    user_id: int,
    bot_id: int,
    conversation_id: str,
    messages: List[Dict],
    tool_calls: List[Dict],
    tool_outputs: List[Dict],
    prompt_variant: str = 'baseline',
    async_mode: bool = True
) -> Optional[AITrajectory]:
    """
    记录一条对话轨迹。

    Args:
        user_id: 用户 ID
        bot_id: Bot ID
        conversation_id: 会话 ID
        messages: 对话消息列表
        tool_calls: 工具调用序列
        tool_outputs: 工具返回结果
        prompt_variant: 使用的 prompt 变体标识
        async_mode: 是否异步记录（默认 True）

    Returns:
        创建的 AITrajectory 实例（同步模式）或 None（异步模式）
    """
    if async_mode:
        from ..tasks import record_trajectory_async
        record_trajectory_async.delay(
            user_id=user_id,
            bot_id=bot_id,
            conversation_id=str(conversation_id),
            messages=messages,
            tool_calls=tool_calls,
            tool_outputs=tool_outputs,
            prompt_variant=prompt_variant,
        )
        logger.info("Queued trajectory recording for user %d, conversation %s", user_id, conversation_id)
        return None

    # 同步记录
    try:
        trajectory = AITrajectory.objects.create(
            user_id=user_id,
            bot_id=bot_id,
            conversation_id=conversation_id,
            messages=messages,
            tool_calls=tool_calls,
            tool_outputs=tool_outputs,
            prompt_variant=prompt_variant,
        )

        logger.info(
            "Recorded trajectory %d for user %d, conversation %s",
            trajectory.id, user_id, conversation_id
        )
        # 同步模式下也做自动评估
        _auto_evaluate_trajectory(trajectory)
        return trajectory

    except Exception as e:
        logger.exception("Failed to record trajectory: %s", e)
        return None


def _auto_evaluate_trajectory(trajectory: AITrajectory) -> None:
    """
    启发式自动评估轨迹 outcome。

    规则（优先级从高到低）：
    1. AI 返回了明确的错误消息 → failure
    2. 所有工具调用都成功 / 无工具调用 → success
    3. 部分工具失败 → partial
    4. 无法判断 → unknown（等待用户反馈覆盖）
    """
    import json as _json

    tool_outputs = trajectory.tool_outputs or []
    messages = trajectory.messages or []
    error_count = 0

    # 统计工具错误
    for output in tool_outputs:
        try:
            parsed = _json.loads(output) if isinstance(output, str) else output
            if isinstance(parsed, dict) and parsed.get('error'):
                error_count += 1
        except (_json.JSONDecodeError, TypeError):
            pass

    tool_error_rate = error_count / len(tool_outputs) if tool_outputs else 0.0

    # 检查 AI 是否返回了错误消息
    ai_messages = [m for m in messages if m.get('role') == 'assistant']
    last_ai = ai_messages[-1].get('content', '') if ai_messages else ''
    error_patterns = (
        'AI 服务暂时不可用', 'AI 暂时无法响应', 'LLM_API_KEY',
        '服务暂时不可用', '连接中断', '请稍后再试',
        '暂时无法响应', '请稍候重试',
    )
    is_error_response = any(p in last_ai for p in error_patterns)

    if is_error_response:
        outcome = 'failure'
        confidence = 0.95
    elif not tool_outputs:
        # 无工具调用 — 纯文本回复，默认成功
        outcome = 'success'
        confidence = 0.6
    elif tool_error_rate == 0:
        outcome = 'success'
        confidence = 0.75  # 工具全成功但可能答案质量差
    elif tool_error_rate >= 0.5:
        outcome = 'failure'
        confidence = 0.7
    else:
        outcome = 'partial'
        confidence = 0.65

    try:
        trajectory.outcome = outcome
        trajectory.outcome_metrics = {
            **trajectory.outcome_metrics,
            'auto_evaluated': True,
            'auto_confidence': confidence,
            'tool_error_rate': tool_error_rate,
        }
        trajectory.evaluated_at = timezone.now()
        trajectory.save(update_fields=['outcome', 'outcome_metrics', 'evaluated_at'])
        logger.info("Auto-evaluated trajectory %d: %s (confidence=%.2f)", trajectory.id, outcome, confidence)
    except Exception:
        logger.warning("Auto-evaluation failed for trajectory %d", trajectory.id, exc_info=True)


def evaluate_trajectory(
    trajectory_id: int,
    outcome: str,
    outcome_metrics: Dict
) -> bool:
    """
    评估一条轨迹的结果。

    Args:
        trajectory_id: 轨迹 ID
        outcome: 结果类型 ('success', 'partial', 'failure')
        outcome_metrics: 结果指标

    Returns:
        是否成功更新
    """
    try:
        trajectory = AITrajectory.objects.get(id=trajectory_id)
        trajectory.outcome = outcome
        trajectory.outcome_metrics = outcome_metrics
        trajectory.evaluated_at = timezone.now()
        trajectory.save(update_fields=['outcome', 'outcome_metrics', 'evaluated_at'])
        
        logger.info("Evaluated trajectory %d: %s", trajectory_id, outcome)
        return True
    
    except AITrajectory.DoesNotExist:
        logger.warning("Trajectory %d not found", trajectory_id)
        return False
    except Exception as e:
        logger.exception("Failed to evaluate trajectory: %s", e)
        return False


def get_trajectory_stats(user_id: int, days: int = 30) -> Dict:
    """
    获取用户的轨迹统计。

    Args:
        user_id: 用户 ID
        days: 统计天数，默认 30

    Returns:
        {
            "total": 45,
            "success_rate": 0.78,
            "avg_tool_calls": 3.2,
            "prompt_variants": {"baseline": 40, "v1": 5}
        }
    """
    from django.utils import timezone
    from django.db.models import Count
    from datetime import timedelta
    
    start_date = timezone.now() - timedelta(days=days)
    
    trajectories = AITrajectory.objects.filter(
        user_id=user_id,
        created_at__gte=start_date
    )
    
    total = trajectories.count()
    if total == 0:
        return {"total": 0, "success_rate": 0, "avg_tool_calls": 0, "prompt_variants": {}}
    
    success_count = trajectories.filter(outcome='success').count()
    
    # 计算平均工具调用数（需要从 JSON 字段计算）
    total_tool_calls = sum(len(t.tool_calls) for t in trajectories.only('tool_calls'))
    
    # 统计 prompt 变体分布
    variant_counts = trajectories.values_list('prompt_variant').annotate(
        count=Count('id')
    )
    variants = {v[0]: v[1] for v in variant_counts}
    
    return {
        "total": total,
        "success_rate": round(success_count / total, 2),
        "avg_tool_calls": round(total_tool_calls / total, 1),
        "prompt_variants": variants
    }


def get_successful_trajectories(
    user_id: Optional[int] = None,
    bot_type: Optional[str] = None,
    min_mastery_delta: float = 0.2,
    limit: int = 100
) -> List[AITrajectory]:
    """
    获取成功的轨迹用于 prompt 优化。

    Args:
        user_id: 可选，限定用户
        bot_type: 可选，限定 bot 类型
        min_mastery_delta: 最小掌握率提升阈值
        limit: 返回数量

    Returns:
        成功的轨迹列表
    """
    qs = AITrajectory.objects.filter(
        outcome='success',
        outcome_metrics__knowledge_mastery_delta__gte=min_mastery_delta
    )
    
    if user_id:
        qs = qs.filter(user_id=user_id)
    if bot_type:
        qs = qs.filter(bot__bot_type=bot_type)
    
    return list(qs.order_by('-created_at')[:limit])
