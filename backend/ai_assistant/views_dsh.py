"""Opt-in DSH callbacks and site entry; reuse the existing AI call ledger."""
import hashlib
import json
from django.conf import settings
from rest_framework import serializers
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response
from rest_framework.settings import api_settings
from rest_framework.views import APIView

from users.permissions import IsMember
from .dsh_authentication import DshTaskAuthentication
from .services.dsh_service import build_context, execute_tool
from .services.dsh_runtime import DshUnavailable, run_site_action, quota_write_lock, site_request_lock
from users.learning import reserve_ai_call, confirm_ai_call, release_ai_call
from users.models import AIUsageReservation


class RouteMessage(serializers.Serializer):
    role = serializers.ChoiceField(choices=('user', 'assistant'))
    content = serializers.CharField(max_length=1000, allow_blank=True)


class ContextInput(serializers.Serializer):
    message = serializers.CharField(max_length=4000, required=False, allow_blank=True, default='')
    recent_messages = RouteMessage(many=True, required=False, default=list, max_length=6)


class ToolInput(serializers.Serializer):
    arguments = serializers.DictField(default=dict)
    memory_version = serializers.CharField(min_length=64, max_length=64)


class DshContextView(APIView):
    authentication_classes = [DshTaskAuthentication, *api_settings.DEFAULT_AUTHENTICATION_CLASSES]
    permission_classes = [IsMember]

    def post(self, request):
        if not getattr(settings, 'UNIMIND_DSH_ENABLED', False):
            raise NotFound()
        data = ContextInput(data=request.data)
        data.is_valid(raise_exception=True)
        return Response(build_context(request.user, **data.validated_data))


class DshToolView(APIView):
    authentication_classes = [DshTaskAuthentication, *api_settings.DEFAULT_AUTHENTICATION_CLASSES]
    permission_classes = [IsMember]

    def post(self, request, name):
        if not getattr(settings, 'UNIMIND_DSH_ENABLED', False):
            raise NotFound()
        data = ToolInput(data=request.data)
        data.is_valid(raise_exception=True)
        return Response(execute_tool(request.user, name, **data.validated_data))


class SiteChatInput(serializers.Serializer):
    message = serializers.CharField(max_length=4000)
    request_id = serializers.UUIDField()
    session_id = serializers.RegexField(r'^[0-9a-f]{32}$', required=False, allow_null=True, default=None)


class SessionInput(serializers.Serializer):
    session_id = serializers.RegexField(r'^[0-9a-f]{32}$', required=False, allow_null=True, default=None)


class DshSiteView(APIView):
    permission_classes = [IsMember]

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if not (getattr(settings, 'UNIMIND_DSH_ENABLED', False) and getattr(settings, 'UNIMIND_DSH_SITE_ENABLED', False)):
            raise NotFound()


class DshChatView(DshSiteView):
    def post(self, request):
        data = SiteChatInput(data=request.data)
        data.is_valid(raise_exception=True)
        body = data.validated_data
        with site_request_lock(request.user):
            fingerprint = hashlib.sha256(json.dumps({'engine': 'dsh', 'message': body['message'],
                                                     'session_id': body['session_id']}, sort_keys=True).encode()).hexdigest()
            with quota_write_lock():
                reservation = reserve_ai_call(request.user, body['request_id'], fingerprint=fingerprint)
            if not reservation.acquired:
                if reservation.status == 'pending':
                    return Response({'error': '这条提问仍在处理中。'}, status=409)
                if reservation.response.get('deleted'):
                    return Response({'error': '该会话已删除。'}, status=410)
                return Response(reservation.response)
            try:
                result = run_site_action(request.user, 'chat', message=body['message'],
                                         session_id=body['session_id'], reservation=reservation)
                if result.get('finish_reason') != 'completed' or not result.get('content', '').strip():
                    raise DshUnavailable('本轮回答未完整完成，未扣除问答额度。')
                result.update(request_id=str(reservation.request_id), engine='dsh')
                with quota_write_lock():
                    confirmed = confirm_ai_call(reservation, response=result)
                if confirmed.status != 'succeeded' or confirmed.attempt_id != reservation.attempt_id:
                    raise DshUnavailable()
                return Response(result)
            finally:
                with quota_write_lock():
                    release_ai_call(reservation)


class DshSessionView(DshSiteView):
    def post(self, request, action):
        data = SessionInput(data=request.data)
        data.is_valid(raise_exception=True)
        session_id = data.validated_data['session_id']
        if action not in ('new', 'read', 'delete'):
            raise NotFound()
        if action != 'new' and not session_id:
            raise ValidationError({'session_id': '需要会话标识。'})
        with site_request_lock(request.user):
            deleted = 0
            if action == 'delete':
                with quota_write_lock():
                    deleted = AIUsageReservation.objects.filter(user=request.user, response__engine='dsh',
                        response__session_id=session_id).update(response={'engine': 'dsh', 'session_id': session_id, 'deleted': True})
            try:
                result = run_site_action(request.user, action, session_id=session_id)
            except DshUnavailable as exc:
                if action == 'delete' and deleted and exc.status_code == 404:
                    result = {'deleted': True}
                else:
                    raise
            return Response(result)
