"""Account-bound video download manifests for the desktop client."""
import hashlib
import os
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.core.cache import cache
from django.core import signing
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.exceptions import APIException, NotFound, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import serializers
from rest_framework.permissions import IsAuthenticated

from users.models import CourseStudentStatus
from users.feature_access import has_learning_feature
from users.permissions import IsMember
from .access import visible_courses
from .serializers import RelativeFileField
from .portal import ProgressInput
from .views import VideoProgressUpdateView


GRANT_SALT = 'courses.offline-video'


def video_version(course):
    return hashlib.sha256(f'{course.video_file.name}:{course.updated_at.isoformat()}'.encode()).hexdigest()


class VideoUnavailable(APIException):
    status_code = 503
    default_detail = '暂时无法读取课程视频，请稍后重试。'
    default_code = 'video_unavailable'


def offline_expiry(user):
    now = timezone.now()
    expiry = now + timedelta(hours=24)
    status = CourseStudentStatus.objects.select_related('cohort').filter(user=user).first()
    if status and status.cohort_id:
        # ends_on includes the final service day in Shanghai.
        end = datetime.combine(status.cohort.ends_on + timedelta(days=1), time.min,
                               tzinfo=ZoneInfo('Asia/Shanghai'))
        expiry = min(expiry, end)
    return int(expiry.timestamp()) if expiry > now else None


def offline_manifest(course, user, expires_at):
    video = course.video_file
    if course.module_id and course.module.is_public:
        expires_at = int((timezone.now() + timedelta(hours=24)).timestamp())
    if not video or expires_at is None:
        raise NotFound()
    name = video.name
    if ('\\' in name or '\x00' in name
            or any(part in {'', '.', '..'} for part in name.split('/'))):
        raise VideoUnavailable()
    version = video_version(course)
    try:
        # Reject local symlinks outside storage just as the media route does.
        try:
            root = os.path.realpath(video.storage.location)
            path = os.path.realpath(video.path)
            if os.path.commonpath([root, path]) != root:
                raise VideoUnavailable()
        except (AttributeError, NotImplementedError):
            pass
        key = f'course:offline-size:{version}'
        size = cache.get(key)
        if size is None:
            # OSS uses object metadata, never downloads the video for its size.
            size = video.storage.size(name)
            if type(size) is not int or size <= 0:
                raise VideoUnavailable()
            cache.set(key, size, timeout=300)
    except Exception as exc:
        raise VideoUnavailable() from exc
    grant = signing.dumps({'user_id': user.pk, 'course_id': course.pk, 'version': version,
                           'issued_at': int(timezone.now().timestamp()), 'expires_at': expires_at}, salt=GRANT_SALT)
    return {'user_id': user.pk, 'course_id': course.pk, 'title': course.title, 'grant': grant,
            'expires_at': expires_at, 'version': version,
            'video': {'url': RelativeFileField().to_representation(video),
                      'filename': os.path.basename(name), 'size': size}}


class OfflineManifestView(APIView):
    permission_classes = [IsMember]

    def get(self, request, pk):
        course = get_object_or_404(visible_courses(request).select_related('module'), pk=pk)
        return Response(offline_manifest(course, request.user, offline_expiry(request.user)))


class OfflineAccessView(APIView):
    permission_classes = [IsMember]

    def post(self, request):
        ids = request.data.get('course_ids') if isinstance(request.data, dict) else None
        if (not isinstance(ids, list) or len(ids) > 100
                or any(type(pk) is not int or pk < 1 for pk in ids)):
            raise ValidationError({'course_ids': '请提供不超过 100 个课程 ID。'})
        expiry = offline_expiry(request.user)
        courses = visible_courses(request).filter(pk__in=ids).select_related('module').exclude(video_file='').exclude(video_file__isnull=True)
        if expiry is None:
            courses = courses.filter(module__is_public=True)
        manifests = [offline_manifest(course, request.user, expiry) for course in courses]
        return Response({'user_id': request.user.pk, 'courses': manifests})


class OfflineProgressInput(ProgressInput):
    event_id = serializers.UUIDField()
    grant = serializers.CharField(max_length=2048)
    version = serializers.CharField(max_length=64)
    position = serializers.FloatField(min_value=0)
    duration = serializers.FloatField(min_value=0)
    watched_seconds = serializers.FloatField(min_value=0, max_value=120)
    started_at = serializers.DateTimeField()
    ended_at = serializers.DateTimeField()
    focused_seconds = serializers.IntegerField(min_value=0, default=0)


class OfflineProgressView(VideoProgressUpdateView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        def reject(code, detail, status=400):
            return Response({'terminal': True, 'code': code, 'detail': detail}, status=status)

        if not has_learning_feature(request.user, 'course.video'):
            return reject('access_revoked', '课程功能已关闭。', 403)
        payload = OfflineProgressInput(data=request.data)
        if not payload.is_valid():
            return reject('invalid_payload', payload.errors)
        data = payload.validated_data
        try:
            grant = signing.loads(data['grant'], salt=GRANT_SALT)
        except signing.BadSignature:
            return reject('invalid_grant', '离线授权无效。')
        if grant['user_id'] != request.user.pk:
            return reject('account_mismatch', '离线授权属于其他账号。', 403)
        if grant['course_id'] != pk:
            return reject('invalid_grant', '离线授权不属于此课程。')
        course = visible_courses(request).filter(pk=pk).first()
        if not course or not course.video_file:
            return reject('access_revoked', '课程不可访问。', 404)
        if data['version'] != grant['version'] or data['version'] != video_version(course):
            return reject('version_changed', '课程视频已更新。', 409)
        now = timezone.now().timestamp()
        # A fixed seven-day upload grace only accepts viewing within the original grant.
        if now > grant['expires_at'] + 7 * 24 * 60 * 60:
            return reject('grant_expired', '离线记录已超过七天补传期限。')
        start, end = data['started_at'].timestamp(), data['ended_at'].timestamp()
        if (start < grant['issued_at'] - 30 or end < start or end > grant['expires_at']
                or end > now + 30 or data['duration'] <= 0
                or data['position'] > data['duration'] + 1
                or data['watched_seconds'] > min(end - start + 1, data['duration'])
                or data['focused_seconds'] > int(data['watched_seconds'])):
            return reject('invalid_interval', '观看时间必须在离线授权期限内，时长不得超过实际区间。')
        session = {key: data[key] for key in ('started_at', 'ended_at', 'focused_seconds')}
        response = self.save_progress(request, course, data, learning_session=session)
        if response.status_code >= 400:
            return reject('event_conflict', response.data.get('error', '活动编号冲突。'))
        return response
