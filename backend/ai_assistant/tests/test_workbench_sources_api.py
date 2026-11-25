from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
from urllib.parse import parse_qs, urlsplit

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIClient

from ai_assistant.models import ConversationProject, ProjectSource
from ai_assistant.services import learning_resources
from ai_assistant.tasks import process_project_source_task
from courses.asr import ASRProviderRegistry, TranscriptResult, TranscriptSegment as ASRSegment
from courses.models import Course, CourseModule, TranscriptSegment, VideoProgress, VideoTranscript
from users.login_sessions import LoginSession
from users.models import CourseStudentStatus, Institution, User, UserAccessProfile
from users.models_workspace import Workspace, WorkspaceCourse, WorkspaceMembership

from .test_workbench_sources_pipeline import _docx, _pdf, _pptx


pytestmark = pytest.mark.django_db(transaction=True)


def signed_in(user):
    client = APIClient()
    client.cookies['auth_token'] = LoginSession.issue(user).key
    return client


@pytest.fixture
def workbench(user, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    settings.UNIMIND_CONTENT_INSTITUTION_ID = 'global'
    settings.CELERY_TASK_ALWAYS_EAGER = True
    project = ConversationProject.objects.create(user=user, name='金融学项目')
    return signed_in(user), project, f'/api/ai/projects/{project.pk}/sources/'


def import_source(client, sources_url, **payload):
    return client.post(f'{sources_url}import/', payload, format='json')


def test_multipart_documents_return_ready_and_ordered_chunks(workbench, settings):
    client, project, url = workbench
    settings.CELERY_TASK_ALWAYS_EAGER = False
    pdf = _pdf(['First page.'], ['Second page.'])
    response = client.post(f'{url}upload/', {'files': [
        SimpleUploadedFile('outline.PDF', pdf, content_type='text/html'),
        SimpleUploadedFile('lecture.pptx', _pptx()),
        SimpleUploadedFile('notes.md', '# 笔记\n\n利率期限结构'.encode()),
        SimpleUploadedFile('guide.docx', _docx()),
    ]}, format='multipart')
    assert response.status_code == 201, response.data
    sources = response.data['sources']
    assert [source['source_type'] for source in sources] == ['pdf', 'pptx', 'text', 'docx']
    assert [source['status'] for source in sources] == ['ready'] * 4
    assert all(source['project_id'] == project.pk for source in sources)
    pdf_source = sources[0]
    assert (pdf_source['title'], pdf_source['file_size'], pdf_source['unit_count']) == ('outline.PDF', len(pdf), 2)
    detail = client.get(f"{url}{pdf_source['id']}/")
    assert detail.status_code == 200
    assert [(chunk['chunk_index'], chunk['anchor_type'], chunk['page_number']) for chunk in detail.data['chunks']] == [
        (0, 'page', 1), (1, 'page', 2),
    ]
    assert detail.data['chunks'][1]['content'] == 'Second page.'
    assert detail.data['chunks'][1]['locator_label'] == 'P.2'
    preview = client.get(pdf_source['file_preview_url'])
    assert preview.status_code == 200
    assert preview['Content-Type'] == 'application/pdf'
    assert preview['Content-Disposition'].startswith('inline;')
    assert preview['X-Content-Type-Options'] == 'nosniff'
    assert b''.join(preview.streaming_content) == pdf
    listed = client.get(url).data
    assert (listed['total_count'], listed['selected_count'], listed['ready_count']) == (4, 4, 4)
    assert all('chunks' not in source for source in listed['sources'])
    assert client.get(reverse('conversation-project-detail', args=[project.pk])).data['source_count'] == 4
    assert client.get('/api/ai/projects/').data[0]['source_count'] == 4


def test_upload_validates_all_files_before_saving(workbench):
    client, project, url = workbench
    for filename, content, message in (
        ('empty.md', b'', '非空'),
        ('invalid.html', b'<p>html</p>', '格式不受支持'),
    ):
        response = client.post(f'{url}upload/', {'files': [
            SimpleUploadedFile('valid.txt', b'content'),
            SimpleUploadedFile(filename, content),
        ]}, format='multipart')
        assert response.status_code == 400
        assert message in str(response.data['files'])
        assert not project.workbench_sources.exists()
    assert client.post(f'{url}upload/', {}, format='multipart').status_code == 400


def test_web_import_retry_and_reimport_after_redirect(workbench, monkeypatch):
    client, project, url = workbench
    link = 'https://example.org/article'
    resolved = 'https://example.org/final'
    fetch = Mock(side_effect=[
        ValidationError('页面暂时不可读。'),
        (resolved, '<title>网页标题</title><h1>本章</h1><p>第一版正文。</p>'),
        (resolved, '<title>新网页标题</title><h1>新章节</h1><p>更新后的正文。</p>'),
    ])
    monkeypatch.setattr(learning_resources, 'public_text', fetch)
    response = import_source(client, url, kind='web_url', url=link)
    assert response.status_code == 201
    assert (response.data['status'], response.data['error_message']) == ('failed', '页面暂时不可读。')
    detail_url = f"{url}{response.data['id']}/"
    retry = client.patch(detail_url, {'action': 'retry'}, format='json')
    assert retry.status_code == 200
    assert (retry.data['status'], retry.data['title'], retry.data['source_url']) == ('ready', '网页标题', resolved)
    refreshed = import_source(client, url, kind='web_url', url=link, title='我的网页资料')
    assert refreshed.status_code == 200
    assert refreshed.data['id'] == response.data['id']
    assert refreshed.data['title'] == '我的网页资料'
    assert '更新后的正文。' in client.get(detail_url).data['chunks'][0]['content']
    assert project.workbench_sources.count() == 1
    assert [call.args for call in fetch.call_args_list] == [(link,), (link,), (link,)]


def test_station_course_import_requires_access_and_updates_subtitles(workbench):
    client, project, url = workbench
    course = Course.objects.create(title='站内课程', is_published=True)
    detail_url = reverse('course-detail', args=[course.pk])
    assert import_source(client, url, kind='course', course_id=course.pk).status_code == 404
    picker = {'workbench_project': project.pk, 'search': '站内'}
    assert client.get('/api/courses/', picker).data['items'] == []
    CourseStudentStatus.objects.create(user=project.user, is_course_student=True)
    Course.objects.create(title='未发布的站内课程', is_published=False)
    Course.objects.create(title='其他主题', is_published=True)
    assert [item['id'] for item in client.get('/api/courses/', picker).data['items']] == [course.pk]
    assert client.get('/api/courses/').data['items'] == []
    other_project = ConversationProject.objects.create(user=User.objects.create_user(username='other-picker-owner'), name='私有项目')
    assert client.get('/api/courses/', {**picker, 'workbench_project': other_project.pk}).status_code == 404
    transcript = VideoTranscript.objects.create(course=course, asr_status='completed')
    segment = TranscriptSegment.objects.create(
        transcript=transcript, index=0, start_time=8, end_time=14, text='站内课程字幕。',
    )
    imported = import_source(client, url, kind='course', course_id=course.pk)
    assert imported.status_code == 201
    assert imported.data['course_id'] == course.pk
    play_link = urlsplit(imported.data['companion_play_url'])
    assert play_link.path == f'/course/{course.pk}'
    assert parse_qs(play_link.query) == {'project': [str(project.pk)]}
    assert client.get(detail_url).data['is_workbench_companion'] is False
    assert client.get(detail_url, {'workbench_project': project.pk}).data['id'] == course.pk
    assert client.get(detail_url, {'workbench_project': project.pk + 1}).status_code == 404

    segment.text = '更新后的课程字幕。'
    segment.save()
    updated = import_source(client, url, kind='course', course_id=course.pk)
    assert updated.status_code == 200
    assert updated.data['id'] == imported.data['id']
    assert project.workbench_sources.count() == 1
    detail = client.get(f"{url}{updated.data['id']}/")
    assert detail.data['chunks'][0]['content'] == '更新后的课程字幕。'
    assert detail.data['chunks'][0]['start_seconds'] == 8

    handout = Course.objects.create(
        title='只有讲义的课程', is_published=True,
        courseware=SimpleUploadedFile('handout.pdf', _pdf(['Lecture handout.'])),
    )
    imported = import_source(client, url, kind='course', course_id=handout.pk)
    assert imported.status_code == 201 and imported.data['status'] == 'ready'
    chunks = client.get(f"{url}{imported.data['id']}/").data['chunks']
    assert [(chunk['anchor_type'], chunk['content']) for chunk in chunks] == [('page', 'Lecture handout.')]


def test_extension_video_reimport_replaces_chunks(workbench):
    client, project, url = workbench
    payload = {
        'kind': 'external_video', 'platform': 'bilibili', 'external_id': 'BV1Workbench', 'part': 1,
        'url': 'https://www.bilibili.com/video/BV1Workbench?p=1', 'title': '扩展采集的视频',
        'duration_seconds': 45, 'segments': [
            {'start_time': 1, 'end_time': 5, 'text': '旧字幕一。'},
            {'start_time': 15, 'end_time': 19, 'text': '旧字幕二。'},
        ],
    }
    imported = import_source(client, url, **payload)
    assert imported.status_code == 201, imported.data
    source = imported.data
    assert (source['external_key'], source['status'], source['duration_seconds']) == ('bilibili:BV1Workbench:p1', 'ready', 45)
    assert source['companion_play_url'] == payload['url']
    detail_url = f"{url}{source['id']}/"
    listed = client.get(detail_url).data['chunks']
    assert [chunk['content'] for chunk in listed] == ['旧字幕一。', '旧字幕二。']
    client.patch(detail_url, {'is_selected': False}, format='json')
    payload['segments'] = [{'start_time': 6, 'end_time': 10, 'text': '新字幕。'}]
    refreshed = import_source(client, url, **payload)
    assert refreshed.status_code == 200
    assert refreshed.data['id'] == source['id']
    assert refreshed.data['is_selected'] is False
    assert project.workbench_sources.count() == 1
    assert [chunk['content'] for chunk in client.get(detail_url).data['chunks']] == ['新字幕。']

    payload['segments'][0]['end_time'] = 2
    assert import_source(client, url, **payload).status_code == 400
    assert [chunk['content'] for chunk in client.get(detail_url).data['chunks']] == ['新字幕。']


def test_clipped_text_rename_selection_refresh_and_delete(workbench, monkeypatch):
    client, project, url = workbench
    fetch = Mock()
    monkeypatch.setattr(learning_resources, 'public_text', fetch)
    imported = import_source(
        client, url, kind='text', title='浏览器剪藏', content='# 第一节\n\n正文\n\n# 第二节\n\n结论',
        source_url='https://example.org/login-required',
    )
    assert imported.status_code == 201
    source = imported.data
    assert source['status'] == 'ready'
    assert source['source_url'] == 'https://example.org/login-required'
    assert source['file_preview_url'] is None
    detail_url = f"{url}{source['id']}/"
    assert [chunk['heading'] for chunk in client.get(detail_url).data['chunks']] == ['第一节', '第二节']
    second = import_source(client, url, kind='text', title='第二份资料', content='另一个来源。').data
    patched = client.patch(detail_url, {'title': '重命名', 'is_selected': False}, format='json')
    assert patched.status_code == 200
    assert (patched.data['title'], patched.data['is_selected']) == ('重命名', False)

    batch_url = f'{url}batch-select/'
    response = client.post(batch_url, {'is_selected': False}, format='json')
    assert response.data == {'project_id': project.pk, 'total_count': 2, 'selected_count': 0, 'ready_count': 2}
    response = client.post(batch_url, {'is_selected': True, 'source_ids': [second['id']]}, format='json')
    assert response.data['selected_count'] == 1
    assert client.get(detail_url).data['is_selected'] is False
    response = client.post(batch_url, {'is_selected': True, 'select_all': True}, format='json')
    assert response.data['selected_count'] == 2
    assert client.post(batch_url, {'is_selected': False, 'source_ids': []}, format='json').status_code == 400

    retry = client.patch(detail_url, {'action': 'retry'}, format='json')
    assert retry.status_code == 200
    assert (retry.data['title'], retry.data['status']) == ('重命名', 'ready')
    assert client.delete(detail_url).status_code == 204
    assert client.get(detail_url).status_code == 404
    assert client.get(url).data['total_count'] == 1
    fetch.assert_not_called()


def test_edits_during_processing_preserve_claim_and_custom_title(workbench, monkeypatch):
    client, project, url = workbench

    def fetch(link):
        source = project.workbench_sources.get()
        assert source.status == 'processing'
        detail_url = f'{url}{source.pk}/'
        assert client.patch(detail_url, {'title': '手动标题'}, format='json').status_code == 200
        assert client.post(f'{url}batch-select/', {'is_selected': False}, format='json').status_code == 200
        return link, '<title>原网页标题</title><p>可以读取的正文。</p>'

    monkeypatch.setattr(learning_resources, 'public_text', fetch)
    response = import_source(client, url, kind='web_url', url='https://example.org/readable')
    assert response.status_code == 201
    assert (response.data['status'], response.data['title'], response.data['is_selected']) == ('ready', '手动标题', False)


def test_mp4_queues_playback_and_deletes_only_exclusive_companion(workbench, settings, monkeypatch):
    client, project, url = workbench
    settings.CELERY_TASK_ALWAYS_EAGER = False
    enqueue = Mock()
    monkeypatch.setattr(process_project_source_task, 'apply_async', enqueue)
    video = b'\x00\x00\x00\x18ftypmp42 private video bytes'
    asr = Mock(return_value=TranscriptResult(segments=[ASRSegment(1, 4, '本地视频字幕。')]))
    monkeypatch.setattr(ASRProviderRegistry, 'get_default_provider', lambda: SimpleNamespace(transcribe=asr))
    response = client.post(f'{url}upload/', {'file': SimpleUploadedFile('lecture.mp4', video)}, format='multipart')
    assert response.status_code == 201
    uploaded = response.data['sources'][0]
    assert uploaded['status'] == 'pending'
    enqueue.assert_called_once_with(args=(uploaded['id'],), retry=False)
    asr.assert_not_called()
    process_project_source_task(uploaded['id'])
    asr.assert_called_once()

    source = project.workbench_sources.get()
    course = source.companion_course
    assert course.author_id == project.user_id and not course.is_published and course.is_workbench_companion
    source_url = f'{url}{source.pk}/'
    course_url = f'/api/courses/{course.pk}/'
    assert client.get(source_url).data['companion_play_url'] == f'/course/{course.pk}?project={project.pk}'
    assert client.get(course_url).status_code == 200
    course_detail = client.get(course_url, {'workbench_project': project.pk})
    assert course_detail.status_code == 200
    assert course_detail.data['is_workbench_companion'] is True
    stream_url = course_detail.data['video_file']
    media = client.get(stream_url, HTTP_RANGE='bytes=4-11')
    assert media.status_code == 206
    assert b''.join(media.streaming_content) == b'ftypmp42'
    preview = client.get(uploaded['file_preview_url'])
    assert preview['Content-Type'] == 'video/mp4'
    assert preview['Content-Disposition'].startswith('inline;')
    assert b''.join(preview.streaming_content) == video
    assert client.get(f'{course_url}transcript/').data['segments'][0]['text'] == '本地视频字幕。'
    assert client.get(f'{course_url}outline/').data == {'status': 'not_available', 'items': []}
    ticket = client.post('/api/media-ticket/', {'path': stream_url}, format='json').data
    assert APIClient().head(ticket['path'], {'media_token': ticket['ticket']}).status_code == 200

    VideoProgress.objects.create(user=project.user, course=course)
    assert client.get('/api/courses/learning-progress/').data == []
    assert client.get('/api/courses/').data['items'] == []
    assert client.get('/api/courses/modules/').data == []
    other_user = User.objects.create_user(username='other-source-owner')
    other = signed_in(other_user)
    assert other.get(url).status_code == 404
    assert other.get(source_url).status_code == 404
    assert other.get(uploaded['file_preview_url']).status_code == 404
    assert other.get(stream_url).status_code == 404
    assert other.post('/api/media-ticket/', {'path': stream_url}, format='json').status_code == 404
    assert other.get(course_url).status_code == 404
    assert other.get(course_url, {'workbench_project': project.pk}).status_code == 404
    assert other.get(f'{course_url}transcript/').status_code == 404
    assert other.get(f'{course_url}outline/').status_code == 404
    assert other.post(f'{course_url}progress/', {'position': 2}, format='json').status_code == 404
    assert other.patch(source_url, {'title': '不可修改'}, format='json').status_code == 404
    assert other.delete(source_url).status_code == 404

    profile = UserAccessProfile.objects.create(user=project.user, blocked_permissions=['course.video'])
    assert client.get(course_url).status_code == 200
    assert client.get(f'{course_url}transcript/').status_code == 200
    assert client.get(f'{course_url}outline/').status_code == 200
    profile.delete()

    other_project = ConversationProject.objects.create(user=other_user, name='第二个用户的项目')
    their_source = ProjectSource.objects.create(
        project=other_project, user=other_user, source_type='text', title='其他用户的来源',
    )
    batch = client.post(f'{url}batch-select/', {
        'is_selected': False, 'source_ids': [str(source.pk), str(their_source.pk)],
    }, format='json')
    assert batch.status_code == 404
    source.refresh_from_db()
    assert source.is_selected

    second_project = ConversationProject.objects.create(user=project.user, name='引用同一个视频的项目')
    shared = ProjectSource.objects.create(
        project=second_project, user=project.user, source_type='uploaded_media', title='同一视频',
        companion_course=course, file=source.file.name,
    )
    file_path = Path(source.file.path)
    assert client.delete(source_url).status_code == 204
    assert Course.objects.filter(pk=course.pk).exists() and file_path.is_file()
    assert client.get(course_url, {'workbench_project': project.pk}).status_code == 404
    assert client.delete(reverse('project-source-detail', args=[second_project.pk, shared.pk])).status_code == 204
    assert not Course.objects.filter(pk=course.pk).exists()
    assert not file_path.exists()
    assert client.get(course_url).status_code == 404


def test_sources_follow_selected_learning_identity(workbench):
    personal, project, url = workbench
    text = import_source(personal, url, kind='text', title='个人资料', content='个人空间中的资料。').data
    institution = Institution.objects.create(name='课程空间', slug='workbench-api-space')
    workspace = Workspace.objects.create(
        institution=institution, service_ends_on=timezone.localdate() + timedelta(days=10), max_students=3,
    )
    WorkspaceMembership.objects.create(workspace=workspace, user=project.user, role='admin')
    school = APIClient()
    school.cookies['auth_token'] = personal.cookies['auth_token'].value
    school.credentials(HTTP_X_UNIMIND_WORKSPACE=str(workspace.pk))
    assert school.get(url).status_code == 404
    assert school.get(f"{url}{text['id']}/").status_code == 404
    school_project = school.post('/api/ai/projects/', {'name': '机构项目'}, format='json')
    assert school_project.status_code == 201
    school_url = reverse('project-source-list', args=[school_project.data['id']])
    assert school.get(school_url).data['total_count'] == 0
    assert personal.get(school_url).status_code == 404
    assert import_source(school, school_url, kind='text', title='机构来源', content='机构资料。').status_code == 403

    module = CourseModule.objects.create(institution=institution, subject='金融', name='机构模块')
    course = Course.objects.create(title='机构课程', is_published=True, institution=institution, module=module)
    WorkspaceCourse.objects.create(workspace=workspace, course=course)
    assert [item['id'] for item in school.get('/api/courses/').data['items']] == [course.pk]
