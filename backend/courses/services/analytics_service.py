"""
Memorix 学情分析服务 — 为教案管理提供班级知识掌握度数据。
"""
import logging
from collections import defaultdict
from datetime import date, timedelta

from django.core.cache import cache
from django.db.models import Sum, Count, Avg, Q
from django.utils import timezone

logger = logging.getLogger(__name__)

CLASS_KP_ANALYTICS_CACHE_TIMEOUT = 600


def get_class_kp_analytics(teaching_plan):
    """
    输入 TeachingPlan，返回该班级在对应学科上的 Memorix 学情分析。

    返回:
    {
        "student_count": int,
        "performance": [{kp_id, kp_name, kp_code, correct_rate, total_attempts, student_count, trend}],
        "weak_kps": [...],             # 正确率 < 60% 的知识点
        "prerequisite_chains": [...],  # 前驱拓扑链
        "forgetting_risk": [...],      # 高遗忘风险知识点
    }
    """
    from quizzes.models import UserQuestionStatus, KnowledgeEdge, UserKnowledgeState

    plan = teaching_plan
    subject = plan.subject
    institution = plan.institution

    # 获取班级学生列表
    student_ids = list(plan.class_obj.students.values_list('id', flat=True))
    if not student_ids:
        return {
            "student_count": 0,
            "performance": [],
            "weak_kps": [],
            "prerequisite_chains": [],
            "forgetting_risk": [],
        }

    # Redis 缓存（按班级 + 日期，600s TTL）
    cache_key = f"class_kp_analytics:{plan.class_obj_id}:{date.today().isoformat()}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    # ── 查询 1: 聚合 UserQuestionStatus + UserKnowledgeState ──
    # 按 KP 计算正确率 + 平均掌握度（单次 values/annotate 链）
    kp_stats_qs = (
        UserQuestionStatus.objects
        .filter(
            user_id__in=student_ids,
            question__knowledge_point__subject=subject,
            question__knowledge_point__isnull=False,
        )
        .values(
            'question__knowledge_point__id',
            'question__knowledge_point__name',
            'question__knowledge_point__code',
        )
        .annotate(
            total_reps=Sum('reps'),
            total_lapses=Sum('lapses'),
            student_count=Count('user_id', distinct=True),
        )
    )

    performance = []
    for row in kp_stats_qs:
        reps = row['total_reps'] or 0
        lapses = row['total_lapses'] or 0
        total = reps + lapses
        correct_rate = round(reps / total * 100, 1) if total > 0 else 0
        performance.append({
            'kp_id': row['question__knowledge_point__id'],
            'kp_name': row['question__knowledge_point__name'],
            'kp_code': row['question__knowledge_point__code'] or '',
            'correct_rate': correct_rate,
            'total_attempts': total,
            'student_count': row['student_count'],
            'trend': 'stable',
            'mastery_avg': None,
        })

    # 构建 kp_id → performance index（避免 BFS 中的 O(n) 线性扫描）
    perf_map = {p['kp_id']: p for p in performance}

    # ── 查询 2: UserKnowledgeState 掌握度聚合 ──
    mastery_qs = (
        UserKnowledgeState.objects
        .filter(
            user_id__in=student_ids,
            knowledge_point__subject=subject,
        )
        .values('knowledge_point_id')
        .annotate(avg_mastery=Avg('mastery_score'))
    )
    mastery_map = {m['knowledge_point_id']: round(m['avg_mastery'] or 0, 2) for m in mastery_qs}

    # 注入 mastery_map 到 performance
    for p in performance:
        p['mastery_avg'] = mastery_map.get(p['kp_id'])

    # ── 弱知识点（正确率最低，有足够数据量）──
    weak_kps = sorted(
        [p for p in performance if p['total_attempts'] >= 3 and p['correct_rate'] < 70],
        key=lambda x: x['correct_rate'],
    )[:8]

    # ── 查询 3: 前驱边 → 构建拓扑链 ──
    prereq_edges = KnowledgeEdge.objects.filter(
        edge_type='prerequisite',
        is_active=True,
        source__subject=subject,
    ).filter(
        Q(institution=institution) | Q(institution__isnull=True)
    ).select_related('source', 'target')

    adj = defaultdict(list)
    indeg = defaultdict(int)
    all_nodes = set()
    for e in prereq_edges:
        adj[e.source_id].append(e.target_id)
        indeg[e.target_id] += 1
        all_nodes.add(e.source_id)
        all_nodes.add(e.target_id)

    # BFS 拓扑排序（使用 perf_map 进行 O(1) 查找）
    prerequisite_chains = []
    visited = set()
    roots = sorted(all_nodes - set(indeg.keys()))
    for root in roots:
        if root in visited:
            continue
        chain = []
        queue = [root]
        while queue:
            node = queue.pop(0)
            if node in visited:
                continue
            visited.add(node)
            kp = perf_map.get(node)
            chain.append({
                'kp_id': node,
                'kp_name': kp['kp_name'] if kp else f'KP#{node}',
                'correct_rate': kp['correct_rate'] if kp else None,
            })
            for child in adj.get(node, []):
                if child not in visited:
                    queue.append(child)
        if len(chain) > 1:
            prerequisite_chains.append({'chain': chain, 'root_kp_id': root})

    # ── 查询 4: ReviewLog 遗忘风险 ──
    cutoff = timezone.now() - timedelta(days=14)
    from quizzes.models import ReviewLog
    risk_qs = (
        ReviewLog.objects
        .filter(
            user_id__in=student_ids,
            knowledge_point__subject=subject,
            review_time__gte=cutoff,
        )
        .values('knowledge_point_id', 'knowledge_point__name')
        .annotate(
            avg_retrievability=Avg('predicted_retrievability'),
            review_count=Count('id'),
        )
        .order_by('avg_retrievability')
    )
    forgetting_risk = []
    for r in risk_qs[:10]:
        if r['avg_retrievability'] is not None and r['avg_retrievability'] < 0.7:
            forgetting_risk.append({
                'kp_id': r['knowledge_point_id'],
                'kp_name': r['knowledge_point__name'],
                'avg_retrievability': round(r['avg_retrievability'], 3),
                'review_count': r['review_count'],
            })

    result = {
        "student_count": len(student_ids),
        "performance": performance,
        "weak_kps": weak_kps,
        "prerequisite_chains": prerequisite_chains,
        "forgetting_risk": forgetting_risk,
    }
    cache.set(cache_key, result, CLASS_KP_ANALYTICS_CACHE_TIMEOUT)
    return result


def format_analytics_for_ai_prompt(analytics: dict) -> str:
    """将 analytics 数据格式化为可注入 AI prompt 的文本。"""
    parts = []

    if analytics['weak_kps']:
        parts.append("## 班级薄弱知识点（需重点强化）")
        for kp in analytics['weak_kps']:
            parts.append(f"- {kp['kp_name']}: 正确率 {kp['correct_rate']}%、{kp['total_attempts']}次练习、{kp['student_count']}名学生")
        parts.append("请在这些知识点上分配更多教学时间。")

    if analytics['prerequisite_chains']:
        parts.append("\n## 知识点前驱关系（必须按此顺序教学）")
        for pc in analytics['prerequisite_chains']:
            chain_names = " → ".join(n['kp_name'] for n in pc['chain'])
            parts.append(f"- {chain_names}")
        parts.append("请严格按前驱关系排序知识点，不可颠倒先后顺序。")

    if analytics['forgetting_risk']:
        parts.append("\n## 高遗忘风险知识点（需插入复习环节）")
        for r in analytics['forgetting_risk'][:5]:
            parts.append(f"- {r['kp_name']}: 遗忘风险指数 {r['avg_retrievability']}、近期{r['review_count']}次复习")
        parts.append("请在学期中段和末尾各安排1-2周综合复习周。")

    return "\n".join(parts) if parts else ""
