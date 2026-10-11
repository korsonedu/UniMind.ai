from types import SimpleNamespace
from unittest.mock import patch

from django.http import QueryDict
from django.test import TestCase

from users.models import User
from .models import KnowledgePoint, Question
from .views_question import QuestionListView


class PracticeQuestionFilterTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='practice-filter', role='student')
        self.subject = KnowledgePoint.objects.create(name='金融学', level='sub')
        self.topic = KnowledgePoint.objects.create(name='利率', parent=self.subject)
        self.normal = Question.objects.create(text='基础题', knowledge_point=self.topic)
        self.hard = Question.objects.create(text='困难题', knowledge_point=self.topic, difficulty_level='hard')
        self.other = Question.objects.create(text='其他学科困难题', difficulty_level='hard')

    def queryset(self, query):
        view = QuestionListView()
        view.request = SimpleNamespace(user=self.user, query_params=QueryDict(query))
        return view.get_queryset()

    @patch('quizzes.views_question.build_adaptive_question_ids')
    def test_subject_and_difficulty_filter_before_adaptive_selection(self, scheduler):
        def select(**kwargs):
            self.assertEqual(list(kwargs['base_queryset'].values_list('id', flat=True)), [self.hard.id])
            self.assertEqual(kwargs['preference'], 'review_first')
            return {'question_ids': [self.hard.id], 'meta': {}}

        scheduler.side_effect = select
        result = self.queryset(f'limit=5&sub_ids={self.subject.id}&difficulty_level=hard&preference=review_first')
        self.assertEqual(list(result), [self.hard])

    def test_explicit_drill_ids_preserve_order_and_apply_difficulty(self):
        ids = f'{self.other.id},{self.normal.id},{self.hard.id}'
        self.assertEqual(list(self.queryset(f'ids={ids}')), [self.other, self.normal, self.hard])
        self.assertEqual(list(self.queryset(f'ids={ids}&difficulty_level=hard')), [self.other, self.hard])

    def test_empty_difficulty_keeps_mixed_questions(self):
        self.assertCountEqual(self.queryset('search=题&difficulty_level='), [self.normal, self.hard, self.other])
