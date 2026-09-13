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
    # 视频
    ".mp4": ["video/mp4"],
    ".m4v": ["video/x-m4v", "video/mp4"],
    ".webm": ["video/webm"],
    ".mov": ["video/quicktime"],
    ".mkv": ["video/x-matroska", "video/mkv"],
    ".avi": ["video/x-msvideo", "video/avi", "video/msvideo"],
    ".flv": ["video/x-flv", "video/flv"],
    ".wmv": ["video/x-ms-wmv", "video/wmv"],
    ".mpeg": ["video/mpeg"],
    ".mpg": ["video/mpeg"],
    ".rmvb": ["application/vnd.rn-realmedia-vbr", "video/vnd.rn-realmedia-vbr"],
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

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
# 注意：mkv/avi/flv/wmv/rmvb 浏览器无法直接播放，上传后需转码或改封装才能在线观看
VIDEO_EXTENSIONS = {
    ".mp4", ".m4v", ".webm", ".mov",
    ".mkv", ".avi", ".flv", ".wmv", ".mpeg", ".mpg", ".rmvb",
}
DOCUMENT_EXTENSIONS = {".pdf", ".doc", ".docx", ".ppt", ".pptx", ".xls", ".xlsx"}

# 文件 magic bytes（用于内容校验，防止伪造扩展名）
MAGIC_BYTES = {
    # 图片
    ".jpg": [b"\xff\xd8\xff"],
    ".jpeg": [b"\xff\xd8\xff"],
    ".png": [b"\x89PNG"],
    ".gif": [b"GIF87a", b"GIF89a"],
    ".webp": [b"RIFF"],
    # 视频
    ".mp4": [b"\x00\x00\x00", b"ftyp"],  # ISO BM4 / ftyp box
    ".m4v": [b"\x00\x00\x00", b"ftyp"],  # 与 mp4 同为 ISO BM4 容器
    ".webm": [b"\x1a\x45\xdf\xa3"],  # EBML header
    ".mkv": [b"\x1a\x45\xdf\xa3"],  # Matroska 同用 EBML
    ".avi": [b"RIFF"],
    ".flv": [b"FLV"],
    ".wmv": [b"\x30\x26\xb2\x75\x8e\x66\xcf\x11"],  # ASF header
    ".mpeg": [b"\x00\x00\x01"],
    ".mpg": [b"\x00\x00\x01"],
    ".rmvb": [b".RMF"],
    # 文档
    ".pdf": [b"%PDF"],
    ".doc": [b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"],  # OLE2
    ".docx": [b"PK"],  # ZIP-based (OOXML)
    ".ppt": [b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"],
    ".pptx": [b"PK"],
    ".xls": [b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"],
    ".xlsx": [b"PK"],
}

# 保留旧名称兼容
IMAGE_MAGIC_BYTES = {k: v for k, v in MAGIC_BYTES.items() if k in IMAGE_EXTENSIONS}

# 危险扩展名黑名单（优先于白名单）
DANGEROUS_EXTENSIONS = {
    ".exe", ".bat", ".cmd", ".sh", ".ps1", ".vbs", ".js", ".msi",
    ".dll", ".so", ".dylib", ".php", ".asp", ".aspx", ".jsp", ".py",
    ".rb", ".pl", ".cgi", ".htaccess",
}


def _get_default_max_bytes(ext: str) -> int:
    """根据扩展名返回对应类别的默认大小上限。"""
    if ext in IMAGE_EXTENSIONS:
        return IMAGE_MAX_BYTES
    if ext in VIDEO_EXTENSIONS:
        return VIDEO_MAX_BYTES
    if ext in DOCUMENT_EXTENSIONS:
        return DOC_MAX_BYTES
    return DEFAULT_MAX_BYTES


def _validate_magic_bytes(file_obj, ext: str) -> None:
    """校验文件的 magic bytes，防止伪造扩展名。"""
    magic_list = MAGIC_BYTES.get(ext)
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

    # magic bytes 校验（图片/视频/文档）
    _validate_magic_bytes(file_obj, ext)
