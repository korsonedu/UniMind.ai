"""Offline uploads share the online completion award and learning records."""
import uuid
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from courses.models import Course, LearningActivity, VideoProgress
from users.models import CourseStudentStatus, LearningSession


@pytest.fixture
def offline_event(auth_client, user, settings, tmp_path):
    settings.UNIMIND_CONTENT_INSTITUTION_ID = 'global'
    settings.MEDIA_ROOT = str(tmp_path)
    CourseStudentStatus.objects.create(user=user, is_course_student=True)
    (tmp_path / 'offline.mp4').write_bytes(b'video')
    course = Course.objects.create(title='offline progress', video_file='offline.mp4', elo_reward=20)
    manifest = auth_client.get(f'/api/courses/{course.pk}/offline-manifest/').json()
    now = timezone.now()
    body = {'event_id': str(uuid.uuid4()), 'grant': manifest['grant'], 'version': manifest['version'],
            'position': 15, 'duration': 120, 'watched_seconds': 15, 'focused_seconds': 10,
            'started_at': (now - timedelta(seconds=20)).isoformat(),
            'ended_at': (now - timedelta(seconds=5)).isoformat(), 'is_finished': True}
    return course, body, f'/api/courses/{course.pk}/offline-progress/'


@pytest.mark.django_db
def test_offline_retry_time_reward_and_position(auth_client, user, offline_event):
    course, body, url = offline_event
    first = auth_client.post(url, body, format='json')
    assert first.status_code == 200, first.data
    assert first.data['elo_added'] == 20
    assert auth_client.post(url, body, format='json').data['duplicate'] is True
    assert LearningActivity.objects.count() == LearningSession.objects.count() == 1
    assert LearningSession.objects.get().active_seconds == 15
    assert LearningSession.objects.get().focused_seconds == 10
    user.refresh_from_db()
    assert user.elo_score == 1020

    # Zero-time completion/checkpoints retain their event receipt without fake study time.
    finished = {**body, 'event_id': str(uuid.uuid4()), 'watched_seconds': 0, 'focused_seconds': 0}
    assert auth_client.post(url, finished, format='json').data['elo_added'] == 0
    assert auth_client.post(url, finished, format='json').data['duplicate']
    assert LearningSession.objects.count() == 1

    # A later online checkpoint wins over delayed offline position snapshots.
    assert auth_client.post(f'/api/courses/{course.pk}/progress/', {'position': 80}, format='json').status_code == 200
    body.update(event_id=str(uuid.uuid4()), position=30)
    assert auth_client.post(url, body, format='json').data['elo_added'] == 0
    progress = VideoProgress.objects.get()
    assert progress.last_position == 80 and progress.is_finished
    assert sum(LearningActivity.objects.values_list('watched_seconds', flat=True)) == 30
    assert sum(LearningSession.objects.values_list('active_seconds', flat=True)) == 30
    assert LearningActivity.objects.latest('pk').created_at.isoformat() == body['ended_at']


@pytest.mark.django_db
def test_offline_actor_revocation_and_event_conflicts(auth_client, user, offline_event):
    from django.contrib.auth import get_user_model
    course, body, url = offline_event
    original = body.copy()
    other = get_user_model().objects.create_user(username='offline-other')
    client = APIClient()
    client.force_authenticate(other)
    response = client.post(url, body, format='json')
    assert response.status_code == 403 and response.data['code'] == 'account_mismatch'
    assert APIClient().post(url, body, format='json').status_code == 401
    assert auth_client.post(url, body, format='json').status_code == 200
    second = Course.objects.create(title='other course', video_file='offline.mp4')
    grant = auth_client.get(f'/api/courses/{second.pk}/offline-manifest/').json()
    body.update(grant=grant['grant'], version=grant['version'])
    response = auth_client.post(f'/api/courses/{second.pk}/offline-progress/', body, format='json')
    assert response.data['code'] == 'event_conflict' and response.data['terminal']
    assert not VideoProgress.objects.filter(course=second).exists()

    body['event_id'] = str(uuid.uuid4())
    LearningSession.objects.create(user=user, session_id=body['event_id'], kind='practice',
        question_ids=[1], started_at=timezone.now(), ended_at=timezone.now(), active_seconds=1)
    response = auth_client.post(f'/api/courses/{second.pk}/offline-progress/', body, format='json')
    assert response.data['code'] == 'event_conflict'
    assert LearningSession.objects.get(session_id=body['event_id']).kind == 'practice'
    CourseStudentStatus.objects.filter(user=user).update(is_course_student=False)
    response = auth_client.post(url, original, format='json')
    assert response.data['terminal'] and response.data['code'] == 'access_revoked'
    assert LearningActivity.objects.count() == 1
    from users.models import UserAccessProfile
    UserAccessProfile.objects.create(user=user, blocked_permissions=['course.video'])
    user.refresh_from_db()
    response = auth_client.post(url, original, format='json')
    assert response.status_code == 403
    assert response.data['terminal'] is True and response.data['code'] == 'access_revoked'


@pytest.mark.django_db
def test_offline_grant_interval_version_and_late_upload(auth_client, user, offline_event):
    from django.core import signing
    from courses.offline import GRANT_SALT
    course, body, url = offline_event
    original = body.copy()
    for changes, code in [({'grant': body['grant'] + 'bad'}, 'invalid_grant'),
                          ({'version': 'old'}, 'version_changed'),
                          ({'focused_seconds': 16}, 'invalid_interval'),
                          ({'watched_seconds': 121}, 'invalid_payload'),
                          ({'ended_at': (timezone.now() + timedelta(seconds=60)).isoformat()}, 'invalid_interval')]:
        response = auth_client.post(url, {**body, **changes}, format='json')
        assert response.data['code'] == code and response.data['terminal']
    grant = signing.loads(body['grant'], salt=GRANT_SALT)
    future = timezone.now() + timedelta(days=2)
    with patch('django.utils.timezone.now', return_value=future):
        assert auth_client.post(url, body, format='json').status_code == 200
    with patch('django.utils.timezone.now', return_value=future + timedelta(days=7)):
        response = auth_client.post(url, body, format='json')
        assert response.data['code'] == 'grant_expired'
    body = {**original, 'event_id': str(uuid.uuid4()),
            'ended_at': timezone.datetime.fromtimestamp(grant['expires_at'] + 1, tz=timezone.get_default_timezone()).isoformat()}
    assert auth_client.post(url, body, format='json').data['code'] == 'invalid_interval'
    course.title = 'changed video metadata'
    course.save()
    assert auth_client.post(url, original, format='json').data['code'] == 'version_changed'
