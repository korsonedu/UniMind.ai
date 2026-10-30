"""Synthetic desktop manifest authorization and expiry smoke."""
from datetime import datetime, timedelta
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest
from rest_framework.test import APIClient


@pytest.mark.django_db
def test_offline_manifest_permissions_and_recheck(auth_client, user, settings, tmp_path):
    from courses.models import Course, CourseModule
    from users.models import CourseStudentStatus
    settings.UNIMIND_CONTENT_INSTITUTION_ID = 'global'
    settings.MEDIA_ROOT = str(tmp_path)
    module = CourseModule.objects.create(subject='offline smoke', name='public', is_public=True)
    public = Course.objects.create(title='public video', module=module, video_file='public.mp4')
    private = Course.objects.create(title='private video', video_file='private.mp4')
    for name in ('public.mp4', 'private.mp4'):
        (tmp_path / name).write_bytes(b'synthetic-video')
    url = f'/api/courses/{private.pk}/offline-manifest/'
    assert APIClient().get(url).status_code == 401
    assert auth_client.get(url).status_code == 404
    response = auth_client.get(f'/api/courses/{public.pk}/offline-manifest/')
    assert response.status_code == 200
    assert response.json()['user_id'] == user.pk
    assert response.json()['video'] == {'url': '/media/public.mp4', 'filename': 'public.mp4', 'size': 15}
    status = CourseStudentStatus.objects.create(user=user, is_course_student=True)
    first = auth_client.get(url).json()
    assert first['course_id'] == private.pk
    private.video_file = 'replacement.mp4'
    (tmp_path / 'replacement.mp4').write_bytes(b'new-video')
    private.save()
    assert auth_client.get(url).json()['version'] != first['version']
    status.is_course_student = False
    status.save()
    checked = auth_client.post('/api/courses/offline-access/', {'course_ids': [public.pk, private.pk]}, format='json')
    assert checked.status_code == 200
    assert [item['course_id'] for item in checked.json()['courses']] == [public.pk]
    assert auth_client.get(url).status_code == 404
    user.is_active = False
    user.save()
    assert auth_client.get(f'/api/courses/{public.pk}/offline-manifest/').status_code == 403


@pytest.mark.django_db
def test_offline_expiry_includes_final_shanghai_day(auth_client, user, settings, tmp_path):
    from courses.models import Course, CourseModule
    from users.models import CourseStudentStatus, StudentCohort
    settings.UNIMIND_CONTENT_INSTITUTION_ID = 'global'
    settings.MEDIA_ROOT = str(tmp_path)
    now = datetime(2026, 10, 29, 23, 30, tzinfo=ZoneInfo('Asia/Shanghai'))
    cohort = StudentCohort.objects.create(name='offline synthetic', target_year=2027,
        starts_on=now.date(), ends_on=now.date(), is_active=True)
    status = CourseStudentStatus.objects.create(user=user, is_course_student=True, cohort=cohort)
    course = Course.objects.create(title='expiry', video_file='expiry.mp4')
    module = CourseModule.objects.create(subject='offline expiry', name='public', is_public=True)
    public = Course.objects.create(title='public expiry', module=module, video_file='public-expiry.mp4')
    (tmp_path / 'expiry.mp4').write_bytes(b'video')
    (tmp_path / 'public-expiry.mp4').write_bytes(b'video')
    url = f'/api/courses/{course.pk}/offline-manifest/'
    with patch('django.utils.timezone.now', return_value=now):
        manifest = auth_client.get(url).json()
        assert manifest['expires_at'] == int((now + timedelta(minutes=30)).timestamp())
        status.cohort = None
        status.save()
        assert auth_client.get(url).json()['expires_at'] == int((now + timedelta(hours=24)).timestamp())
        status.cohort = cohort
        status.save()
    with patch('django.utils.timezone.now', return_value=now + timedelta(minutes=30)):
        assert auth_client.get(url).status_code == 404
        assert auth_client.post('/api/courses/offline-access/', {'course_ids': [course.pk]}, format='json').json()['courses'] == []
        manifest = auth_client.get(f'/api/courses/{public.pk}/offline-manifest/').json()
        assert manifest['expires_at'] == int((now + timedelta(minutes=30, hours=24)).timestamp())
        checked = auth_client.post('/api/courses/offline-access/', {'course_ids': [course.pk, public.pk]}, format='json')
        assert [item['course_id'] for item in checked.json()['courses']] == [public.pk]


@pytest.mark.django_db
def test_offline_missing_video_and_invalid_batch(auth_client, user, settings, tmp_path):
    from courses.models import Course
    from users.models import CourseStudentStatus
    settings.UNIMIND_CONTENT_INSTITUTION_ID = 'global'
    settings.MEDIA_ROOT = str(tmp_path)
    CourseStudentStatus.objects.create(user=user, is_course_student=True)
    absent = Course.objects.create(title='no video')
    missing = Course.objects.create(title='missing storage object', video_file='missing.mp4')
    assert auth_client.get(f'/api/courses/{absent.pk}/offline-manifest/').status_code == 404
    assert auth_client.get(f'/api/courses/{missing.pk}/offline-manifest/').status_code == 503
    for ids in ([True], ['1'], list(range(1, 102))):
        assert auth_client.post('/api/courses/offline-access/', {'course_ids': ids}, format='json').status_code == 400
