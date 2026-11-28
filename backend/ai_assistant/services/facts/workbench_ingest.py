"""Claim workbench sources and publish complete extraction results in one transaction."""

import logging
import math
import re
from datetime import timedelta

from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.db import IntegrityError, transaction
from django.utils import timezone
from kombu.exceptions import OperationalError

from ai_assistant.models import WORKBENCH_SOURCE_PREFIX, ProjectSource, ProjectSourceChunk
from courses.models import VideoTranscript
from users.workspaces.identity import learner_identity

from .workbench_media import (
    ingest_external_video, ingest_station_course, ingest_uploaded_media,
    prepare_companion_course, save_companion_subtitles,
)
from .workbench_parsers import (
    WorkbenchParseError, parse_docx_file, parse_pdf_document, parse_pptx_document,
    parse_text_content, parse_web_url,
)


def is_personal_space(user):
    return getattr(user, 'workspace_id', None) is None and not hasattr(user, 'workspace_learner')

logger = logging.getLogger(__name__)

PAGED_DOCUMENT_PARSERS = {
    ProjectSource.Type.PDF: parse_pdf_document,
    ProjectSource.Type.PPTX: parse_pptx_document,
}
DOCUMENT_TYPES = {*PAGED_DOCUMENT_PARSERS, ProjectSource.Type.DOCX, ProjectSource.Type.TEXT}
INLINE_DOCUMENT_BYTES = 15 * 1024 * 1024
SOURCE_TASK_TIME_LIMIT = 5400
WORD = re.compile(r'[\u3400-\u9fff]|[^\W_\u3400-\u9fff]+')
EAST_ASIAN_TEXT = re.compile(r'[\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af]')


def _parse_source(source, asr_provider):
    kind = source.source_type
    if kind in DOCUMENT_TYPES:
        if source.file:
            if not source.file.name.startswith(f'{WORKBENCH_SOURCE_PREFIX}{source.user_id}/'):
                raise WorkbenchParseError('未找到当前账号上传的文档。')
            with source.file.open('rb') as file:
                updates = {'file_size': file.size}
                if kind in PAGED_DOCUMENT_PARSERS:
                    chunks, updates['unit_count'] = PAGED_DOCUMENT_PARSERS[kind](file)
                    return chunks, updates, None
                if kind == ProjectSource.Type.DOCX:
                    return parse_docx_file(file), updates, None
                try:
                    content = file.read().decode('utf-8-sig')
                except UnicodeDecodeError as exc:
                    raise WorkbenchParseError('请将文本文件保存为 UTF-8 编码后重新上传。') from exc
        elif kind == ProjectSource.Type.TEXT:
            content = source.metadata.get('text', '')
            updates = {}
            if not isinstance(content, str):
                raise WorkbenchParseError('请提供可读取的文本或 Markdown 内容。')
        else:
            raise WorkbenchParseError('请先上传要解析的文档。')
        return parse_text_content(content), updates, None
    if kind == ProjectSource.Type.WEB_URL:
        chunks, url, title = parse_web_url(source.metadata.get('url') or source.source_url)
        return chunks, {'source_url': url, 'title': title}, None
    if kind == ProjectSource.Type.COURSE:
        result = ingest_station_course(source)
    elif kind == ProjectSource.Type.EXTERNAL_VIDEO:
        result = ingest_external_video(source)
    elif kind == ProjectSource.Type.UPLOADED_MEDIA:
        result = ingest_uploaded_media(source, asr_provider=asr_provider)
        result.updates['file_size'] = source.file.size
    else:
        raise WorkbenchParseError('当前来源类型暂不支持解析。')
    return result.chunks, result.updates, result


def _publish(source, chunks, updates, media):
    text = '\n'.join(chunk['content'] for chunk in chunks)
    units = {
        (chunk['anchor_type'], chunk.get('page_number') or chunk.get('slide_number') or index)
        for index, chunk in enumerate(chunks)
    }
    transcript_end = max((chunk.get('end_seconds', 0) for chunk in chunks), default=0)
    updates.update(
        unit_count=updates.get('unit_count', len(units)),
        word_count=sum(1 for _ in WORD.finditer(text)),
        duration_seconds=max(updates.get('duration_seconds', 0), math.ceil(transcript_end)),
        summary=re.sub(r'\s+', ' ', text[:1200]).strip()[:300],
        status=ProjectSource.Status.READY,
        error_message='',
    )
    if source.source_type in (ProjectSource.Type.WEB_URL, ProjectSource.Type.EXTERNAL_VIDEO):
        # Read the title from the locked row so edits during parsing take effect.
        title = source.metadata.get('title')
        if isinstance(title, str) and title:
            updates['title'] = title[:240]

    entries = []
    for index, chunk in enumerate(chunks):
        content = chunk['content']
        east_asian_chars = sum(1 for _ in EAST_ASIAN_TEXT.finditer(content))
        token_estimate = east_asian_chars + (len(content) - east_asian_chars + 3) // 4
        entries.append(ProjectSourceChunk(source=source, chunk_index=index, token_estimate=token_estimate, **chunk))
    source.chunks.all().delete()
    ProjectSourceChunk.objects.bulk_create(entries, batch_size=1000)
    if source.source_type == ProjectSource.Type.UPLOADED_MEDIA:
        save_companion_subtitles(source, media)
    for field, value in updates.items():
        setattr(source, field, value)
    source.save(update_fields=[*updates, 'updated_at'])


def process_project_source(source_id, *, asr_provider=None):
    """Process a pending or failed source. Set it to pending to reprocess edited input."""
    with transaction.atomic():
        source = ProjectSource.objects.select_for_update().filter(pk=source_id).first()
        if source is None or source.status == ProjectSource.Status.READY:
            return source
        lease_start = timezone.now() - timedelta(seconds=SOURCE_TASK_TIME_LIMIT)
        if source.status == ProjectSource.Status.PROCESSING and source.updated_at > lease_start:
            return source
        source.status = ProjectSource.Status.PROCESSING
        source.error_message = ''
        source.save(update_fields=['status', 'error_message', 'updated_at'])

    owned = ProjectSource.objects.filter(
        pk=source_id, status=ProjectSource.Status.PROCESSING, updated_at=source.updated_at,
    )
    updates = {}
    try:
        if (source.project.user_id != source.user_id or not source.user.is_active
                or learner_identity(source.user) is not None):
            raise WorkbenchParseError('请在本人个人空间中处理项目来源。')
        if source.source_type == ProjectSource.Type.UPLOADED_MEDIA:
            with transaction.atomic():
                if not owned.select_for_update().exists():
                    return None
                prepare_companion_course(source)
        chunks, updates, media = _parse_source(source, asr_provider)
        with transaction.atomic():
            source = owned.select_for_update().first()
            if source is not None:
                _publish(source, chunks, updates, media)
        return source
    except WorkbenchParseError as exc:
        message = str(exc)
    except IntegrityError:
        if updates.get('external_key') and ProjectSource.objects.filter(
            project_id=source.project_id, external_key=updates['external_key'],
        ).exclude(pk=source_id).exists():
            message = '该视频已在当前项目中，请更新已有来源。'
        else:
            logger.exception('Could not save workbench source %s', source_id)
            message = '保存解析结果失败，请重试。'
    except Exception:
        logger.exception('Failed to process workbench source %s', source_id)
        message = '解析失败，请检查来源内容或文件格式后重试。'
    with transaction.atomic():
        source = owned.select_for_update().first()
        if source is not None:
            source.status = ProjectSource.Status.FAILED
            source.error_message = message[:500]
            source.save(update_fields=['status', 'error_message', 'updated_at'])
            if source.companion_course_id:
                VideoTranscript.objects.filter(
                    course_id=source.companion_course_id, asr_status='processing',
                    course__is_workbench_companion=True, course__author_id=source.user_id,
                    course__video_file=source.file.name,
                ).update(asr_status='failed', error_message=source.error_message, updated_at=timezone.now())
    return source


def _can_process_inline(source):
    kind = source.source_type
    if kind in DOCUMENT_TYPES:
        if not source.file:
            text = source.metadata.get('text')
            return not isinstance(text, str) or len(text.encode('utf-8')) <= INLINE_DOCUMENT_BYTES
        if isinstance(source.file.storage, FileSystemStorage):
            try:
                return source.file.size <= INLINE_DOCUMENT_BYTES
            except FileNotFoundError:
                return True  # Let ingestion record the missing file.
        return 0 < source.file_size <= INLINE_DOCUMENT_BYTES
    if kind == ProjectSource.Type.EXTERNAL_VIDEO:
        return bool(source.metadata.get('segments'))
    if kind == ProjectSource.Type.COURSE:
        return VideoTranscript.objects.filter(
            course_id=source.course_id, asr_status='completed', segments__isnull=False,
        ).exists()
    return False


def dispatch_project_source_processing(source, *, sync=False):
    """Start parsing only once the transaction that saved the input commits."""
    def dispatch():
        from ai_assistant.tasks import process_project_source_task

        if sync or settings.CELERY_TASK_ALWAYS_EAGER or _can_process_inline(source):
            process_project_source(source.pk)
            return
        try:
            process_project_source_task.apply_async(args=(str(source.pk),), retry=False)
        except OperationalError:
            logger.warning('Workbench processing queue unavailable for source %s', source.pk)
            if not settings.IS_PROD:
                process_project_source(source.pk)
            else:
                ProjectSource.objects.filter(pk=source.pk, status=ProjectSource.Status.PENDING).update(
                    status=ProjectSource.Status.FAILED, error_message='解析队列暂不可用，请稍后重试。',
                    updated_at=timezone.now(),
                )
    transaction.on_commit(dispatch, using=source._state.db)
