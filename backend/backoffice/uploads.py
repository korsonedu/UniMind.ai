import io
import logging
import math
from pathlib import Path
from uuid import uuid4

from django.conf import settings
from django.core import signing
from django.db import transaction
from django.core.files.uploadedfile import UploadedFile
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers
from rest_framework.exceptions import APIException

from core.file_validation import (validate_upload_file, IMAGE_EXTENSIONS, DOCUMENT_EXTENSIONS,
                                  IMAGE_MAX_BYTES, DOC_MAX_BYTES, VIDEO_MAX_BYTES)
from courses.models import Course, VideoTranscript, CourseOutline
from courses.views import _get_oss_bucket, OSS_PART_SIZE
from users.quota import check_and_add_storage_usage, remove_storage_usage
from .common import identity, managed, delete_files_after_commit

FIELDS = {'video_file': ({'.mp4', '.m4v', '.webm', '.mov'}, VIDEO_MAX_BYTES),
          'cover_image': (IMAGE_EXTENSIONS, IMAGE_MAX_BYTES),
          'courseware': (DOCUMENT_EXTENSIONS, DOC_MAX_BYTES),
          'reference_materials': (DOCUMENT_EXTENSIONS, DOC_MAX_BYTES)}
SALT = 'backoffice.upload.v1'
logger = logging.getLogger(__name__)


def cleanup_upload(store, key, upload_id):
    import oss2
    try:
        try:
            store.abort_multipart_upload(key, upload_id)
        except oss2.exceptions.NoSuchUpload:
            pass
        store.delete_object(key)
    except Exception:
        logger.exception('Backoffice abandoned upload cleanup failed')


def process_video(course_id):
    try:
        from courses.views import _extract_cover_async
        from courses.services.task_dispatcher import dispatch_transcription
        _extract_cover_async(course_id)
        dispatch_transcription(course_id)
    except Exception:
        logger.exception('Backoffice video processing dispatch failed for course %s', course_id)


class StorageUnavailable(APIException):
    status_code = 503
    default_detail = '文件存储暂不可用，请稍后重试。'


def bucket():
    if not all((settings.OSS_BUCKET_NAME, settings.OSS_ACCESS_KEY_ID, settings.OSS_ACCESS_KEY_SECRET, settings.OSS_ENDPOINT)):
        raise serializers.ValidationError('请先配置 OSS 文件存储。')
    return _get_oss_bucket()


def state(request, data):
    try:
        value = signing.loads(str(data.get('ticket', '')), salt=SALT, max_age=7200)
    except signing.BadSignature:
        raise serializers.ValidationError('上传凭证无效或已过期，请重新上传。')
    course = get_object_or_404(managed(Course.objects.select_for_update()), pk=value['course'])
    if value['actor'] != request.auth or value['institution'] != course.institution_id:
        raise serializers.ValidationError('上传凭证与当前操作者或课程不匹配。')
    return value, course


def start(request, data):
    course = get_object_or_404(managed(Course.objects.all()), pk=identity(data, 'course'))
    field = serializers.ChoiceField(choices=list(FIELDS)).run_validation(data.get('field'))
    name = serializers.CharField(max_length=255).run_validation(data.get('name'))
    extensions, maximum = FIELDS[field]
    size = serializers.IntegerField(min_value=1, max_value=maximum).run_validation(data.get('size'))
    ext = Path(name).suffix.lower()
    if ext not in extensions:
        raise serializers.ValidationError('文件格式不受支持。视频请使用 MP4、M4V、WebM 或 MOV。')
    key = f'institutions/{course.institution_id or "public"}/backoffice/{uuid4().hex}{ext}'
    store = bucket()
    try:
        upload_id = store.init_multipart_upload(key).upload_id
        request.backoffice_rollback = lambda: cleanup_upload(store, key, upload_id)
        urls = [store.sign_url('PUT', key, 3600, params={'uploadId': upload_id, 'partNumber': str(number)})
                for number in range(1, math.ceil(size / OSS_PART_SIZE) + 1)]
    except Exception as exc:
        raise StorageUnavailable() from exc
    ticket = signing.dumps({'actor': request.auth, 'course': course.pk, 'institution': course.institution_id,
                            'field': field, 'size': size, 'key': key, 'upload': upload_id, 'name': name}, salt=SALT)
    return {'id': course.pk, 'ticket': ticket, 'part_size': OSS_PART_SIZE, 'urls': urls}


def complete(request, data):
    import oss2
    value, course = state(request, data)
    if getattr(course, value['field']).name == value['key']:
        request.backoffice_no_change = True
        return {'id': course.pk, 'attached': True}
    store = bucket()
    request.backoffice_rollback = lambda: cleanup_upload(store, value['key'], value['upload'])
    if value['field'] == 'video_file' and (
        VideoTranscript.objects.filter(course=course, asr_status='processing').exists()
        or CourseOutline.objects.filter(course=course, status='generating').exists()
    ):
        raise serializers.ValidationError('当前视频仍在处理中，请处理完成后再替换。')
    try:
        # Parts are enumerated by OSS, never trusted from browser-supplied ETags.
        try:
            parts = store.list_parts(value['key'], value['upload'], max_parts=1000).parts
            if len(parts) != math.ceil(value['size'] / OSS_PART_SIZE) or sum(part.size for part in parts) != value['size']:
                raise serializers.ValidationError('文件尚未完整上传。')
            store.complete_multipart_upload(value['key'], value['upload'],
                                            [oss2.models.PartInfo(part.part_number, part.etag) for part in parts])
        except oss2.exceptions.NoSuchUpload:
            pass  # Completion may have succeeded before a lost response; revalidate the object.
        actual_size = store.head_object(value['key']).content_length
        if actual_size != value['size']:
            raise serializers.ValidationError('上传文件大小与声明不符。')
        header = store.get_object(value['key'], byte_range=(0, 7)).read()
        extensions, maximum = FIELDS[value['field']]
        validate_upload_file(UploadedFile(file=io.BytesIO(header), name=value['name'], size=actual_size),
                             allowed_extensions=extensions, max_size_bytes=maximum)
    except serializers.ValidationError:
        raise
    except Exception as exc:
        raise StorageUnavailable() from exc
    old_file = getattr(course, value['field'])
    from courses.signals import _get_file_size
    old_size = _get_file_size(old_file)
    remove_storage_usage(course.institution, old_size)
    check_and_add_storage_usage(course.institution, actual_size)
    # File side effects follow the committed metadata and audit transaction.
    Course.objects.filter(pk=course.pk).update(**{value['field']: value['key'], 'updated_at': timezone.now()})
    delete_files_after_commit([old_file])
    if value['field'] == 'video_file':
        VideoTranscript.objects.filter(course=course).delete()
        CourseOutline.objects.filter(course=course).delete()
        course.video_questions.update(is_active=False)
        transaction.on_commit(lambda: process_video(course.pk))
    return {'id': course.pk, 'attached': True}


def cancel(request, data):
    value, course = state(request, data)
    if getattr(course, value['field']).name == value['key']:
        raise serializers.ValidationError('文件已保存到课程，不能取消上传。')
    try:
        import oss2
        store = bucket()
        try:
            store.abort_multipart_upload(value['key'], value['upload'])
        except oss2.exceptions.NoSuchUpload:
            pass
        store.delete_object(value['key'])
    except Exception as exc:
        raise StorageUnavailable() from exc
    return {'id': course.pk, 'cancelled': True}
