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

    # 商业化分层：每个功能对应的会员等级
    TIER_FEATURES = {
        'memorix_adaptive': ['starter', 'growth', 'enterprise'],
        'error_analysis': ['starter', 'growth', 'enterprise'],
    }

    # 固定间隔（免费用户）：第 N 次复习的间隔天数
    FIXED_INTERVALS = [1, 3, 7, 14, 30]

    @staticmethod
    def _has_feature(user, feature: str) -> bool:
        """检查用户是否具备某个付费功能。user 为 None 或 free 用户不具备付费功能。"""
        if user is None:
            return False
        tier = getattr(user, 'membership_tier', 'free') or 'free'
        return tier in MemorySystem.TIER_FEATURES.get(feature, [])

    @staticmethod
    def _due_reviews_fixed(user, limit: int = 20, institution=None):
        """固定间隔调度：根据 last_review + 固定间隔 计算到期题目。"""
        from quizzes.models import UserQuestionStatus

        limit = min(int(limit), 50)
        now = timezone.now()

        # 收集所有有 review 记录的题目，在 Python 层计算固定间隔是否到期
        all_statuses = UserQuestionStatus.objects.filter(
            user=user, is_active=True
        ).select_related('question__knowledge_point').order_by('last_review')

        due_list = []
        for d in all_statuses:
            if d.last_review is None:
                # 从未复习过 → 视为到期
                due_list.append(d)
                continue
            interval_idx = min(d.reps, len(MemorySystem.FIXED_INTERVALS) - 1)
            interval_days = MemorySystem.FIXED_INTERVALS[interval_idx]
            next_due = d.last_review + timedelta(days=interval_days)
            if next_due <= now:
                due_list.append(d)

        # 按最 overdue 排序
        due_list.sort(key=lambda d: d.last_review or now)
        due_count = len(due_list)
        due_list = due_list[:limit]

        def _priority(d):
            if d.lapses >= 3:
                return "critical"
            if d.difficulty >= 7:
                return "high"
            if d.reps == 0:
                return "high"
            return "medium" if d.wrong_count > 0 else "low"

        return {
            "due_count": due_count,
            "interval_policy": "fixed",
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
                    "priority": _priority(d),
                    "next_review_at": d.next_review_at.isoformat() if d.next_review_at else None,
                }
                for d in due_list
            ],
        }

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
        """查询到期待复习的题目。免费用户走固定间隔，付费用户走 Memorix 自适应。"""
        if not MemorySystem._has_feature(user, 'memorix_adaptive'):
            return MemorySystem._due_reviews_fixed(user, limit, institution)

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
            "interval_policy": "memorix",
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

    @staticmethod
    def query_user_wrong_questions(user, limit=5, institution=None):
        """查询用户错题列表。"""
        from quizzes.models import UserQuestionStatus

        limit = min(int(limit), 10)
        qs = UserQuestionStatus.objects.filter(user=user, wrong_count__gt=0)
        if institution:
            qs = qs.filter(
                models.Q(question__institution=institution) |
                models.Q(question__institution__isnull=True)
            )
        wrong_qs = qs.select_related('question__knowledge_point').order_by('-wrong_count')[:limit]

        return {
            "questions": [
                {
                    "id": wq.question_id,
                    "text": (wq.question.text or '')[:500],
                    "answer": (wq.question.correct_answer or '')[:300],
                    "q_type": wq.question.q_type,
                    "kp_name": wq.question.knowledge_point.name if wq.question.knowledge_point else '',
                    "wrong_count": wq.wrong_count,
                }
                for wq in wrong_qs
            ],
        }

    # ── Phase 4: 以下方法从 tool_executor handler 迁移 ────────

    @staticmethod
    def query_user_subjects(user, institution=None) -> Dict:
        """查询用户有做题记录的学科列表。"""
        from quizzes.models import UserQuestionStatus
        return {
            "subjects": list(
                UserQuestionStatus.objects.filter(user=user)
                .values_list('question__knowledge_point__subject', flat=True)
                .distinct()
            ),
        }

    @staticmethod
    def query_knowledge_tree(query: str, subject: str, user, institution=None) -> Dict:
        """搜索知识点树。"""
        from django.db.models import Q, Count
        from quizzes.models import KnowledgePoint

        qs = KnowledgePoint.objects.filter(
            Q(name__icontains=query) | Q(description__icontains=query),
        )
        if subject:
            qs = qs.filter(subject=subject)
        else:
            user_subjects_data = MemorySystem.query_user_subjects(user, institution)
            user_subjects = user_subjects_data.get("subjects", [])
            if user_subjects:
                qs = qs.filter(Q(subject__in=user_subjects) | Q(subject__isnull=True))
        if institution:
            qs = qs.filter(Q(institution=institution) | Q(institution__isnull=True))

        nodes = list(qs.select_related('parent').values(
            'id', 'code', 'name', 'level', 'subject', 'parent__name',
        )[:15])

        node_ids = [n['id'] for n in nodes]
        child_counts = dict(
            KnowledgePoint.objects.filter(parent_id__in=node_ids)
            .values_list('parent_id')
            .annotate(cnt=Count('id'))
            .values_list('parent_id', 'cnt')
        )
        for node in nodes:
            node['child_count'] = child_counts.get(node['id'], 0)

        return {
            "found": len(nodes),
            "results": [
                {
                    "id": n['id'],
                    "code": n['code'] or '',
                    "name": n['name'],
                    "level": n['level'],
                    "subject": n['subject'] or '',
                    "parent": n['parent__name'] or '',
                    "child_count": n['child_count'],
                }
                for n in nodes
            ],
        }

    @staticmethod
    def query_class_weak_points(institution, limit: int = 5) -> Dict:
        """获取班级最薄弱的知识点。"""
        from django.db.models import Sum, Count
        from quizzes.models import UserQuestionStatus

        student_ids = list(
            institution.students.filter(institution_role='student').values_list('id', flat=True)
        )
        if not student_ids:
            return {"weak_points": [], "message": "该机构暂无学生"}

        qs = (
            UserQuestionStatus.objects
            .filter(user_id__in=student_ids, question__knowledge_point__isnull=False)
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

        scored = []
        for row in qs:
            total = (row['total_reps'] or 0) + (row['total_lapses'] or 0)
            if total == 0:
                continue
            correct_rate = (row['total_reps'] or 0) / total
            scored.append({
                'kp_name': row['question__knowledge_point__name'] or '',
                'kp_code': row['question__knowledge_point__code'] or '',
                'correct_rate': round(correct_rate * 100, 1),
                'total_attempts': total,
                'student_count': row['student_count'] or 0,
            })

        scored.sort(key=lambda x: x['correct_rate'])
        return {"weak_points": scored[:limit]}

    @staticmethod
    def query_class_performance(institution) -> Dict:
        """获取班级整体学习数据概览。"""
        from django.db.models import Sum, Count
        from quizzes.models import UserQuestionStatus, ReviewLog

        student_ids = list(
            institution.students.filter(institution_role='student').values_list('id', flat=True)
        )
        if not student_ids:
            return {"summary": {}, "message": "该机构暂无学生"}

        week_ago = timezone.now() - timedelta(days=7)

        total_students = len(student_ids)
        total_statuses = UserQuestionStatus.objects.filter(user_id__in=student_ids)
        total_questions = total_statuses.count()
        agg = total_statuses.aggregate(t_reps=Sum('reps'), t_lapses=Sum('lapses'))
        total_reps = agg['t_reps'] or 0
        total_lapses = agg['t_lapses'] or 0
        total_attempts = total_reps + total_lapses
        overall_rate = round(total_reps / total_attempts * 100, 1) if total_attempts > 0 else 0

        weekly_active = ReviewLog.objects.filter(
            user_id__in=student_ids, review_time__gte=week_ago,
        ).values('user_id').distinct().count()

        kp_agg = (
            total_statuses
            .filter(question__knowledge_point__isnull=False)
            .values('question__knowledge_point__id')
            .annotate(t_reps=Sum('reps'), t_lapses=Sum('lapses'))
        )
        weak_kp_count = 0
        for row in kp_agg:
            t = (row['t_reps'] or 0) + (row['t_lapses'] or 0)
            if t > 0 and (row['t_reps'] or 0) / t < 0.6:
                weak_kp_count += 1

        return {
            "summary": {
                "total_students": total_students,
                "weekly_active_students": weekly_active,
                "total_questions_tracked": total_questions,
                "total_attempts": total_attempts,
                "overall_correct_rate": overall_rate,
                "weak_kp_count": weak_kp_count,
            }
        }

    @staticmethod
    def query_question(question_id: int, institution=None) -> Dict:
        """根据 ID 查询题目详情。"""
        from django.db.models import Q
        from quizzes.models import Question

        qs = Question.objects.select_related('knowledge_point')
        if institution:
            qs = qs.filter(institution=institution)
        try:
            q = qs.get(id=question_id)
        except Question.DoesNotExist:
            return {"error": f"题目 #{question_id} 不存在"}

        return {
            "id": q.id,
            "text": q.text or '',
            "q_type": q.q_type,
            "subjective_type": q.subjective_type or '',
            "options": q.options or [],
            "correct_answer": q.correct_answer or '',
            "grading_points": q.grading_points or '',
            "difficulty_level": q.difficulty_level,
            "knowledge_point_id": q.knowledge_point_id,
            "kp_name": q.knowledge_point.name if q.knowledge_point else '',
            "kp_code": q.knowledge_point.code if q.knowledge_point else '',
            "subject": q.knowledge_point.subject if q.knowledge_point else '',
        }

    @staticmethod
    def query_practice_questions(user, kp_name: str = '', subject: str = '',
                                 difficulty: str = '', limit: int = 5,
                                 exclude_mastered: bool = True,
                                 institution=None) -> Dict:
        """从题库中抽取练习题。优先返回做错过的题目。"""
        from quizzes.models import Question, UserQuestionStatus

        limit = min(int(limit), 10)
        qs = Question.objects.select_related('knowledge_point')

        if institution:
            qs = qs.filter(institution=institution)

        if kp_name:
            qs = qs.filter(knowledge_point__name__icontains=kp_name)
        if subject:
            qs = qs.filter(knowledge_point__subject=subject)
        if difficulty:
            qs = qs.filter(difficulty_level=difficulty)

        if exclude_mastered:
            mastered_ids = set(
                UserQuestionStatus.objects.filter(
                    user=user, is_mastered=True
                ).values_list('question_id', flat=True)
            )
            if mastered_ids:
                qs = qs.exclude(id__in=mastered_ids)

        wrong_qids = set(
            UserQuestionStatus.objects.filter(
                user=user, wrong_count__gt=0
            ).values_list('question_id', flat=True)
        )

        wrong_qs = qs.filter(id__in=wrong_qids).order_by('?')[:limit]
        wrong_list = list(wrong_qs)

        remaining = limit - len(wrong_list)
        new_list = []
        if remaining > 0:
            wrong_ids = {q.id for q in wrong_list}
            new_qs = qs.exclude(id__in=wrong_ids | wrong_qids).order_by('?')[:remaining]
            new_list = list(new_qs)

        all_questions = wrong_list + new_list

        return {
            "total_found": qs.count(),
            "questions": [
                {
                    "id": q.id,
                    "text": (q.text or '')[:500],
                    "q_type": q.q_type,
                    "subjective_type": q.subjective_type or '',
                    "options": q.options or [],
                    "difficulty_level": q.difficulty_level,
                    "kp_name": q.knowledge_point.name if q.knowledge_point else '',
                    "kp_code": q.knowledge_point.code if q.knowledge_point else '',
                    "is_review": q.id in wrong_qids,
                }
                for q in all_questions
            ],
            "practice_url": "/quiz/practice",
            "message": f"已从题库抽取 {len(all_questions)} 道题目" + (
                f"（{len(wrong_list)} 道错题复习 + {len(new_list)} 道新题）"
                if wrong_list and new_list else
                f"（{len(wrong_list)} 道错题复习）" if wrong_list else
                f"（{len(new_list)} 道新题）"
            ),
        }

    @staticmethod
    def query_exam_history(user, limit: int = 10, institution=None) -> Dict:
        """查询用户考试历史。"""
        from quizzes.models import QuizExam

        limit = min(int(limit), 20)
        exams = QuizExam.objects.filter(user=user).order_by('-created_at')[:limit]
        return {
            "exams": [
                {
                    "id": e.id,
                    "total_score": e.total_score,
                    "max_score": e.max_score,
                    "percentage": round(e.total_score / e.max_score * 100, 1) if e.max_score else 0,
                    "elo_change": e.elo_change,
                    "created_at": e.created_at.isoformat(),
                }
                for e in exams
            ],
        }

    @staticmethod
    def write_grading_record(user, question_id: int, score: float, max_score: float,
                             is_correct: bool, error_type: str, error_metadata: dict,
                             feedback: str, analysis: str) -> Dict:
        """写入判分记录。"""
        from quizzes.models import GradingRecord

        try:
            record = GradingRecord.objects.create(
                user=user,
                question_id=question_id,
                score=score,
                max_score=max_score,
                is_correct=is_correct,
                error_type=error_type,
                error_metadata=error_metadata,
                feedback=feedback,
                analysis=analysis,
            )
            return {"grading_record_id": record.id}
        except Exception as e:
            logger.warning("write_grading_record failed: %s", e)
            return {"error": str(e)}

    @staticmethod
    def write_question_status_error(user, question_id: int, error_type: str,
                                    error_metadata: dict) -> bool:
        """更新 UserQuestionStatus 的错因字段。"""
        from quizzes.models import UserQuestionStatus

        try:
            uqs = UserQuestionStatus.objects.filter(
                user=user, question_id=question_id
            ).first()
            if uqs:
                uqs.error_type = error_type
                uqs.error_metadata = error_metadata
                uqs.save(update_fields=['error_type', 'error_metadata'])
                return True
        except Exception as e:
            logger.warning("write_question_status_error failed: %s", e)
        return False

    @staticmethod
    def query_similar_questions(kp_id: int, difficulty_level: str = 'normal',
                                exclude_id: int = 0, limit: int = 3,
                                institution=None) -> Dict:
        """查询同知识点、相近难度的题目（变式题匹配）。"""
        from quizzes.models import Question

        DIFFICULTY_ORDER = {'entry': 0, 'easy': 1, 'normal': 2, 'hard': 3, 'extreme': 4}
        target_rank = DIFFICULTY_ORDER.get(difficulty_level, 2)
        adjacent = [k for k, v in DIFFICULTY_ORDER.items() if abs(v - target_rank) <= 1]

        qs = Question.objects.filter(
            knowledge_point_id=kp_id,
            difficulty_level__in=adjacent,
        ).exclude(id=exclude_id)
        if institution:
            qs = qs.filter(
                models.Q(institution=institution) | models.Q(institution__isnull=True)
            )

        questions = list(qs.select_related('knowledge_point').order_by('?')[:limit])
        return {
            "questions": [
                {
                    "id": q.id,
                    "text": (q.text or '')[:300],
                    "difficulty_level": q.difficulty_level,
                    "kp_name": q.knowledge_point.name if q.knowledge_point else '',
                }
                for q in questions
            ],
        }

    @staticmethod
    def query_kp_breakdown(user, kp_ids: list) -> Dict:
        """查询指定知识点的掌握度和练习统计。"""
        from django.db.models import Sum
        from quizzes.models import UserKnowledgeState, UserQuestionStatus

        states = UserKnowledgeState.objects.filter(
            user=user, knowledge_point_id__in=kp_ids
        ).select_related('knowledge_point')

        breakdown = []
        for state in states:
            kp = state.knowledge_point
            uqs_agg = UserQuestionStatus.objects.filter(
                user=user, question__knowledge_point_id=kp.id
            ).aggregate(
                total_reps=Sum('reps'),
                total_wrong=Sum('wrong_count'),
            )
            total_attempts = uqs_agg['total_reps'] or 0
            total_wrong = uqs_agg['total_wrong'] or 0
            correct_count = max(0, total_attempts - total_wrong)

            breakdown.append({
                "kp_id": kp.id,
                "kp_name": kp.name,
                "mastery_score": round(state.mastery_score, 1),
                "total_attempts": total_attempts,
                "correct_count": correct_count,
            })

        return {"kp_breakdown": breakdown}
