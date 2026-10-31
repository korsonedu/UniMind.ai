"""Tests for meta-cognition task — learning data analysis and insight generation."""
import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'school_system.settings')
django.setup()

from unittest.mock import patch, MagicMock
from datetime import timedelta
from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.utils import timezone
from quizzes.models import ExamQuestionResult, QuizExam


class TestAnalyzeUser(TestCase):
    """Test _analyze_user insight generation logic."""

    def setUp(self):
        self.user = get_user_model().objects.create_user(username='learning-analysis')
        self.now = timezone.now()
        self.cutoff = self.now - timedelta(days=7)

    def test_no_activity_has_no_study_pattern(self):
        from ai_assistant.tasks import _analyze_user

        result = _analyze_user(self.user, self.cutoff, self.now)
        self.assertFalse(any(i['type'] == 'study_pattern' for i in result))

    def test_high_error_rate_uses_only_own_graded_results(self):
        from ai_assistant.tasks import _analyze_user

        exam = QuizExam.objects.create(user=self.user, status='partial')
        for position in range(10):
            ExamQuestionResult.objects.create(
                exam=exam, position=position, user_answer='',
                score=int(position >= 8), max_score=1,
                is_correct=position >= 8, status='graded',
            )
        for status in ('pending', 'failed'):
            ExamQuestionResult.objects.create(
                exam=exam, user_answer='', score=0, max_score=1, status=status,
            )
        other = get_user_model().objects.create_user(username='other-analysis')
        other_exam = QuizExam.objects.create(user=other, status='completed')
        ExamQuestionResult.objects.create(
            exam=other_exam, user_answer='', score=1, max_score=1,
            is_correct=True, status='graded',
        )
        result = _analyze_user(self.user, self.cutoff, self.now)
        texts = [i['text'] for i in result]
        self.assertTrue(any('错误率 80%（8/10）' in t for t in texts))


class TestStoreInsights(SimpleTestCase):
    """Test _store_insights writes to mem0."""

    def test_no_institution_skips(self):
        """Users without institution should be skipped without error."""
        from ai_assistant.tasks import _store_insights
        user = MagicMock()
        user.institution_id = None
        # Should return early without raising
        _store_insights(user, [{"type": "test", "text": "test"}])

    @patch('ai_assistant.tasks.TenantMemoryManager')
    def test_stores_each_insight(self, MockManager):
        from ai_assistant.tasks import _store_insights
        user = MagicMock()
        user.institution_id = 1
        manager = MockManager.return_value

        insights = [
            {"type": "study_pattern", "text": "测试洞察"},
            {"type": "engagement", "text": "高频用户"},
        ]

        _store_insights(user, insights)

        self.assertEqual(manager.add.call_count, 2)
        call_args = manager.add.call_args_list[0]
        self.assertEqual(call_args.kwargs['user_id'], user.id)
        self.assertIn('[系统分析]', call_args.kwargs['message'])
