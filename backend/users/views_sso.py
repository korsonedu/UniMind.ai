"""SSO 单点登录 — OAuth2 授权流程。"""
from django.shortcuts import redirect, get_object_or_404
from django.contrib.auth import login as auth_login
from rest_framework import status
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Institution, SSOConfig
from .serializers_institution import SSOConfigSerializer
from .services.sso import (
    get_authorize_url, exchange_code, normalize_user_info,
    find_or_create_sso_user, verify_state_token,
)


class SSOAuthorizeView(APIView):
    """GET /api/users/sso/authorize/?institution_slug=xxx — 重定向到 SSO 提供商登录页。"""
    permission_classes = [AllowAny]

    def get(self, request):
        slug = request.query_params.get('institution_slug', '')
        if not slug:
            return Response({'error': '缺少机构标识'}, status=400)

        inst = get_object_or_404(Institution, slug=slug, is_active=True)
        config = get_object_or_404(SSOConfig, institution=inst, enabled=True)

        base_url = f'{request.scheme}://{request.get_host()}'
        try:
            auth_url = get_authorize_url(config, base_url)
            return redirect(auth_url)
        except ValueError as e:
            return Response({'error': str(e)}, status=400)


class SSOCallbackView(APIView):
    """GET /api/users/sso/callback/ — 处理 SSO 提供商回调。"""
    permission_classes = [AllowAny]

    def get(self, request):
        code = request.query_params.get('code', '')
        state = request.query_params.get('state', '')

        if not code:
            return Response({'error': '授权失败，未收到授权码'}, status=400)

        inst_id = verify_state_token(state)
        if not inst_id:
            return Response({'error': '无效的 SSO 状态，请重新登录'}, status=400)

        inst = get_object_or_404(Institution, pk=inst_id, is_active=True)
        config = get_object_or_404(SSOConfig, institution=inst, enabled=True)

        base_url = f'{request.scheme}://{request.get_host()}'
        raw_info = exchange_code(config, code, base_url)
        if not raw_info:
            return Response({'error': 'SSO 授权失败，无法获取用户信息'}, status=400)

        user_info = normalize_user_info(config.provider, raw_info)
        user = find_or_create_sso_user(inst, user_info, config)

        # 登录用户
        auth_login(request, user)

        # 重定向到前端
        frontend_url = request.COOKIES.get('sso_redirect_to', '/')
        return redirect(frontend_url)


class SSOConfigView(APIView):
    """GET/PUT /api/users/institution/me/sso-config/ — 机构 SSO 配置管理。"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        inst = getattr(request.user, 'institution', None)
        if not inst:
            return Response({'error': '无机构归属'}, status=403)
        role = getattr(request.user, 'institution_role', '')
        if role not in ('owner',):
            return Response({'error': '仅机构所有者可查看'}, status=403)

        config, _ = SSOConfig.objects.get_or_create(
            institution=inst,
            defaults={'provider': 'feishu', 'enabled': False},
        )
        return Response(SSOConfigSerializer(config).data)

    def put(self, request):
        inst = getattr(request.user, 'institution', None)
        if not inst:
            return Response({'error': '无机构归属'}, status=403)
        role = getattr(request.user, 'institution_role', '')
        if role not in ('owner',):
            return Response({'error': '仅机构所有者可配置'}, status=403)

        config, _ = SSOConfig.objects.get_or_create(institution=inst)
        ser = SSOConfigSerializer(config, data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        ser.save()
        return Response(ser.data)
