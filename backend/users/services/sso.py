"""SSO 单点登录服务 — OAuth2 提供商抽象层。"""
import hashlib
import hmac
import json
import secrets
import time
from urllib.parse import urlencode

from django.conf import settings
from django.contrib.auth import get_user_model

User = get_user_model()

# 默认回调地址
DEFAULT_REDIRECT_URI = '/api/users/sso/callback/'

# 各提供商的 OAuth 端点
PROVIDER_ENDPOINTS = {
    'feishu': {
        'authorize': 'https://open.feishu.cn/open-apis/authen/v1/authorize',
        'token': 'https://open.feishu.cn/open-apis/authen/v1/access_token',
        'userinfo': 'https://open.feishu.cn/open-apis/authen/v1/user_info',
    },
    'dingtalk': {
        'authorize': 'https://login.dingtalk.com/oauth2/auth',
        'token': 'https://api.dingtalk.com/v1.0/oauth2/userAccessToken',
        'userinfo': 'https://api.dingtalk.com/v1.0/contact/users/me',
    },
    'wecom': {
        'authorize': 'https://open.work.weixin.qq.com/wwopen/sso/qrConnect',
        'token': 'https://qyapi.weixin.qq.com/cgi-bin/gettoken',
        'userinfo': 'https://qyapi.weixin.qq.com/cgi-bin/user/getuserinfo',
    },
}


def generate_state_token(institution_id: int) -> str:
    """生成防 CSRF 的状态令牌。"""
    payload = json.dumps({'inst': institution_id, 'ts': int(time.time())})
    sig = hmac.new(
        settings.SECRET_KEY.encode('utf-8'),
        payload.encode('utf-8'),
        hashlib.sha256,
    ).hexdigest()[:16]
    return f'{payload}|{sig}'


def verify_state_token(state: str) -> int | None:
    """验证状态令牌，返回 institution_id 或 None。"""
    try:
        payload_str, sig = state.rsplit('|', 1)
        expected = hmac.new(
            settings.SECRET_KEY.encode('utf-8'),
            payload_str.encode('utf-8'),
            hashlib.sha256,
        ).hexdigest()[:16]
        if not hmac.compare_digest(sig, expected):
            return None
        payload = json.loads(payload_str)
        # 10 分钟过期
        if int(time.time()) - payload.get('ts', 0) > 600:
            return None
        return payload.get('inst')
    except (ValueError, json.JSONDecodeError):
        return None


def get_authorize_url(config, base_url: str) -> str:
    """构建提供商 OAuth 授权 URL。"""
    eps = PROVIDER_ENDPOINTS.get(config.provider, {})
    auth_url = eps.get('authorize', '')
    if not auth_url:
        raise ValueError(f'Unknown SSO provider: {config.provider}')

    redirect_uri = config.redirect_uri or f'{base_url}{DEFAULT_REDIRECT_URI}'
    # 只允许 base_url 域名或已配置的合法 redirect_uri
    if config.redirect_uri and not config.redirect_uri.startswith(base_url):
        raise ValueError('redirect_uri 必须与当前站点域名一致')

    state = generate_state_token(config.institution_id)

    params = {
        'app_id': config.client_id,
        'redirect_uri': redirect_uri,
        'state': state,
        'response_type': 'code',
        'scope': 'contact:user.email:readonly' if config.provider == 'feishu' else 'snsapi_userinfo',
    }

    return f'{auth_url}?{urlencode(params)}'


def exchange_code(config, code: str, base_url: str) -> dict | None:
    """用授权码交换 access token 并获取用户信息。"""
    import requests

    eps = PROVIDER_ENDPOINTS.get(config.provider, {})
    token_url = eps.get('token', '')
    userinfo_url = eps.get('userinfo', '')

    redirect_uri = config.redirect_uri or f'{base_url}{DEFAULT_REDIRECT_URI}'

    try:
        # 获取 access token
        token_data = {
            'app_id': config.client_id,
            'app_secret': config.client_secret,
            'code': code,
            'grant_type': 'authorization_code',
        }
        if config.provider == 'feishu':
            token_data['redirect_uri'] = redirect_uri

        resp = requests.post(token_url, json=token_data if config.provider == 'feishu' else token_data, timeout=10)
        token_result = resp.json()

        if config.provider == 'wecom':
            # 企微先获取企业 token，再获取用户信息
            access_token = token_result.get('access_token', '')
            resp2 = requests.get(f'{userinfo_url}?access_token={access_token}&code={code}', timeout=10)
            return resp2.json()

        access_token = (
            token_result.get('data', {}).get('access_token', '') or
            token_result.get('accessToken', '') or
            token_result.get('access_token', '')
        )

        if not access_token:
            return None

        # 获取用户信息
        headers = {'Authorization': f'Bearer {access_token}'}
        resp3 = requests.get(userinfo_url, headers=headers, timeout=10)
        return resp3.json()
    except Exception:
        return None


def normalize_user_info(provider: str, raw: dict) -> dict:
    """将不同提供商的用户信息标准化为统一格式。"""
    if provider == 'feishu':
        data = raw.get('data', raw)
        return {
            'name': data.get('name', data.get('nickname', '')),
            'email': data.get('email', ''),
            'phone': data.get('mobile', ''),
            'open_id': data.get('open_id', ''),
            'avatar': data.get('avatar_url', data.get('avatar', '')),
        }
    elif provider == 'dingtalk':
        return {
            'name': raw.get('nick', raw.get('name', '')),
            'email': raw.get('email', ''),
            'phone': raw.get('mobile', raw.get('stateCode', '') + (raw.get('mobile', ''))),
            'open_id': raw.get('openId', raw.get('unionId', '')),
            'avatar': raw.get('avatarUrl', ''),
        }
    elif provider == 'wecom':
        return {
            'name': raw.get('name', raw.get('UserId', '')),
            'email': raw.get('email', ''),
            'phone': raw.get('mobile', ''),
            'open_id': raw.get('OpenId', raw.get('UserId', '')),
            'avatar': raw.get('avatar', ''),
        }
    else:
        return {
            'name': raw.get('name', raw.get('nickname', raw.get('sub', ''))),
            'email': raw.get('email', ''),
            'phone': raw.get('phone', raw.get('phone_number', '')),
            'open_id': raw.get('sub', raw.get('open_id', '')),
            'avatar': raw.get('picture', raw.get('avatar', '')),
        }


def find_or_create_sso_user(institution, user_info: dict, config):
    """根据 SSO 用户信息匹配或创建本地用户，并关联到机构。"""
    from django.db import IntegrityError, transaction

    email = user_info.get('email', '').strip()

    name = user_info.get("name", "").strip()
    # 1. 按邮箱匹配
    user = None
    if not user and email:
        user = User.objects.filter(email=email).first()

    # 2. 创建新用户（处理并发创建导致的 IntegrityError）
    if not user:
        username = f'sso_{user_info.get("open_id", secrets.token_hex(6))}'
        base_username = username
        counter = 1
        while User.objects.filter(username=username).exists():
            username = f'{base_username}_{counter}'
            counter += 1

        try:
            with transaction.atomic():
                user = User.objects.create_user(
                    username=username,
                    email=email or f'{username}@sso.local',
                    nickname=name,
                    role='student',
                )
        except IntegrityError:
            # 并发创建——回退到查询
            if not user and email:
                user = User.objects.filter(email=email).first()
            if not user:
                raise

    # 3. 自动加入机构（如果尚未加入）
    if config.auto_join and not user.institution:
        user.institution = institution
        user.institution_role = config.default_role
        user.save(update_fields=['institution', 'institution_role'])

    return user
