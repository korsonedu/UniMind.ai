from datetime import timedelta
from uuid import uuid4
from urllib.parse import unquote, urlsplit, parse_qs

from django.contrib.auth import login, authenticate
from django.contrib.auth.hashers import check_password, make_password
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import transaction, IntegrityError
from django.db.models import F
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.utils.http import url_has_allowed_host_and_scheme

from core.rate_limit import _incr_cache
from users.models import User


def legacy_cookie_user(request):
    from rest_framework.authtoken.models import Token
    token = request.COOKIES.get('auth_token')
    record = Token.objects.select_related('user').filter(key=token).first() if token else None
    user = record.user if record else None
    return user if user and user.is_active and not (user.locked_until and user.locked_until > timezone.now()) else None


def account_conflict(request):
    platform = legacy_cookie_user(request)
    return platform if account_is_current(request, audience='account') and platform and platform.pk != request.user.pk else None


def revoke_account_sessions(user_id):
    from rest_framework.authtoken.models import Token
    from oauth2_provider.models import Grant, AccessToken, RefreshToken, IDToken
    with transaction.atomic():
        User.objects.select_for_update().get(pk=user_id)
        User.objects.filter(pk=user_id).update(account_session_version=F('account_session_version') + 1)
        for model in (Token, Grant, RefreshToken, AccessToken, IDToken):
            model.objects.filter(user_id=user_id).delete()


def begin_account_session(request, user, *, audience):
    login(request, user, backend='django.contrib.auth.backends.ModelBackend')
    request.session['account_user_id'] = user.pk
    request.session['account_session_version'] = user.account_session_version
    request.session['account_audience'] = audience


def account_is_current(request, *, audience):
    user = request.user
    return bool(
        user.is_authenticated and user.is_active
        and request.session.get('account_audience') == audience
        and request.session.get('account_user_id') == user.pk
        and request.session.get('account_session_version') == user.account_session_version
    )


def safe_account_next(value):
    decoded = unquote(value or '')
    if (decoded.startswith('/accounts/') and '\\' not in decoded
            and url_has_allowed_host_and_scheme(decoded, allowed_hosts=set())
            and not any(ord(char) < 32 for char in decoded)
            and urlsplit(decoded).path in {'/accounts/o/authorize/', '/accounts/profile/', '/accounts/unimind/', '/accounts/desktop/'}):
        return value
    return '/accounts/profile/'


def safe_site_return_path(value):
    decoded = unquote(value or '')
    if (decoded.startswith('/') and not decoded.startswith('//') and '\\' not in decoded
            and not any(ord(char) < 32 for char in decoded)
            and url_has_allowed_host_and_scheme(decoded, allowed_hosts=set())):
        return value
    return '/account'


def account_website_origin(request):
    from django.conf import settings
    query = request.GET if request.path == '/accounts/o/authorize/' else parse_qs(urlsplit(safe_account_next(request.POST.get('next') or request.GET.get('next'))).query)
    uri = query.get('redirect_uri', '')
    uri = uri[0] if isinstance(uri, list) and uri else uri
    callback = urlsplit(uri)
    candidate = request.GET.get('website') or (f'{callback.scheme}://{callback.netloc}' if callback.path == '/account-api/callback/' else '')
    if candidate in settings.ACCOUNT_WEBSITE_ORIGINS:
        request.session['account_website_origin'] = candidate
    origin = request.session.get('account_website_origin')
    return origin if origin in settings.ACCOUNT_WEBSITE_ORIGINS else settings.ACCOUNT_WEBSITE_ORIGINS[0]


def send_account_code(email, *, purpose):
    from core.email_service import generate_verification_code, send_verification_email
    if purpose not in {'register', 'reset_password'}:
        raise ValidationError('验证码用途不正确。')
    if not cache.add(f'account_code_cooldown:{email}', True, timeout=60):
        raise ValidationError('请等待 60 秒后重新发送。', code='cooldown')
    existing = User.objects.filter(email__iexact=email, email_verified=True).exists()
    if (purpose == 'register' and existing) or (purpose == 'reset_password' and not existing):
        return
    key = f'account_code:{purpose}:{email}'
    code = generate_verification_code()
    cache.set(key, {'purpose': purpose, 'id': uuid4().hex, 'code_hash': make_password(code), 'sent_at': timezone.now().isoformat()}, timeout=600)
    if not send_verification_email(email, code):
        cache.delete(key)
        raise ValidationError('验证码发送失败，请稍后重试。')


def consume_account_code(email, code, *, purpose):
    key = f'account_code:{purpose}:{email}'
    record = cache.get(key)
    sent_at = parse_datetime(record.get('sent_at', '')) if record else None
    if (not record or record.get('purpose') != purpose or not sent_at or timezone.is_naive(sent_at)
            or sent_at + timedelta(minutes=10) <= timezone.now()):
        raise ValidationError('验证码错误或已过期。')
    attempts = f"account_code_attempts:{record['id']}"
    if not check_password(code, record.get('code_hash', '')):
        if _incr_cache(attempts, 600) >= 5:
            cache.delete(key)
        raise ValidationError('验证码错误或已过期。')
    if cache.get(attempts, 0) >= 5 or not cache.add(f"account_code_used:{record['id']}", True, timeout=600):
        raise ValidationError('验证码错误或已过期。')
    cache.delete(key)


def is_verified_email_conflict(error):
    return 'users_verified_email_ci_unique' in str(error) or getattr(getattr(error.__cause__, 'diag', None), 'constraint_name', None) == 'users_verified_email_ci_unique'


def register_account(*, email, code, password, nickname, agreed_to_terms):
    from .forms import clean_account_password
    if agreed_to_terms is not True:
        raise ValidationError('请先同意用户协议和隐私政策。')
    email = email.strip().lower()
    clean_account_password(password)
    if User.objects.filter(email__iexact=email, email_verified=True).exists():
        raise ValidationError('该邮箱已有账号，请直接登录。')
    consume_account_code(email, code, purpose='register')
    try:
        with transaction.atomic():
            return User.objects.create_user(
                username=f'{email.split("@")[0][:64]}_{uuid4().hex[:12]}', email=email,
                password=password, nickname=nickname, email_verified=True,
                agreed_to_terms=True, agreed_to_terms_at=timezone.now(),
                role='student', is_member=False, personal_plan='free', institution=None,
            )
    except IntegrityError as exc:
        if not is_verified_email_conflict(exc):
            raise
        raise ValidationError('该邮箱已有账号，请直接登录。') from exc


def authenticate_account(request, identifier, password):
    # Persist failures outside the successful authentication transaction too.
    candidates = list(User.objects.filter(username=identifier).values_list('pk', flat=True)[:1])
    if not candidates:
        candidates = list(User.objects.filter(email__iexact=identifier).values_list('pk', flat=True)[:2])
    if len(candidates) != 1:
        make_password(password)
        raise ValidationError('账号或密码不正确；邮箱对应多个账号时请使用原用户名并联系我们。')
    with transaction.atomic():
        user = User.objects.select_for_update().get(pk=candidates[0])
        if not user.is_active or (user.locked_until and user.locked_until > timezone.now()):
            error = '账号暂不可用，请稍后重试或联系我们。'
        elif authenticate(request, username=user.username, password=password) is None:
            user.failed_login_count += 1
            if user.failed_login_count >= 5:
                user.locked_until = timezone.now() + timedelta(minutes=15)
            user.save(update_fields=['failed_login_count', 'locked_until'])
            error = '账号或密码不正确。'
        else:
            user.failed_login_count = 0
            user.locked_until = None
            user.last_login = timezone.now()
            user.save(update_fields=['failed_login_count', 'locked_until', 'last_login'])
            return user
    raise ValidationError(error)


def reset_account_password(*, email, code, password):
    from .forms import clean_account_password
    clean_account_password(password)
    users = list(User.objects.filter(email__iexact=email, email_verified=True, is_active=True)[:2])
    if len(users) != 1:
        raise ValidationError('无法重置该账号，请核实邮箱或联系我们。')
    consume_account_code(email, code, purpose='reset_password')
    with transaction.atomic():
        user = User.objects.select_for_update().get(pk=users[0].pk)
        user.set_password(password)
        user.failed_login_count = 0
        user.locked_until = None
        user.save(update_fields=['password', 'failed_login_count', 'locked_until'])
