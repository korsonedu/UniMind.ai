from unittest.mock import MagicMock, patch

from django.test import TestCase

# Create your tests here.


class AlbumListIsolationTests(TestCase):
    """/api/courses/albums/ 机构隔离：机构用户只看到本机构专辑，不再包含全局专辑。"""

    def setUp(self):
        from django.contrib.auth import get_user_model

        from courses.models import Album
        from users.models import Institution

        User = get_user_model()
        self.inst_a = Institution.objects.create(
            name='机构A', slug='inst-a', contact_name='A', contact_email='a@example.com',
        )
        self.inst_b = Institution.objects.create(
            name='机构B', slug='inst-b', contact_name='B', contact_email='b@example.com',
        )
        self.user_a = User.objects.create_user(
            username='user_a', email='ua@example.com', password='pw', institution=self.inst_a,
        )
        self.global_album = Album.objects.create(name='全局专辑')
        self.album_a = Album.objects.create(name='A机构专辑', institution=self.inst_a)
        self.album_b = Album.objects.create(name='B机构专辑', institution=self.inst_b)

    def _client(self, user):
        from rest_framework.test import APIClient

        client = APIClient()
        client.force_authenticate(user=user)
        return client

    def test_institution_user_sees_only_own_albums(self):
        resp = self._client(self.user_a).get('/api/courses/albums/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual({a['name'] for a in resp.data}, {'A机构专辑'})


class OSSMultipartResignTests(TestCase):
    """resign 接口：断点续传时重新签发分片 URL，并返回 OSS 上已传的分片。"""

    def setUp(self):
        from django.contrib.auth import get_user_model

        from users.models import Institution

        User = get_user_model()
        self.inst = Institution.objects.create(
            name='机构A', slug='resign-a', contact_name='A', contact_email='a@example.com',
        )
        self.user = User.objects.create_user(
            username='resign_user', email='r@example.com', password='pw',
            institution=self.inst, institution_role='owner',
        )
        self.object_key = f'institutions/{self.inst.id}/video/x.mp4'

        from rest_framework.test import APIClient

        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    @staticmethod
    def _bucket(parts=None, exc=None):
        bucket = MagicMock()
        if exc is not None:
            bucket.list_parts.side_effect = exc
            return bucket
        result = MagicMock()
        result.parts = parts or []
        bucket.list_parts.return_value = result
        bucket.sign_url.side_effect = (
            lambda method, key, expire, params=None: f'https://oss.example/{key}?part={params["partNumber"]}'
        )
        return bucket

    def _post(self, payload):
        return self.client.post('/api/courses/oss/multipart/resign/', payload, format='json')

    @patch('courses.views._get_oss_bucket')
    def test_returns_signed_urls_and_uploaded_parts(self, mock_bucket):
        part = MagicMock(part_number=3, etag='"abc123"')
        mock_bucket.return_value = self._bucket(parts=[part])

        resp = self._post({'upload_id': 'uid-1', 'object_key': self.object_key, 'total_parts': 3})

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['uploaded_parts'], [{'number': 3, 'etag': '"abc123"'}])
        self.assertEqual(len(resp.data['signed_urls']), 3)
        self.assertIn('part=1', resp.data['signed_urls'][0])

    @patch('courses.views._get_oss_bucket')
    def test_other_institution_key_forbidden(self, mock_bucket):
        mock_bucket.return_value = self._bucket()
        resp = self._post({
            'upload_id': 'uid-1', 'object_key': 'institutions/999/video/x.mp4', 'total_parts': 1,
        })
        self.assertEqual(resp.status_code, 403)

    @patch('courses.views._get_oss_bucket')
    def test_missing_params(self, mock_bucket):
        mock_bucket.return_value = self._bucket()
        resp = self._post({'upload_id': 'uid-1'})
        self.assertEqual(resp.status_code, 400)

    @patch('courses.views._get_oss_bucket')
    def test_expired_upload_returns_404(self, mock_bucket):
        class _Gone(Exception):
            code = 'NoSuchUpload'

        mock_bucket.return_value = self._bucket(exc=_Gone('gone'))
        resp = self._post({'upload_id': 'uid-1', 'object_key': self.object_key, 'total_parts': 1})

        self.assertEqual(resp.status_code, 404)
        self.assertIn('失效', resp.data['error'])

    @patch('courses.views._get_oss_bucket')
    def test_oss_error_returns_500(self, mock_bucket):
        mock_bucket.return_value = self._bucket(exc=RuntimeError('boom'))
        resp = self._post({'upload_id': 'uid-1', 'object_key': self.object_key, 'total_parts': 1})
        self.assertEqual(resp.status_code, 500)
