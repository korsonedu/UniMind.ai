import re
from urllib.parse import urlencode

from django.contrib.auth import get_user_model
from django.db import transaction
from django.http import Http404, HttpResponse, HttpResponseBadRequest, HttpResponseRedirect, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt, csrf_protect
from django.views.decorators.http import require_GET, require_http_methods, require_POST
from oauthlib.common import add_params_to_uri
from oauthlib.oauth2 import OAuth2Error

from ai_assistant.services.learning_memory_oauth import (
    READ_SCOPE, SCOPES, learner_account_active, oauth_enabled, registered_client, resource_uri, server,
)
from core.rate_limit import rate_limit
from users.accounts.services import platform_cookie_user
from users.workspaces.identity import account_learner_ids


def _require_oauth(request):
    if not oauth_enabled(request):
        raise Http404


def _endpoint(request, name):
    return request.build_absolute_uri(reverse(name))


@require_GET
def resource_metadata(request):
    _require_oauth(request)
    return JsonResponse({
        'resource': resource_uri(),
        'authorization_servers': [request.build_absolute_uri('/').rstrip('/')],
        'scopes_supported': [READ_SCOPE],
        'bearer_methods_supported': ['header'],
    })


@require_GET
def server_metadata(request):
    _require_oauth(request)
    return JsonResponse({
        'issuer': request.build_absolute_uri('/').rstrip('/'),
        'authorization_endpoint': _endpoint(request, 'learning-memory-oauth-authorize'),
        'token_endpoint': _endpoint(request, 'learning-memory-oauth-token'),
        'response_types_supported': ['code'],
        'grant_types_supported': ['authorization_code', 'refresh_token'],
        'scopes_supported': list(SCOPES),
        'code_challenge_methods_supported': ['S256'],
        'token_endpoint_auth_methods_supported': ['none', 'client_secret_basic', 'client_secret_post'],
    })


@require_http_methods(['GET', 'POST'])
@never_cache
@csrf_protect
@rate_limit('learning_memory_oauth_consent', 30, 300, methods={'POST'})
def authorize(request):
    _require_oauth(request)
    account = platform_cookie_user(request)
    if account is None:
        if request.method == 'POST':
            return HttpResponse(status=401)
        return HttpResponseRedirect('/login?' + urlencode({'next': request.get_full_path()}))
    fields = ('client_id', 'redirect_uri', 'response_type', 'resource', 'scope', 'state',
              'code_challenge', 'code_challenge_method')
    values = request.POST if request.method == 'POST' else request.GET
    if any(len(values.getlist(name)) > 1 for name in fields):
        return HttpResponseBadRequest('授权请求存在重复参数。')
    params = {key: values[key] for key in fields if key in values}
    if (params.get('resource') != resource_uri() or params.get('response_type') != 'code'
            or not params.get('redirect_uri') or params.get('code_challenge_method') != 'S256'
            or not re.fullmatch(r'[A-Za-z0-9_-]{43}', params.get('code_challenge', ''))):
        return HttpResponseBadRequest('授权请求缺少有效的资源、回调地址或 PKCE 参数。')
    params.setdefault('scope', READ_SCOPE)
    uri = _endpoint(request, 'learning-memory-oauth-authorize') + '?' + urlencode(params)
    oauth = server()
    try:
        scopes, _ = oauth.validate_authorization_request(uri)
    except OAuth2Error:
        return HttpResponseBadRequest('授权请求无效或客户端未注册。')
    learners = get_user_model().objects.filter(pk__in=account_learner_ids(account))
    if request.method == 'GET':
        spaces = [(learner.pk, '个人学习空间' if learner.pk == account.pk else learner.workspace_learner.workspace.name)
                  for learner in learners.select_related('workspace_learner__workspace').order_by('pk')
                  if learner_account_active(learner, account)]
        return render(request, 'learning_memory_oauth_consent.html', {
            'client': registered_client(params['client_id']),
            'spaces': spaces,
            'params': params, 'scopes': [SCOPES[scope] for scope in scopes],
        })
    if values.get('decision') == 'deny':
        response = [('error', 'access_denied')]
        if 'state' in params:
            response.append(('state', params['state']))
        return HttpResponseRedirect(add_params_to_uri(params['redirect_uri'], response))
    learner_id = values.get('learner_id', '')
    if values.get('decision') != 'allow' or not re.fullmatch(r'[1-9][0-9]{0,17}', learner_id):
        return HttpResponseBadRequest('请选择要授权的学习空间。')
    learner = get_object_or_404(learners, pk=learner_id)
    if not learner_account_active(learner, account):
        raise Http404
    headers, body, status = oauth.create_authorization_response(uri, scopes=scopes,
        credentials={'user': account, 'learning_learner': learner})
    return HttpResponse(body, status=status, headers=headers)


@csrf_exempt
@require_POST
@never_cache
@rate_limit('learning_memory_oauth_token', 60, 300, methods={'POST'})
def token(request):
    _require_oauth(request)
    if request.content_type != 'application/x-www-form-urlencoded' or len(request.body) > 16384:
        return JsonResponse({'error': 'invalid_request'}, status=400)
    body = request.body.decode('ascii', errors='replace')
    params = request.POST
    if len(params.getlist('grant_type')) != 1 or params.getlist('resource') != [resource_uri()]:
        return JsonResponse({'error': 'invalid_request'}, status=400)
    if params['grant_type'] == 'authorization_code':
        fields = ('redirect_uri', 'code_verifier', 'code')
        if (any(len(params.getlist(name)) != 1 for name in fields)
                or not re.fullmatch(r'[A-Za-z0-9._~-]{43,128}', params['code_verifier'])):
            return JsonResponse({'error': 'invalid_request'}, status=400)
    elif params['grant_type'] == 'refresh_token':
        if len(params.getlist('refresh_token')) != 1 or len(params.getlist('scope')) > 1:
            return JsonResponse({'error': 'invalid_request'}, status=400)
        if params.get('scope') and READ_SCOPE not in params['scope'].split():
            return JsonResponse({'error': 'invalid_scope'}, status=400)
    else:
        return JsonResponse({'error': 'unsupported_grant_type'}, status=400)
    with transaction.atomic():
        headers, response, status = server().create_token_response(
            _endpoint(request, 'learning-memory-oauth-token'), http_method='POST', body=body, headers=request.headers,
        )
    return HttpResponse(response, headers=headers, status=status)
