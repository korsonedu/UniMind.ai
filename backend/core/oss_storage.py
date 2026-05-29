"""
阿里云 OSS 存储后端 (兼容 Django 6.0)
"""
import oss2
from django.core.files.storage import Storage
from django.core.files.base import ContentFile
from django.utils.deconstruct import deconstructible
from django.conf import settings


@deconstructible
class OssMediaStorage(Storage):
    """阿里云 OSS 存储后端"""

    def __init__(self):
        auth = oss2.Auth(settings.OSS_ACCESS_KEY_ID, settings.OSS_ACCESS_KEY_SECRET)
        self.bucket = oss2.Bucket(auth, settings.OSS_ENDPOINT, settings.OSS_BUCKET_NAME)

    def _open(self, name, mode="rb"):
        result = self.bucket.get_object(name)
        return ContentFile(result.read())

    def _save(self, name, content):
        if hasattr(content, "read"):
            content = content.read()
        self.bucket.put_object(name, content)
        return name

    def delete(self, name):
        self.bucket.delete_object(name)

    def exists(self, name):
        return self.bucket.object_exists(name)

    def url(self, name):
        return f"https://{settings.OSS_BUCKET_NAME}.{settings.OSS_ENDPOINT}/{name}"

    def size(self, name):
        result = self.bucket.get_object_meta(name)
        return result.content_length
