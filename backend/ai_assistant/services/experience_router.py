"""
Experience Router — 经验的验证、去重、生命周期管理。

Phase 1 职责：
- 验证 LLM 提取的路由决策是否合法
- 去重：避免重复提取相似规律
- 管理经验生命周期：衰减、休眠、归档

Phase 2 扩展：
- 反事实验证触发
- 置信度升级/降级
"""

import logging
from typing import Optional
from django.utils import timezone
from datetime import timedelta

logger = logging.getLogger(__name__)


def validate_routing(experience) -> bool:
    """
    验证一条经验的路由决策是否合法。

    Returns:
        True if routing is valid
    """
    from ..models import Experience

    # 1. 维度必须合法
    valid_dims = dict(Experience.DIMENSION_CHOICES).keys()
    if experience.dimension not in valid_dims:
        logger.warning("experience_router: invalid dimension '%s' for exp %s", experience.dimension, experience.id)
        return False

    # 2. 作用范围必须合法
    valid_scopes = dict(Experience.SCOPE_CHOICES).keys()
    if experience.scope_type not in valid_scopes:
        logger.warning("experience_router: invalid scope_type '%s' for exp %s", experience.scope_type, experience.id)
        return False

    # 3. scope_type 和 scope_value 一致性
    if experience.scope_type == 'student':
        if 'student_id' not in (experience.scope_value or {}):
            logger.warning("experience_router: student scope missing student_id for exp %s", experience.id)
            # 尝试从 user 字段回填
            if experience.user_id:
                experience.scope_value = {'student_id': experience.user_id}
                experience.save(update_fields=['scope_value'])
            else:
                return False

    if experience.scope_type == 'kp_chain':
        if 'kp_id' not in (experience.scope_value or {}):
            logger.warning("experience_router: kp_chain scope missing kp_id for exp %s", experience.id)
            return False

    # 4. title 不能为空
    if not experience.title or len(experience.title.strip()) < 3:
        logger.warning("experience_router: title too short for exp %s", experience.id)
        return False

    return True


def find_duplicates(experience, threshold: float = 0.85) -> list:
    """
    查找与给定经验可能重复的已有经验。

    当前使用 title 简单匹配，后续可升级为语义相似度匹配。

    Args:
        experience: 待检查的经验
        threshold: 相似度阈值（当前不使用，预留）

    Returns:
        list[Experience]: 可能重复的经验列表
    """
    from ..models import Experience

    title_lower = experience.title.lower().strip()

    # 同维度 + 同 scope_type 的活跃经验
    candidates = Experience.objects.filter(
        dimension=experience.dimension,
        scope_type=experience.scope_type,
        status='active',
    ).exclude(id=experience.id)

    duplicates = []
    for candidate in candidates:
        candidate_title = candidate.title.lower().strip()
        # 简单匹配：共享 ≥ 5 个连续字符即视为可能重复
        if _title_similarity(title_lower, candidate_title) > 0.7:
            duplicates.append(candidate)

    return duplicates


def _title_similarity(a: str, b: str) -> float:
    """简单的标题相似度：最长公共子串占比。"""
    if not a or not b:
        return 0.0
    # 找最长公共子串
    m, n = len(a), len(b)
    max_len = 0
    for i in range(m):
        for j in range(n):
            k = 0
            while i + k < m and j + k < n and a[i + k] == b[j + k]:
                k += 1
            max_len = max(max_len, k)
    return max_len / max(len(a), len(b))


def merge_experiences(target, source) -> None:
    """
    将 source 经验合并到 target 经验。
    - 提升 target 的权重
    - 标记 source 为 retired
    """
    target.weight += 1.0
    target.verify_count += 1
    target.save(update_fields=['weight', 'verify_count'])

    source.status = 'retired'
    source.save(update_fields=['status'])

    logger.info(
        "experience_router: merged exp %d into %d (both titled '%s')",
        source.id, target.id, target.title,
    )


def apply_decay() -> int:
    """
    对所有经验的权重做定期衰减。

    规则：
    - 30 天内未触发：权重衰减 50%
    - 60 天内未触发：标记 dormant
    - 90 天内未触发：标记 archived

    Returns:
        受影响的经验数量
    """
    from ..models import Experience

    now = timezone.now()
    affected = 0

    # 30 天衰减
    cutoff_30 = now - timedelta(days=30)
    stale = Experience.objects.filter(
        status='active',
        last_triggered_at__lt=cutoff_30,
        last_triggered_at__isnull=False,
    )
    for exp in stale:
        exp.weight *= 0.5
        exp.save(update_fields=['weight'])
        affected += 1
    logger.info("experience_router: decayed weight for %d experiences (30d)", stale.count())

    # 60 天休眠
    cutoff_60 = now - timedelta(days=60)
    dormant_candidates = Experience.objects.filter(
        status='active',
        last_triggered_at__lt=cutoff_60,
    )
    count = dormant_candidates.update(status='dormant')
    affected += count
    logger.info("experience_router: marked %d experiences as dormant (60d)", count)

    # 90 天归档
    cutoff_90 = now - timedelta(days=90)
    archived_candidates = Experience.objects.filter(
        status__in=['active', 'dormant'],
        last_triggered_at__lt=cutoff_90,
    )
    count = archived_candidates.update(status='archived')
    affected += count
    logger.info("experience_router: marked %d experiences as archived (90d)", count)

    return affected


def retire_experience(experience, reason: str = '') -> None:
    """
    淘汰一条经验（验证失败等）。
    不删除，保留记录用于分析。
    """
    experience.status = 'retired'
    experience.verify_fail_count += 1
    experience.save(update_fields=['status', 'verify_fail_count'])
    logger.info(
        "experience_router: retired exp %d '%s' (reason: %s)",
        experience.id, experience.title, reason or 'unspecified',
    )
