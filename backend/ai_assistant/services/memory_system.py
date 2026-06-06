"""
MemorySystem - 统一记忆查询接口。

将 PlannerToolExecutor 中直接操作 model 的查询逻辑
抽取到此层，供 Agent 工具调用和 API 复用。
"""

import logging
from datetime import timedelta
from typing import Dict, Optional

from django.db import models
from django.utils import timezone

logger = logging.getLogger(__name__)


class MemorySystem:
    """记忆系统查询入口 — 所有方法都是静态方法，直接传 user。"""

    @staticmethod
    def query_learning_stats(user, institution=None) -> Dict:
        """查询用户学习统计数据。"""
        from quizzes.models import UserQuestionStatus, ReviewLog

        now = timezone.now()
        uqs = UserQuestionStatus.objects.filter(user=user)
        total_questions = uqs.count()
        total_correct = uqs.filter(last_correct=True).count()
        total_wrong = uqs.filter(wrong_count__gt=0).count()

        # Study streak: consecutive days with review activity in last 30 days
        review_days = (
            ReviewLog.objects.filter(user=user, review_time__gte=now - timedelta(days=30))
            .values_list('review_time__date', flat=True)
            .distinct()
        )
        sorted_days = sorted(set(review_days), reverse=True)
        streak = 0
        if sorted_days:
            check_date = sorted_days[0]
            for d in sorted_days:
                if d == check_date:
                    streak += 1
                    check_date -= timedelta(days=1)
                elif d < check_date:
                    break

        # Subject coverage
        subjects_with_progress = (
            uqs.values('question__knowledge_point__subject')
            .distinct()
            .count()
        )

        return {
            "total_questions_attempted": total_questions,
            "correct_count": total_correct,
            "accuracy": round(total_correct / total_questions * 100, 1) if total_questions else 0,
            "wrong_count": total_wrong,
            "study_streak_days": streak,
            "subjects_with_progress": subjects_with_progress,
            "is_new_user": total_questions == 0,
            "suggested_action": "diagnostic_test" if total_questions == 0 else None,
            "diagnostic_url": "/tests" if total_questions == 0 else None,
        }

    @staticmethod
    def query_mastery_map(user, subject: Optional[str] = None, institution=None) -> Dict:
        """查询用户知识掌握图谱。"""
        from quizzes.models import UserKnowledgeState

        qs = UserKnowledgeState.objects.filter(user=user).select_related('knowledge_point')
        if institution:
            qs = qs.filter(
                models.Q(knowledge_point__institution=institution) |
                models.Q(knowledge_point__institution__isnull=True)
            )
        subject_filter = (subject or '').strip()
        if subject_filter:
            qs = qs.filter(knowledge_point__subject=subject_filter)

        result = {}
        for uks in qs:
            kp = uks.knowledge_point
            subj = kp.subject or '未分类'
            if subj not in result:
                result[subj] = []
            result[subj].append({
                "kp_id": kp.id,
                "kp_code": kp.code or '',
                "kp_name": kp.name,
                "mastery_score": round(uks.mastery_score, 2),
            })

        for subj in result:
            result[subj].sort(key=lambda x: x['mastery_score'])

        return {"mastery_map": result}

    @staticmethod
    def query_weak_points(user, institution=None) -> Dict:
        """查询用户薄弱知识点。"""
        from django.db.models import Sum
        from quizzes.models import UserQuestionStatus

        qs = UserQuestionStatus.objects.filter(user=user, wrong_count__gt=0)
        if institution:
            qs = qs.filter(
                models.Q(question__institution=institution) |
                models.Q(question__institution__isnull=True)
            )

        aggregated = (
            qs.values('question__knowledge_point__name', 'question__knowledge_point__code')
            .annotate(total_wrong=Sum('wrong_count'))
            .order_by('-total_wrong')[:5]
        )

        return {
            "weak_points": [
                {
                    "kp_name": item['question__knowledge_point__name'] or '未知',
                    "kp_code": item['question__knowledge_point__code'] or '',
                    "total_wrong": item['total_wrong'],
                }
                for item in aggregated
            ],
        }

    @staticmethod
    def query_due_reviews(user, limit: int = 20, institution=None) -> Dict:
        """查询到期待复习的题目。"""
        from quizzes.models import UserQuestionStatus

        limit = min(int(limit), 50)
        now = timezone.now()
        due_qs = UserQuestionStatus.objects.filter(user=user, next_review_at__lte=now)
        if institution:
            due_qs = due_qs.filter(
                models.Q(question__institution=institution) |
                models.Q(question__institution__isnull=True)
            )
        due_qs = due_qs.select_related('question__knowledge_point').order_by('next_review_at')
        due_count = due_qs.count()
        due_list = due_qs[:limit]

        def _calculate_memorix_priority(d):
            if d.lapses >= 3:
                return "critical"
            if d.difficulty >= 7:
                return "high"
            if d.stability < 2:
                return "high"
            if d.stability < 7:
                return "medium"
            return "low"

        return {
            "due_count": due_count,
            "reviews": [
                {
                    "question_id": d.question_id,
                    "question_text": (d.question.text or '')[:200],
                    "kp_name": d.question.knowledge_point.name if d.question.knowledge_point else '',
                    "wrong_count": d.wrong_count,
                    "stability": round(d.stability, 2),
                    "difficulty": round(d.difficulty, 1),
                    "reps": d.reps,
                    "lapses": d.lapses,
                    "error_type": d.error_type or '',
                    "error_metadata": d.error_metadata or {},
                    "memorix_priority": _calculate_memorix_priority(d),
                    "next_review_at": d.next_review_at.isoformat() if d.next_review_at else None,
                }
                for d in due_list
            ],
        }

    @staticmethod
    def query_user_profile(user, institution=None) -> Dict:
        """查询用户综合画像 — 聚合学习统计 + 掌握图谱 + 薄弱点。"""
        stats = MemorySystem.query_learning_stats(user, institution=institution)
        mastery = MemorySystem.query_mastery_map(user, institution=institution)
        weak = MemorySystem.query_weak_points(user, institution=institution)

        return {
            "stats": stats,
            "mastery_map": mastery.get("mastery_map", {}),
            "weak_points": weak.get("weak_points", []),
        }

    @staticmethod
    def query_difficulty_analysis(user, subject: Optional[str] = None, institution=None) -> Dict:
        """查询知识点的 Memorix 难度分析。"""
        from quizzes.models import UserQuestionStatus

        subject = (subject or '').strip()

        qs = UserQuestionStatus.objects.filter(
            user=user,
            is_active=True
        ).select_related('question__knowledge_point')

        if institution:
            qs = qs.filter(
                models.Q(question__institution=institution) |
                models.Q(question__institution__isnull=True)
            )

        if subject:
            qs = qs.filter(question__knowledge_point__subject=subject)

        # 按知识点聚合
        kp_stats = {}
        for status in qs:
            kp = status.question.knowledge_point
            if not kp:
                continue
            kp_name = kp.name
            if kp_name not in kp_stats:
                kp_stats[kp_name] = {
                    "difficulties": [],
                    "stabilities": [],
                    "total_reviews": 0,
                    "lapse_counts": []
                }
            kp_stats[kp_name]["difficulties"].append(status.difficulty)
            kp_stats[kp_name]["stabilities"].append(status.stability)
            kp_stats[kp_name]["total_reviews"] += status.reps
            kp_stats[kp_name]["lapse_counts"].append(status.lapses)

        # 计算统计
        knowledge_points = []
        for kp_name, stats in kp_stats.items():
            avg_diff = sum(stats["difficulties"]) / len(stats["difficulties"])
            avg_stab = sum(stats["stabilities"]) / len(stats["stabilities"])
            total_lapses = sum(stats["lapse_counts"])

            if avg_diff >= 7 or avg_stab < 2:
                mastery = "weak"
            elif avg_diff >= 5 or avg_stab < 5:
                mastery = "developing"
            else:
                mastery = "strong"

            insight_parts = []
            if avg_diff >= 7:
                insight_parts.append(f"平均难度较高（{avg_diff:.1f}）")
            if avg_stab < 3:
                insight_parts.append(f"记忆稳定性低（{avg_stab:.1f}天）")
            if total_lapses >= 5:
                insight_parts.append(f"累计遗忘 {total_lapses} 次")

            if insight_parts:
                insight = f"该知识点{', '.join(insight_parts)}，建议增加复习频率并使用间隔重复策略"
            else:
                insight = "该知识点掌握情况良好"

            knowledge_points.append({
                "name": kp_name,
                "avg_difficulty": round(avg_diff, 1),
                "avg_stability": round(avg_stab, 1),
                "total_reviews": stats["total_reviews"],
                "mastery_level": mastery,
                "memorix_insight": insight
            })

        knowledge_points.sort(key=lambda x: x["avg_difficulty"], reverse=True)

        weak_count = sum(1 for kp in knowledge_points if kp["mastery_level"] == "weak")

        return {
            "knowledge_points": knowledge_points,
            "summary": f"共 {len(knowledge_points)} 个知识点，其中 {weak_count} 个需要重点关注"
        }
