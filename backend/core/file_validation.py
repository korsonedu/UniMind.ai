"""文件上传安全校验（等保二级：恶意代码防范）。"""

import os
import struct
from rest_framework.exceptions import ValidationError

# 允许的文件扩展名 → MIME 类型映射
ALLOWED_UPLOAD_TYPES = {
    # 图片
    ".jpg": ["image/jpeg"],
    ".jpeg": ["image/jpeg"],
    ".png": ["image/png"],
    ".gif": ["image/gif"],
    ".webp": ["image/webp"],
    ".svg": ["image/svg+xml"],
    # 视频
    ".mp4": ["video/mp4"],
    ".webm": ["video/webm"],
    ".mov": ["video/quicktime"],
    # 文档
    ".pdf": ["application/pdf"],
    ".doc": ["application/msword"],
    ".docx": ["application/vnd.openxmlformats-officedocument.wordprocessingml.document"],
    ".ppt": ["application/vnd.ms-powerpoint"],
    ".pptx": ["application/vnd.openxmlformats-officedocument.presentationml.presentation"],
    ".xls": ["application/vnd.ms-excel"],
    ".xlsx": ["application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"],
    # 压缩包
    ".zip": ["application/zip", "application/x-zip-compressed"],
    ".md": ["text/markdown", "text/plain"],
    ".txt": ["text/plain"],
}

# 按类别文件大小上限（可通过环境变量覆盖）
IMAGE_MAX_BYTES = 10 * 1024 * 1024       # 10 MB
DOC_MAX_BYTES = 50 * 1024 * 1024         # 50 MB
VIDEO_MAX_BYTES = 500 * 1024 * 1024      # 500 MB
DEFAULT_MAX_BYTES = 50 * 1024 * 1024     # 50 MB

_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg"}
_VIDEO_EXTS = {".mp4", ".webm", ".mov"}
_DOC_EXTS = {".pdf", ".doc", ".docx", ".ppt", ".pptx", ".xls", ".xlsx"}

# 图片 magic bytes（用于内容校验，防止伪造扩展名）
IMAGE_MAGIC_BYTES = {
    ".jpg": [b"\xff\xd8\xff"],
    ".jpeg": [b"\xff\xd8\xff"],
    ".png": [b"\x89PNG"],
    ".gif": [b"GIF87a", b"GIF89a"],
    ".webp": [b"RIFF"],
}

# 危险扩展名黑名单（优先于白名单）
DANGEROUS_EXTENSIONS = {
    ".exe", ".bat", ".cmd", ".sh", ".ps1", ".vbs", ".js", ".msi",
    ".dll", ".so", ".dylib", ".php", ".asp", ".aspx", ".jsp", ".py",
    ".rb", ".pl", ".cgi", ".htaccess",
}


def _get_default_max_bytes(ext: str) -> int:
    """根据扩展名返回对应类别的默认大小上限。"""
    if ext in _IMAGE_EXTS:
        return IMAGE_MAX_BYTES
    if ext in _VIDEO_EXTS:
        return VIDEO_MAX_BYTES
    if ext in _DOC_EXTS:
        return DOC_MAX_BYTES
    return DEFAULT_MAX_BYTES


def _validate_image_magic(file_obj, ext: str) -> None:
    """校验图片文件的 magic bytes，防止伪造扩展名。"""
    magic_list = IMAGE_MAGIC_BYTES.get(ext)
    if not magic_list:
        return
    header = file_obj.read(8)
    file_obj.seek(0)
    if not any(header.startswith(m) for m in magic_list):
        raise ValidationError({"error": "文件内容与声明的格式不匹配"})


def validate_upload_file(
    file_obj,
    *,
    allowed_extensions: set[str] | None = None,
    max_size_bytes: int | None = None,
):
    """校验上传文件的扩展名、MIME 类型和大小。

    Args:
        file_obj: Django InMemoryUploadedFile 或 TemporaryUploadedFile
        allowed_extensions: 自定义允许的扩展名集合（如 {".jpg", ".png"}），
                           为 None 时使用全局 ALLOWED_UPLOAD_TYPES 白名单。
        max_size_bytes: 自定义大小上限（字节），为 None 时按文件类别自动判断。

    Raises:
        ValidationError: 文件不在白名单中、扩展名被黑名单拦截、或超出大小限制
    """
    if not file_obj:
        return

    ext = os.path.splitext(file_obj.name)[1].lower()

    # 黑名单优先
    if ext in DANGEROUS_EXTENSIONS:
        raise ValidationError({"error": f"不允许上传 {ext} 类型的文件"})

    # 自定义白名单
    if allowed_extensions is not None:
        if ext not in allowed_extensions:
            raise ValidationError({"error": f"不允许上传 {ext} 类型的文件"})
    else:
        # 全局白名单
        if ext not in ALLOWED_UPLOAD_TYPES:
            raise ValidationError({"error": f"不允许上传 {ext} 类型的文件"})

        # MIME 类型校验（content_type 由浏览器提供，不完全可信，但多一层防护）
        allowed_mimes = ALLOWED_UPLOAD_TYPES[ext]
        content_type = getattr(file_obj, "content_type", None)
        if content_type and content_type not in allowed_mimes:
            raise ValidationError({"error": f"文件类型不匹配：期望 {', '.join(allowed_mimes)}，收到 {content_type}"})

    # 文件大小校验
    limit = max_size_bytes if max_size_bytes is not None else _get_default_max_bytes(ext)
    if file_obj.size > limit:
        limit_mb = limit // (1024 * 1024)
        raise ValidationError({"error": f"文件大小超出限制（上限 {limit_mb}MB）"})

    # 图片 magic bytes 校验
    if ext in _IMAGE_EXTS:
        _validate_image_magic(file_obj, ext)
