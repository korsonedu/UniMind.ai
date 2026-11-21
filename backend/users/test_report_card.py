from django.test import override_settings
from rest_framework.test import APITestCase
from .models import User
from .views import _build_report_data


@override_settings(CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}})
class ReportCardTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='report_owner', nickname='报告测试学员')
        self.client.force_authenticate(self.user)

    def test_old_student_report_routes_are_retired(self):
        for path in ('/api/users/me/report-card/', '/api/users/me/report-card/pdf/'):
            self.assertEqual(self.client.get(path).status_code, 404)

    def test_report_ignores_zero_rep_rows(self):
        from quizzes.models import Question, UserQuestionStatus

        question = Question.objects.create(text='仅收藏')
        UserQuestionStatus.objects.create(user=self.user, question=question, reps=0)

        data = _build_report_data(self.user)
        self.assertEqual(data['student']['id'], self.user.pk)
        self.assertEqual(data['stats']['attempted_questions'], 0)
        self.assertEqual(data['stats']['accuracy'], 0)
        self.assertFalse(data['stats']['has_attempts'])

    def test_date_range_report_does_not_filter_exams_by_review_field(self):
        from datetime import timedelta

        from django.utils import timezone

        now = timezone.now()
        data = _build_report_data(
            self.user, date_from=now - timedelta(days=7), date_to=now,
        )

        self.assertIn('stats', data)
        self.assertEqual(data['stats']['attempted_questions'], 0)
