"""
阿里云 OSS 存储后端 (兼容 Django 6.0)
"""
import time
import tempfile
import oss2
from django.core.files.storage import Storage
from django.core.files import File
from django.utils.deconstruct import deconstructible
from django.conf import settings
from django.core.cache import cache


# 签名 URL 有效期（秒）：图片 24h，可覆盖
OSS_URL_TTL = getattr(settings, "OSS_URL_TTL", 86400)


@deconstructible
class OssMediaStorage(Storage):
    """阿里云 OSS 存储后端（私有 Bucket，返回签名 URL）"""

    def __init__(self):
        auth = oss2.Auth(settings.OSS_ACCESS_KEY_ID, settings.OSS_ACCESS_KEY_SECRET)
        self.bucket = oss2.Bucket(auth, settings.OSS_ENDPOINT, settings.OSS_BUCKET_NAME)

    def _open(self, name, mode="rb"):
        content = tempfile.SpooledTemporaryFile(max_size=8 * 1024 * 1024, mode="w+b")
        try:
            with self.bucket.get_object(name) as result:
                while chunk := result.read(1024 * 1024):
                    content.write(chunk)
            content.seek(0)
            return File(content, name=name)
        except BaseException:
            content.close()
            raise

    def _save(self, name, content):
        self.bucket.put_object(name, content)
        return name

    def delete(self, name):
        self.bucket.delete_object(name)

    def exists(self, name):
        return self.bucket.object_exists(name)

    def url(self, name):
        """返回签名 URL。加缓存避免每次调用都向 OSS 发请求。"""
        cache_key = f"oss:url:{name}"
        cached = cache.get(cache_key)
        if cached and cached["expires_at"] > time.time() + 300:
            return cached["url"]
        signed_url = self.bucket.sign_url("GET", name, OSS_URL_TTL)
        cache.set(cache_key, {"url": signed_url, "expires_at": time.time() + OSS_URL_TTL}, timeout=OSS_URL_TTL - 60)
        return signed_url

    def size(self, name):
        result = self.bucket.get_object_meta(name)
        return result.content_length
