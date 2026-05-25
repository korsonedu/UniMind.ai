"""小宇 Dashboard 聚合接口 — 一次返回所有面板数据。"""
import json
import logging
from django.db.models import Sum
from django.utils import timezone
from datetime import timedelta
from rest_framework.views import APIView
from rest_framework.response import Response
from users.views import IsMember

logger = logging.getLogger(__name__)


class XiaoYuDashboardView(APIView):
    """GET /api/xiaoyu/dashboard/ — 聚合小宇 dashboard 所需的全部数据。"""
    permission_classes = [IsMember]

    def get(self, request):
        user = request.user
        data = {}

        # 1. Active Study Plan
        data['plan'] = self._get_plan(user)

        # 2. Learning Stats
        data['stats'] = self._get_stats(user)

        # 3. Knowledge Mastery
        data['mastery'] = self._get_mastery(user)

        # 4. Due Reviews
        data['reviews'] = self._get_reviews(user)

        # 5. Exam History
        data['exams'] = self._get_exams(user)

        # 6. Dashboard layout config (set by XiaoYu AI via set_dashboard_layout tool)
        default_config = {
            'section_order': ['plan', 'stats', 'mastery', 'reviews', 'exams'],
            'highlight': 'stats',
        }
        data['dashboard_config'] = user.dashboard_config or default_config

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
    def _get_stats(self, user):
        from quizzes.models import UserQuestionStatus, ReviewLog
        now = timezone.now()
        uqs = UserQuestionStatus.objects.filter(user=user)
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
    def _get_mastery(self, user):
        from quizzes.models import UserKnowledgeState
        qs = UserKnowledgeState.objects.filter(user=user).select_related('knowledge_point')
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
    def _get_reviews(self, user):
        from quizzes.models import UserQuestionStatus
        now = timezone.now()
        due_qs = (
            UserQuestionStatus.objects
            .filter(user=user, next_review_at__lte=now)
            .select_related('question__knowledge_point')
            .order_by('next_review_at')[:20]
        )
        return {
            'due_count': UserQuestionStatus.objects.filter(user=user, next_review_at__lte=now).count(),
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
