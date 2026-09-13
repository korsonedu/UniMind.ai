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
