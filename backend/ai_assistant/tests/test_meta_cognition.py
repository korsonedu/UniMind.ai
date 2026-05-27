"""Tests for meta-cognition task — learning data analysis and insight generation."""
import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'school_system.settings')
django.setup()

from unittest.mock import patch, MagicMock
from django.test import SimpleTestCase


class TestAnalyzeUser(SimpleTestCase):
    """Test _analyze_user insight generation logic."""

    @patch('quizzes.models.QuizExam')
    @patch('ai_assistant.models.AIChatMessage')
    def test_no_activity_returns_empty(self, MockChat, MockExam):
        from ai_assistant.tasks import _analyze_user
        MockExam.objects.filter.return_value.order_by.return_value.__getitem__ = MagicMock(return_value=[])
        MockChat.objects.filter.return_value.count.return_value = 0
        MockChat.objects.filter.return_value.annotate.return_value.values.return_value.annotate.return_value.order_by.return_value = []

        user = MagicMock()
        from datetime import datetime
        now = datetime.now()
        result = _analyze_user(user, now, now)
        self.assertIsInstance(result, list)

    @patch('quizzes.models.QuizExam')
    @patch('ai_assistant.models.AIChatMessage')
    def test_high_error_rate_insight(self, MockChat, MockExam):
        from ai_assistant.tasks import _analyze_user
        exam = MagicMock()
        exam.results = {
            'questions': [
                {'is_correct': False} for _ in range(8)
            ] + [
                {'is_correct': True} for _ in range(2)
            ]
        }
        MockExam.objects.filter.return_value.order_by.return_value.__getitem__ = MagicMock(return_value=[exam])
        MockChat.objects.filter.return_value.count.return_value = 5
        MockChat.objects.filter.return_value.annotate.return_value.values.return_value.annotate.return_value.order_by.return_value = [
            {'hour': 14, 'cnt': 5}
        ]

        user = MagicMock()
        from datetime import datetime
        now = datetime.now()
        result = _analyze_user(user, now, now)

        texts = [i['text'] for i in result]
        self.assertTrue(any('错误率' in t for t in texts))


class TestStoreInsights(SimpleTestCase):
    """Test _store_insights writes to mem0."""

    @patch('ai_assistant.tasks._store_insights')
    def test_no_institution_skips(self, mock_store):
        """Users without institution should be skipped."""
        from ai_assistant.tasks import _store_insights as real_store
        user = MagicMock()
        user.institution_id = None
        real_store(user, [{"type": "test", "text": "test"}])

    @patch('ai_assistant.services.tenant_memory.TenantMemoryManager')
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
