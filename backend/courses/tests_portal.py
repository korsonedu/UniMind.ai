import uuid
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate
from courses.models import Course, LearningActivity, VideoProgress, WatchLater
from courses.portal import LearningActivityView, LearningProgressView, WatchLaterDetailView, WatchLaterListView
from courses.views import VideoProgressUpdateView
from users.models import Institution


class CoursePortalTests(TestCase):
    def setUp(self):
        self.inst = Institution.objects.create(name='A', slug='portal-a')
        self.enterContext(self.settings(UNIMIND_CONTENT_INSTITUTION_ID=str(self.inst.pk)))
        self.other_inst = Institution.objects.create(name='B', slug='portal-b')
        self.user = get_user_model().objects.create_user(username='learner', is_member=True, institution=self.inst)
        self.other = get_user_model().objects.create_user(username='other', is_member=True, institution=self.inst)
        self.course = Course.objects.create(title='课程', institution=self.inst, video_file='sample.mp4', elo_reward=20)
        self.hidden = Course.objects.create(title='其他机构课程', institution=self.other_inst, video_file='other.mp4')

    def call(self, view, method='get', data=None, pk=None, user=None):
        request = getattr(APIRequestFactory(), method)('/', data or {}, format='json')
        force_authenticate(request, user=user or self.user)
        return view.as_view()(request, **({'pk': pk} if pk else {}))

    @patch('courses.views.record_event')
    def test_retry_deduplicates_watch_time_and_reward(self, _):
        event = {'position': 15, 'duration': 120, 'watched_seconds': 15, 'event_id': str(uuid.uuid4())}
        self.assertEqual(self.call(VideoProgressUpdateView, 'post', event, self.course.pk).status_code, 200)
        self.call(VideoProgressUpdateView, 'post', event, self.course.pk)
        first = self.call(VideoProgressUpdateView, 'post', {'is_finished': True}, self.course.pk)
        second = self.call(VideoProgressUpdateView, 'post', {'is_finished': True}, self.course.pk)
        self.assertEqual(first.data['elo_added'], 20)
        self.assertEqual(second.data['elo_added'], 0)
        self.user.refresh_from_db()
        self.assertEqual(self.user.elo_score, 1020)
        activity = self.call(LearningActivityView).data
        self.assertEqual(activity['totals'][0]['watched_seconds'], 15)
        self.assertEqual(activity['totals'][0]['elo_earned'], 20)
        self.assertEqual(activity['totals'][0]['completions'], 1)

    def test_progress_is_private_and_institution_scoped(self):
        VideoProgress.objects.create(user=self.user, course=self.course, last_position=15)
        VideoProgress.objects.create(user=self.user, course=self.hidden, last_position=30)
        VideoProgress.objects.create(user=self.other, course=self.course, last_position=60)
        records = self.call(LearningProgressView).data
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]['last_position'], 15)
        self.assertEqual(self.call(VideoProgressUpdateView, 'post', {'position': 5}, self.hidden.pk).status_code, 404)

    def test_queue_is_private_idempotent_and_scoped(self):
        self.call(WatchLaterDetailView, 'put', pk=self.course.pk)
        self.call(WatchLaterDetailView, 'put', pk=self.course.pk)
        self.assertEqual(WatchLater.objects.count(), 1)
        self.assertEqual(self.call(WatchLaterListView, user=self.other).data, [])
        self.assertEqual(self.call(WatchLaterDetailView, 'put', pk=self.hidden.pk).status_code, 404)
        self.assertEqual(self.call(WatchLaterDetailView, 'delete', pk=self.course.pk).status_code, 204)
        self.assertEqual(self.call(WatchLaterListView).data, [])

    def test_activity_is_private_and_uses_beijing_date(self):
        event = LearningActivity.objects.create(user=self.user, course=self.course, watched_seconds=20)
        boundary = timezone.now().replace(hour=17, minute=0, second=0, microsecond=0)
        LearningActivity.objects.filter(pk=event.pk).update(created_at=boundary)
        LearningActivity.objects.create(user=self.other, course=self.course, watched_seconds=900)
        LearningActivity.objects.create(user=self.user, course=self.hidden, watched_seconds=800)
        data = self.call(LearningActivityView).data
        self.assertEqual(len(data['totals']), 1)
        self.assertEqual(data['totals'][0]['watched_seconds'], 20)
        self.assertEqual(data['days'][0]['date'], (boundary + timedelta(hours=8)).date())

    @patch('courses.views.record_event')
    def test_invalid_activity_and_existing_completion(self, _):
        for payload in [{'position': -1}, {'watched_seconds': 121, 'event_id': str(uuid.uuid4())}, {'watched_seconds': 10}, {'duration': 'Infinity'}]:
            self.assertEqual(self.call(VideoProgressUpdateView, 'post', payload, self.course.pk).status_code, 400)
        VideoProgress.objects.create(user=self.user, course=self.course, is_finished=True, last_position=120)
        response = self.call(VideoProgressUpdateView, 'post', {'is_finished': True}, self.course.pk)
        self.assertEqual(response.data['elo_added'], 0)
        self.assertEqual(response.data['progress']['last_position'], 120)
        self.assertEqual(LearningActivity.objects.count(), 0)
