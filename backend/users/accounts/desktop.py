import base64
import hashlib
import json
import re
import secrets
import time
from functools import wraps
from urllib.parse import urlencode

from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from django.http import JsonResponse, RawPostDataException
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt, csrf_protect
from django.views.decorators.http import require_POST, require_http_methods
from rest_framework.authtoken.models import Token

from core.rate_limit import rate_limit
from users.models import User
from users.permissions import is_member_or_admin
from .services import account_is_current, account_website_origin
from .views import set_platform_cookie

VALUE = re.compile(r'[A-Za-z0-9_-]{43}\Z')
REQUEST_TTL = 180
CODE_TTL = 60


def error(message='登录请求已失效，请返回 UniMind 重新登录。', status=400):
    return JsonResponse({'error': message}, status=status)


def desktop_api(view):
    @wraps(view)
    def wrapped(request):
        if not settings.ACCOUNT_ENABLED:
            return error('账号服务暂未启用。', 503)
        origin = f'{request.scheme}://{request.get_host()}'
        if (origin not in {settings.ACCOUNT_CENTER_ORIGIN, settings.ACCOUNT_UNIMIND_ORIGIN}
                or request.headers.get('Origin', origin) != origin
                or request.headers.get('Sec-Fetch-Site') == 'cross-site'):
            return error('账号请求来源不正确。', 403)
        if request.content_type != 'application/json':
            return error('请使用 JSON 请求。', 415)
        try:
            length = int(request.META.get('CONTENT_LENGTH') or 0)
            if length > 1024:
                return error('登录请求过大。', 413)
            body = request.read(1025)
            if len(body) > 1024:
                return error('登录请求过大。', 413)
            data = json.loads(body)
        except (ValueError, UnicodeDecodeError, RawPostDataException):
            return error('登录请求不正确。')
        if not isinstance(data, dict):
            return error('登录请求不正确。')
        return view(request, data)
    return wrapped


def valid_values(data, *keys):
    return set(data) == set(keys) and all(isinstance(data.get(k), str) and VALUE.fullmatch(data[k]) for k in keys)


@csrf_exempt
@require_POST
@desktop_api
@rate_limit('desktop_start', 10, 300)
def start(request, data):
    if not valid_values(data, 'state', 'code_challenge'):
        return error('登录校验参数不正确。')
    request_id = secrets.token_urlsafe(32)
    try:
        stored = cache.add('desktop_request:' + request_id, {**data, 'expires_at': time.time() + REQUEST_TTL}, timeout=REQUEST_TTL)
    except Exception:
        return error('登录服务暂不可用，请稍后重试。', 503)
    if not stored:
        return error('登录服务暂不可用，请稍后重试。', 503)
    return JsonResponse({'request_id': request_id, 'expires_in': REQUEST_TTL})


@require_http_methods(['GET', 'POST'])
@csrf_protect
@rate_limit('desktop_confirm', 20, 300, methods={'POST'})
def confirm(request):
    request_id = request.POST.get('request') if request.method == 'POST' else request.GET.get('request')
    if not isinstance(request_id, str) or not VALUE.fullmatch(request_id):
        return error()
    try:
        ticket = cache.get('desktop_request:' + request_id)
    except Exception:
        return error('登录服务暂不可用，请稍后重试。', 503)
    if not ticket or ticket['expires_at'] <= time.time():
        return error()
    if not account_is_current(request, audience='account'):
        return redirect('/accounts/login/?' + urlencode({'next': '/accounts/desktop/?' + urlencode({'request': request_id})}))
    context = {'request_id': request_id, 'website': account_website_origin(request)}
    if request.method == 'GET':
        return render(request, 'users/accounts/desktop.html', context)
    with transaction.atomic():
        user = User.objects.select_for_update().filter(pk=request.user.pk).first()
        if (ticket['expires_at'] <= time.time() or not is_member_or_admin(user)
                or user.account_session_version != request.session.get('account_session_version')
                or (user.locked_until and user.locked_until > timezone.now())):
            return error()
        code = secrets.token_urlsafe(32)
        try:
            if not cache.add('desktop_confirmed:' + request_id, True, timeout=REQUEST_TTL):
                return error('此登录请求已确认，请返回 UniMind；需要重新登录时请在 App 中重新开始。')
            if not cache.add('desktop_code:' + code, {
                'request_id': request_id, 'user_id': user.pk, 'version': user.account_session_version,
                'expires_at': min(ticket['expires_at'], time.time() + CODE_TTL),
            }, timeout=CODE_TTL):
                return error('登录服务暂不可用，请重新开始。', 503)
        except Exception:
            return error('登录服务暂不可用，请重新开始。', 503)
    context['callback'] = 'unimind://auth/callback?' + urlencode({'code': code, 'state': ticket['state']})
    return render(request, 'users/accounts/desktop.html', context)


@csrf_exempt
@require_POST
@desktop_api
@rate_limit('desktop_exchange', 20, 300)
def exchange(request, data):
    if not valid_values(data, 'code', 'code_verifier'):
        return error('登录校验参数不正确。')
    try:
        record = cache.get('desktop_code:' + data['code'])
        ticket = cache.get('desktop_request:' + record['request_id']) if record else None
    except Exception:
        return error('登录服务暂不可用，请稍后重试。', 503)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(data['code_verifier'].encode('ascii')).digest()).rstrip(b'=').decode('ascii')
    if (not ticket or record['expires_at'] <= time.time() or ticket['expires_at'] <= time.time()
            or not secrets.compare_digest(challenge, ticket['code_challenge'])):
        return error()
    with transaction.atomic():
        user = User.objects.select_for_update().filter(pk=record['user_id']).first()
        if (record['expires_at'] <= time.time() or ticket['expires_at'] <= time.time()
                or not is_member_or_admin(user) or user.account_session_version != record['version']
                or (user.locked_until and user.locked_until > timezone.now())):
            return error()
        try:
            if not cache.add('desktop_used:' + data['code'], True, timeout=REQUEST_TTL + CODE_TTL):
                return error()
        except Exception:
            return error('登录服务暂不可用，请稍后重试。', 503)
        token, _ = Token.objects.get_or_create(user=user)
        response = JsonResponse({'ok': True})
        set_platform_cookie(response, token)
        return response
