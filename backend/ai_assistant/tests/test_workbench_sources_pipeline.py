import subprocess
from datetime import timedelta
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.urls import reverse
from django.utils import timezone
from docx import Document
from kombu.exceptions import OperationalError
from pptx import Presentation
from pptx.util import Inches
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject
from rest_framework.test import APIClient

from ai_assistant.models import ConversationProject, ProjectSource
from ai_assistant.services import learning_resources
from ai_assistant.services.facts import workbench_ingest, workbench_media
from ai_assistant.services.facts.workbench_ingest import dispatch_project_source_processing, process_project_source
from ai_assistant.services.facts.workbench_media import segments_to_timestamp_chunks
from ai_assistant.services.facts.workbench_parsers import PDF_NO_TEXT, WorkbenchParseError, parse_pdf_bytes
from ai_assistant.tasks import process_project_source_task
from courses.asr import ASRProviderRegistry, OpenAIWhisperProvider, TranscriptResult, TranscriptSegment as ASRSegment
from courses.models import Course, CourseModule, CourseOutline, OutlineItem, TranscriptSegment, VideoTranscript
from users.models import CourseStudentStatus, Institution, User
from users.login_sessions import LoginSession
from users.models_workspace import Workspace, WorkspaceCourse, WorkspaceMembership


def _buffer(document, save):
    buffer = BytesIO()
    getattr(document, save)(buffer)
    return buffer.getvalue()


def _pdf(*pages, encrypted=False):
    writer = PdfWriter()
    for lines in pages:
        page = writer.add_blank_page(612, 792)
        page[NameObject('/Resources')] = DictionaryObject({
            NameObject('/Font'): DictionaryObject({
                NameObject('/F1'): DictionaryObject({
                    NameObject('/Type'): NameObject('/Font'),
                    NameObject('/Subtype'): NameObject('/Type1'),
                    NameObject('/BaseFont'): NameObject('/Helvetica'),
                }),
            }),
        })
        stream = DecodedStreamObject()
        items = ' T* '.join(f'({line}) Tj' for line in lines)
        stream.set_data(f'BT /F1 12 Tf 14 TL 20 750 Td {items} ET'.encode())
        page[NameObject('/Contents')] = stream
    if encrypted:
        writer.encrypt('password')
    return _buffer(writer, 'write')


def _pptx():
    presentation = Presentation()
    slide = presentation.slides.add_slide(presentation.slide_layouts[5])
    slide.shapes.title.text = '第一张'
    group = slide.shapes.add_group_shape()
    group.shapes.add_textbox(Inches(1), Inches(1), Inches(4), Inches(1)).text = '分组文本'
    table = slide.shapes.add_table(1, 2, Inches(1), Inches(2), Inches(6), Inches(2)).table
    table.cell(0, 0).text, table.cell(0, 1).text = '行标题', '单元格'
    slide.notes_slide.notes_text_frame.text = '这份备注也可被引用'
    slide = presentation.slides.add_slide(presentation.slide_layouts[5])
    slide.shapes.title.text = '第二张'
    return _buffer(presentation, 'save')


def _docx():
    document = Document()
    document.add_heading('总标题', level=0)
    document.add_paragraph('正文在表格前。')
    table = document.add_table(rows=1, cols=2)
    table.rows[0].cells[0].text, table.rows[0].cells[1].text = '表头', '数据'
    document.add_paragraph('正文在表格后。')
    document.add_heading('第二章', level=2)
    document.add_paragraph('另一段正文。')
    return _buffer(document, 'save')


@pytest.fixture
def project(user, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    settings.UNIMIND_CONTENT_INSTITUTION_ID = 'global'
    return ConversationProject.objects.create(user=user, name='复习项目')


def _source(project, kind, **fields):
    return ProjectSource.objects.create(project=project, user=project.user, source_type=kind, title='学习资料', **fields)


def test_pdf_keeps_page_numbers_and_splits_long_pages(project):
    payload = _pdf(['Cover', 'First paragraph.'], [], ['Chapter three', 'Readable text. ' * 150])
    parsed = parse_pdf_bytes(payload)
    assert [(chunk['page_number'], chunk['locator_label']) for chunk in parsed] == [
        (1, 'P.1'), (3, 'P.3'), (3, 'P.3 (2)'),
    ]
    assert parsed[0]['heading'] == 'Cover'
    assert max(len(chunk['content']) for chunk in parsed) <= 1800
    source = _source(project, 'pdf', file=SimpleUploadedFile('lecture.pdf', payload))
    ready = process_project_source(source.pk)
    assert ready.status == 'ready'
    assert ready.unit_count == 3
    assert ready.word_count > 300
    assert ready.file_size == len(payload)
    assert ready.summary.startswith('Cover First paragraph.')
    assert all(chunk.token_estimate for chunk in ready.chunks.all())


@pytest.mark.parametrize('payload', [_pdf([]), _pdf(['Encrypted text'], encrypted=True)])
def test_pdf_without_readable_text_gives_actionable_error(payload, project):
    with pytest.raises(WorkbenchParseError, match=PDF_NO_TEXT):
        parse_pdf_bytes(payload)
    source = _source(project, 'pdf', file=SimpleUploadedFile('unreadable.pdf', payload))
    failed = process_project_source(source.pk)
    assert failed.status == 'failed'
    assert failed.error_message == PDF_NO_TEXT
    assert not failed.chunks.exists()


def test_pptx_import_extracts_titles_groups_tables_and_notes(project):
    source = _source(project, 'pptx', file=SimpleUploadedFile('lecture.pptx', _pptx()))
    ready = process_project_source(source.pk)
    assert ready.status == 'ready'
    first, second = ready.chunks.all()
    assert (first.anchor_type, first.slide_number, first.locator_label, first.heading) == ('slide', 1, 'Slide 1', '第一张')
    assert '分组文本' in first.content
    assert '行标题 | 单元格' in first.content
    assert '[讲者备注] 这份备注也可被引用' in first.content
    assert (second.slide_number, second.heading) == (2, '第二张')


def test_docx_import_preserves_document_order(project):
    source = _source(project, 'docx', file=SimpleUploadedFile('lecture.docx', _docx()))
    ready = process_project_source(source.pk)
    assert ready.status == 'ready'
    first, second = ready.chunks.all()
    assert (first.anchor_type, first.heading, first.locator_label) == ('section', '总标题', '§1 总标题')
    assert first.content.index('正文在表格前') < first.content.index('表头 | 数据') < first.content.index('正文在表格后')
    assert second.heading == '第二章'


def test_text_inline_post_commit_and_reprocessing(project, django_capture_on_commit_callbacks):
    markdown = '# 第一章\n\n第一段。\n\n```md\n# 代码内容\n```\n\n## 第二章\n\n' + '很长的段落。' * 300
    with django_capture_on_commit_callbacks(execute=True) as commits:
        source = _source(project, 'text', metadata={'text': markdown})
        dispatch_project_source_processing(source)
        source.refresh_from_db()
        assert source.status == 'pending'
    assert len(commits) == 1
    source.refresh_from_db()
    assert source.status == 'ready'
    chunks = list(source.chunks.all())
    assert [chunk.heading for chunk in chunks] == ['第一章', '第二章', '第二章']
    assert '# 代码内容' in chunks[0].content
    assert all(len(chunk.content) <= 1400 for chunk in chunks)
    process_project_source_task(str(source.pk))
    assert list(source.chunks.values_list('id', flat=True)) == [chunk.pk for chunk in chunks]

    source.file = SimpleUploadedFile('inline.txt', '改为纯文本。\n\n新段落。'.encode())
    source.status = 'pending'
    source.save(update_fields=['file', 'status', 'updated_at'])
    ready = process_project_source(source.pk)
    assert ready.chunks.get().content == '改为纯文本。\n\n新段落。'


def test_web_ingestion_preserves_structure_and_fetched_url(project, monkeypatch):
    fetch = Mock(return_value=(
        'https://example.org/final',
        '<title>课程资料</title><nav><p>菜单</p></nav><h1>第一节</h1>'
        '<p>阅读 <strong>正文</strong>。</p><ul><li>列表内容</li></ul>'
        '<script>hidden()</script><h2>第二节</h2><p>结论</p>',
    ))
    monkeypatch.setattr(learning_resources, 'public_text', fetch)
    source = _source(project, 'web_url', source_url='https://example.org/redirect')
    ready = process_project_source(source.pk)
    fetch.assert_called_once_with('https://example.org/redirect')
    assert (ready.status, ready.title, ready.source_url) == ('ready', '课程资料', 'https://example.org/final')
    first, second = ready.chunks.all()
    assert first.heading == '第一节'
    assert first.content == '第一节\n\n阅读 正文。\n\n列表内容'
    assert second.heading == '第二节'


def test_timestamp_coalescing_respects_sentences_pauses_and_hour_labels():
    segments = [
        {'start_time': start, 'end_time': start + 3, 'text': '跟着讲解。'}
        for start in range(0, 39, 3)
    ] + [{'start_time': 3661.9, 'end_time': 3664, 'text': '长暂停后的内容。'}]
    first, second, last = segments_to_timestamp_chunks(segments)
    assert (first['locator_label'], first['start_seconds'], first['end_seconds']) == ('00:00', 0, 27)
    assert len(first['metadata']['segments']) == 9
    assert first['content'] == '跟着讲解。' * 9
    assert second['locator_label'] == '00:27'
    assert last['locator_label'] == '01:01:01'
    with pytest.raises(WorkbenchParseError, match='字幕时间无效'):
        segments_to_timestamp_chunks([{'start_time': 5, 'end_time': 2, 'text': '无效'}])


@pytest.mark.parametrize(('platform', 'external_id', 'external_key'), [
    ('bilibili', 'BV123', 'bilibili:BV123:p2'),
    ('youtube', 'dQw4w9WgXcQ', 'youtube:dQw4w9WgXcQ'),
    ('generic', 'video-123', 'generic:video-123'),
])
def test_external_video_has_project_scoped_identity(project, platform, external_id, external_key):
    metadata = {
        'platform': platform, 'external_id': external_id, 'part': 2, 'url': 'https://example.org/video',
        'title': '视频标题', 'duration_seconds': 90,
        'segments': [{'start_time': 15, 'end_time': 43, 'text': '外部视频字幕。'}],
    }
    source = _source(project, 'external_video', metadata=metadata)
    ready = process_project_source(source.pk)
    assert (ready.status, ready.external_key, ready.duration_seconds, ready.title) == ('ready', external_key, 90, '视频标题')
    assert ready.chunks.get().locator_label == '00:15'
    duplicate = process_project_source(_source(project, 'external_video', metadata=metadata).pk)
    assert duplicate.status == 'failed'
    assert '已在当前项目中' in duplicate.error_message
    assert not duplicate.chunks.exists()
    ready.metadata = {**metadata, 'segments': [{'start_time': 20, 'end_time': 24, 'text': '新版字幕。'}]}
    ready.status = 'pending'
    ready.save(update_fields=['metadata', 'status', 'updated_at'])
    updated = process_project_source(ready.pk)
    assert (updated.pk, updated.external_key, updated.chunks.get().content) == (source.pk, external_key, '新版字幕。')


def test_station_course_checks_access_before_reading_subtitles(project):
    course = Course.objects.create(title='站内课', is_published=True)
    transcript = VideoTranscript.objects.create(course=course, asr_status='completed')
    TranscriptSegment.objects.create(transcript=transcript, index=0, start_time=5, end_time=32.25, text='站内课程字幕。')
    outline = CourseOutline.objects.create(course=course, status='completed')
    OutlineItem.objects.create(outline=outline, title='本课要点', timestamp=5, index=0)
    source = _source(project, 'course', course=course)
    assert process_project_source(source.pk).status == 'failed'

    CourseStudentStatus.objects.create(user=project.user, is_course_student=True)
    ready = process_project_source(source.pk)
    assert ready.status == 'ready'
    assert ready.chunks.get().content == '站内课程字幕。'
    assert ready.duration_seconds == 33
    assert ready.metadata['outline'][0]['title'] == '本课要点'

    institution = Institution.objects.create(name='另一机构', slug='other-workbench-course')
    course.institution = institution
    course.save(update_fields=['institution'])
    assert process_project_source(_source(project, 'course', course=course).pk).status == 'failed'


def test_station_course_uses_courseware_and_description_without_transcript(project):
    CourseStudentStatus.objects.create(user=project.user, is_course_student=True)
    course = Course.objects.create(title='讲义', description='课程简介。', is_published=True,
                                   courseware=SimpleUploadedFile('notes.pdf', _pdf(['Lecture notes.'])))
    ready = process_project_source(_source(project, 'course', course=course).pk)
    assert ready.status == 'ready'
    assert list(ready.chunks.values_list('anchor_type', flat=True)) == ['section', 'page']
    assert ready.summary == '课程简介。 Lecture notes.'


def test_uploaded_video_plays_with_private_subtitles_without_listing(project, api_client, monkeypatch):
    source = _source(project, 'uploaded_media', file=SimpleUploadedFile('本地视频' * 35 + '.mp4', b'private video bytes'))

    def transcribe(path):
        assert Path(path).read_bytes() == b'private video bytes'
        current = ProjectSource.objects.get(pk=source.pk)
        assert current.status == 'processing'
        assert current.companion_course.transcript.asr_status == 'processing'
        assert process_project_source(source.pk).status == 'processing'
        return TranscriptResult(segments=[ASRSegment(0, 3, '测试字幕。'), ASRSegment(3, 6.5, '下一行。')])

    provider = Mock(spec=['transcribe'], transcribe=Mock(side_effect=transcribe))
    monkeypatch.setattr(ASRProviderRegistry, 'get_default_provider', lambda: provider)
    ready = process_project_source(source.pk)
    assert ready.status == 'ready'
    assert ready.duration_seconds == 7
    assert ready.metadata['is_private_companion'] is True
    companion = ready.companion_course
    assert companion.author == project.user
    assert companion.is_workbench_companion and not companion.is_published
    assert companion.video_file.name == source.file.name
    assert len(companion.video_file.name) <= Course._meta.get_field('video_file').max_length
    assert source.file.name.startswith(f'workbench_sources/{project.user_id}/{source.pk}_')
    assert ready.chunks.get().content == '测试字幕。下一行。'
    assert companion.transcript.segments.count() == 2
    with pytest.raises(IntegrityError), transaction.atomic():
        Course.objects.filter(pk=companion.pk).update(is_published=True)

    api_client.cookies['auth_token'] = LoginSession.issue(project.user).key
    detail = reverse('course-detail', args=[companion.pk])
    subtitles = reverse('course-transcript', args=[companion.pk])
    payload = api_client.get(detail, {'workbench_project': project.pk}).data
    assert payload['id'] == companion.pk
    assert api_client.get(detail, {'workbench_project': project.pk + 1}).status_code == 404
    assert api_client.get(subtitles).data['segments'][1]['text'] == '下一行。'

    media_url = payload['video_file']
    media = api_client.get(media_url, HTTP_RANGE='bytes=0-6')
    assert media.status_code == 206
    assert b''.join(media.streaming_content) == b'private'
    assert media['Cache-Control'] == 'private, no-store'
    assert api_client.put(media_url, b'overwrite', content_type='video/mp4').status_code == 405
    assert APIClient().get(media_url).status_code == 401

    other_user = User.objects.create_user(username='observer')
    other = APIClient()
    other.cookies['auth_token'] = LoginSession.issue(other_user).key
    institution = Institution.objects.create(name='课程机构', slug='workbench-observer-school')
    workspace = Workspace.objects.create(institution=institution, service_ends_on=timezone.localdate() + timedelta(days=30), max_students=3)
    WorkspaceMembership.objects.create(workspace=workspace, user=other_user, role='admin')
    module = CourseModule.objects.create(institution=institution, subject='Finance', name='正式课程模块')
    published = Course.objects.create(title='正式课程', institution=institution, module=module, is_published=True)
    WorkspaceCourse.objects.create(workspace=workspace, course=published)
    other.credentials(HTTP_X_UNIMIND_WORKSPACE=str(workspace.pk))
    listed = other.get('/api/courses/', {'page': 1})
    assert listed.status_code == 200
    assert [item['id'] for item in listed.data['items']] == [published.pk]
    assert other.get(detail).status_code == 404
    assert other.get(subtitles).status_code == 404
    assert other.get(media_url).status_code == 404

    process_project_source_task(str(source.pk))
    provider.transcribe.assert_called_once()
    assert Course.objects.filter(author=project.user).count() == 1


@pytest.mark.parametrize(('provider_name', 'config', 'error'), [
    ('dummy', {}, '尚未配置'),
    ('qwen_filetrans', {'api_key': ''}, '缺少有效的 API 密钥'),
])
def test_uploaded_video_records_configuration_failure(project, settings, provider_name, config, error):
    settings.ASR_DEFAULT_PROVIDER = provider_name
    settings.ASR_PROVIDER_CONFIG = {provider_name: config}
    source = _source(project, 'uploaded_media', file=SimpleUploadedFile('missing-asr.webm', b'media'))
    failed = process_project_source(source.pk)
    assert failed.status == 'failed'
    assert error in failed.error_message
    assert failed.companion_course.transcript.asr_status == 'failed'
    assert not failed.chunks.exists()

    provider = SimpleNamespace(transcribe=lambda path: TranscriptResult(segments=[ASRSegment(0, 2, '字幕')]))
    ready = process_project_source(source.pk, asr_provider=provider)
    assert ready.status == 'ready'
    assert ready.companion_course_id == failed.companion_course_id
    assert ready.companion_course.transcript.asr_status == 'completed'


@pytest.mark.parametrize('filename', ['audio.mp3', 'audio.m4a', 'audio.wav'])
def test_uploaded_audio_has_timestamp_citations_without_a_companion(project, filename):
    source = _source(project, 'uploaded_media', file=SimpleUploadedFile(filename, b'local audio'))
    provider = SimpleNamespace(transcribe=lambda path: TranscriptResult(segments=[ASRSegment(2, 4, '音频笔记')]))
    ready = process_project_source(source.pk, asr_provider=provider)
    assert ready.status == 'ready'
    assert ready.companion_course_id is None
    assert ready.chunks.get().locator_label == '00:02'


@pytest.mark.parametrize('times_out', [False, True])
def test_local_asr_extraction_limits_ffmpeg_and_cleans_temp_files(project, monkeypatch, times_out):
    source = _source(project, 'uploaded_media', file=SimpleUploadedFile('clip.mov', b'local video'))
    provider = OpenAIWhisperProvider()
    transcribe = Mock(return_value=TranscriptResult(segments=[ASRSegment(0, 2, '字幕')]))
    monkeypatch.setattr(provider, 'transcribe', transcribe)
    extracted = []

    def run(command, *, timeout, **kwargs):
        assert timeout == 300
        assert command[command.index('-protocol_whitelist') + 1] == 'file,pipe'
        assert command[command.index('-f') + 1] == 'mov'
        audio = Path(command[-1])
        extracted.append(audio)
        audio.write_bytes(b'partial audio')
        if times_out:
            raise subprocess.TimeoutExpired(command, timeout)

    monkeypatch.setattr(workbench_media.subprocess, 'run', run)
    result = process_project_source(source.pk, asr_provider=provider)
    assert len(extracted) == 1 and not extracted[0].parent.exists()
    if times_out:
        assert result.status == 'failed'
        assert '提取音轨超时' in result.error_message
        transcribe.assert_not_called()
    else:
        assert result.status == 'ready'
        transcribe.assert_called_once_with(str(extracted[0]))


def test_project_source_cleanup_runs_on_commit_and_respects_shared_file(project, django_capture_on_commit_callbacks):
    source = _source(project, 'uploaded_media', file=SimpleUploadedFile('video.mov', b'a video'))
    provider = SimpleNamespace(transcribe=lambda path: TranscriptResult(segments=[ASRSegment(0, 2, '字幕')]))
    ready = process_project_source(source.pk, asr_provider=provider)
    companion_id = ready.companion_course_id
    file = Path(source.file.path)
    shared = _source(project, 'uploaded_media', file=source.file.name)

    with pytest.raises(RuntimeError), django_capture_on_commit_callbacks(execute=True), transaction.atomic():
        ProjectSource.objects.filter(pk=source.pk).delete()
        raise RuntimeError('rollback')
    assert Course.objects.filter(pk=companion_id).exists()
    assert file.is_file()

    with django_capture_on_commit_callbacks(execute=True):
        source.delete()
        assert file.is_file()
    assert not Course.objects.filter(pk=companion_id).exists()
    assert file.is_file()
    with django_capture_on_commit_callbacks(execute=True):
        ProjectSource.objects.filter(pk=shared.pk).delete()
        assert file.is_file()
    assert not file.exists()


def test_publish_failure_rolls_back_chunk_replacement(project, monkeypatch):
    source = _source(project, 'text', metadata={'text': '原来的正文'})
    ready = process_project_source(source.pk)
    old_chunk = ready.chunks.get()
    ready.metadata = {'text': '新正文'}
    ready.status = 'pending'
    ready.save(update_fields=['metadata', 'status', 'updated_at'])
    writer = Mock(side_effect=IntegrityError('simulated write failure'))
    monkeypatch.setattr(workbench_ingest.ProjectSourceChunk.objects, 'bulk_create', writer)

    failed = process_project_source(ready.pk)
    assert failed.status == 'failed'
    assert failed.chunks.get().pk == old_chunk.pk
    assert failed.chunks.get().content == '原来的正文'


@pytest.mark.parametrize('mode', ['async', 'eager', 'sync', 'broker_down'])
def test_processing_dispatch_uses_post_commit_and_expected_execution_mode(
    project, settings, monkeypatch, django_capture_on_commit_callbacks, mode,
):
    source = _source(project, 'web_url', source_url='https://example.org/note')
    settings.CELERY_TASK_ALWAYS_EAGER = mode == 'eager'
    settings.IS_PROD = False
    fetch = Mock(return_value=(source.source_url, '<p>网页正文</p>'))
    enqueue = Mock(side_effect=OperationalError('unreachable') if mode == 'broker_down' else None)
    monkeypatch.setattr(learning_resources, 'public_text', fetch)
    monkeypatch.setattr(process_project_source_task, 'apply_async', enqueue)

    with django_capture_on_commit_callbacks(execute=True):
        dispatch_project_source_processing(source, sync=mode == 'sync')
        fetch.assert_not_called()
        enqueue.assert_not_called()
    source.refresh_from_db()
    if mode in ['async', 'broker_down']:
        enqueue.assert_called_once_with(args=(str(source.pk),), retry=False)
    else:
        enqueue.assert_not_called()
    if mode == 'async':
        fetch.assert_not_called()
        assert source.status == 'pending'
        process_project_source_task(str(source.pk))
        source.refresh_from_db()
    fetch.assert_called_once()
    assert source.status == 'ready'
