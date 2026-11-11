from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.http import HttpRequest
from django.middleware.csrf import get_token
from django.test import SimpleTestCase, override_settings
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.test import APIRequestFactory
from rest_framework.views import APIView

from core.authentication import CookieTokenAuthentication
from school_system.media_serve import media_serve


class CookieProbe(APIView):
    authentication_classes = [CookieTokenAuthentication]
    permission_classes = [IsAuthenticated]
    throttle_classes = []

    def post(self, request):
        return Response({'ok': True})


@override_settings(CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}})
class AuditSmokeTests(SimpleTestCase):
    def test_cookie_writes_require_csrf_but_header_auth_does_not(self):
        seed = HttpRequest()
        csrf_token = get_token(seed)
        session = SimpleNamespace(user=SimpleNamespace(is_authenticated=True, is_active=True))
        factory = APIRequestFactory(enforce_csrf_checks=True)
        with patch('core.authentication.LoginSession.resolve',
                   side_effect=lambda key: session if key == 'audit-cookie' else None):
            for token, origin, expected in (
                ('', 'http://testserver', 403),
                (csrf_token, 'http://testserver', 200),
                (csrf_token, 'https://untrusted.invalid', 403),
            ):
                with self.subTest(token=bool(token), origin=origin):
                    request = factory.post('/probe/', {}, format='json',
                                           HTTP_ORIGIN=origin, HTTP_X_CSRFTOKEN=token)
                    request.COOKIES.update(auth_token='audit-cookie', csrftoken=seed.META['CSRF_COOKIE'])
                    self.assertEqual(CookieProbe.as_view()(request).status_code, expected)
            request = factory.post('/probe/', {}, format='json', HTTP_AUTHORIZATION='Token audit-cookie')
            self.assertEqual(CookieProbe.as_view()(request).status_code, 200)

    def test_csrf_bootstrap_and_retired_routes(self):
        response = self.client.get('/api/csrf/')
        self.assertEqual(response.status_code, 200)
        self.assertIn('csrftoken', response.cookies)
        self.assertTrue(response.json()['csrf_token'])
        self.assertEqual(response['Cache-Control'], 'no-store')
        for method, url in (
            ('get', '/api/payments/coupons/'),
            ('post', '/api/payments/coupons/'),
            ('put', '/api/payments/coupons/1/'),
            ('delete', '/api/payments/coupons/1/'),
            ('get', '/api/users/institution/me/'),
            ('post', '/api/users/institution/me/students/'),
            ('get', '/api/users/institution/me/data-export/'),
        ):
            with self.subTest(method=method, url=url):
                self.assertEqual(getattr(self.client, method)(url).status_code, 410)
        response = self.client.post('/api/payments/webhook/?gateway=wechat', {})
        self.assertEqual(response.status_code, 400)

    def test_media_suffix_open_and_unsatisfiable_ranges(self):
        empty = MagicMock()
        empty.exists.return_value = False
        with TemporaryDirectory() as directory, override_settings(MEDIA_ROOT=directory, OSS_ACCESS_KEY_ID=''), \
                patch('courses.models.Course.objects.filter', return_value=empty), \
                patch('faq_system.models.Question.objects.filter', return_value=empty), \
                patch('courses.models.StartupMaterial.objects.filter', return_value=empty):
            path = Path(directory) / 'course_covers/audit.png'
            path.parent.mkdir()
            path.write_bytes(b'0123456789')
            for value, status, content_range, body in (
                ('bytes=-4', 206, 'bytes 6-9/10', b'6789'),
                ('bytes=2-', 206, 'bytes 2-9/10', b'23456789'),
                ('bytes=2-5', 206, 'bytes 2-5/10', b'2345'),
                ('bytes=99-100', 416, 'bytes */10', b''),
                ('bytes=5-2', 416, 'bytes */10', b''),
                ('bytes=-0', 416, 'bytes */10', b''),
            ):
                with self.subTest(range=value):
                    request = APIRequestFactory().get('/media/course_covers/audit.png', HTTP_RANGE=value)
                    request.user = SimpleNamespace(is_authenticated=True)
                    response = media_serve(request, 'course_covers/audit.png')
                    self.assertEqual(response.status_code, status)
                    self.assertEqual(response['Content-Range'], content_range)
                    actual = b''.join(response.streaming_content) if response.streaming else response.content
                    self.assertEqual(actual, body)

    def test_batch_tags_can_serialize_after_assignment(self):
        from courses.models import CourseTag
        from courses.views_tags import BatchAssignTagsView

        tag = CourseTag(id=123, name='Audit', slug='audit')
        course = MagicMock()
        course.tag_relations.select_related.return_value.all.return_value = [SimpleNamespace(tag=tag)]
        request = SimpleNamespace(data={'course_id': 1, 'tags': ['Audit']}, user=object())
        with patch('courses.views_tags.apply_institution_filter') as scope, \
                patch('courses.views_tags.get_content_institution', return_value=None), \
                patch('courses.views_tags._assign_tags'), \
                patch('courses.access.visible_courses') as visible, \
                patch.object(CourseTag, 'course_relations') as relations:
            scope.return_value.filter.return_value.first.return_value = course
            relations.filter.return_value.count.return_value = 1
            visible.return_value.filter.return_value.only.return_value = []
            response = BatchAssignTagsView().post(request)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data[0]['course_count'], 1)
