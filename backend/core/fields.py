import os
from django.conf import settings
from django.db import models
from cryptography.fernet import Fernet, MultiFernet
import base64
import hashlib


def _get_fernet() -> Fernet:
    key = getattr(settings, 'ENCRYPTION_KEY', '')
    if not key:
        from django.core.exceptions import ImproperlyConfigured
        raise ImproperlyConfigured(
            "ENCRYPTION_KEY is required for encrypted fields. "
            "Generate one with: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
        )
    return Fernet(key.encode() if isinstance(key, str) else key)


class EncryptedCharField(models.CharField):
    """AES 加密存储的 CharField，读取时自动解密。"""

    def __init__(self, *args, **kwargs):
        kwargs.setdefault('max_length', 512)
        super().__init__(*args, **kwargs)

    def get_prep_value(self, value):
        if value is None or value == '':
            return value
        return _get_fernet().encrypt(str(value).encode()).decode()

    def from_db_value(self, value, expression, connection):
        if value is None or value == '':
            return value
        try:
            return _get_fernet().decrypt(value.encode()).decode()
        except Exception:
            import logging
            logging.getLogger(__name__).error("EncryptedCharField decrypt failed, returning empty string")
            return ''

    def to_python(self, value):
        return value


class EncryptedTextField(models.TextField):
    """AES 加密存储的 TextField，读取时自动解密。"""

    def get_prep_value(self, value):
        if value is None or value == '':
            return value
        return _get_fernet().encrypt(str(value).encode()).decode()

    def from_db_value(self, value, expression, connection):
        if value is None or value == '':
            return value
        try:
            return _get_fernet().decrypt(value.encode()).decode()
        except Exception:
            return ''

    def to_python(self, value):
        return value
