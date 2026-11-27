import base64
import hashlib
import json
from datetime import timedelta
from urllib.parse import parse_qs, urlencode, urlsplit
from uuid import uuid4

import pytest
from django.test import Client
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from ai_assistant.models import AIChatMessage, Bot, Conversation, ExternalMcpServer, LearningMemoryDynamicClient
from ai_assistant.services.dsh_service import build_context, execute_tool
from ai_assistant.services.runtime.mcp_client import call_external_mcp_tool, sync_server_tools
from notes.models import Note
from quizzes.models import KnowledgePoint, Question, UserQuestionStatus
from users.login_sessions import LoginSession


@pytest.mark.django_db
def test_a1_oauth_dcr_registration_discovery_and_end_to_end_token_flow(settings, user):
    settings.UNIMIND_LEARNING_MEMORY_CONNECTORS = True
    settings.UNIMIND_CONTENT_INSTITUTION_ID = 'global'
    settings.UNIMIND_LEARNING_MEMORY_OAUTH_ORIGIN = 'http://testserver'
    settings.UNIMIND_LEARNING_MEMORY_OAUTH_CLIENT_IDS = frozenset()
    settings.UNIMIND_LEARNING_MEMORY_OAUTH_DCR = True

    browser = Client(enforce_csrf_checks=True)
    browser.cookies['auth_token'] = LoginSession.issue(user).key
    mcp_url = reverse('learning-memory-mcp')
    resource = 'http://testserver' + mcp_url

    metadata = browser.get(reverse('learning-memory-oauth-metadata')).json()
    assert metadata['registration_endpoint'] == 'http://testserver' + reverse('learning-memory-oauth-register')

    # Reject non-HTTPS non-loopback redirect URI and confidential auth method
    bad_redirect = browser.post(
        reverse('learning-memory-oauth-register'),
        data=json.dumps({'client_name': 'Bad', 'redirect_uris': ['http://evil.example/cb']}),
        content_type='application/json',
    )
    assert bad_redirect.status_code == 400 and bad_redirect.json()['error'] == 'invalid_redirect_uri'

    bad_auth = browser.post(
        reverse('learning-memory-oauth-register'),
        data=json.dumps({
            'client_name': 'Confidential',
            'redirect_uris': ['https://chatgpt.com/connector_platform_oauth_redirect'],
            'token_endpoint_auth_method': 'client_secret_basic',
        }),
        content_type='application/json',
    )
    assert bad_auth.status_code == 400

    # Valid DCR registration (HTTPS + localhost loopback)
    redirect_uri = 'https://chatgpt.com/connector_platform_oauth_redirect'
    reg_resp = browser.post(
        reverse('learning-memory-oauth-register'),
        data=json.dumps({
            'client_name': 'ChatGPT Connector',
            'redirect_uris': [redirect_uri, 'http://localhost:8765/callback'],
            'token_endpoint_auth_method': 'none',
            'scope': 'learning.memory.read learning.memory.notes',
        }),
        content_type='application/json',
    )
    assert reg_resp.status_code == 201, reg_resp.content
    reg = reg_resp.json()
    client_id = reg['client_id']
    assert client_id.startswith('umdcr_')
    assert 'client_secret' not in reg
    assert LearningMemoryDynamicClient.objects.filter(client_id=client_id).exists()

    # Complete full PKCE authorization code exchange with the dynamically registered client
    verifier = 'v' * 48
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')
    query = {
        'client_id': client_id,
        'redirect_uri': redirect_uri,
        'response_type': 'code',
        'resource': resource,
        'scope': 'learning.memory.read',
        'state': 'dcr-state',
        'code_challenge': challenge,
        'code_challenge_method': 'S256',
    }
    consent_url = reverse('learning-memory-oauth-authorize')
    assert browser.get(consent_url, query).status_code == 200
    csrf = {'X-CSRFToken': browser.cookies['csrftoken'].value}
    approved = browser.post(consent_url, {**query, 'learner_id': user.pk, 'decision': 'allow'}, headers=csrf)
    assert approved.status_code == 302
    code = parse_qs(urlsplit(approved['Location']).query)['code'][0]

    token_resp = browser.post(
        reverse('learning-memory-oauth-token'),
        data=urlencode({
            'grant_type': 'authorization_code',
            'code': code,
            'code_verifier': verifier,
            'client_id': client_id,
            'redirect_uri': redirect_uri,
            'resource': resource,
        }),
        content_type='application/x-www-form-urlencoded',
    )
    assert token_resp.status_code == 200, token_resp.content
    access_token = token_resp.json()['access_token']
    rpc = browser.post(
        mcp_url,
        data=json.dumps({'jsonrpc': '2.0', 'id': 1, 'method': 'tools/list', 'params': {}}),
        content_type='application/json',
        headers={'Authorization': f'Bearer {access_token}'},
    )
    assert rpc.status_code == 200
    tool_names = [item['name'] for item in rpc.json()['result']['tools']]
    assert 'recall_learning' in tool_names and 'get_due_reviews' in tool_names


@pytest.mark.django_db
def test_a3_extended_mcp_server_tools_due_reviews_practice_and_notes(settings, user, auth_client, django_user_model):
    settings.UNIMIND_LEARNING_MEMORY_CONNECTORS = True
    settings.UNIMIND_CONTENT_INSTITUTION_ID = 'global'
    user.is_member = True
    user.save(update_fields=['is_member'])

    kp = KnowledgePoint.objects.create(name='净现值 NPV', subject='金融431')
    q1 = Question.objects.create(knowledge_point=kp, text='计算某项目的净现值。', correct_answer='A', q_type='objective')
    UserQuestionStatus.objects.create(
        user=user,
        question=q1,
        wrong_count=4,
        lapses=3,
        difficulty=7.5,
        stability=1.5,
        next_review_at=timezone.now() - timedelta(hours=2),
    )
    stranger = django_user_model.objects.create_user(username='other-note-owner')
    foreign_note = Note.objects.create(user=stranger, title='他人笔记', content='私有')

    read_only_grant = auth_client.post('/api/ai/learning-memory/grants/', {'name': 'Reader'}, format='json').data
    full_grant = auth_client.post(
        '/api/ai/learning-memory/grants/',
        {'name': 'Writer', 'can_write': True, 'share_notes': True},
        format='json',
    ).data
    external = APIClient()

    def rpc(grant, method, params=None):
        return external.post(
            '/api/ai/learning-memory/mcp/',
            {'jsonrpc': '2.0', 'id': 1, 'method': method, 'params': params or {}},
            format='json',
            HTTP_AUTHORIZATION=f"Bearer {grant['token']}",
        ).json()

    ro_tools = {item['name'] for item in rpc(read_only_grant, 'tools/list')['result']['tools']}
    assert {'recall_learning', 'read_learning_source', 'get_due_reviews', 'start_weak_point_practice'} <= ro_tools
    assert 'save_learning_note' not in ro_tools

    rw_tools = {item['name'] for item in rpc(full_grant, 'tools/list')['result']['tools']}
    assert 'save_learning_note' in rw_tools

    # 1. Memorix due reviews
    due = rpc(read_only_grant, 'tools/call', {'name': 'get_due_reviews', 'arguments': {'limit': 5}})['result']['structuredContent']
    assert due['due_count'] == 1
    assert due['reviews'][0]['question_id'] == q1.pk
    assert due['href'].endswith('/tests/review')

    # 2. Weak-point practice session
    practice = rpc(
        read_only_grant, 'tools/call', {'name': 'start_weak_point_practice', 'arguments': {'count': 3}},
    )['result']['structuredContent']
    assert practice['total_questions'] == 1
    assert practice['session_id']
    assert 'correct_answer' not in practice['questions'][0]
    assert f"/tests/session?session_id={practice['session_id']}" in practice['href']

    # 3. Note creation + idempotency + conflict + append + cross-user protection
    req_id = str(uuid4())
    create_args = {
        'mode': 'create',
        'title': 'NPV 折现要点',
        'content': '第 0 期现金流不需要折现。',
        'tags': ['金融431', 'NPV'],
        'request_id': req_id,
    }
    assert 'error' in rpc(read_only_grant, 'tools/call', {'name': 'save_learning_note', 'arguments': create_args})
    created = rpc(full_grant, 'tools/call', {'name': 'save_learning_note', 'arguments': create_args})['result']['structuredContent']
    retried = rpc(full_grant, 'tools/call', {'name': 'save_learning_note', 'arguments': create_args})['result']['structuredContent']
    assert created == retried
    assert Note.objects.filter(user=user, title='NPV 折现要点').count() == 1

    # Same request_id with altered payload -> conflict error
    conflict = rpc(
        full_grant, 'tools/call',
        {'name': 'save_learning_note', 'arguments': {**create_args, 'content': '不同内容'}},
    )
    assert conflict['error']['code'] == -32602

    # Append to created note
    appended = rpc(
        full_grant, 'tools/call',
        {
            'name': 'save_learning_note',
            'arguments': {'mode': 'append', 'note_id': created['note_id'], 'content': '补充：折现率与期限匹配。', 'request_id': str(uuid4())},
        },
    )['result']['structuredContent']
    assert appended['version'] == 2
    saved_note = Note.objects.get(pk=created['note_id'])
    assert '第 0 期现金流不需要折现。' in saved_note.content and '折现率与期限匹配。' in saved_note.content

    # Cannot append to another user's note
    denied_foreign = rpc(
        full_grant, 'tools/call',
        {
            'name': 'save_learning_note',
            'arguments': {'mode': 'append', 'note_id': foreign_note.pk, 'content': 'hack', 'request_id': str(uuid4())},
        },
    )
    assert denied_foreign['error']['code'] == -32602


@pytest.mark.django_db
def test_b_mcp_client_crud_ssrf_sync_and_xiaoyu_ulr_execution(settings, user, auth_client):
    settings.UNIMIND_LEARNING_MEMORY_CONNECTORS = True
    settings.UNIMIND_MCP_CLIENT_ENABLED = True
    settings.UNIMIND_CONTENT_INSTITUTION_ID = 'global'
    user.is_member = True
    user.save(update_fields=['is_member'])

    # SSRF protection rejects private/loopback and plain HTTP URLs
    assert auth_client.post('/api/ai/mcp-servers/', {'name': 'Local', 'url': 'http://127.0.0.1:9000/mcp'}, format='json').status_code == 400
    assert auth_client.post('/api/ai/mcp-servers/', {'name': 'Private', 'url': 'https://169.254.169.254/latest'}, format='json').status_code == 400

    # Create valid external MCP server (secret is encrypted and never echoed back)
    created_resp = auth_client.post(
        '/api/ai/mcp-servers/',
        {
            'name': 'Notion',
            'url': 'https://mcp.notion.com/mcp',
            'auth_type': 'bearer',
            'auth_secret': 'ntn_super_secret_token',
            'allow_write_tools': False,
        },
        format='json',
    )
    assert created_resp.status_code == 201, created_resp.data
    assert created_resp.data['has_secret'] is True
    assert 'auth_secret' not in created_resp.data
    server = ExternalMcpServer.objects.get(pk=created_resp.data['id'])
    assert server.auth_secret == 'ntn_super_secret_token'

    # Mock Streamable HTTP remote server transport
    calls = []

    def fake_transport(url, headers, body_bytes, timeout):
        payload = json.loads(body_bytes.decode('utf-8'))
        calls.append((headers.get('Authorization'), payload['method']))
        method = payload['method']
        if method == 'initialize':
            return 200, {'content-type': 'application/json', 'mcp-session-id': 'notion-sess-1'}, json.dumps({
                'jsonrpc': '2.0', 'id': payload['id'], 'result': {'protocolVersion': '2025-11-25', 'capabilities': {'tools': {}}},
            })
        if method == 'notifications/initialized':
            return 202, {}, ''
        if method == 'tools/list':
            return 200, {'content-type': 'application/json'}, json.dumps({
                'jsonrpc': '2.0',
                'id': payload['id'],
                'result': {
                    'tools': [
                        {
                            'name': 'search_pages',
                            'description': 'Search Notion pages',
                            'inputSchema': {'type': 'object', 'properties': {'query': {'type': 'string'}}, 'required': ['query']},
                            'annotations': {'readOnlyHint': True},
                        },
                        {
                            'name': 'delete_page',
                            'description': 'Delete a Notion page',
                            'inputSchema': {'type': 'object', 'properties': {'page_id': {'type': 'string'}}},
                            'annotations': {'readOnlyHint': False, 'destructiveHint': True},
                        },
                    ],
                },
            })
        if method == 'tools/call':
            return 200, {'content-type': 'application/json'}, json.dumps({
                'jsonrpc': '2.0',
                'id': payload['id'],
                'result': {'content': [{'type': 'text', 'text': f"Found Notion note for {payload['params']['arguments']['query']}"}]},
            })
        raise AssertionError(f'Unexpected method {method}')

    synced = sync_server_tools(server, transport=fake_transport)
    assert len(synced) == 2

    # Verify ULR build_context exposes ONLY read-only tool while allow_write_tools=False and routes to external_mcp
    bot = Bot.objects.create(name='小宇')
    room = Conversation.objects.create(user=user, bot=bot, conversation_id=uuid4())
    msg = AIChatMessage.objects.create(user=user, bot=bot, conversation_id=room.conversation_id, role='user', content='帮我查一下 Notion 里关于 NPV 的笔记')
    claims = {'message_id': msg.pk, 'conversation_id': str(room.conversation_id), 'bot_id': bot.pk}

    context = build_context(user, msg.content, chat_context=claims, ulr=True)
    assert context['routing']['initial_group'] == 'external_mcp'
    ext_names = [tool['function']['name'] for tool in context['tool_groups']['external_mcp']['tools']]
    assert ext_names == ['mcp__notion__search_pages']

    # Direct execution respects read-only gate and invokes remote transport cleanly
    with pytest.raises(Exception):
        call_external_mcp_tool(user, 'mcp__notion__delete_page', {'page_id': '1'}, transport=fake_transport)

    result = call_external_mcp_tool(user, 'mcp__notion__search_pages', {'query': 'NPV'}, transport=fake_transport)
    assert result['external_data'] is True and result['is_error'] is False
    assert 'Found Notion note for NPV' in result['content']

    # Verify execute_tool path delegates cleanly when transport is patched
    import ai_assistant.services.runtime.bridge as bridge_mod
    orig_call = bridge_mod.call_external_mcp_tool
    bridge_mod.call_external_mcp_tool = lambda u, n, a: call_external_mcp_tool(u, n, a, transport=fake_transport)
    try:
        via_bridge = execute_tool(user, 'mcp__notion__search_pages', {'query': '久期'}, context['memory']['version'], chat_context=claims)
        assert 'Found Notion note for 久期' in via_bridge['content']
    finally:
        bridge_mod.call_external_mcp_tool = orig_call

    # Delete server cleanly
    assert auth_client.delete(f'/api/ai/mcp-servers/{server.pk}/').status_code == 204
    assert not ExternalMcpServer.objects.filter(pk=server.pk).exists()
