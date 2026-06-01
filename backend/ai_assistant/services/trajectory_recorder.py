"""
Trajectory recorder: capture agent conversations for GEPA self-evolution.

Part of xiaoyu self-evolution optimization.
Records conversation trajectories for future GEPA (Genetic-Pareto) optimization.
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
    prompt_variant: str = 'baseline'
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

    Returns:
        创建的 AITrajectory 实例，失败返回 None
    """
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
        return trajectory
    
    except Exception as e:
        logger.exception("Failed to record trajectory: %s", e)
        return None


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
