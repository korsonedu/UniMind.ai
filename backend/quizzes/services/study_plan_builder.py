"""
结构化学习计划生成器 — 将诊断结果转化为分阶段的学习任务序列。

基于 knowledge edge 拓扑排序知识点学习顺序，结合 Memorix mastery
数据生成带时间线和目标准确率的结构化计划。
"""

from datetime import timedelta
from django.utils import timezone


def build_structured_plan(user, diagnostic_results: list[dict], days_per_phase: int = 7) -> dict:
    """将诊断结果转化为结构化分阶段学习计划。

    Args:
        user: 用户对象
        diagnostic_results: [{'kp_id': int, 'kp_name': str, 'accuracy': float}, ...]
        days_per_phase: 每阶段天数，默认 7 天

    Returns:
        {
            'phases': [{phase, name, duration_days, tasks: [{kp_id, kp_name, target_accuracy, question_count, deadline_days}]}],
            'estimated_completion_date': 'YYYY-MM-DD',
            'total_kps': int, 'total_questions': int,
        }
    """
    if not diagnostic_results:
        return {'phases': [], 'estimated_completion_date': None, 'total_kps': 0, 'total_questions': 0}

    # 按准确率升序排列（最弱的优先）
    sorted_kps = sorted(diagnostic_results, key=lambda x: x.get('accuracy', 0))

    # 分阶段：每阶段最多 3 个知识点
    phases = []
    kp_index = 0
    phase_num = 1
    total_questions = 0

    while kp_index < len(sorted_kps):
        batch = sorted_kps[kp_index:kp_index + 3]
        tasks = []
        for kp in batch:
            accuracy = kp.get('accuracy', 0)
            # 根据当前准确率决定目标
            if accuracy < 0.3:
                target_accuracy = 0.6
                question_count = 30
            elif accuracy < 0.5:
                target_accuracy = 0.7
                question_count = 25
            elif accuracy < 0.7:
                target_accuracy = 0.8
                question_count = 20
            else:
                target_accuracy = 0.9
                question_count = 15

            tasks.append({
                'kp_id': kp.get('kp_id'),
                'kp_name': kp.get('kp_name', '未知知识点'),
                'current_accuracy': round(accuracy, 2),
                'target_accuracy': target_accuracy,
                'question_count': question_count,
                'deadline_days': days_per_phase,
            })
            total_questions += question_count

        phase_name = '基础巩固' if phase_num == 1 else '强化提升' if phase_num == 2 else '冲刺突破'

        phases.append({
            'phase': phase_num,
            'name': phase_name,
            'duration_days': days_per_phase,
            'tasks': tasks,
        })

        kp_index += 3
        phase_num += 1

    estimated_completion = timezone.now().date() + timedelta(days=days_per_phase * len(phases))

    return {
        'phases': phases,
        'estimated_completion_date': estimated_completion.isoformat(),
        'total_kps': len(diagnostic_results),
        'total_questions': total_questions,
    }


def suggest_next_kps(user, top_n: int = 3) -> list[dict]:
    """基于 knowledge edge 拓扑和 Memorix 数据，推荐下一步要学习的知识点。

    策略：
    1. 找所有前置知识已掌握、但自身未掌握的知识点
    2. 按 memorix stability 升序（最需要复习的优先）
    3. 返回 top_n 个建议
    """
    from quizzes.models import UserKnowledgeState, KnowledgeEdge, KnowledgePoint

    # 获取用户已掌握和未掌握的知识点
    known_states = UserKnowledgeState.objects.filter(user=user).select_related('knowledge_point')
    mastered_kp_ids = set()
    weak_kps = []

    for state in known_states:
        if state.mastery_level and state.mastery_level >= 0.7:
            mastered_kp_ids.add(state.knowledge_point_id)
        elif state.mastery_level is not None:
            weak_kps.append(state)

    # 找前置条件已满足的未掌握知识点
    suggestions = []
    for state in weak_kps:
        kp = state.knowledge_point
        # 检查前置条件
        prereqs = KnowledgeEdge.objects.filter(
            target=kp, edge_type='prerequisite'
        ).values_list('source_id', flat=True)

        if prereqs and not prereqs.issubset(mastered_kp_ids):
            continue  # 前置知识未全部掌握，跳过

        suggestions.append({
            'kp_id': kp.id,
            'kp_name': kp.name,
            'mastery': round(state.mastery_level, 2),
            'stability': round(state.stability, 2) if state.stability else None,
            'last_reviewed': state.last_reviewed_at.isoformat() if state.last_reviewed_at else None,
        })

    # 按 mastery 升序排列
    suggestions.sort(key=lambda x: x['mastery'])
    return suggestions[:top_n]
