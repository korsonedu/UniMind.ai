import re
import secrets
import time
from importlib import import_module
from urllib.parse import urlencode

from django.conf import settings
from django.core.cache import cache
from django.http import HttpResponseBadRequest, JsonResponse
from django.shortcuts import redirect, render

from users.models import User
from .services import account_is_current, platform_cookie_user

VALUE = re.compile(r'[A-Za-z0-9_-]{43}\Z')
TTL = 60


def invalid():
    return HttpResponseBadRequest('登录授权已失效，请返回官网重新进入。')


def site_entry(request):
    if not account_is_current(request, audience='website'):
        return redirect(settings.ACCOUNT_UNIMIND_ORIGIN + '/xiaoyu')
    website = f'{request.scheme}://{request.get_host()}'
    target = settings.ACCOUNT_CENTER_ORIGIN + '/accounts/unimind/'
    state = request.GET.get('entry_state')
    if state is None:
        return redirect(target + '?' + urlencode({'website': website}))
    if not VALUE.fullmatch(state):
        return invalid()
    code = secrets.token_urlsafe(32)
    grant = {'user_id': request.user.pk, 'version': request.user.account_session_version,
             'website_session': request.session.session_key, 'website': website, 'state': state,
             'expires_at': time.time() + TTL}
    try:
        if not cache.add('unimind_entry:' + code, grant, timeout=TTL):
            return JsonResponse({'error': '登录服务暂不可用，请稍后重试。'}, status=503)
    except Exception:
        return JsonResponse({'error': '登录服务暂不可用，请稍后重试。'}, status=503)
    return redirect(target + '?' + urlencode({'website': website, 'code': code, 'entry_state': state}))


def receive(request):
    """Bind the website's single-use authorization to this destination browser."""
    data = request.POST if request.method == 'POST' else request.GET
    website = data.get('website')
    if website is None:
        return None
    if website not in settings.ACCOUNT_WEBSITE_ORIGINS:
        return invalid()
    states = request.session.get('unimind_entry_states', {})
    code, state = data.get('code'), data.get('entry_state')
    if code is None and request.method == 'GET':
        state = secrets.token_urlsafe(32)
        states = {key: value for key, value in states.items() if value['expires_at'] > time.time()}
        states[state] = {'website': website, 'expires_at': time.time() + TTL}
        request.session['unimind_entry_states'] = dict(list(states.items())[-5:])
        return redirect(website + '/account-api/center/unimind/?' + urlencode({'entry_state': state}))
    if not isinstance(code, str) or not VALUE.fullmatch(code) or not isinstance(state, str) or not VALUE.fullmatch(state):
        return invalid()
    pending = states.get(state)
    if not pending or pending['website'] != website or pending['expires_at'] <= time.time():
        return invalid()
    try:
        grant = cache.get('unimind_entry:' + code)
        if not grant or grant['website'] != website or grant['state'] != state or grant['expires_at'] <= time.time():
            return invalid()
        source = import_module(settings.SESSION_ENGINE).SessionStore(grant['website_session']).load()
    except Exception:
        return JsonResponse({'error': '登录服务暂不可用，请稍后重试。'}, status=503)
    user = User.objects.filter(pk=grant['user_id'], is_active=True, account_session_version=grant['version']).first()
    if (not user or source.get('account_audience') != 'website' or source.get('account_user_id') != user.pk
            or source.get('account_session_version') != grant['version']):
        return invalid()
    platform = platform_cookie_user(request)
    chosen = user
    if platform and platform.pk != user.pk:
        if request.method == 'GET':
            return render(request, 'users/accounts/entry_select.html', {
                'website': website, 'website_user': user, 'platform': platform, 'code': code, 'entry_state': state,
            })
        if (data.get('account_id') != str(user.pk) or data.get('platform_id') != str(platform.pk)
                or data.get('selection') not in {'website', 'platform'}):
            return invalid()
        if data['selection'] == 'platform':
            chosen = platform
    elif request.method == 'POST':
        return invalid()
    try:
        if not cache.add('unimind_entry_used:' + code, True, timeout=TTL):
            return invalid()
    except Exception:
        return JsonResponse({'error': '登录服务暂不可用，请稍后重试。'}, status=503)
    states.pop(state)
    request.session['unimind_entry_states'] = states
    from .views import finish_unimind_login
    return finish_unimind_login(request, chosen)
