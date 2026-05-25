"""文件上传安全校验（等保二级：恶意代码防范）。"""

import os
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

# 危险扩展名黑名单（优先于白名单）
DANGEROUS_EXTENSIONS = {
    ".exe", ".bat", ".cmd", ".sh", ".ps1", ".vbs", ".js", ".msi",
    ".dll", ".so", ".dylib", ".php", ".asp", ".aspx", ".jsp", ".py",
    ".rb", ".pl", ".cgi", ".htaccess",
}


def validate_upload_file(file_obj, *, allowed_extensions: set[str] | None = None):
    """校验上传文件的扩展名和 MIME 类型。

    Args:
        file_obj: Django InMemoryUploadedFile 或 TemporaryUploadedFile
        allowed_extensions: 自定义允许的扩展名集合（如 {".jpg", ".png"}），
                           为 None 时使用全局 ALLOWED_UPLOAD_TYPES 白名单。

    Raises:
        ValidationError: 文件不在白名单中或扩展名被黑名单拦截
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
        return

    # 全局白名单
    if ext not in ALLOWED_UPLOAD_TYPES:
        raise ValidationError({"error": f"不允许上传 {ext} 类型的文件"})

    # MIME 类型校验（content_type 由浏览器提供，不完全可信，但多一层防护）
    allowed_mimes = ALLOWED_UPLOAD_TYPES[ext]
    content_type = getattr(file_obj, "content_type", None)
    if content_type and content_type not in allowed_mimes:
        raise ValidationError({"error": f"文件类型不匹配：期望 {', '.join(allowed_mimes)}，收到 {content_type}"})
