from datetime import timedelta
from unittest.mock import patch
import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from users.login_sessions import LoginSession
from rest_framework.test import APIClient
from courses.models import Course, CourseModule, VideoTranscript, TranscriptSegment
from users.models import User, Institution
from users.models_workspace import Workspace, WorkspaceMembership, WorkspaceCourse, WorkspaceInvite, WorkspaceEnrollment

pytestmark = pytest.mark.django_db
BASE = '/api/users/workspace/'


@pytest.fixture
def setup_workspace(settings, tmp_path):
    settings.UNIMIND_CONTENT_INSTITUTION_ID = 'global'
    settings.MEDIA_ROOT = str(tmp_path)
    settings.OSS_ACCESS_KEY_ID = ''
    institution = Institution.objects.create(name='Smoke institution', slug='smoke-inst')
    workspace = Workspace.objects.create(institution=institution, service_ends_on=timezone.localdate() + timedelta(days=30), max_students=2)
    owner = User.objects.create_user(username='workspace-owner')
    WorkspaceMembership.objects.create(workspace=workspace, user=owner, role='admin')
    module = CourseModule.objects.create(institution=institution, subject='finance', name='Basics')
    course = Course.objects.create(institution=institution, module=module, title='PV', is_published=True, video_file='test-course.mp4')
    transcript = VideoTranscript.objects.create(course=course, full_text='Present value discounts future cash flows.', asr_status='completed', revision=1)
    segment = TranscriptSegment.objects.create(transcript=transcript, start_time=0, end_time=10, text=transcript.full_text, index=0)
    link = WorkspaceCourse.objects.create(workspace=workspace, course=course, processing_status='completed', transcript_revision=1,
        knowledge=[{'name': 'PV', 'children': ['Discounting'], 'source_segment_ids': [segment.pk]}])
    invite = WorkspaceInvite.objects.create(workspace=workspace, created_by=owner, name='Basics', expires_on=workspace.service_ends_on,
        service_ends_on=workspace.service_ends_on, max_uses=1)
    invite.courses.add(course)
    client = APIClient()
    client.force_authenticate(owner)
    return workspace, owner, course, link, invite, client


def test_join_is_explicit_idempotent_and_course_scoped(setup_workspace, user, auth_client):
    workspace, owner, course, link, invite, client = setup_workspace
    other = Course.objects.create(institution=workspace.institution, module=course.module, title='Unassigned', is_published=True)
    WorkspaceCourse.objects.create(workspace=workspace, course=other)
    legacy = Course.objects.create(title='Platform paid course', is_published=True)
    user.is_member = True
    user.institution = workspace.institution
    user.institution_role = 'owner'
    user.save()
    assert auth_client.get(BASE).data['workspace'] is None
    assert auth_client.post(BASE+'invites/', {}).status_code == 403
    data = {'code': invite.code}
    assert auth_client.post(BASE+'invite-preview/', data).status_code == 200
    assert auth_client.post(BASE+'join/', data).status_code == 200
    assert auth_client.post(BASE+'join/', data).status_code == 200
    invite.refresh_from_db()
    assert invite.used_count == 1
    result = auth_client.get('/api/courses/').data
    items = result.get('items', result.get('results', [])) if isinstance(result, dict) else result
    assert {item['id'] for item in items} == {course.pk}
    assert auth_client.get(f'/api/courses/{other.pk}/').status_code == 404
    assert auth_client.get(f'/api/courses/{legacy.pk}/transcript/').status_code == 404
    assert auth_client.get(BASE+f'courses/{other.pk}/').status_code == 404
    assert auth_client.get(BASE).data['members'] == []
    invite.is_active = False
    invite.save()
    assert auth_client.post(BASE+'join/', data).status_code == 200
    stranger = User.objects.create_user(username='unlisted')
    auth_client.force_authenticate(stranger)
    assert auth_client.post(BASE+'join/', data).status_code == 400


def test_pause_revokes_video_transcript_and_course_context(setup_workspace, user, auth_client, tmp_path):
    workspace, owner, course, link, invite, client = setup_workspace
    auth_client.post(BASE+'join/', {'code': invite.code})
    member = WorkspaceMembership.objects.get(user=user)
    (tmp_path/'test-course.mp4').write_bytes(b'synthetic video')
    assert auth_client.get(f'/api/courses/{course.pk}/transcript/').status_code == 200
    assert client.patch(BASE+f'members/{member.pk}/', {'active': False}, format='json').status_code == 200
    assert auth_client.get(f'/api/courses/{course.pk}/').status_code == 404
    assert auth_client.get(f'/api/courses/{course.pk}/transcript/').status_code == 404
    session = LoginSession.issue(user)
    assert auth_client.get('/media/test-course.mp4', HTTP_AUTHORIZATION=f'Token {session.key}').status_code in (403, 404)
    from courses.access import visible_courses
    from rest_framework.test import APIRequestFactory
    request = APIRequestFactory().get('/')
    request.user = user
    assert not visible_courses(request).exists()
    assert auth_client.post(BASE+'join/', {'code': invite.code}).status_code == 403
    assert client.patch(BASE+f'members/{member.pk}/', {'active': True}, format='json').status_code == 200
    assert auth_client.get(f'/api/courses/{course.pk}/').status_code == 200
    WorkspaceEnrollment.objects.filter(membership=member).update(service_ends_on=timezone.localdate()-timedelta(days=1))
    assert auth_client.get(f'/api/courses/{course.pk}/transcript/').status_code == 404


def test_cross_workspace_admin_and_invite_validation(setup_workspace):
    workspace, owner, course, link, invite, client = setup_workspace
    other_inst = Institution.objects.create(name='Other', slug='other')
    other_ws = Workspace.objects.create(institution=other_inst, service_ends_on=workspace.service_ends_on, max_students=10)
    other_course = Course.objects.create(title='Foreign', institution=other_inst, is_published=True)
    other_link = WorkspaceCourse.objects.create(workspace=other_ws, course=other_course)
    assert client.patch(BASE+f'courses/{other_course.pk}/', {'status':'draft'}, format='json').status_code == 404
    assert client.get(BASE+f'courses/{other_course.pk}/').status_code == 404
    payload = {'name':'Bad grant', 'courses':[other_course.pk], 'max_uses':1,
        'expires_at':str(workspace.service_ends_on), 'service_ends_at':str(workspace.service_ends_on)}
    assert client.post(BASE+'invites/', payload, format='json').status_code == 400
    payload['courses'] = [course.pk]
    assert client.post(BASE+'invites/', payload, format='json').status_code == 201
    student = User.objects.create_user(username='foreign-student')
    WorkspaceMembership.objects.create(user=student, workspace=other_ws)
    client.force_authenticate(student)
    assert client.post(BASE+'join/', {'code':invite.code}).status_code == 400


def test_upload_records_jobs_and_processing_publication(setup_workspace, django_capture_on_commit_callbacks):
    workspace, owner, course, link, invite, client = setup_workspace
    file = SimpleUploadedFile('new.mp4', b'\x00\x00\x00\x18ftypmp42'+b'0'*64, content_type='video/mp4')
    with patch('users.workspaces.views.dispatch_processing') as dispatch:
        with django_capture_on_commit_callbacks(execute=True):
            result = client.post(BASE+'courses/', {'module':'Uploaded', 'videos':[file]}, format='multipart')
        assert result.status_code == 201, result.data
        dispatch.assert_called_once()
    pending = WorkspaceCourse.objects.get(course__title='new')
    assert pending.processing_status == 'pending'
    assert not pending.course.is_published
    assert client.patch(BASE+f'courses/{pending.course_id}/', {'status':'published'}, format='json').status_code == 400
    transcript = pending.course.transcript
    transcript.full_text = 'A course on discounts.'
    transcript.asr_status = 'completed'
    transcript.revision = 1
    transcript.save()
    segment = TranscriptSegment.objects.create(transcript=transcript, start_time=0, end_time=20, text=transcript.full_text, index=0)
    from users.workspaces.tasks import process_course
    knowledge = [{'name':'Discounting', 'children':['PV'], 'source_segment_ids':[segment.pk]}]
    with patch('ai_engine.ai_service.AIService.structured_output', return_value=knowledge), patch('courses.services.ai_course_service.AICourseService.transcribe_video') as asr:
        process_course.run(pending.pk)
        asr.assert_not_called()
    pending.refresh_from_db()
    assert pending.processing_status == 'completed'
    assert pending.knowledge[0]['source_segment_ids'] == [segment.pk]
    assert client.patch(BASE+f'courses/{pending.course_id}/', {'status':'published'}, format='json').status_code == 200
    invalid = SimpleUploadedFile('bad.mp4', b'not a video', content_type='video/mp4')
    assert client.post(BASE+'courses/', {'module':'Bad', 'videos':[invalid]}, format='multipart').status_code == 400
