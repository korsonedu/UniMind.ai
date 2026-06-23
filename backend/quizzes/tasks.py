import logging

from celery import shared_task

from quizzes.ai_workflow import run_exam_grading
from quizzes.services.ai_parse_service import run_parse_task

logger = logging.getLogger(__name__)


@shared_task(name='quizzes.run_exam_grading_task')
def run_exam_grading_task(user_id: int, exam_id: int, questions_data):
    run_exam_grading(user_id, exam_id, questions_data)


@shared_task(name='quizzes.run_ai_parse_task')
def run_ai_parse_task(raw_text: str, task_id: str):
    run_parse_task(raw_text, task_id)


@shared_task(name='quizzes.run_adversarial_pipeline_task')
def run_adversarial_pipeline_task(task_id: int, kp_ids: list, questions_per_kp: int, difficulty: str = "normal", types: list = None):
    from quizzes.models import ContentPipelineTask, KnowledgePoint
    from quizzes.services.adversarial_pipeline import _execute_pipeline

    task = ContentPipelineTask.objects.select_related('institution').get(id=task_id)
    kps = list(KnowledgePoint.objects.filter(id__in=kp_ids))
    try:
        _execute_pipeline(task, kps, questions_per_kp, difficulty=difficulty, types=types, institution=task.institution)
    except Exception as e:
        logger.exception("Adversarial pipeline task failed: task_id=%s", task_id)
        task.status = 'failed'
        task.error_message = str(e)[:500]
        from django.utils import timezone
        task.finished_at = timezone.now()
        task.save(update_fields=['status', 'error_message', 'finished_at', 'updated_at'])


@shared_task(name='quizzes.run_bulk_pipeline_task')
def run_bulk_pipeline_task(
    task_id: int,
    subject: str,
    total_target: int = 500,
    difficulty_dist: dict = None,
    type_dist: dict = None,
    kp_code: str = None,
    institution_id: int = None,
    institution_only: bool = False,
):
    from quizzes.models import ContentPipelineTask
    from quizzes.services.bulk_pipeline import _execute_bulk_pipeline
    from users.models import Institution

    task = ContentPipelineTask.objects.get(id=task_id)
    institution = Institution.objects.get(id=institution_id) if institution_id else None
    try:
        _execute_bulk_pipeline(
            task=task,
            subject=subject,
            total_target=total_target,
            difficulty_dist=difficulty_dist or {},
            type_dist=type_dist or {},
            kp_code=kp_code,
            institution=institution,
            institution_only=institution_only,
        )
    except Exception as e:
        logger.exception("Bulk pipeline task failed: task_id=%s", task_id)
        task.status = 'failed'
        task.error_message = str(e)[:500]
        from django.utils import timezone
        task.finished_at = timezone.now()
        task.save(update_fields=['status', 'error_message', 'finished_at', 'updated_at'])


@shared_task(name='quizzes.generate_personalized_pdf_mock_exam')
def generate_personalized_pdf_mock_exam(record_id: int):
    from quizzes.models import PersonalizedMockExam
    from quizzes.services.pdf_generator import generate_mock_exam_pdf

    record = PersonalizedMockExam.objects.get(id=record_id)
    try:
        record.status = 'processing'
        record.save(update_fields=['status'])
        generate_mock_exam_pdf(record)
        record.status = 'ready'
        record.save(update_fields=['status'])
    except Exception as e:
        record.status = 'failed'
        record.error_message = str(e)
        record.save(update_fields=['status', 'error_message'])


# ═══════════════════════════════════════════
# Memorix-Field: 边权重学习
# ═══════════════════════════════════════════

import logging
from datetime import timedelta
from collections import defaultdict
from django.utils import timezone

MEMORIX_DYNAMIC_EDGE_PREFIX = "memorix:edge"
MIN_PAIR_SAMPLES = 10          # 最少样本量
DELTA_THRESHOLD = 0.10         # Δ 显著性阈值
DYNAMIC_EDGE_TTL = 86400 * 7   # Redis TTL 7 天


@shared_task(name='quizzes.learn_edge_weights_from_reviews')
def learn_edge_weights_from_reviews():
    """
    从 ReviewLog 学习知识点间的转移概率，生成动态边写入 Redis。
    
    方法：对每个用户，按时间排序其复习记录。对于连续复习对 (A→B)，
    在 A 答对 (grade ≥ 3) 的前提下，计算：
      Δ = P(B_correct | A_good) - P(B_baseline)
    
    Δ >  +threshold → co_occur 边（A 帮助 B）
    Δ <  -threshold → confusion 边（A 干扰 B）
    
    显著边写入 Redis memorix:edge:{source}:{target}，TTL 7 天。
    连续 3 次稳定出现的边同步回 KnowledgeEdge 表。
    """
    from quizzes.models import ReviewLog, KnowledgeEdge

    now = timezone.now()
    window_start = now - timedelta(days=30)

    logs = list(
        ReviewLog.objects
        .filter(review_time__gte=window_start)
        .select_related('knowledge_point')
        .order_by('user_id', 'review_time')
        .only('user_id', 'knowledge_point_id', 'grade', 'review_time')
    )

    # 全局基线统计
    kp_total = defaultdict(int)
    kp_correct = defaultdict(int)
    # 转移统计：{source_kp: {target_kp: [correct, total]}}
    transitions = defaultdict(lambda: defaultdict(lambda: [0, 0]))

    prev_log = None
    for log in logs:
        kp_id = log.knowledge_point_id
        is_correct = log.grade >= 3

        kp_total[kp_id] += 1
        if is_correct:
            kp_correct[kp_id] += 1

        if prev_log is not None and prev_log.user_id == log.user_id:
            prev_kp = prev_log.knowledge_point_id
            prev_good = prev_log.grade >= 3
            if prev_kp != kp_id and prev_good:
                t = transitions[prev_kp][kp_id]
                t[1] += 1
                if is_correct:
                    t[0] += 1

        prev_log = log

    # 计算 Δ 并筛选
    dynamic_edges = []
    for source_kp, targets in transitions.items():
        for target_kp, (correct, total) in targets.items():
            if total < MIN_PAIR_SAMPLES:
                continue
            p_given = correct / total
            target_baseline = kp_correct[target_kp] / max(kp_total[target_kp], 1)
            delta = p_given - target_baseline

            if delta > DELTA_THRESHOLD:
                weight = min(1.0, round(delta * 2.0, 3))
                dynamic_edges.append((source_kp, target_kp, 'co_occur', weight))
            elif delta < -DELTA_THRESHOLD:
                weight = min(1.0, round(abs(delta) * 1.5, 3))
                dynamic_edges.append((source_kp, target_kp, 'confusion', weight))

    if not dynamic_edges:
        logger.info("learn_edge_weights: no significant edges (scanned %d logs)", len(logs))
        return {"edges_created": 0}

    # 写入 Redis
    try:
        from django_redis import get_redis_connection
        redis_conn = get_redis_connection("default")
    except Exception:
        logger.warning("learn_edge_weights: Redis unavailable")
        return {"edges_created": 0}

    pipe = redis_conn.pipeline()
    for source_id, target_id, edge_type, weight in dynamic_edges:
        key = f"{MEMORIX_DYNAMIC_EDGE_PREFIX}:{source_id}:{target_id}"
        pipe.hset(key, mapping={
            'source_id': str(source_id),
            'target_id': str(target_id),
            'type': edge_type,
            'weight': str(weight),
            'updated': now.isoformat(),
        })
        pipe.expire(key, DYNAMIC_EDGE_TTL)
    pipe.execute()

    # 稳定边同步回 DB
    stable_count = 0
    for source_id, target_id, edge_type, weight in dynamic_edges:
        edge_key = f"{MEMORIX_DYNAMIC_EDGE_PREFIX}:{source_id}:{target_id}"
        run_count_key = f"memorix:edge_rc:{source_id}:{target_id}"
        new_run_count = redis_conn.incr(run_count_key)
        redis_conn.expire(run_count_key, DYNAMIC_EDGE_TTL)
        if new_run_count >= 3:
            KnowledgeEdge.objects.update_or_create(
                source_id=source_id,
                target_id=target_id,
                edge_type=edge_type,
                defaults={
                    'weight': weight,
                    'source_type': 'data',
                    'is_active': True,
                },
            )
            stable_count += 1

    # 清除邻接表缓存（强制下次调度重建）
    from quizzes.services.memorix_scheduler import invalidate_adjacency_cache
    invalidate_adjacency_cache()

    logger.info("learn_edge_weights: %d edges → Redis, %d stable → DB",
                len(dynamic_edges), stable_count)
    return {"edges_created": len(dynamic_edges), "stable_synced": stable_count}


# ═══════════════════════════════════════════
# Memorix-Field: 每日扩散
# ═══════════════════════════════════════════

@shared_task(name='quizzes.diffuse_memorix_field_daily')
def diffuse_memorix_field_daily():
    """
    对所有活跃用户的 u 向量执行一次图扩散步。

    u ← u + (-α·u + βe·L·u) × dt

    扫描 Redis 中所有 memorix:field:u:* 键，逐个用户扩散。
    应在边权重学习 (learn-memorix-edge-weights-daily) 之后执行，
    确保新学到的动态边被纳入扩散。
    """
    from quizzes.memorix.field import diffuse_all_active_users
    return diffuse_all_active_users()


# ═══════════════════════════════════════════
# Memorix-Field: 参数自进化
# ═══════════════════════════════════════════

# 自进化参数列表（按轮询顺序）
_FIELD_TUNABLE_PARAMS = ['decay', 'beta_e', 'beta_a', 'eta']
_FIELD_PERTURBATION_MULTIPLIERS = [1.1, 0.9]  # +10%, -10%
_BRIER_MIN_SAMPLES = 50          # Brier 最少样本量
_BRIER_WINDOW_DAYS = 7           # Brier 评估窗口


@shared_task(name='quizzes.evaluate_field_brier_daily')
def evaluate_field_brier_daily():
    """
    每日计算各机构的 Field Brier score（7 天窗口 ReviewLog）。

    Brier = mean((predicted_R - actual_binary)²)
    predicted_R 取 ReviewLog.predicted_retrievability，
    actual 取 grade≥3 → 1 else 0。

    结果写入 MemorixFieldConfig.brier_score，供每周扰动对比。
    """
    from django.db.models import Avg, Count, Q
    from quizzes.models import ReviewLog, MemorixFieldConfig

    now = timezone.now()
    window_start = now - timedelta(days=_BRIER_WINDOW_DAYS)

    # 按机构聚合
    institution_stats = (
        ReviewLog.objects
        .filter(review_time__gte=window_start)
        .values('user__institution_id')
        .annotate(
            review_count=Count('id'),
        )
        .filter(review_count__gte=_BRIER_MIN_SAMPLES)
    )

    updated = 0
    for row in institution_stats:
        inst_id = row['user__institution_id']
        if not inst_id:
            continue

        # 逐条算 Brier（SQL 不直接支持幂运算，走 Python）
        logs = ReviewLog.objects.filter(
            user__institution_id=inst_id,
            review_time__gte=window_start,
        ).only('predicted_retrievability', 'grade')

        total = 0.0
        count = 0
        for log in logs:
            pred = log.predicted_retrievability or 0.5
            actual = 1.0 if (log.grade or 0) >= 3 else 0.0
            total += (pred - actual) ** 2
            count += 1

        if count < _BRIER_MIN_SAMPLES:
            continue

        brier = round(total / count, 6)

        MemorixFieldConfig.objects.update_or_create(
            institution_id=inst_id,
            defaults={
                'brier_score': brier,
                'reviews_evaluated': count,
                'last_evaluated_at': now,
            },
        )
        updated += 1

    logger.info("Field Brier evaluation: %d institutions updated", updated)
    return {"institutions_evaluated": updated}


@shared_task(name='quizzes.perturb_field_params_weekly')
def perturb_field_params_weekly():
    """
    每周参数扰动：对开启了自进化的机构，尝试调整一个参数 ±10%。

    策略：
      1. 若机构有进行中的扰动 → 对比 Brier，接受改善/回退劣化
      2. 选择下一个 (参数, 方向) 组合，记录基线 Brier，应用扰动

    8 周完整周期（4 参数 × 2 方向），收敛后扰动幅度减半。
    """
    from django.conf import settings
    from quizzes.models import MemorixFieldConfig
    from quizzes.memorix.field import set_field_params, SAFE_BOUNDS

    auto_tune = getattr(settings, 'MEMORIX_FIELD_AUTO_TUNE_ENABLED', False)
    if not auto_tune:
        return {"status": "auto_tune_disabled"}

    now = timezone.now()
    configs = list(MemorixFieldConfig.objects.filter(institution__isnull=False))

    accepted_count = 0
    reverted_count = 0
    perturbed_count = 0

    for cfg in configs:
        history = cfg.perturbation_history or []

        # ── 步骤 1：评估进行中的扰动 ──
        if cfg.perturbation_param and cfg.last_perturbed_at:
            # 需要至少 6 天数据积累
            days_since = (now - cfg.last_perturbed_at).days
            if days_since < 6:
                continue

            brier_now = cfg.brier_score
            brier_before = cfg.perturbation_brier_before

            if brier_now is not None and brier_before is not None:
                if brier_now < brier_before:
                    # 改善 → 保留
                    history.append({
                        'param': cfg.perturbation_param,
                        'old': round(cfg.perturbation_original_value, 6),
                        'new': round(
                            cfg.perturbation_original_value * cfg.perturbation_multiplier, 6
                        ),
                        'brier_before': brier_before,
                        'brier_after': brier_now,
                        'accepted': True,
                        'at': now.isoformat(),
                    })
                    accepted_count += 1
                else:
                    # 劣化 → 回退
                    set_field_params(cfg.institution_id, {
                        cfg.perturbation_param: cfg.perturbation_original_value,
                    })
                    history.append({
                        'param': cfg.perturbation_param,
                        'old': round(
                            cfg.perturbation_original_value * cfg.perturbation_multiplier, 6
                        ),
                        'new': round(cfg.perturbation_original_value, 6),
                        'brier_before': brier_before,
                        'brier_after': brier_now,
                        'accepted': False,
                        'at': now.isoformat(),
                    })
                    reverted_count += 1

            # 清除扰动状态
            cfg.perturbation_param = None
            cfg.perturbation_multiplier = None
            cfg.perturbation_brier_before = None
            cfg.perturbation_original_value = None
            cfg.perturbation_history = history
            cfg.save(update_fields=[
                'perturbation_param', 'perturbation_multiplier',
                'perturbation_brier_before', 'perturbation_original_value',
                'perturbation_history',
            ])
            # 清缓存让下次读取生效
            from quizzes.memorix.field import invalidate_param_cache
            invalidate_param_cache(cfg.institution_id)

        # ── 步骤 2：发起新扰动 ──
        if not cfg.perturbation_param:
            # 选择下一个 (参数, 方向)
            cycle_idx = len(history) % (len(_FIELD_TUNABLE_PARAMS) * len(_FIELD_PERTURBATION_MULTIPLIERS))
            param_idx = cycle_idx // len(_FIELD_PERTURBATION_MULTIPLIERS)
            dir_idx = cycle_idx % len(_FIELD_PERTURBATION_MULTIPLIERS)

            param = _FIELD_TUNABLE_PARAMS[param_idx]
            multiplier = _FIELD_PERTURBATION_MULTIPLIERS[dir_idx]

            # 当前参数值
            current = getattr(cfg, param)
            new_value = round(current * multiplier, 6)

            # 安全边界检查
            lo, hi = SAFE_BOUNDS.get(param, (0, float('inf')))
            if new_value < lo or new_value > hi:
                # 跳过此方向，记录
                history.append({
                    'param': param,
                    'skipped': True,
                    'reason': f'{new_value} out of bounds [{lo}, {hi}]',
                    'at': now.isoformat(),
                })
                cfg.perturbation_history = history
                cfg.save(update_fields=['perturbation_history'])
                continue

            # 发起扰动
            set_field_params(cfg.institution_id, {param: new_value})

            cfg.perturbation_param = param
            cfg.perturbation_multiplier = multiplier
            cfg.perturbation_brier_before = cfg.brier_score
            cfg.perturbation_original_value = current
            cfg.last_perturbed_at = now
            cfg.save(update_fields=[
                'perturbation_param', 'perturbation_multiplier',
                'perturbation_brier_before', 'perturbation_original_value',
                'last_perturbed_at',
            ])

            perturbed_count += 1

    logger.info(
        "Field param perturbation: %d accepted, %d reverted, %d new perturbations",
        accepted_count, reverted_count, perturbed_count,
    )
    return {
        "accepted": accepted_count,
        "reverted": reverted_count,
        "perturbed": perturbed_count,
    }


@shared_task(
    soft_time_limit=900,
    time_limit=960,
    acks_late=True,
)
def estimate_irt_params_task():
    """每日 IRT 3PL 参数估计：对满足最小答题数的题目估计 a/b/c，对学生估计 θ。"""
    from quizzes.services.irt_estimator import IRTEstimator

    result = IRTEstimator.run_batch_estimation()
    logger.info("estimate_irt_params_task: %s", result)
    return result
