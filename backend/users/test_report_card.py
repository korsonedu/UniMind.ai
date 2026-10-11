from pathlib import Path
from unittest.mock import patch
from django.test import override_settings
from rest_framework.test import APITestCase
from .models import User


@override_settings(CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}})
class ReportCardTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='report_owner', nickname='报告测试学员')
        self.client.force_authenticate(self.user)

    def test_report_returns_current_student(self):
        response = self.client.get('/api/users/me/report-card/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['student']['id'], self.user.id)
        self.assertEqual(response.data['stats']['total_attempted'], 0)

    def test_pdf_renders_real_template_before_export(self):
        def render_pdf(html, output_path):
            self.assertIn('报告测试学员', html)
            self.assertIn('成绩报告', html)
            Path(output_path).write_bytes(b'%PDF-1.4\nmock-rendered-document')

        with patch('users.views._html_to_pdf', side_effect=render_pdf) as renderer:
            response = self.client.get('/api/users/me/report-card/pdf/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/pdf')
        self.assertTrue(response.content.startswith(b'%PDF'))
        renderer.assert_called_once()

    def test_report_and_export_require_login(self):
        self.client.force_authenticate(None)
        for path in ('/api/users/me/report-card/', '/api/users/me/report-card/pdf/'):
            self.assertIn(self.client.get(path).status_code, (401, 403))
