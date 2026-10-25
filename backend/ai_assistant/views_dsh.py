"""Opt-in M0 endpoints; no model execution or new billing path."""
from django.conf import settings
from rest_framework import serializers
from rest_framework.exceptions import NotFound
from rest_framework.response import Response
from rest_framework.views import APIView

from users.permissions import IsMember
from .services.dsh_service import build_context, execute_tool


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
    permission_classes = [IsMember]

    def post(self, request):
        if not getattr(settings, 'UNIMIND_DSH_ENABLED', False):
            raise NotFound()
        data = ContextInput(data=request.data)
        data.is_valid(raise_exception=True)
        return Response(build_context(request.user, **data.validated_data))


class DshToolView(APIView):
    permission_classes = [IsMember]

    def post(self, request, name):
        if not getattr(settings, 'UNIMIND_DSH_ENABLED', False):
            raise NotFound()
        data = ToolInput(data=request.data)
        data.is_valid(raise_exception=True)
        return Response(execute_tool(request.user, name, **data.validated_data))
