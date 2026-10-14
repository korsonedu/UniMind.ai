from pathlib import Path
from tempfile import TemporaryDirectory

from django.test import Client, TestCase, override_settings
from rest_framework.authtoken.models import Token

from users.models import Institution, User


class CourseMediaAuthenticationTests(TestCase):
    def setUp(self):
        self.institution = Institution.objects.create(
            name='Media school', slug='media-school', contact_name='Teacher',
            contact_email='teacher@example.com',
        )
        self.user = User.objects.create_user(username='media-user', institution=self.institution)
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.settings_override = override_settings(MEDIA_ROOT=self.directory.name, OSS_ACCESS_KEY_ID='')
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)
        path = Path(self.directory.name) / f'institutions/{self.institution.pk}/lesson.webm'
        path.parent.mkdir(parents=True)
        path.write_bytes(b'0123456789')
        self.url = f'/media/institutions/{self.institution.pk}/lesson.webm'

    def test_login_cookie_can_load_and_seek_own_course(self):
        self.client.cookies['auth_token'] = Token.objects.create(user=self.user).key
        response = self.client.get(self.url, HTTP_RANGE='bytes=2-5')
        self.assertEqual(response.status_code, 206)
        self.assertEqual(b''.join(response.streaming_content), b'2345')
        self.assertEqual(response['Content-Range'], 'bytes 2-5/10')

    def test_anonymous_or_invalid_cookie_is_denied(self):
        self.assertEqual(self.client.get(self.url).status_code, 401)
        self.client.cookies['auth_token'] = 'invalid-token'
        self.assertEqual(self.client.get(self.url).status_code, 401)

    def test_other_institution_is_denied(self):
        foreign = User.objects.create_user(username='foreign-user')
        self.client.cookies['auth_token'] = Token.objects.create(user=foreign).key
        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_inactive_cookie_is_denied(self):
        self.user.is_active = False
        self.user.save(update_fields=['is_active'])
        self.client.cookies['auth_token'] = Token.objects.create(user=self.user).key
        self.assertEqual(self.client.get(self.url).status_code, 401)

    def test_platform_admin_can_access_course_media(self):
        admin = User.objects.create_superuser(username='media-admin', email='admin@example.com', password='test')
        client = Client()
        client.cookies['auth_token'] = Token.objects.create(user=admin).key
        response = client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(b''.join(response.streaming_content), b'0123456789')
