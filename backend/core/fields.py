import logging
from django.conf import settings
from django.db import models
from cryptography.fernet import Fernet

logger = logging.getLogger(__name__)


_fernet_instance = None


def _get_fernet() -> Fernet:
    global _fernet_instance
    if _fernet_instance is None:
        key = getattr(settings, 'ENCRYPTION_KEY', None) or settings.SECRET_KEY
        _fernet_instance = Fernet(key.encode() if isinstance(key, str) else key)
    return _fernet_instance


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
            logger.warning("EncryptedCharField decryption failed", exc_info=True)
            return ''

    def to_python(self, value):
        if value is None or value == '':
            return value
        try:
            return _get_fernet().decrypt(value.encode()).decode()
        except Exception:
            return value  # 非密文（如表单输入的明文）直接返回


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
            logger.warning("EncryptedTextField decryption failed", exc_info=True)
            return ''

    def to_python(self, value):
        if value is None or value == '':
            return value
        try:
            return _get_fernet().decrypt(value.encode()).decode()
        except Exception:
            return value  # 非密文（如表单输入的明文）直接返回
