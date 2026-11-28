"""Validate and format multimodal chat image attachments for XiaoYu (data URLs or safe HTTPS URLs)."""

import base64
import ipaddress
import re
from typing import Any, List
from urllib.parse import urlparse

from rest_framework.exceptions import ValidationError


MAX_CHAT_IMAGES = 3
MAX_IMAGE_BYTES = 1_500_000  # 1.5 MB decoded per image to bound vision token cost & DB metadata size
_DATA_URL_RE = re.compile(r"^data:image/(jpeg|jpg|png|webp);base64,([A-Za-z0-9+/=\s]+)$", re.IGNORECASE)

_MAGIC_HEADERS = {
    "jpeg": (b"\xff\xd8\xff",),
    "jpg": (b"\xff\xd8\xff",),
    "png": (b"\x89PNG\r\n\x1a\n",),
    "webp": (b"RIFF",),
}


def _validate_https_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname:
        raise ValidationError({"images": "仅支持 https 图片链接或 base64 图片数据。"})
    host = parsed.hostname.lower()
    if host in ("localhost", "127.0.0.1", "0.0.0.0", "::1") or host.endswith(".local"):
        raise ValidationError({"images": "不允许使用本地或内网图片地址。"})
    try:
        ip = ipaddress.ip_address(host)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            raise ValidationError({"images": "不允许使用内网或保留网段图片地址。"})
    except ValueError:
        pass
    if len(url) > 2048:
        raise ValidationError({"images": "图片链接过长。"})
    return url


def _validate_data_url(raw: str) -> str:
    match = _DATA_URL_RE.match(raw.strip())
    if not match:
        raise ValidationError({"images": "图片格式仅支持 JPEG、PNG 或 WebP。"})
    fmt = match.group(1).lower()
    b64_body = re.sub(r"\s+", "", match.group(2))
    try:
        decoded = base64.b64decode(b64_body, validate=True)
    except Exception as exc:
        raise ValidationError({"images": "图片 base64 编码无效。"}) from exc
    if not decoded or len(decoded) > MAX_IMAGE_BYTES:
        raise ValidationError({"images": "单张图片大小不能超过 1.5MB，请先压缩后上传。"})
    if not any(decoded.startswith(prefix) for prefix in _MAGIC_HEADERS[fmt]):
        raise ValidationError({"images": "图片内容与声明格式不符。"})
    if fmt == "webp" and decoded[8:12] != b"WEBP":
        raise ValidationError({"images": "WebP 图片头无效。"})
    mime = "jpeg" if fmt == "jpg" else fmt
    return f"data:image/{mime};base64,{b64_body}"


def prepare_chat_images(raw_images: Any) -> List[dict]:
    """Validate incoming request `images` field and return sanitized metadata list.

    Accepts a list of either:
      - string (`data:image/...;base64,...` or `https://...`)
      - dict (`{"url": "...", "alt": "..."}`)
    """
    if not raw_images:
        return []
    if not isinstance(raw_images, list):
        raise ValidationError({"images": "images 必须为数组。"})
    if len(raw_images) > MAX_CHAT_IMAGES:
        raise ValidationError({"images": f"单条消息最多附带 {MAX_CHAT_IMAGES} 张图片。"})

    sanitized: List[dict] = []
    for item in raw_images:
        if isinstance(item, str):
            url_raw = item.strip()
            alt = ""
        elif isinstance(item, dict):
            url_raw = str(item.get("url") or "").strip()
            alt = str(item.get("alt") or "").strip()[:120]
        else:
            raise ValidationError({"images": "图片项格式无效。"})
        if not url_raw:
            continue
        if url_raw.lower().startswith("data:image/"):
            clean_url = _validate_data_url(url_raw)
        else:
            clean_url = _validate_https_url(url_raw)
        entry = {"url": clean_url}
        if alt:
            entry["alt"] = alt
        sanitized.append(entry)
    return sanitized


def chat_image_messages(chat_images: Any) -> List[dict]:
    """Convert sanitized `metadata['chat_images']` entries into OpenAI `image_url` content blocks."""
    if not chat_images or not isinstance(chat_images, list):
        return []
    blocks: List[dict] = []
    for entry in chat_images[:MAX_CHAT_IMAGES]:
        if not isinstance(entry, dict):
            continue
        url = str(entry.get("url") or "").strip()
        if not url:
            continue
        blocks.append({"type": "image_url", "image_url": {"url": url}})
    return blocks
