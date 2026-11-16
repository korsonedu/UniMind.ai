"""Mobile media tickets retain course, feature, and content permissions."""
from unittest.mock import patch

import pytest
from django.contrib.auth.models import AnonymousUser
from django.core import signing
from rest_framework.test import APIClient, APIRequestFactory

from courses.models import Course, CourseModule
from school_system.media_serve import (
    MEDIA_TICKET_SALT, issue_media_ticket, media_serve,
    normalize_media_path, resolve_user_from_media_token,
)
from users.login_sessions import LoginSession
from users.models import CourseStudentStatus


@pytest.fixture
def media_setup(settings, tmp_path, user):
    settings.MEDIA_ROOT = str(tmp_path)
    settings.OSS_ACCESS_KEY_ID = ''
    settings.UNIMIND_CONTENT_INSTITUTION_ID = 'global'
    module = CourseModule.objects.create(name='Mobile public', is_public=True)
    course = Course.objects.create(title='Mobile video', is_published=True, module=module,
                                   video_file='videos/课 程.mp4')
    path = tmp_path / course.video_file.name
    path.parent.mkdir()
    path.write_bytes(b'0123456789')
    return course, tmp_path


@pytest.mark.parametrize('raw, expected', [
    ('/media/videos/%E8%AF%BE%20%E7%A8%8B.mp4', 'videos/课 程.mp4'),
    ('videos/a.mp4', 'videos/a.mp4'), ('media/videos/a.mp4', 'videos/a.mp4'),
    ('https://example.org/media/videos/a.mp4', 'videos/a.mp4'),
    ('', None), (None, None), ([], None), ('/etc/passwd', None),
    ('../a.mp4', None), ('/media/../a.mp4', None),
    ('/media/%2e%2e/a.mp4', None), ('videos/%2e/a.mp4', None),
    ('/media//a.mp4', None), ('videos/a\\b.mp4', None),
    ('videos/a%00.mp4', None), ('//evil/media/a.mp4', None),
    ('https://[bad/media/a.mp4', None), ('file:///media/a.mp4', None),
])
def test_normalize_media_path(raw, expected):
    assert normalize_media_path(raw) == expected


@pytest.mark.django_db
def test_media_ticket_header_auth_and_json_contract(media_setup, user):
    client = APIClient(enforce_csrf_checks=True)
    assert client.post('/api/media-ticket/', {'path': '/media/videos/a.mp4'}, format='json').status_code == 401
    client.credentials(HTTP_AUTHORIZATION='Token ' + LoginSession.issue(user).key)
    response = client.post('/api/media-ticket/', {'path': '/media/videos/%E8%AF%BE%20%E7%A8%8B.mp4'}, format='json')
    assert response.status_code == 200
    assert set(response.json()) == {'ticket', 'path', 'expires_in'}
    assert response.json()['path'] == '/media/videos/%E8%AF%BE%20%E7%A8%8B.mp4'
    assert response.json()['expires_in'] == 300
    assert response['Cache-Control'] == 'no-store'
    for data in ({}, {'path': '../a.mp4'}, {'path': ['a.mp4']}, []):
        assert client.post('/api/media-ticket/', data, format='json').status_code == 400


@pytest.mark.django_db
def test_media_token_get_head_and_ranges(media_setup, user):
    course, _ = media_setup
    ticket, path = issue_media_ticket(user, course.video_file.name)
    client = APIClient()
    url = '/media/videos/%E8%AF%BE%20%E7%A8%8B.mp4'
    assert client.get(url).status_code == 401
    for headers, status, expected in (({}, 200, b'0123456789'),
                                     ({'HTTP_RANGE': 'bytes=2-5'}, 206, b'2345'),
                                     ({'HTTP_RANGE': 'bytes=6-'}, 206, b'6789'),
                                     ({'HTTP_RANGE': 'bytes=-3'}, 206, b'789')):
        response = client.get(url, {'media_token': ticket}, **headers)
        assert response.status_code == status
        assert b''.join(response.streaming_content) == expected
        assert response['Content-Length'] == str(len(expected))
        response.close()
        request = APIRequestFactory().head(url, {'media_token': ticket}, **headers)
        request.user = AnonymousUser()
        response = media_serve(request, path)
        assert response.status_code == status
        assert not response.streaming and response.content == b''
        assert response['Content-Length'] == str(len(expected))
    response = client.get(url, {'media_token': ticket}, HTTP_RANGE='bytes=99-100')
    assert response.status_code == 416
    assert response['Content-Range'] == 'bytes */10'


@pytest.mark.django_db
def test_media_token_tampering_expiry_path_user_and_revocation(media_setup, user):
    course, _ = media_setup
    ticket, path = issue_media_ticket(user, course.video_file.name)
    assert resolve_user_from_media_token(ticket, path).pk == user.pk
    assert resolve_user_from_media_token(ticket, 'videos/other.mp4') is None
    assert resolve_user_from_media_token(ticket + 'x', path) is None
    with patch('django.core.signing.time.time', return_value=1):
        expired, _ = issue_media_ticket(user, path)
    assert resolve_user_from_media_token(expired, path) is None
    client = APIClient()
    assert client.get('/media/videos/other.mp4', {'media_token': ticket}).status_code == 401
    for value in ('broken', ticket + 'x', expired):
        assert client.get('/media/' + path, {'media_token': value}).status_code == 401
    for payload in ({'u': True, 'v': 0, 'p': path}, {'u': user.pk, 'v': False, 'p': path}, []):
        malformed = signing.dumps(payload, salt=MEDIA_TICKET_SALT)
        assert resolve_user_from_media_token(malformed, path) is None
    user.set_password('ChangedPassword123!')
    user.save()
    assert resolve_user_from_media_token(ticket, path) is None
    ticket, _ = issue_media_ticket(user, path)
    user.is_active = False
    user.save()
    assert resolve_user_from_media_token(ticket, path) is None


@pytest.mark.django_db
def test_media_ticket_preserves_course_visibility_and_feature_access(media_setup, user):
    course, _ = media_setup
    client = APIClient()
    ticket, path = issue_media_ticket(user, course.video_file.name)
    course.module.is_public = False
    course.module.save()
    assert client.get('/media/' + path, {'media_token': ticket}).status_code == 403
    CourseStudentStatus.objects.create(user=user, is_course_student=True)
    response = client.get('/media/' + path, {'media_token': ticket})
    assert response.status_code == 200
    response.close()
    with patch('users.feature_access.has_learning_feature', return_value=False):
        assert client.get('/media/' + path, {'media_token': ticket}).status_code == 403
    course.is_published = False
    course.save()
    assert client.get('/media/' + path, {'media_token': ticket}).status_code == 403


@pytest.mark.django_db
def test_media_existing_auth_public_covers_unknown_files_and_traversal(media_setup, user):
    course, root = media_setup
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION='Token ' + LoginSession.issue(user).key)
    response = client.get('/media/' + course.video_file.name)
    assert response.status_code == 200
    response.close()
    client.credentials()
    client.cookies['auth_token'] = LoginSession.issue(user).key
    response = client.get('/media/' + course.video_file.name)
    assert response.status_code == 200
    response.close()
    client.cookies.clear()
    cover = root / 'course_covers/public.png'
    cover.parent.mkdir()
    cover.write_bytes(b'image')
    response = client.get('/media/course_covers/public.png')
    assert response.status_code == 200
    response.close()
    course.cover_image = 'course_covers/public.png'
    course.is_published = False
    course.save()
    assert client.get('/media/course_covers/public.png').status_code == 404
    unknown = root / 'unassociated.mp4'
    unknown.write_bytes(b'secret')
    token, _ = issue_media_ticket(user, unknown.name)
    assert client.get('/media/unassociated.mp4', {'media_token': token}).status_code == 404
    for path in ('../secret', 'videos/../secret', 'videos\\secret', '/etc/passwd'):
        request = APIRequestFactory().get('/media/' + path)
        request.user = AnonymousUser()
        assert media_serve(request, path).status_code == 404


@pytest.mark.django_db
def test_media_ticket_other_user_and_institution_stay_restricted(media_setup, user):
    from django.contrib.auth import get_user_model
    from users.models import Institution
    course, _ = media_setup
    other = get_user_model().objects.create_user(username='other-mobile', password='OtherPassword123!')
    token, path = issue_media_ticket(other, course.video_file.name)
    assert resolve_user_from_media_token(token, path).pk == other.pk
    institution = Institution.objects.create(name='Other institution')
    course.institution = institution
    course.save()
    assert APIClient().get('/media/' + path, {'media_token': token}).status_code == 403


@pytest.mark.django_db
@pytest.mark.parametrize('method', ['GET', 'HEAD'])
@pytest.mark.parametrize('workspace_member, expected_ttl', [(False, 3600), (True, 300)])
def test_media_ticket_oss_uses_request_method(media_setup, user, settings, method, workspace_member, expected_ttl):
    from datetime import timedelta
    from types import SimpleNamespace
    from unittest.mock import MagicMock
    from django.utils import timezone
    from users.models import Institution
    from users.models_workspace import Workspace, WorkspaceCourse, WorkspaceMembership
    course, _ = media_setup
    if workspace_member:
        institution = Institution.objects.create(name='Mobile workspace inst')
        course.institution = institution
        course.save(update_fields=['institution'])
        workspace = Workspace.objects.create(
            institution=institution,
            service_ends_on=timezone.localdate() + timedelta(days=30),
            max_students=10,
        )
        WorkspaceMembership.objects.create(user=user, workspace=workspace, role='admin')
        WorkspaceCourse.objects.create(workspace=workspace, course=course)
        from users.workspaces.identity import select_learner
        user = select_learner(user, str(workspace.pk))
    ticket, path = issue_media_ticket(user, course.video_file.name)
    settings.OSS_ACCESS_KEY_ID = 'test-only'
    settings.OSS_ACCESS_KEY_SECRET = 'test-only'
    settings.OSS_ENDPOINT = 'https://example.invalid'
    settings.OSS_BUCKET_NAME = 'test-only'
    request = APIRequestFactory().generic(method, '/media/' + path + '?media_token=' + ticket)
    request.user = AnonymousUser()
    bucket = MagicMock()
    bucket.sign_url.return_value = 'https://example.invalid/signed'
    oss = SimpleNamespace(Auth=MagicMock(), Bucket=MagicMock(return_value=bucket))
    with patch.dict('sys.modules', {'oss2': oss}):
        response = media_serve(request, path)
    assert response.status_code == 302
    bucket.sign_url.assert_called_once_with(method, path, expected_ttl)
