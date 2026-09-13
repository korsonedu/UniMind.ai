from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings
from django.http import HttpRequest, JsonResponse

from .rate_limit import rate_limit
from .fields import EncryptedCharField, EncryptedTextField


class RateLimitTests(TestCase):
    def setUp(self):
        self.request = HttpRequest()
        self.request.META["REMOTE_ADDR"] = "192.168.1.1"

    def _make_view(self):
        @rate_limit(key_prefix="test_rl", max_requests=3, window_seconds=60)
        def view(request):
            return JsonResponse({"ok": True})
        return view

    def test_allows_requests_within_limit(self):
        view = self._make_view()
        for _ in range(3):
            resp = view(self.request)
            self.assertEqual(resp.status_code, 200)

    def test_blocks_after_limit_exceeded(self):
        view = self._make_view()
        for _ in range(3):
            view(self.request)
        resp = view(self.request)
        self.assertEqual(resp.status_code, 429)

    def test_different_ips_independent(self):
        view = self._make_view()
        for _ in range(3):
            view(self.request)
        req2 = HttpRequest()
        req2.META["REMOTE_ADDR"] = "10.0.0.2"
        resp = view(req2)
        self.assertEqual(resp.status_code, 200)

    def test_cache_unavailable_blocks_request(self):
        # 安全设计：缓存不可用时 fail-closed（直接限流），防止限流被绕过
        view = self._make_view()
        with patch("core.rate_limit.cache.add", side_effect=Exception("redis down")):
            resp = view(self.request)
            self.assertEqual(resp.status_code, 429)


class EncryptedFieldTests(TestCase):
    @override_settings(ENCRYPTION_KEY="rQdZ3OUKMF_cn4vsuWiUYTkXl7GN9mp0vPg8bxaWcxc=")
    def test_roundtrip_charfield(self):
        field = EncryptedCharField()
        encrypted = field.get_prep_value("hello world")
        self.assertNotEqual(encrypted, "hello world")
        decrypted = field.from_db_value(encrypted, None, None)
        self.assertEqual(decrypted, "hello world")

    @override_settings(ENCRYPTION_KEY="rQdZ3OUKMF_cn4vsuWiUYTkXl7GN9mp0vPg8bxaWcxc=")
    def test_roundtrip_textfield(self):
        field = EncryptedTextField()
        encrypted = field.get_prep_value("long text content")
        self.assertNotEqual(encrypted, "long text content")
        decrypted = field.from_db_value(encrypted, None, None)
        self.assertEqual(decrypted, "long text content")

    @override_settings(ENCRYPTION_KEY="rQdZ3OUKMF_cn4vsuWiUYTkXl7GN9mp0vPg8bxaWcxc=")
    def test_none_passthrough(self):
        field = EncryptedCharField()
        self.assertIsNone(field.get_prep_value(None))

    @override_settings(ENCRYPTION_KEY="rQdZ3OUKMF_cn4vsuWiUYTkXl7GN9mp0vPg8bxaWcxc=")
    def test_empty_string_passthrough(self):
        field = EncryptedCharField()
        self.assertEqual(field.get_prep_value(""), "")

    @override_settings(ENCRYPTION_KEY="rQdZ3OUKMF_cn4vsuWiUYTkXl7GN9mp0vPg8bxaWcxc=")
    def test_corrupt_data_returns_empty_string(self):
        field = EncryptedCharField()
        result = field.from_db_value("not-valid-ciphertext", None, None)
        self.assertEqual(result, "")

    def test_missing_key_falls_back_to_secret_key(self):
        # 设计行为：ENCRYPTION_KEY 缺失时从 SECRET_KEY 派生（不抛异常）
        with self.settings(ENCRYPTION_KEY=""):
            field = EncryptedCharField()
            encrypted = field.get_prep_value("test")
            self.assertNotEqual(encrypted, "test")
            self.assertEqual(field.from_db_value(encrypted, None, None), "test")


class CircuitBreakerTests(TestCase):
    """Test AICircuitBreaker 3-state machine via mocked cache."""

    def setUp(self):
        self._cache_store = {}

    def _mock_cache(self):
        """Return a dict-backed mock and patch django cache methods."""
        store = self._cache_store
        mock = MagicMock()

        def _get(key, default=None):
            return store.get(key, default)

        def _set(key, value, timeout=None):
            store[key] = value

        def _delete(key):
            store.pop(key, None)

        mock.get.side_effect = _get
        mock.set.side_effect = _set
        mock.delete.side_effect = _delete
        return mock

    def test_closed_allows_request(self):
        from ai_engine.circuit_breaker import AICircuitBreaker
        mock_cache = self._mock_cache()
        with patch("ai_engine.circuit_breaker.cache", mock_cache):
            AICircuitBreaker.check("test_svc")  # 不应抛异常
            self.assertFalse(AICircuitBreaker.is_open("test_svc"))

    def test_failure_threshold_opens_circuit(self):
        from ai_engine.circuit_breaker import AICircuitBreaker, CircuitBreakerError

        mock_cache = self._mock_cache()
        with patch("ai_engine.circuit_breaker.cache", mock_cache):
            for _ in range(5):
                AICircuitBreaker.record_failure("test_svc")
            self.assertTrue(AICircuitBreaker.is_open("test_svc"))

    def test_open_circuit_raises_on_check(self):
        from ai_engine.circuit_breaker import AICircuitBreaker, CircuitBreakerError

        mock_cache = self._mock_cache()
        with patch("ai_engine.circuit_breaker.cache", mock_cache):
            for _ in range(5):
                AICircuitBreaker.record_failure("test_svc")
            with self.assertRaises(CircuitBreakerError):
                AICircuitBreaker.check("test_svc")

    def test_success_in_closed_resets_counter(self):
        from ai_engine.circuit_breaker import AICircuitBreaker

        mock_cache = self._mock_cache()
        with patch("ai_engine.circuit_breaker.cache", mock_cache):
            for _ in range(3):
                AICircuitBreaker.record_failure("test_svc")
            AICircuitBreaker.record_success("test_svc")
            self.assertFalse(AICircuitBreaker.is_open("test_svc"))


class InstitutionFilterTests(TestCase):
    """apply_institution_filter：机构用户只看本机构，无机构用户只看全局，超管看全部。"""

    def setUp(self):
        from django.contrib.auth import get_user_model

        from courses.models import Album
        from users.models import Institution

        User = get_user_model()
        self.inst = Institution.objects.create(
            name="机构A", slug="inst-a", contact_name="联系人A", contact_email="a@example.com",
        )
        self.global_album = Album.objects.create(name="全局专辑")
        self.own_album = Album.objects.create(name="本机构专辑", institution=self.inst)
        self.inst_user = User.objects.create_user(
            username="inst_user", email="inst@example.com", password="pw", institution=self.inst,
        )
        self.plain_user = User.objects.create_user(
            username="plain_user", email="plain@example.com", password="pw",
        )
        self.admin = User.objects.create_superuser(
            username="platform_admin", email="admin@example.com", password="pw",
        )

    def test_institution_user_sees_only_own(self):
        from courses.models import Album
        from core.utils import apply_institution_filter

        qs = apply_institution_filter(Album.objects.all(), self.inst_user)
        self.assertEqual(list(qs), [self.own_album])

    def test_user_without_institution_sees_only_global(self):
        from courses.models import Album
        from core.utils import apply_institution_filter

        qs = apply_institution_filter(Album.objects.all(), self.plain_user)
        self.assertEqual(list(qs), [self.global_album])

    def test_platform_admin_sees_all(self):
        from courses.models import Album
        from core.utils import apply_institution_filter

        qs = apply_institution_filter(Album.objects.all(), self.admin)
        self.assertEqual(set(qs), {self.global_album, self.own_album})


class FileValidationTests(TestCase):
    """视频白名单与课件文档限制。"""

    @staticmethod
    def _file(name, content_type, magic=b"\x00\x00\x00\x18ftypmp42"):
        from django.core.files.uploadedfile import SimpleUploadedFile

        return SimpleUploadedFile(name, magic + b"\x00" * 64, content_type=content_type)

    def test_m4v_accepted(self):
        from core.file_validation import validate_upload_file

        validate_upload_file(self._file("a.m4v", "video/x-m4v"))  # 不应抛异常

    def test_m4v_with_mp4_content_type_accepted(self):
        # 部分系统把 .m4v 报成 video/mp4（容器相同）
        from core.file_validation import validate_upload_file

        validate_upload_file(self._file("a.m4v", "video/mp4"))

    def test_m4v_uses_video_size_limit(self):
        from core.file_validation import VIDEO_MAX_BYTES, _get_default_max_bytes

        self.assertEqual(_get_default_max_bytes(".m4v"), VIDEO_MAX_BYTES)

    def test_extended_video_formats_registered_in_both_tables(self):
        # 白名单与类别集合必须同时登记，漏登记会让大小上限退回默认的 50MB
        from core.file_validation import (
            ALLOWED_UPLOAD_TYPES, VIDEO_EXTENSIONS, VIDEO_MAX_BYTES, _get_default_max_bytes,
        )

        for ext in [".mkv", ".avi", ".flv", ".wmv", ".mpeg", ".mpg", ".rmvb"]:
            self.assertIn(ext, VIDEO_EXTENSIONS, f"{ext} 未登记到 VIDEO_EXTENSIONS")
            self.assertIn(ext, ALLOWED_UPLOAD_TYPES, f"{ext} 未登记到 ALLOWED_UPLOAD_TYPES")
            self.assertEqual(_get_default_max_bytes(ext), VIDEO_MAX_BYTES)

    def test_mkv_accepted_with_matching_magic(self):
        from core.file_validation import validate_upload_file

        validate_upload_file(self._file("a.mkv", "video/x-matroska", magic=b"\x1a\x45\xdf\xa3"))

    def test_document_extensions_reject_video(self):
        from rest_framework.exceptions import ValidationError

        from core.file_validation import DOCUMENT_EXTENSIONS, validate_upload_file

        with self.assertRaises(ValidationError):
            validate_upload_file(self._file("a.mp4", "video/mp4"), allowed_extensions=DOCUMENT_EXTENSIONS)

    def test_document_extensions_accept_docx(self):
        from core.file_validation import DOCUMENT_EXTENSIONS, validate_upload_file

        validate_upload_file(
            self._file("a.docx", "application/octet-stream", magic=b"PK"),
            allowed_extensions=DOCUMENT_EXTENSIONS,
        )

    def test_image_extensions_reject_video(self):
        # 课程封面只接受图片：要么上传图片，要么由系统从视频截取首帧
        from rest_framework.exceptions import ValidationError

        from core.file_validation import IMAGE_EXTENSIONS, validate_upload_file

        with self.assertRaises(ValidationError):
            validate_upload_file(self._file("cover.mp4", "video/mp4"), allowed_extensions=IMAGE_EXTENSIONS)

    def test_image_extensions_accept_jpg(self):
        from core.file_validation import IMAGE_EXTENSIONS, validate_upload_file

        validate_upload_file(
            self._file("cover.jpg", "image/jpeg", magic=b"\xff\xd8\xff"),
            allowed_extensions=IMAGE_EXTENSIONS,
        )

    def test_unknown_extension_still_rejected(self):
        from rest_framework.exceptions import ValidationError

        from core.file_validation import validate_upload_file

        with self.assertRaises(ValidationError):
            validate_upload_file(self._file("a.xyz", "application/octet-stream"))

