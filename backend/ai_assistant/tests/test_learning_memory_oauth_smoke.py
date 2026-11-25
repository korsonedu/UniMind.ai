import base64
import hashlib
import json
from urllib.parse import parse_qs, urlencode, urlsplit

import pytest
from django.test import Client
from django.urls import reverse
from oauth2_provider.models import Application

from ai_assistant.models import ConversationProject, LearningMemoryGrant
from users.login_sessions import LoginSession


@pytest.mark.django_db
@pytest.mark.parametrize('client_type', (Application.CLIENT_PUBLIC, Application.CLIENT_CONFIDENTIAL))
def test_oauth_consent_code_and_workspace_bound_mcp(settings, user, django_user_model, client_type):
    settings.UNIMIND_LEARNING_MEMORY_CONNECTORS = True
    settings.UNIMIND_CONTENT_INSTITUTION_ID = 'global'
    settings.UNIMIND_LEARNING_MEMORY_OAUTH_ORIGIN = 'http://testserver'
    settings.UNIMIND_LEARNING_MEMORY_OAUTH_CLIENT_IDS = {'accept-mcp'}
    redirect = 'https://client.example/callback'
    secret = 'synthetic-client-secret'
    Application.objects.create(client_id='accept-mcp', name='验收 Agent', client_type=client_type, client_secret=secret,
        redirect_uris=redirect, authorization_grant_type=Application.GRANT_AUTHORIZATION_CODE)
    stranger = django_user_model.objects.create_user(username='learning-oauth-other')
    foreign = ConversationProject.objects.create(user=stranger, name='他人的私有项目')
    project = ConversationProject.objects.create(user=user, name='OAuth 验收项目')
    browser = Client(enforce_csrf_checks=True)
    browser.cookies['auth_token'] = LoginSession.issue(user).key
    mcp = reverse('learning-memory-mcp')
    resource = 'http://testserver' + mcp
    consent = reverse('learning-memory-oauth-authorize')
    token = reverse('learning-memory-oauth-token')
    verifier = 'a' * 43
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')
    query = {'client_id':'accept-mcp', 'redirect_uri':redirect, 'response_type':'code', 'resource': resource,
             'scope':'learning.memory.read learning.memory.notes', 'state':'client_nonce',
             'code_challenge':challenge, 'code_challenge_method':'S256'}

    rpc = {'jsonrpc':'2.0','id':1,'method':'tools/call',
           'params':{'name':'recall_learning','arguments':{}}}
    unauthorized = browser.post(mcp, data=json.dumps(rpc), content_type='application/json')
    assert unauthorized.status_code == 401 and 'resource_metadata=' in unauthorized.headers['WWW-Authenticate']
    discovery = browser.get(reverse('learning-memory-oauth-resource')).json()
    assert discovery['resource'] == resource and discovery['scopes_supported'] == ['learning.memory.read']
    metadata = browser.get(reverse('learning-memory-oauth-metadata')).json()
    assert metadata['code_challenge_methods_supported'] == ['S256']
    assert browser.get(consent, {**query, 'redirect_uri':redirect + '/elsewhere'}).status_code == 400
    assert browser.get(consent, {**query, 'code_challenge_method':'plain'}).status_code == 400
    assert browser.get(consent, {**query, 'client_id':'unknown-client'}).status_code == 400
    prompt = browser.get(consent, query)
    assert prompt.status_code == 200 and '个人学习空间' in prompt.content.decode()
    assert project.name not in prompt.content.decode()
    assert foreign.name not in prompt.content.decode()
    assert browser.post(consent, {**query,'learner_id':user.pk,'decision':'allow'}).status_code == 403
    csrf = {'X-CSRFToken':browser.cookies['csrftoken'].value}
    assert browser.post(consent, {**query,'learner_id':foreign.user_id,'decision':'allow'}, headers=csrf).status_code == 404
    approved = browser.post(consent, {**query,'learner_id':user.pk,'decision':'allow'}, headers=csrf)
    returned = parse_qs(urlsplit(approved['Location']).query)
    assert returned['state'] == ['client_nonce']
    form = {'grant_type':'authorization_code','code':returned['code'][0], 'code_verifier':verifier,
            'client_id':'accept-mcp','redirect_uri':redirect,'resource':resource}

    def exchange(params):
        if client_type == Application.CLIENT_CONFIDENTIAL:
            params = {**params, 'client_secret': secret}
        return browser.post(token, data=urlencode(params), content_type='application/x-www-form-urlencoded')

    assert exchange({**form,'resource':resource+'other'}).status_code == 400
    assert exchange({**form,'code_verifier':'b'*43}).status_code == 400
    issued = exchange(form)
    assert issued.status_code == 200, issued.content
    assert exchange(form).status_code == 400
    access_token = issued.json()['access_token']
    grant = LearningMemoryGrant.objects.get(learner=user)
    assert grant.share_notes and not grant.can_write and grant.oauth_resource == resource and grant.project_id is None

    def read(credential=access_token):
        return browser.post(mcp, data=json.dumps(rpc), content_type='application/json',
                            headers={'Authorization':'Bearer '+credential})

    assert [row['id'] for row in read().json()['result']['structuredContent']['projects']] == [project.pk]
    renewal = {'grant_type':'refresh_token','refresh_token':issued.json()['refresh_token'],
               'client_id':'accept-mcp','resource':resource}
    assert exchange({**renewal,'scope':'learning.memory.read learning.memory.write'}).status_code == 400
    rotated = exchange(renewal)
    assert rotated.status_code == 200, rotated.content
    new_access = rotated.json()['access_token']
    assert read().status_code == 401
    assert [row['id'] for row in read(new_access).json()['result']['structuredContent']['projects']] == [project.pk]
    assert exchange(renewal).status_code == 400
    assert read(new_access).status_code == 401 and not LearningMemoryGrant.objects.filter(pk=grant.pk).exists()

    approved = browser.post(consent, {**query,'learner_id':user.pk,'decision':'allow'}, headers=csrf)
    returned = parse_qs(urlsplit(approved['Location']).query)
    reissued = exchange({**form,'code':returned['code'][0]}).json()
    user.account_session_version += 1
    user.save(update_fields=['account_session_version'])
    assert read(reissued['access_token']).status_code == 401
    assert exchange({**renewal,'refresh_token':reissued['refresh_token']}).status_code == 400
