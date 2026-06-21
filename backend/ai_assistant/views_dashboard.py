"""Dashboard 聚合接口 — 小宇 + 命题官。"""
import json
import logging
import os
from django.db import models
from django.db.models import Sum, Count, Q
from django.db.models.functions import TruncDate
from django.utils import timezone
from datetime import timedelta
from rest_framework.views import APIView
from rest_framework.response import Response
from users.views import IsMember
from users.permissions import IsMemberOrReadOnlyList

logger = logging.getLogger(__name__)

USE_MEM0 = os.getenv('USE_MEM0', 'false').lower() == 'true'


class XiaoYuDashboardView(APIView):
    """GET /api/xiaoyu/dashboard/ — 聚合小宇 dashboard 所需的全部数据。"""
    permission_classes = [IsMemberOrReadOnlyList]

    def get(self, request):
        user = request.user
        institution = getattr(user, 'institution', None)
        data = {}

        # 1. Active Study Plan
        data['plan'] = self._get_plan(user)

        # 2. Learning Stats
        data['stats'] = self._get_stats(user, institution)

        # 3. Knowledge Mastery
        data['mastery'] = self._get_mastery(user, institution)

        # 4. Due Reviews
        data['reviews'] = self._get_reviews(user, institution)

        # 5. Exam History
        data['exams'] = self._get_exams(user)

        # 6. Dashboard layout config (legacy, from user.dashboard_config)
        default_config = {
            'section_order': ['plan', 'stats', 'mastery', 'reviews', 'exams', 'custom_cards'],
            'highlight': 'stats',
        }
        data['dashboard_config'] = user.dashboard_config or default_config

        # 7. Custom data cards (legacy, from user.dashboard_config)
        data['custom_cards'] = (user.dashboard_config or {}).get('custom_cards', [])

        return Response(data)

    # ── Plan ──────────────────────────────────────────────
    def _get_plan(self, user):
        from ai_assistant.models import StudyPlan
        plan = StudyPlan.objects.filter(user=user, status='active').first()
        if not plan:
            return None
        data = plan.plan_data or {}
        tasks = data.get('tasks', [])
        completed = sum(1 for t in tasks if t.get('status') == 'completed')

        plan_result = {
            'id': plan.id,
            'title': plan.title,
            'summary': plan.summary,
            'total_tasks': len(tasks),
            'completed_tasks': completed,
            'progress_pct': round(completed / len(tasks) * 100, 1) if tasks else 0,
            'tasks': tasks,
            'created_at': plan.created_at.isoformat(),
            'subjects_covered': data.get('subjects_covered', []),
        }

        # 目标信息来自关联的 TeachingPlan
        if plan.teaching_plan_id:
            tp = plan.teaching_plan
            total_days = (tp.deadline - plan.created_at.date()).days if tp.deadline and plan.created_at else (tp.week_count * 7)
            elapsed_days = max((timezone.now().date() - plan.created_at.date()).days, 0) if plan.created_at else 0
            expected_progress_pct = round(min(elapsed_days / total_days * 100, 100), 1) if total_days > 0 else None
            progress_delta = round(plan_result['progress_pct'] - expected_progress_pct, 1) if expected_progress_pct is not None else None

            plan_result.update({
                'goal': tp.goal or '',
                'deadline': tp.deadline.isoformat() if tp.deadline else None,
                'subject': tp.subject or '',
                'target_score': tp.target_score,
                'current_level': tp.current_level or '',
                'expected_progress_pct': expected_progress_pct,
                'progress_delta': progress_delta,
                'total_days': total_days,
                'elapsed_days': elapsed_days,
                'teaching_plan_id': tp.id,
                'teaching_plan_title': tp.title,
            })

        return plan_result

    # ── Stats ─────────────────────────────────────────────
    def _get_stats(self, user, institution=None):
        from quizzes.models import UserQuestionStatus, ReviewLog
        now = timezone.now()
        uqs = UserQuestionStatus.objects.filter(user=user)
        if institution:
            uqs = uqs.filter(
                models.Q(question__institution=institution)
            )
        total = uqs.count()
        correct = uqs.filter(last_correct=True).count()
        wrong = uqs.filter(wrong_count__gt=0).count()

        # Study streak
        review_days = (
            ReviewLog.objects.filter(user=user, review_time__gte=now - timedelta(days=30))
            .values_list('review_time__date', flat=True)
            .distinct()
        )
        streak = 0
        check_date = now.date()
        for d in sorted(set(review_days), reverse=True):
            if d == check_date:
                streak += 1
                check_date -= timedelta(days=1)
            elif d < check_date:
                break

        # This week activity
        week_ago = now - timedelta(days=7)
        weekly_questions = (
            ReviewLog.objects.filter(user=user, review_time__gte=week_ago)
            .count()
        )

        # Daily check-in status
        from users.models import DailyCheckIn
        today_checkin = DailyCheckIn.objects.filter(user=user, date=now.date()).first()
        checkin_streak = today_checkin.streak if today_checkin else 0

        # Weekly activity heatmap (last 28 days) — single query
        cutoff = now.date() - timedelta(days=27)
        daily_counts = dict(
            ReviewLog.objects
            .filter(user=user, review_time__date__gte=cutoff)
            .annotate(day=TruncDate('review_time'))
            .values('day')
            .annotate(count=Count('id'))
            .values_list('day', 'count')
        )
        heatmap_days = []
        for i in range(27, -1, -1):
            d = now.date() - timedelta(days=i)
            heatmap_days.append({'date': d.isoformat(), 'count': daily_counts.get(d, 0)})

        # 7-day check-in history — single query
        week_ago_date = now.date() - timedelta(days=6)
        checkin_dates = set(
            DailyCheckIn.objects
            .filter(user=user, date__gte=week_ago_date)
            .values_list('date', flat=True)
        )
        checkin_history = []
        for i in range(6, -1, -1):
            d = now.date() - timedelta(days=i)
            checkin_history.append({
                'date': d.isoformat(),
                'checked_in': d in checkin_dates,
            })

        # Next achievements
        from users.models import Achievement, UserAchievement
        unlocked_keys = set(
            UserAchievement.objects.filter(user=user)
            .values_list('achievement__key', flat=True)
        )
        next_achievements = []
        for a in Achievement.objects.filter(is_active=True).order_by('category', 'threshold'):
            if a.key not in unlocked_keys:
                next_achievements.append({
                    'key': a.key, 'name': a.name, 'description': a.description,
                    'icon': a.icon, 'category': a.category,
                })
                if len(next_achievements) >= 3:
                    break

        return {
            'total_attempted': total,
            'correct_count': correct,
            'accuracy': round(correct / total * 100, 1) if total else 0,
            'wrong_count': wrong,
            'streak_days': streak,
            'weekly_activity': weekly_questions,
            'is_new_user': total == 0,
            'today_checked_in': today_checkin is not None,
            'checkin_streak': checkin_streak,
            'checkin_history': checkin_history,
            'heatmap_days': heatmap_days,
            'unlocked_achievement_count': len(unlocked_keys),
            'next_achievements': next_achievements,
        }

    # ── Mastery ───────────────────────────────────────────
    def _get_mastery(self, user, institution=None):
        from quizzes.models import UserKnowledgeState
        qs = UserKnowledgeState.objects.filter(user=user).select_related('knowledge_point')
        if institution:
            qs = qs.filter(
                models.Q(knowledge_point__institution=institution) |
                models.Q(knowledge_point__institution__isnull=True)
            )
        result = {}
        for uks in qs:
            kp = uks.knowledge_point
            subj = kp.subject or '未分类'
            if subj not in result:
                result[subj] = []
            result[subj].append({
                'kp_id': kp.id,
                'kp_code': kp.code or '',
                'kp_name': kp.name,
                'mastery_score': round(uks.mastery_score, 2),
            })
        for subj in result:
            result[subj].sort(key=lambda x: x['mastery_score'])
        return result

    # ── Reviews ───────────────────────────────────────────
    def _get_reviews(self, user, institution=None):
        from quizzes.models import UserQuestionStatus
        now = timezone.now()
        due_qs = UserQuestionStatus.objects.filter(user=user, next_review_at__lte=now)
        if institution:
            due_qs = due_qs.filter(
                models.Q(question__institution=institution)
            )
        due_qs = due_qs.select_related('question__knowledge_point').order_by('next_review_at')[:20]
        base_qs = UserQuestionStatus.objects.filter(user=user, next_review_at__lte=now)
        if institution:
            base_qs = base_qs.filter(
                models.Q(question__institution=institution)
            )
        return {
            'due_count': base_qs.count(),
            'items': [
                {
                    'question_id': d.question_id,
                    'question_text': (d.question.text or '')[:200],
                    'kp_name': d.question.knowledge_point.name if d.question.knowledge_point else '',
                    'wrong_count': d.wrong_count,
                    'stability': round(d.stability, 2),
                }
                for d in due_qs
            ],
        }

    # ── Exams ─────────────────────────────────────────────
    def _get_exams(self, user):
        from quizzes.models import QuizExam
        exams = QuizExam.objects.filter(user=user).order_by('-created_at')[:10]
        # Exams are already per-user, no additional institution filter needed
        return [
            {
                'id': e.id,
                'total_score': e.total_score,
                'max_score': e.max_score,
                'percentage': round(e.total_score / e.max_score * 100, 1) if e.max_score else 0,
                'elo_change': e.elo_change,
                'created_at': e.created_at.isoformat(),
            }
            for e in exams
        ]


class ExamWorkbenchDashboardView(APIView):
    """GET /api/ai/workbench/dashboard/ — 聚合命题官 dashboard 所需的全部数据。"""
    permission_classes = [IsMember]

    def get(self, request):
        user = request.user
        institution = getattr(user, 'institution', None)
        if not user.is_institution_admin:
            return Response({"error": "仅机构管理员可访问"}, status=403)

        data = {}

        # 1. Recent questions generated
        data['recent_questions'] = self._get_recent_questions(institution)

        # 2. ARC pipeline status
        data['pipeline_status'] = self._get_pipeline_status(user)

        # 3. Question library stats
        data['library_stats'] = self._get_library_stats(institution)

        # 4. Teacher insights from meta-cognition
        data['teacher_insights'] = self._get_teacher_insights(user)

        # 5. Dashboard layout config
        default_config = {
            'section_order': ['recent_questions', 'pipeline_status', 'library_stats', 'teacher_insights'],
            'highlight': 'recent_questions',
        }
        data['dashboard_config'] = (user.dashboard_config or {}).get('workbench', default_config)

        return Response(data)

    def _get_recent_questions(self, institution):
        """最近生成的题目（含 review 状态）。"""
        from quizzes.models import Question
        qs = Question.objects.filter(institution=institution).order_by('-created_at')[:20]
        return [
            {
                'id': q.id,
                'text': (q.text or '')[:200],
                'q_type': q.q_type,
                'difficulty_level': q.difficulty_level,
                'kp_name': q.knowledge_point.name if q.knowledge_point else '',
                'subject': q.knowledge_point.subject if q.knowledge_point else '',
                'created_at': q.created_at.isoformat(),
            }
            for q in qs
        ]

    def _get_pipeline_status(self, user):
        """进行中的 ARC 管线任务。"""
        from quizzes.models import ContentPipelineTask
        tasks = ContentPipelineTask.objects.filter(
            created_by=user,
            status__in=['pending', 'running'],
        ).order_by('-created_at')[:5]
        return [
            {
                'id': t.id,
                'title': t.title,
                'status': t.status,
                'progress': t.progress,
                'current_stage': (t.payload or {}).get('current_stage', ''),
                'created_at': t.created_at.isoformat(),
            }
            for t in tasks
        ]

    def _get_library_stats(self, institution):
        """题库统计。"""
        from quizzes.models import Question
        qs = Question.objects.filter(institution=institution)

        total = qs.count()
        if total == 0:
            return {'total': 0, 'by_type': {}, 'by_difficulty': {}, 'by_subject': {}}

        by_type = dict(qs.values_list('q_type').annotate(c=Count('id')).values_list('q_type', 'c'))
        by_difficulty = dict(qs.values_list('difficulty_level').annotate(c=Count('id')).values_list('difficulty_level', 'c'))

        by_subject = {}
        subject_qs = (
            qs.filter(knowledge_point__isnull=False)
            .values('knowledge_point__subject')
            .annotate(c=Count('id'))
            .order_by('-c')
        )
        for row in subject_qs:
            subj = row['knowledge_point__subject'] or '未分类'
            by_subject[subj] = row['c']

        return {
            'total': total,
            'by_type': by_type,
            'by_difficulty': by_difficulty,
            'by_subject': by_subject,
        }

    def _get_teacher_insights(self, user):
        """从 mem0 获取教师偏好洞察。"""
        if not USE_MEM0 or not user.institution_id:
            return []

        try:
            from ai_assistant.services.tenant_memory import TenantMemoryManager
            mgr = TenantMemoryManager(institution_id=user.institution_id)
            memories = mgr.get_all(user_id=user.id)[:20]
            insights = [
                m for m in memories
                if isinstance(m, dict)
                and '[系统分析]' in m.get('memory', '')
            ]
            return [
                {'text': m['memory'].replace('[系统分析] ', '')}
                for m in insights[:10]
            ]
        except Exception:
            logger.exception("Failed to get teacher insights for user %d", user.id)
            return []
