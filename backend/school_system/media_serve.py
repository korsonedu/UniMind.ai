"""
Range-aware media file serving view.

Django's built-in static serve does not handle HTTP Range requests, which
means HTML5 <video> elements cannot seek or jump to timestamps.  This view
adds Range support so that video seeking works correctly in the browser.
"""

import os
import re
from email.utils import formatdate, parsedate_to_datetime

from django.conf import settings
from django.http import HttpResponse, StreamingHttpResponse, HttpResponseRedirect
from rest_framework.exceptions import AuthenticationFailed, PermissionDenied

from core.authentication import CookieTokenAuthentication

_RANGE_RE = re.compile(r"bytes\s*=\s*(\d*)\s*-\s*(\d*)")

_CONTENT_TYPE_MAP = {
    ".mp4": "video/mp4",
    ".webm": "video/webm",
    ".ogv": "video/ogg",
    ".mkv": "video/x-matroska",
    ".mov": "video/quicktime",
    ".avi": "video/x-msvideo",
    ".mp3": "audio/mpeg",
    ".m4a": "audio/mp4",
    ".ogg": "audio/ogg",
    ".wav": "audio/wav",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".svg": "image/svg+xml",
    ".pdf": "application/pdf",
}


def _guess_content_type(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()
    return _CONTENT_TYPE_MAP.get(ext, "application/octet-stream")


def _iter_chunks(file_path: str, offset: int = 0, size: int | None = None, chunk_size: int = 65536):
    """Yield file chunks from *offset*, limited to *size* bytes total."""
    sent = 0
    with open(file_path, "rb") as f:
        f.seek(offset)
        while True:
            chunk = f.read(min(chunk_size, size - sent) if size is not None else chunk_size)
            if not chunk:
                break
            sent += len(chunk)
            yield chunk
            if size is not None and sent >= size:
                break


def media_serve(request, path):
    # 所有存储后端共用同一对象路径，必须在查询和签名前拒绝路径穿越。
    if (not path or '\\' in path or '\x00' in path
            or any(part in {'.', '..', ''} for part in path.split('/'))):
        return HttpResponse(status=404)
    if not request.user.is_authenticated:
        try:
            authentication = CookieTokenAuthentication().authenticate(request)
        except AuthenticationFailed:
            return HttpResponse(status=401)
        if authentication is not None:
            request.user, _ = authentication

    from django.db.models import Q
    from courses.models import Course, StartupMaterial
    from faq_system.models import Question
    from core.utils import apply_institution_filter
    from users.feature_access import has_learning_feature

    course_file = Q(video_file=path) | Q(courseware=path) | Q(reference_materials=path)
    courses = Course.objects.filter(course_file)
    questions = Question.objects.filter(attachment=path)
    materials = StartupMaterial.objects.filter(file=path)
    protected = None
    feature = None
    if courses.exists():
        protected, feature = courses, 'course.video'
    elif questions.exists():
        protected, feature = questions, 'faq.system'
    elif materials.exists():
        protected, feature = materials, 'course.video'

    # 聊天图片在发送消息前就需要预览，上传接口使用 UUID 文件名。
    is_chat_image = bool(re.fullmatch(r'chat_images/[a-f0-9]{32}(?:_[A-Za-z0-9]+)?\.(?:jpg|jpeg|png|gif|webp)', path))
    if is_chat_image and feature is None:
        feature = 'study.room'

    if protected is not None or is_chat_image:
        if not request.user.is_authenticated:
            return HttpResponse(status=401)
        if not has_learning_feature(request.user, feature):
            return HttpResponse(status=403)
        try:
            if protected is not None and not apply_institution_filter(protected, request.user, request).exists():
                return HttpResponse(status=403)
        except PermissionDenied:
            return HttpResponse(status=403)
    else:
        public_image_dirs = {'album_covers', 'course_covers', 'article_covers', 'school_logos', 'institution_logos', 'bot_avatars'}
        is_image = os.path.splitext(path)[1].lower() in {'.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg', '.avif'}
        if not (is_image and (path.split('/')[0] in public_image_dirs or Course.objects.filter(cover_image=path).exists())):
            # 未关联业务记录的文件不能凭路径获得新的签名。
            return HttpResponse(status=404)

    # 如果配置了 OSS，使用签名 URL
    if hasattr(settings, 'OSS_ACCESS_KEY_ID') and settings.OSS_ACCESS_KEY_ID:
        import oss2
        auth = oss2.Auth(settings.OSS_ACCESS_KEY_ID, settings.OSS_ACCESS_KEY_SECRET)
        bucket = oss2.Bucket(auth, settings.OSS_ENDPOINT, settings.OSS_BUCKET_NAME)

        # 生成签名 URL（有效期 1 小时）
        url = bucket.sign_url('GET', path, 3600)
        return HttpResponseRedirect(url)

    # 本地文件服务（开发环境）
    document_root = settings.MEDIA_ROOT

    document_root = os.path.realpath(document_root)
    full = os.path.realpath(os.path.join(document_root, path))
    if os.path.commonpath([document_root, full]) != document_root:
        return HttpResponse(status=404)
    if not os.path.isfile(full):
        return HttpResponse(status=404)

    stat = os.stat(full)
    file_size = stat.st_size
    mtime = stat.st_mtime

    # 304 Not Modified
    since = request.META.get("HTTP_IF_MODIFIED_SINCE", "")
    if since:
        try:
            if parsedate_to_datetime(since).timestamp() >= mtime:
                resp = HttpResponse(status=304)
                resp["Last-Modified"] = formatdate(mtime, usegmt=True)
                return resp
        except (ValueError, TypeError):
            pass

    content_type = _guess_content_type(full)
    range_header = request.META.get("HTTP_RANGE", "").strip()

    # ── Range request ──────────────────────────────────────────────────
    m = _RANGE_RE.match(range_header)
    if m:
        first, last = m.groups()
        start = int(first) if first else 0
        end = int(last) if last else file_size - 1
        if start >= file_size:
            start = file_size - 1
        if end >= file_size:
            end = file_size - 1
        if start > end:
            start = end

        chunk = _iter_chunks(full, offset=start, size=end - start + 1)
        resp = StreamingHttpResponse(chunk, content_type=content_type, status=206)
        resp["Content-Range"] = f"bytes {start}-{end}/{file_size}"
        resp["Content-Length"] = str(end - start + 1)
        resp["Accept-Ranges"] = "bytes"
        resp["Last-Modified"] = formatdate(mtime, usegmt=True)
        return resp

    # ── Full request ───────────────────────────────────────────────────
    resp = StreamingHttpResponse(
        _iter_chunks(full, offset=0),
        content_type=content_type,
        status=200,
    )
    resp["Content-Length"] = str(file_size)
    resp["Accept-Ranges"] = "bytes"
    resp["Last-Modified"] = formatdate(mtime, usegmt=True)
    return resp
