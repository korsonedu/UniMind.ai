"""Dashboard 聚合接口 — 小宇 + 命题官。"""
import json
import logging
import os
from django.db import models
from django.db.models import Sum, Count, Q
from django.utils import timezone
from datetime import timedelta
from rest_framework.views import APIView
from rest_framework.response import Response
from users.views import IsMember

logger = logging.getLogger(__name__)

USE_MEM0 = os.getenv('USE_MEM0', 'false').lower() == 'true'


class XiaoYuDashboardView(APIView):
    """GET /api/xiaoyu/dashboard/ — 聚合小宇 dashboard 所需的全部数据。"""
    permission_classes = [IsMember]

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

        # 6. Dashboard layout config (set by XiaoYu AI via set_dashboard_layout tool)
        default_config = {
            'section_order': ['plan', 'stats', 'mastery', 'reviews', 'exams', 'custom_cards'],
            'highlight': 'stats',
        }
        data['dashboard_config'] = user.dashboard_config or default_config

        # 7. Custom data cards (set by XiaoYu AI via create_dashboard_card tool)
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
        return {
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

    # ── Stats ─────────────────────────────────────────────
    def _get_stats(self, user, institution=None):
        from quizzes.models import UserQuestionStatus, ReviewLog
        now = timezone.now()
        uqs = UserQuestionStatus.objects.filter(user=user)
        if institution:
            uqs = uqs.filter(
                models.Q(question__institution=institution) |
                models.Q(question__institution__isnull=True)
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

        return {
            'total_attempted': total,
            'correct_count': correct,
            'accuracy': round(correct / total * 100, 1) if total else 0,
            'wrong_count': wrong,
            'streak_days': streak,
            'weekly_activity': weekly_questions,
            'is_new_user': total == 0,
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
                models.Q(question__institution=institution) |
                models.Q(question__institution__isnull=True)
            )
        due_qs = due_qs.select_related('question__knowledge_point').order_by('next_review_at')[:20]
        base_qs = UserQuestionStatus.objects.filter(user=user, next_review_at__lte=now)
        if institution:
            base_qs = base_qs.filter(
                models.Q(question__institution=institution) |
                models.Q(question__institution__isnull=True)
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
