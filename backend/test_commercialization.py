"""Tests for account deletion, data export, feedback, legal API."""

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

User = get_user_model()


@pytest.mark.django_db
class TestAccountDeletion:
    def test_delete_requires_auth(self, api_client):
        resp = api_client.post('/api/users/me/delete/', {'password': 'x'})
        assert resp.status_code in (401, 403)

    def test_delete_requires_password(self, auth_client, user):
        resp = auth_client.post('/api/users/me/delete/', {})
        assert resp.status_code == 400
        assert '密码' in resp.data.get('error', '')

    def test_delete_wrong_password(self, auth_client, user):
        resp = auth_client.post('/api/users/me/delete/', {'password': 'wrong'})
        assert resp.status_code == 400

    def test_delete_success(self, auth_client, user):
        resp = auth_client.post('/api/users/me/delete/', {'password': 'TestPass123!'})
        assert resp.status_code == 200
        assert resp.data['status'] == 'ok'

        user.refresh_from_db()
        assert not user.is_active
        assert user.email == ''
        assert user.username.startswith('deleted_')
        assert not user.has_usable_password()

    def test_delete_clears_token(self, auth_client, user):
        from rest_framework.authtoken.models import Token
        Token.objects.create(user=user)
        auth_client.post('/api/users/me/delete/', {'password': 'TestPass123!'})
        assert Token.objects.filter(user=user).count() == 0


@pytest.mark.django_db
class TestDataExport:
    def test_export_requires_auth(self, api_client):
        resp = api_client.get('/api/users/me/data-export/')
        assert resp.status_code in (401, 403)

    def test_export_returns_json(self, auth_client, user):
        resp = auth_client.get('/api/users/me/data-export/')
        assert resp.status_code == 200
        assert 'application/json' in resp['Content-Type']
        assert 'attachment' in resp.get('Content-Disposition', '')

    def test_export_contains_profile(self, auth_client, user):
        resp = auth_client.get('/api/users/me/data-export/')
        import json
        data = json.loads(resp.content)
        assert data['profile']['username'] == user.username
        assert 'exported_at' in data['export_info']

    def test_export_rate_limited(self, auth_client, user):
        for _ in range(5):
            auth_client.get('/api/users/me/data-export/')
        resp = auth_client.get('/api/users/me/data-export/')
        assert resp.status_code == 429


@pytest.mark.django_db
class TestFeedback:
    def test_submit_requires_auth(self, api_client):
        resp = api_client.post('/api/users/feedback/', {'content': 'test'})
        assert resp.status_code in (401, 403)

    def test_submit_empty_content(self, auth_client):
        resp = auth_client.post('/api/users/feedback/', {'content': ''})
        assert resp.status_code == 400

    def test_submit_success(self, auth_client, user):
        resp = auth_client.post('/api/users/feedback/', {
            'category': 'bug',
            'content': '测试反馈',
            'contact': 'test@test.com',
        })
        assert resp.status_code == 200
        assert resp.data['status'] == 'ok'

        from core.models import Feedback
        assert Feedback.objects.filter(user=user, content='测试反馈').exists()


@pytest.mark.django_db
class TestLegalAPI:
    def test_list_legal_docs(self, api_client):
        from core.models import LegalDocument
        from datetime import date
        LegalDocument.objects.create(
            doc_type='privacy', version='1.0', title='隐私政策',
            content='<p>隐私政策内容</p>', is_active=True,
            effective_date=date(2026, 6, 1),
        )
        resp = api_client.get('/api/legal/')
        assert resp.status_code == 200
        assert len(resp.data) >= 1

    def test_get_specific_doc(self, api_client):
        from core.models import LegalDocument
        from datetime import date
        LegalDocument.objects.create(
            doc_type='terms', version='1.0', title='用户协议',
            content='<p>协议内容</p>', is_active=True,
            effective_date=date(2026, 6, 1),
        )
        resp = api_client.get('/api/legal/terms/')
        assert resp.status_code == 200
        assert resp.data['version'] == '1.0'
        assert resp.data['doc_type'] == 'terms'

    def test_invalid_doc_type(self, api_client):
        resp = api_client.get('/api/legal/invalid/')
        assert resp.status_code == 404


@pytest.mark.django_db
class TestHealthCheck:
    def test_health_ok(self, api_client):
        resp = api_client.get('/health/')
        assert resp.status_code == 200
        assert resp.data['status'] == 'ok'
        assert resp.data['database'] is True
        assert resp.data['cache'] is True
