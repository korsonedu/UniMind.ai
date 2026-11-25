"""
Range-aware media file serving view.

Django's built-in static serve does not handle HTTP Range requests, which
means HTML5 <video> elements cannot seek or jump to timestamps.  This view
adds Range support so that video seeking works correctly in the browser.
"""

import os
import re
from email.utils import formatdate, parsedate_to_datetime
from urllib.parse import unquote, urlsplit

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core import signing
from django.http import HttpResponse, HttpResponseNotAllowed, StreamingHttpResponse, HttpResponseRedirect
from rest_framework.exceptions import AuthenticationFailed, NotFound, PermissionDenied

from core.authentication import CookieTokenAuthentication

MEDIA_TICKET_SALT = "media-access"
MEDIA_TICKET_TTL = 300

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


def _is_valid_media_path(path: str) -> bool:
    return bool(
        path
        and '\\' not in path
        and '\x00' not in path
        and not any(part in {'.', '..', ''} for part in path.split('/'))
    )


def normalize_media_path(raw_path: str) -> str | None:
    """Normalize a /media/... path or URL into the relative storage path expected by media_serve."""
    if not isinstance(raw_path, str):
        return None
    candidate = raw_path.strip()
    if not candidate:
        return None
    try:
        parsed = urlsplit(candidate)
    except ValueError:
        return None
    if parsed.scheme or parsed.netloc:
        if parsed.scheme not in {'http', 'https'} or not parsed.netloc or not parsed.path.startswith('/media/'):
            return None
    elif parsed.path.startswith('/') and not parsed.path.startswith('/media/'):
        return None
    decoded = unquote(parsed.path)
    if decoded.startswith('/media/'):
        decoded = decoded.removeprefix('/media/')
    elif decoded.startswith('media/'):
        decoded = decoded.removeprefix('media/')
    return decoded if _is_valid_media_path(decoded) else None


def issue_media_ticket(user, raw_path: str) -> tuple[str, str] | None:
    """Sign a short-lived media access token bound to (user_id, account_session_version, media_path)."""
    media_path = normalize_media_path(raw_path)
    if not media_path:
        return None
    from ai_assistant.models import WORKBENCH_SOURCE_PREFIX
    if media_path.startswith(WORKBENCH_SOURCE_PREFIX):
        from courses.access import private_companion_courses
        if not private_companion_courses(user).filter(video_file=media_path).exists():
            raise NotFound('视频不存在。')
    from users.workspaces.identity import account_user
    account = account_user(user)
    payload = {
        "u": user.id,
        "p": media_path,
        "v": account.account_session_version,
    }
    token = signing.dumps(payload, salt=MEDIA_TICKET_SALT, compress=True)
    return token, media_path


def resolve_user_from_media_token(media_token: str, media_path: str):
    """Verify a signed media token against exact media_path, TTL, active user, and session version."""
    if not media_token:
        return None
    try:
        payload = signing.loads(media_token, salt=MEDIA_TICKET_SALT, max_age=MEDIA_TICKET_TTL)
    except signing.BadSignature:
        return None
    if not isinstance(payload, dict) or payload.get("p") != media_path:
        return None
    user_id = payload.get("u")
    version = payload.get("v")
    if (not isinstance(user_id, int) or isinstance(user_id, bool)
            or not isinstance(version, int) or isinstance(version, bool)):
        return None
    user = get_user_model().objects.filter(pk=user_id, is_active=True).first()
    if not user:
        return None
    from users.workspaces.identity import account_user
    account = account_user(user)
    if not account.is_active or account.account_session_version != version:
        return None
    return user


def media_serve(request, path):
    # 所有存储后端共用同一对象路径，必须在查询和签名前拒绝路径穿越。
    if not _is_valid_media_path(path):
        return HttpResponse(status=404)
    if not request.user.is_authenticated:
        try:
            authentication = CookieTokenAuthentication().authenticate(request)
        except AuthenticationFailed:
            return HttpResponse(status=401)
        except PermissionDenied:
            return HttpResponse(status=403)
        if authentication is not None:
            request.user, _ = authentication
    media_identity = False
    if not request.user.is_authenticated and request.method in ("GET", "HEAD"):
        media_token = request.GET.get("media_token", "").strip()
        if media_token:
            user = resolve_user_from_media_token(media_token, path)
            if user is None:
                return HttpResponse(status=401)
            request.user = user
            media_identity = True

    if request.user.is_authenticated:
        from users.workspaces.identity import account_user, request_learner
        try:
            if media_identity:
                from users.workspaces.access import membership_for
                membership_for(request.user)
            else:
                request.user = request_learner(request, account_user(request.user))
        except PermissionDenied:
            return HttpResponse(status=403)

    from ai_assistant.models import WORKBENCH_SOURCE_PREFIX
    if path.startswith(WORKBENCH_SOURCE_PREFIX):
        if request.method not in ('GET', 'HEAD'):
            return HttpResponseNotAllowed(('GET', 'HEAD'))
        if not request.user.is_authenticated:
            return HttpResponse(status=401)
        from courses.access import private_companion_courses
        if not private_companion_courses(request.user).filter(video_file=path).exists():
            return HttpResponse(status=404)
        response = _serve_media_file(request, path)
        response['Cache-Control'] = 'private, no-store'
        return response

    denial = _shared_media_denial(request, path)
    return denial if denial is not None else _serve_media_file(request, path)


def _shared_media_denial(request, path):
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
        from courses.access import visible_courses
        protected, feature = courses.filter(pk__in=visible_courses(request)), 'course.video'
    elif questions.exists():
        protected, feature = questions, 'faq.system'
    elif materials.exists():
        from courses.access import has_full_course_access
        if request.user.is_authenticated and not has_full_course_access(request.user):
            return HttpResponse(status=403)
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
        covers = Course.objects.filter(cover_image=path)
        if covers.exists() and not covers.filter(is_published=True).exists():
            return HttpResponse(status=404)
        if not (is_image and (path.split('/')[0] in public_image_dirs or Course.objects.filter(cover_image=path).exists())):
            # 未关联业务记录的文件不能凭路径获得新的签名。
            return HttpResponse(status=404)


def _serve_media_file(request, path):
    # 如果配置了 OSS，使用签名 URL
    if hasattr(settings, 'OSS_ACCESS_KEY_ID') and settings.OSS_ACCESS_KEY_ID:
        import oss2
        auth = oss2.Auth(settings.OSS_ACCESS_KEY_ID, settings.OSS_ACCESS_KEY_SECRET)
        bucket = oss2.Bucket(auth, settings.OSS_ENDPOINT, settings.OSS_BUCKET_NAME)

        # 生成签名 URL（有效期 1 小时）
        from users.workspaces.access import membership_for
        ttl = 300 if membership_for(request.user) else 3600
        url = bucket.sign_url(request.method, path, ttl)
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
    m = _RANGE_RE.fullmatch(range_header)
    if m:
        first, last = m.groups()
        start = int(first) if first else max(0, file_size - int(last or 0))
        end = min(int(last), file_size - 1) if first and last else file_size - 1
        if (not first and not last) or start >= file_size or start > end:
            resp = HttpResponse(status=416)
            resp['Content-Range'] = f'bytes */{file_size}'
            return resp

        if request.method == 'HEAD':
            resp = HttpResponse(content_type=content_type, status=206)
        else:
            resp = StreamingHttpResponse(
                _iter_chunks(full, offset=start, size=end - start + 1),
                content_type=content_type, status=206,
            )
        resp["Content-Range"] = f"bytes {start}-{end}/{file_size}"
        resp["Content-Length"] = str(end - start + 1)
        resp["Accept-Ranges"] = "bytes"
        resp["Last-Modified"] = formatdate(mtime, usegmt=True)
        return resp

    # ── Full request ───────────────────────────────────────────────────
    if request.method == 'HEAD':
        resp = HttpResponse(content_type=content_type)
    else:
        resp = StreamingHttpResponse(_iter_chunks(full, offset=0), content_type=content_type)
    resp["Content-Length"] = str(file_size)
    resp["Accept-Ranges"] = "bytes"
    resp["Last-Modified"] = formatdate(mtime, usegmt=True)
    return resp
