from django.test import TestCase
from rest_framework.test import APIRequestFactory, force_authenticate

from users.models import Institution, User
from .goal import LearningGoalView
from .models import Course, LearningGoal, VideoProgress


class LearningGoalTests(TestCase):
    def setUp(self):
        self.institution = Institution.objects.create(name='目标测试', slug='goal-test')
        self.user = User.objects.create_user(username='goal-student', institution=self.institution, is_member=True)
        self.other = User.objects.create_user(username='goal-other', institution=self.institution, is_member=True)
        self.course = Course.objects.create(title='金融学', institution=self.institution, video_file='finance.mp4')
        self.second = Course.objects.create(title='经济学', institution=self.institution, video_file='economics.mp4')
        self.hidden = Course.objects.create(title='不可见课程', institution=Institution.objects.create(name='其他', slug='goal-hidden'), video_file='hidden.mp4')

    def call(self, method='get', data=None, user=None):
        request = getattr(APIRequestFactory(), method)('/', data or {}, format='json')
        force_authenticate(request, user=user or self.user)
        return LearningGoalView.as_view()(request)

    def payload(self, **changes):
        return {'title': '完成基础课程', 'deadline': '2027-01-01', 'courses': [self.course.pk, self.second.pk], **changes}

    def test_goal_is_private_and_completion_updates_automatically(self):
        self.assertIsNone(self.call().data)
        self.assertEqual(self.call('put', self.payload()).status_code, 200)
        self.assertEqual(self.call().data['progress_percent'], 0)
        VideoProgress.objects.create(user=self.user, course=self.course, is_finished=True)
        VideoProgress.objects.create(user=self.other, course=self.second, is_finished=True)
        self.assertEqual(self.call().data['progress_percent'], 50)
        self.assertIsNone(self.call(user=self.other).data)
        self.call('put', self.payload(title='调整后的目标'))
        self.assertEqual(LearningGoal.objects.count(), 1)

    def test_invalid_or_hidden_courses_do_not_replace_goal(self):
        self.call('put', self.payload())
        for payload in [self.payload(courses=[]), self.payload(courses=[self.hidden.pk]), self.payload(title=' '), self.payload(deadline='无效日期')]:
            self.assertEqual(self.call('put', payload).status_code, 400)
        self.assertEqual(self.call().data['courses'], [self.course.pk, self.second.pk])

    def test_removed_course_access_does_not_leak_or_count_completion(self):
        self.call('put', self.payload())
        self.course.institution = self.hidden.institution
        self.course.save()
        self.second.delete()
        result = self.call().data
        self.assertEqual(result['courses'], [])
        self.assertEqual(result['progress_percent'], 0)
