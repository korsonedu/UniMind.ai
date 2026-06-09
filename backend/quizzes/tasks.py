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
