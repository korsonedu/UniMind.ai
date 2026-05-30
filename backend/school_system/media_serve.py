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
    # 权限检查：机构文件必须登录才能访问
    if path.startswith('institutions/') and not request.user.is_authenticated:
        return HttpResponse(status=401)

    # 权限检查：租户只能访问自己机构的文件
    if request.user.is_authenticated:
        # 检查是否访问的是机构文件
        if path.startswith('institutions/'):
            # 提取机构 ID
            parts = path.split('/')
            if len(parts) >= 2:
                institution_id = parts[1]

                # 超管可以访问所有文件
                if request.user.is_superuser:
                    pass
                # 普通用户只能访问自己机构的文件
                elif hasattr(request.user, 'institution_id') and str(request.user.institution_id) == institution_id:
                    pass
                else:
                    return HttpResponse(status=403)

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

    full = os.path.normpath(os.path.join(document_root, path))
    if not full.startswith(os.path.normpath(document_root)):
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
