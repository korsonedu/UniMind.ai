from pathlib import Path
from tempfile import TemporaryDirectory

from django.test import Client, TestCase, override_settings
from rest_framework.authtoken.models import Token

from courses.models import Course
from users.models import CourseStudentStatus, Institution, User


class CourseMediaAuthenticationTests(TestCase):
    def setUp(self):
        self.institution = Institution.objects.create(
            name='Media school', slug='media-school', contact_name='Teacher',
            contact_email='teacher@example.com',
        )
        self.user = User.objects.create_user(username='media-user', institution=self.institution)
        CourseStudentStatus.objects.create(user=self.user, is_course_student=True)
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.settings_override = override_settings(MEDIA_ROOT=self.directory.name, OSS_ACCESS_KEY_ID='',
            UNIMIND_CONTENT_INSTITUTION_ID=str(self.institution.pk))
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)
        path = Path(self.directory.name) / f'institutions/{self.institution.pk}/lesson.webm'
        path.parent.mkdir(parents=True)
        path.write_bytes(b'0123456789')
        self.course = Course.objects.create(title='Protected media', institution=self.institution,
            video_file=f'institutions/{self.institution.pk}/lesson.webm')
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

    def test_other_institution_content_is_denied(self):
        self.course.institution = Institution.objects.create(name='Other media owner', slug='other-media')
        self.course.save(update_fields=['institution'])
        self.client.cookies['auth_token'] = Token.objects.create(user=self.user).key
        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_inactive_cookie_is_denied(self):
        self.user.is_active = False
        self.user.save(update_fields=['is_active'])
        self.client.cookies['auth_token'] = Token.objects.create(user=self.user).key
        self.assertEqual(self.client.get(self.url).status_code, 401)

    def test_platform_admin_can_access_course_media(self):
        admin = User.objects.create_superuser(username='media-admin', email='admin@example.com', password='test')
        other = User.objects.create_superuser(username='other-media-admin')
        self.enterContext(override_settings(UNIMIND_DIRECTUS_ADMIN_MAP={
            '00000000-0000-4000-8000-000000000001': admin.pk,
            '00000000-0000-4000-8000-000000000002': other.pk,
        }))
        client = Client()
        client.cookies['auth_token'] = Token.objects.create(user=admin).key
        response = client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(b''.join(response.streaming_content), b'0123456789')
