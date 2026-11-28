"""Tests for MCP learning-memory endpoint X-Trace-Id header and observability logging."""
import logging
from unittest.mock import patch
from uuid import uuid4

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from ai_assistant.models import LearningMemoryGrant
from ai_assistant.services.learning_memory_oauth import digest as memory_digest, memory_token


@pytest.mark.django_db
def test_mcp_view_emits_trace_id_header_and_logs_without_breaking_idempotency(user, settings, caplog):
    settings.UNIMIND_LEARNING_MEMORY_CONNECTORS = True
    token = memory_token()
    LearningMemoryGrant.objects.create(
        learner=user, name='Codex', digest=memory_digest(token),
        can_write=True, share_notes=False, expires_at=timezone.now() + timezone.timedelta(days=7),
    )
    client = APIClient()
    checkpoint_req = str(uuid4())
    custom_trace = 'trace-mcp-001'
    body = {
        'jsonrpc': '2.0',
        'id': 1,
        'method': 'tools/call',
        'params': {
            'name': 'record_learning_checkpoint',
            'arguments': {'text': '完成第 0 期折现自检', 'request_id': checkpoint_req},
        },
    }
    headers = {'HTTP_AUTHORIZATION': f'Bearer {token}', 'HTTP_X_TRACE_ID': custom_trace}

    with caplog.at_level(logging.INFO, logger='ai_engine.observability'), \
            patch('ai_assistant.views_learning_memory.membership_for', return_value=None):
        first = client.post('/api/ai/learning-memory/mcp/', data=body, format='json', **headers)
        second = client.post('/api/ai/learning-memory/mcp/', data=body, format='json', **headers)

    assert first.status_code == 200
    assert second.status_code == 200
    assert first['X-Trace-Id'] == custom_trace
    assert second['X-Trace-Id'] == custom_trace
    assert first.json()['result']['structuredContent']['source'] == second.json()['result']['structuredContent']['source']
    assert "ai.obs operation=mcp.record_learning_checkpoint" in caplog.text
    assert f"'trace_id': '{custom_trace}'" in caplog.text
