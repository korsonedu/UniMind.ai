"""
批量出题管线 (Bulk Question Generation Pipeline)

与 ARC 对抗性管线的区别：
- ARC：Author → Reviewer → AuthorRevise → Classifier，追求单题极致质量
- Bulk：Author → Classifier，追求速度和数量，通过率 ≥ 70% 即可

用途：快速扩充学科题库，从每科 20 道灌到 500+ 道。

用法：
  python manage.py bulk_generate --subject=高中数学 --target=500
  python manage.py bulk_generate --subject=CFA --target=300 --difficulty=normal
  python manage.py bulk_generate --subject=金融431 --target=200 --kp-code=FIN431.01

难度分布默认：easy:normal:hard = 1:2:1
题型分布默认：objective:subjective = 4:6
"""

import json
import logging
from typing import Any, Dict, List, Optional, Tuple
from collections import defaultdict
from dataclasses import dataclass, field

from django.db.models import Count, Q
from django.utils import timezone

from ai_engine.config import get_model_for_task
from quizzes.models import ContentPipelineTask, KnowledgePoint, Question
from quizzes.services.adversarial_pipeline import (
    _author_generate,
    _classifier_tag,
    _difficulty_label,
    _get_subject_knowledge_points,
    _update_task,
)

logger = logging.getLogger(__name__)

# ── 默认分布 ──
DEFAULT_DIFFICULTY_DIST = {"easy": 0.25, "normal": 0.50, "hard": 0.25}
DEFAULT_TYPE_DIST = {"objective": 0.40, "subjective": 0.60}

# ── Classifier 通过条件 ──
# 批量模式下，答案必须正确；难度偏差不超过 1 级即可通过
DIFFICULTY_LEVELS_ORDERED = ['entry', 'easy', 'normal', 'hard', 'extreme']

def _difficulty_within_tolerance(target: str, detected: str, tolerance: int = 1) -> bool:
    """检查检测到的难度是否在目标难度的 tolerance 级以内。"""
    try:
        ti = DIFFICULTY_LEVELS_ORDERED.index(target)
        di = DIFFICULTY_LEVELS_ORDERED.index(detected)
        return abs(ti - di) <= tolerance
    except ValueError:
        return target == detected


@dataclass
class BulkGenerationResult:
    """单次批量生成的统计结果"""
    total_generated: int = 0      # Author 生成的候选数
    total_audited: int = 0        # Classifier 审计通过数
    total_saved: int = 0          # 实际入库数
    answer_errors: int = 0        # 答案错误
    difficulty_mismatches: int = 0  # 难度不匹配
    skipped_duplicates: int = 0   # 去重跳过
    per_kp: Dict[str, int] = field(default_factory=dict)


def run_bulk_pipeline(
    subject: str,
    total_target: int = 500,
    difficulty_dist: Optional[Dict[str, float]] = None,
    type_dist: Optional[Dict[str, float]] = None,
    kp_code: Optional[str] = None,
    institution=None,
    created_by=None,
    institution_only: bool = False,
) -> int:
    """启动批量出题管线，返回 pipeline_task_id。"""
    difficulty_dist = difficulty_dist or DEFAULT_DIFFICULTY_DIST
    type_dist = type_dist or DEFAULT_TYPE_DIST

    task = ContentPipelineTask.objects.create(
        task_type="ai_generate",
        status="running",
        title=f"批量出题：{subject}",
        description=f"目标 {total_target} 道题，难度分布 {difficulty_dist}，题型分布 {type_dist}",
        payload={
            "subject": subject,
            "total_target": total_target,
            "difficulty_dist": difficulty_dist,
            "type_dist": type_dist,
            "kp_code": kp_code,
            "institution_only": institution_only,
            "bulk_mode": True,
            "stages": [],
        },
        progress=0,
        created_by=created_by,
        institution=institution,
        started_at=timezone.now(),
    )

    # Celery 异步执行
    from quizzes.tasks import run_bulk_pipeline_task
    run_bulk_pipeline_task.delay(
        task_id=task.id,
        subject=subject,
        total_target=total_target,
        difficulty_dist=difficulty_dist,
        type_dist=type_dist,
        kp_code=kp_code,
        institution_id=institution.id if institution else None,
        institution_only=institution_only,
    )
    return task.id


def _execute_bulk_pipeline(
    task: ContentPipelineTask,
    subject: str,
    total_target: int,
    difficulty_dist: Dict[str, float],
    type_dist: Dict[str, float],
    kp_code: Optional[str] = None,
    institution=None,
    institution_only: bool = False,
):
    """执行批量出题管线。"""
    stage_log: List[Dict] = []

    # ── Phase 1: 选择目标知识点 ──
    _update_task(task, 2, f"正在为「{subject}」选择目标知识点…", stage_log, "select_kps")
    kps = _select_target_kps(subject, total_target, kp_code=kp_code, institution=institution, institution_only=institution_only)
    if not kps:
        task.status = "failed"
        task.error_message = f"学科「{subject}」下没有可用知识点"
        task.finished_at = timezone.now()
        task.save()
        return

    stage_log.append({
        "stage": "kps_selected",
        "count": len(kps),
        "kps": [{"code": k.code, "name": k.name, "question_count": k._question_count} for k in kps],
        "timestamp": str(timezone.now()),
    })
    _update_task(task, 5, f"已选择 {len(kps)} 个知识点", stage_log, "kps_selected")

    # ── Phase 2: 分配配额 ──
    quota_map = _distribute_quotas(kps, total_target, difficulty_dist, type_dist)
    _update_task(task, 8, f"已分配配额，开始批量生成…", stage_log, "quotas_assigned")

    # ── Phase 3: 逐 KP 生成 + 审计 + 入库 ──
    result = BulkGenerationResult()
    total_kps = len(quota_map)
    processed = 0

    for kp, quotas in quota_map.items():
        processed += 1
        progress = 8 + int(87 * processed / total_kps)
        _update_task(task, progress, f"正在处理 {kp.name}（{processed}/{total_kps}）…", stage_log, "generating")

        for difficulty, count in quotas.items():
            if count <= 0:
                continue

            # 确定题型列表
            types = _resolve_types(type_dist, count)

            # Stage A: Author 生成
            drafts = _author_generate([kp], q_per_kp=count, difficulty=difficulty, types=types)
            result.total_generated += len(drafts)

            if not drafts:
                continue

            # Stage B: Classifier 批量审计
            subject_kps = _get_subject_knowledge_points([kp], institution=institution)
            passed = []
            for draft in drafts:
                classification = _classifier_tag(draft, subject_kps, target_difficulty=difficulty)
                draft["detected_difficulty"] = classification.get("detected_difficulty", difficulty)
                draft["difficulty_match"] = classification.get("difficulty_match", True)
                draft["difficulty_mismatch_reason"] = classification.get("difficulty_mismatch_reason", "")
                draft["knowledge_tags"] = classification.get("knowledge_tags", [])
                draft["question_type"] = classification.get("question_type", draft.get("q_type", "objective"))
                draft["subjective_type"] = classification.get("subjective_type", draft.get("subjective_type"))
                draft["answer_correct"] = classification.get("answer_correct", True)
                draft["answer_accuracy_note"] = classification.get("answer_accuracy_note", "")
                draft["bloom_level"] = classification.get("bloom_level", "understand")
                draft["difficulty_level"] = difficulty

                if not draft.get("answer_correct", True):
                    result.answer_errors += 1
                    continue
                # 批量模式：难度不匹配仅记录警告，不阻塞入库
                # difficulty_level 已锁定为 Author 的目标难度
                if not _difficulty_within_tolerance(difficulty, draft.get("detected_difficulty", difficulty)):
                    result.difficulty_mismatches += 1
                    logger.debug(
                        "Bulk classifier difficulty mismatch: kp=%s target=%s detected=%s",
                        draft.get("kp_code", "?"), difficulty,
                        draft.get("detected_difficulty", "?"),
                    )
                passed.append(draft)

            result.total_audited += len(passed)

            # Stage C: 入库
            saved = _save_questions(passed, institution=institution)
            result.total_saved += saved
            result.total_audited -= (len(passed) - saved)  # 去重跳过的不计入通过
            result.skipped_duplicates += (len(passed) - saved)

            result.per_kp[kp.code] = result.per_kp.get(kp.code, 0) + saved

    # ── Phase 4: 写入结果 ──
    stage_log.append({
        "stage": "bulk_done",
        "total_generated": result.total_generated,
        "total_audited": result.total_audited,
        "total_saved": result.total_saved,
        "answer_errors": result.answer_errors,
        "difficulty_mismatches": result.difficulty_mismatches,
        "skipped_duplicates": result.skipped_duplicates,
        "per_kp": result.per_kp,
        "timestamp": str(timezone.now()),
    })

    task.result = {
        "questions_saved": result.total_saved,
        "stages": stage_log,
        "summary": {
            "subject": subject,
            "target": total_target,
            "generated": result.total_generated,
            "saved": result.total_saved,
            "pass_rate": round(result.total_saved / max(result.total_generated, 1), 3),
            "answer_errors": result.answer_errors,
            "difficulty_mismatches": result.difficulty_mismatches,
            "skipped_duplicates": result.skipped_duplicates,
        },
    }
    task.status = "completed"
    task.progress = 100
    task.finished_at = timezone.now()
    task.save()

    logger.info(
        "Bulk pipeline done: subject=%s target=%d generated=%d saved=%d pass_rate=%.1f%%",
        subject, total_target, result.total_generated, result.total_saved,
        100 * result.total_saved / max(result.total_generated, 1),
    )


# ── KP 选择 ──────────────────────────────────────────────────────

def _select_target_kps(
    subject: str,
    total_target: int,
    kp_code: Optional[str] = None,
    institution=None,
    institution_only: bool = False,
) -> List[KnowledgePoint]:
    """选择目标知识点：优先选择已有题目最少的知识点。

    Args:
        subject: 学科名称
        total_target: 总目标题数（选择足够多的 KP 来承载）
        kp_code: 可选，限定单个知识点
        institution: 机构过滤
        institution_only: 仅限机构专属 KP（不含全局），默认 False
    """
    if kp_code:
        # 单 KP 模式：仅限指定编码
        qs = KnowledgePoint.objects.filter(subject=subject, code=kp_code)
        if institution:
            if institution_only:
                qs = qs.filter(institution=institution)
            else:
                qs = qs.filter(Q(institution=institution) | Q(institution__isnull=True))
        kps = list(qs)
        for k in kps:
            k._question_count = Question.objects.filter(knowledge_point=k).count()
        return kps

    # 多 KP 模式
    qs = KnowledgePoint.objects.filter(subject=subject, level='kp')
    if institution:
        if institution_only:
            qs = qs.filter(institution=institution)
        else:
            qs = qs.filter(Q(institution=institution) | Q(institution__isnull=True))

    # 按已有题目数升序排列（题目少的优先）
    kps = list(qs.annotate(
        _question_count=Count('questions')
    ).order_by('_question_count'))

    if not kps:
        return []

    # 每个 KP 的目标题数（差异化：题目少的 KP 多出，题目多的少出）
    # 简单策略：每个 KP 出 5-15 道，选足够多的 KP 来满足 total_target
    kps_per_batch = max(1, total_target // 10)  # 每 KP 约 10 道
    selected = kps[:min(kps_per_batch, len(kps))]

    # 如果 KP 不够，所有 KP 都选
    if len(selected) < kps_per_batch and len(kps) > len(selected):
        selected = kps

    return selected


# ── 配额分配 ──────────────────────────────────────────────────────

def _distribute_quotas(
    kps: List[KnowledgePoint],
    total_target: int,
    difficulty_dist: Dict[str, float],
    type_dist: Dict[str, float],
) -> Dict[KnowledgePoint, Dict[str, int]]:
    """将总目标题数分配到各个知识点和难度等级。

    策略：题目少的 KP 多分，题目多的少分（趋近均匀分布）。
    """
    if not kps:
        return {}

    # 计算每个 KP 的权重：已有题目越少，权重越高
    counts = [getattr(k, '_question_count', 0) for k in kps]
    max_count = max(counts) if counts else 1

    # 权重 = max_count - count + 1（确保最少的权重最大，且避免零权重）
    weights = [max_count - c + 1 for c in counts]
    total_weight = sum(weights)

    quota_map: Dict[KnowledgePoint, Dict[str, int]] = {}
    remaining = total_target

    for i, kp in enumerate(kps):
        if i == len(kps) - 1:
            # 最后一个 KP 拿走剩余全部
            kp_total = remaining
        else:
            kp_total = max(3, int(total_target * weights[i] / total_weight))
            kp_total = min(kp_total, remaining - 3 * (len(kps) - i - 1))  # 确保后面 KP 至少 3 道
            kp_total = max(3, kp_total)

        remaining -= kp_total
        quota_map[kp] = {}
        for diff, ratio in difficulty_dist.items():
            quota_map[kp][diff] = max(0, int(kp_total * ratio))

        # 修正：确保总和等于 kp_total（因取整导致）
        allocated = sum(quota_map[kp].values())
        if allocated < kp_total and quota_map[kp]:
            # 把差额加到占比最大的难度
            max_diff = max(quota_map[kp], key=lambda d: quota_map[kp].get(d, 0))
            quota_map[kp][max_diff] += kp_total - allocated

    return quota_map


def _resolve_types(type_dist: Dict[str, float], count: int) -> List[str]:
    """根据题型分布和总数，返回具体的题型列表。"""
    obj_count = int(count * type_dist.get("objective", 0.4))
    subj_count = count - obj_count

    types = []
    if obj_count > 0:
        types.append("objective")
    if subj_count > 0:
        # 主观题从各类子类型中随机选择
        types.append("subjective:noun")
        types.append("subjective:short")
        types.append("subjective:essay")
        types.append("subjective:calculate")
    return types


# ── 入库 ──────────────────────────────────────────────────────────

def _save_questions(questions: List[Dict], institution=None) -> int:
    """将审核通过的题目保存到数据库。

    跳过与已有题目文本高度相似的（简单去重：完全相同文本）。
    """
    saved = 0
    for q in questions:
        text = (q.get("question") or q.get("text") or "").strip()
        if not text:
            continue

        # 去重：完全相同的题目跳过
        exists_qs = Question.objects.filter(text=text)
        if institution:
            exists_qs = exists_qs.filter(
                Q(institution=institution) | Q(institution__isnull=True)
            )
        if exists_qs.exists():
            continue

        # 解析选项
        options = q.get("options")
        if isinstance(options, dict):
            options = [options[k] for k in sorted(options.keys())]

        q_type = q.get("question_type") or q.get("q_type", "objective")
        subjective_type = q.get("subjective_type") if q_type == "subjective" else None
        difficulty = q.get("difficulty_level", "normal")

        try:
            Question.objects.create(
                knowledge_point_id=q.get("kp_id"),
                text=text,
                q_type=q_type,
                subjective_type=subjective_type,
                difficulty_level=difficulty,
                options=options,
                correct_answer=q.get("answer") or q.get("correct_answer", ""),
                ai_answer=q.get("ai_explanation") or q.get("ai_answer", ""),
                grading_points=q.get("grading_points", ""),
                difficulty=Question.DIFFICULTY_MAP.get(difficulty, 1200),
                institution=institution,
            )
            saved += 1
        except Exception as exc:
            logger.warning("Failed to save question for kp=%s: %s", q.get("kp_code", "?"), exc)

    return saved
