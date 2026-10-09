from urllib.parse import urlencode, urlsplit, parse_qs
from django.contrib.auth import logout
from django.core.exceptions import PermissionDenied
from authlib.common.errors import AuthlibBaseError
from joserfc.errors import JoseError
from requests import RequestException
from users.models import User
from django.conf import settings
from django import forms
from django.core.exceptions import ValidationError
from django.http import JsonResponse, HttpResponseBadRequest
from django.db import transaction
from rest_framework.authtoken.models import Token
from users.permissions import is_member_or_admin
from django.middleware.csrf import get_token
from django.shortcuts import render, redirect
from django.views.decorators.http import require_GET, require_POST, require_http_methods
from django.views.decorators.csrf import csrf_protect
from core.rate_limit import rate_limit

from .forms import LoginForm, RegisterForm, ResetPasswordForm
from .services import (account_is_current, begin_account_session, safe_account_next,
                       authenticate_account, register_account, reset_account_password, send_account_code,
                       safe_site_return_path, account_conflict, revoke_account_sessions, account_website_origin)
from .oidc import website_oauth

def account_form_response(request, *, form, title, subtitle, submit_label, purpose='', next_path='', status=200):
    return render(request, 'users/accounts/form.html', {
        'form': form, 'title': title, 'subtitle': subtitle, 'submit_label': submit_label,
        'purpose': purpose, 'next_path': next_path,
        'next_query': urlencode({'next': next_path}),
        'website': account_website_origin(request),
    }, status=status)


@require_http_methods(['GET', 'POST'])
@csrf_protect
@rate_limit('account_login', 10, 300, methods={'POST'})
def account_login(request):
    next_path = safe_account_next(request.POST.get('next') or request.GET.get('next'))
    form = LoginForm(request.POST if request.method == 'POST' else None)
    if request.method == 'POST' and form.is_valid():
        try:
            user = authenticate_account(request, **form.cleaned_data)
            begin_account_session(request, user, audience='account')
            return redirect(next_path)
        except ValidationError as exc:
            form.add_error(None, exc)
    return account_form_response(request, form=form, title='登录科晟账号',
                                 subtitle='已有 UniMind 账号可直接使用原用户名和密码。', submit_label='登录',
                                 next_path=next_path, status=400 if request.method == 'POST' else 200)


@require_http_methods(['GET', 'POST'])
@csrf_protect
@rate_limit('account_register', 5, 3600, methods={'POST'})
def account_register(request):
    next_path = safe_account_next(request.POST.get('next') or request.GET.get('next'))
    form = RegisterForm(request.POST if request.method == 'POST' else None)
    if request.method == 'POST' and form.is_valid():
        try:
            user = register_account(**form.cleaned_data)
            begin_account_session(request, user, audience='account')
            return redirect(next_path)
        except ValidationError as exc:
            form.add_error(None, exc)
    return account_form_response(request, form=form, title='注册科晟账号',
                                 subtitle='注册免费，不会自动开通 UniMind 学习服务。', submit_label='创建账号',
                                 purpose='register', next_path=next_path, status=400 if request.method == 'POST' else 200)


@require_POST
@csrf_protect
@rate_limit('account_send_code', 3, 600)
def account_send_code(request):
    try:
        email = forms.EmailField().clean(request.POST.get('email', '')).strip().lower()
        send_account_code(email, purpose=request.POST.get('purpose', ''))
    except ValidationError as exc:
        return JsonResponse({'error': '；'.join(exc.messages)}, status=429 if getattr(exc, 'code', '') == 'cooldown' else 400)
    return JsonResponse({'message': '如该邮箱符合条件，验证码已发送，10 分钟内有效。'})


@require_http_methods(['GET', 'POST'])
@csrf_protect
@rate_limit('account_reset', 5, 600, methods={'POST'})
def account_reset_password(request):
    next_path = safe_account_next(request.POST.get('next') or request.GET.get('next'))
    form = ResetPasswordForm(request.POST if request.method == 'POST' else None)
    if request.method == 'POST' and form.is_valid():
        try:
            reset_account_password(**form.cleaned_data)
            return redirect('/accounts/login/?' + urlencode({'next': next_path, 'reset': '1'}))
        except ValidationError as exc:
            form.add_error(None, exc)
    return account_form_response(request, form=form, title='找回密码',
                                 subtitle='验证注册邮箱后设置新密码。', submit_label='重置密码',
                                 purpose='reset_password', next_path=next_path, status=400 if request.method == 'POST' else 200)


@require_GET
def account_profile(request):
    if not account_is_current(request, audience='account'):
        return redirect('/accounts/login/')
    from users.permissions import is_member_or_admin
    return render(request, 'users/accounts/profile.html', {'website': account_website_origin(request), 'learning_available': is_member_or_admin(request.user)})


@require_GET
def site_session(request):
    user = request.user if account_is_current(request, audience='website') else None
    return JsonResponse({
        'user': {
            'id': user.pk, 'nickname': user.nickname, 'email': user.email,
            'email_verified': user.email_verified,
        } if user else None,
        'csrf_token': get_token(request),
    })


@require_GET
@rate_limit('account_authorize', 20, 300)
def site_login(request):
    try:
        client = website_oauth()
        origin = f'{request.scheme}://{request.get_host()}'
        response = client.authorize_redirect(request, origin + '/account-api/callback/')
    except (AuthlibBaseError, RequestException):
        return redirect('/account?error=unavailable')
    state = parse_qs(urlsplit(response['Location']).query)['state'][0]
    returns = request.session.get('account_returns', {})
    returns[state] = safe_site_return_path(request.GET.get('return_to'))
    request.session['account_returns'] = dict(list(returns.items())[-5:])
    mode = request.GET.get('mode')
    if mode in {'register', 'reset-password'}:
        authorization = urlsplit(response['Location'])
        response['Location'] = settings.ACCOUNT_CENTER_ORIGIN + f'/accounts/{mode}/?' + urlencode({'next': authorization.path + '?' + authorization.query})
    return response


@require_GET
def site_callback(request):
    state = request.GET.get('state', '')
    returns = request.session.get('account_returns', {})
    return_path = returns.pop(state, None)
    request.session['account_returns'] = returns
    if return_path is None:
        return redirect('/account?error=login')
    try:
        client = website_oauth()
        state_data = client.framework.get_state_data(request.session, state)
        if not state_data or not state_data.get('nonce'):
            raise PermissionDenied('缺少登录校验信息。')
        token = client.authorize_access_token(request, leeway=30)
        identity = token['userinfo']
        if identity.get('nonce') != state_data['nonce'] or identity.get('nonce_supported') is False:
            raise PermissionDenied('登录校验信息不匹配。')
        user = User.objects.get(pk=identity['sub'], is_active=True)
        if identity.get('account_session_version') != user.account_session_version:
            raise PermissionDenied('该登录已失效。')
        begin_account_session(request, user, audience='website')
    except (AuthlibBaseError, JoseError, RequestException, User.DoesNotExist, PermissionDenied, KeyError, ValueError):
        return redirect('/account?error=login')
    return redirect(safe_site_return_path(return_path))


@require_POST
@csrf_protect
def site_logout(request):
    logout(request)
    return JsonResponse({'status': 'ok'})


def set_platform_cookie(response, token):
    response.set_cookie('auth_token', token.key, max_age=30 * 24 * 3600,
                        httponly=True, secure=settings.SESSION_COOKIE_SECURE, samesite='Lax')


@require_GET
def unimind_entry(request):
    if not account_is_current(request, audience='account'):
        return redirect('/accounts/login/?' + urlencode({'next': '/accounts/unimind/'}))
    if account_conflict(request):
        return redirect('/accounts/select/?' + urlencode({'next': '/accounts/unimind/'}))
    with transaction.atomic():
        user = User.objects.select_for_update().get(pk=request.user.pk)
        if not user.is_active or user.account_session_version != request.session.get('account_session_version'):
            return redirect('/accounts/login/')
        if not is_member_or_admin(user):
            return render(request, 'users/accounts/profile.html', {'website': account_website_origin(request), 'learning_available': False})
        token, _ = Token.objects.get_or_create(user=user)
        response = redirect(settings.ACCOUNT_UNIMIND_ORIGIN + '/account-callback')
        set_platform_cookie(response, token)
        return response


@require_http_methods(['GET', 'POST'])
@csrf_protect
def account_select(request):
    if not account_is_current(request, audience='account'):
        return redirect('/accounts/login/')
    platform = account_conflict(request)
    next_path = safe_account_next(request.POST.get('next') or request.GET.get('next'))
    if not platform:
        return redirect(next_path)
    if request.method == 'POST':
        choice = request.POST.get('selection')
        if choice not in {'account', 'platform'}:
            return HttpResponseBadRequest('请选择账号。')
        with transaction.atomic():
            chosen = platform if choice == 'platform' else request.user
            user = User.objects.select_for_update().get(pk=chosen.pk)
            if not user.is_active or user.account_session_version != chosen.account_session_version:
                return redirect('/accounts/login/')
            begin_account_session(request, user, audience='account')
            response = redirect(next_path)
            if is_member_or_admin(user):
                token, _ = Token.objects.get_or_create(user=user)
                set_platform_cookie(response, token)
            else:
                response.delete_cookie('auth_token', samesite='Lax')
            return response
    return render(request, 'users/accounts/select.html', {'platform': platform, 'next_path': next_path, 'website': account_website_origin(request)})


@require_POST
@csrf_protect
def account_logout_all(request):
    if not account_is_current(request, audience='account'):
        return redirect('/accounts/login/')
    website = account_website_origin(request)
    revoke_account_sessions(request.user.pk)
    logout(request)
    response = redirect(website + '/account?logged_out=1')
    response.delete_cookie('auth_token', samesite='Lax')
    return response


@require_GET
def site_center(request, action):
    if action not in {'profile', 'unimind'}:
        return HttpResponseBadRequest('账号入口不正确。')
    origin = f'{request.scheme}://{request.get_host()}'
    return redirect(settings.ACCOUNT_CENTER_ORIGIN + f'/accounts/{action}/?' + urlencode({'website': origin}))
