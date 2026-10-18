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
from users.permissions import IsMemberOrReadOnlyList, IsPlatformAdmin
from core.utils import get_content_institution, get_content_institution_id

logger = logging.getLogger(__name__)

USE_MEM0 = os.getenv('USE_MEM0', 'false').lower() == 'true'


class XiaoYuDashboardView(APIView):
    """GET /api/xiaoyu/dashboard/ — 聚合小宇 dashboard 所需的全部数据。"""
    permission_classes = [IsMemberOrReadOnlyList]

    def get(self, request):
        user = request.user
        institution = get_content_institution()
        data = {}

        # 1. Learning Stats
        data['stats'] = self._get_stats(user, institution)

        # 2. Knowledge Mastery
        data['mastery'] = self._get_mastery(user, institution)

        # 3. Due Reviews
        data['reviews'] = self._get_reviews(user, institution)

        # 4. Exam History
        data['exams'] = self._get_exams(user)

        # 5. Dashboard layout config (legacy, from user.dashboard_config)
        default_config = {
            'section_order': ['stats', 'mastery', 'reviews', 'exams', 'custom_cards'],
            'highlight': 'stats',
        }
        data['dashboard_config'] = user.dashboard_config or default_config

        # 6. Custom data cards (legacy, from user.dashboard_config)
        data['custom_cards'] = (user.dashboard_config or {}).get('custom_cards', [])

        return Response(data)

    # ── Stats ─────────────────────────────────────────────
    def _get_stats(self, user, institution=None):
        from quizzes.models import ReviewLog
        from quizzes.services.learning_stats import build_learning_stats

        now = timezone.now()
        stats = build_learning_stats(user, institution=institution)

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
            'total_attempted': stats['attempted_questions'],
            'correct_count': stats['last_correct_count'],
            'accuracy': stats['last_accuracy'] or 0,
            'wrong_count': stats['wrong_question_count'],
            'streak_days': stats['study_streak_days'],
            'weekly_activity': weekly_questions,
            'is_new_user': stats['is_new_user'],
            'attempted_questions': stats['attempted_questions'],
            'total_attempts': stats['total_attempts'],
            'last_accuracy': stats['last_accuracy'],
            'lifetime_accuracy': stats['lifetime_accuracy'],
            'has_attempts': stats['has_attempts'],
            'unclassified_questions': stats['unclassified_questions'],
            'subject_count': stats['subject_count'],
            'mastery': stats['mastery'],
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
        qs = qs.filter(knowledge_point__institution_id=get_content_institution_id())
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
        due_qs = due_qs.filter(question__institution_id=get_content_institution_id())
        due_qs = due_qs.select_related('question__knowledge_point').order_by('next_review_at')[:20]
        base_qs = UserQuestionStatus.objects.filter(user=user, next_review_at__lte=now)
        base_qs = base_qs.filter(question__institution_id=get_content_institution_id())
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
    permission_classes = [IsPlatformAdmin]

    def get(self, request):
        user = request.user
        institution = get_content_institution()

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
            created_by=user, institution_id=get_content_institution_id(),
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
