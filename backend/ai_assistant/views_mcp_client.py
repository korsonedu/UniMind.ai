"""REST views for managing user-configured external MCP servers (MCP Client)."""

from django.http import Http404
from django.shortcuts import get_object_or_404
from rest_framework import serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from ai_assistant.models import ExternalMcpServer
from ai_assistant.services.runtime.mcp_client import (
    MCP_PRESETS,
    McpClientError,
    make_server_slug,
    mcp_client_enabled,
    sync_server_tools,
    validate_mcp_server_url,
)

MAX_SERVERS_PER_USER = 16


def _require_enabled():
    if not mcp_client_enabled():
        raise Http404


class ExternalMcpServerSerializer(serializers.ModelSerializer):
    has_secret = serializers.SerializerMethodField()
    tool_count = serializers.SerializerMethodField()
    tools = serializers.SerializerMethodField()

    class Meta:
        model = ExternalMcpServer
        fields = [
            'id',
            'name',
            'slug',
            'url',
            'auth_type',
            'auth_header_name',
            'has_secret',
            'enabled',
            'allow_write_tools',
            'tool_count',
            'tools',
            'last_synced_at',
            'last_error',
            'created_at',
            'updated_at',
        ]
        read_only_fields = fields

    def get_has_secret(self, obj):
        return bool(obj.auth_secret)

    def get_tool_count(self, obj):
        return len(obj.cached_tools or [])

    def get_tools(self, obj):
        return [
            {
                'name': item.get('name', ''),
                'namespaced_name': item.get('namespaced_name', ''),
                'description': item.get('description', ''),
                'read_only': bool(item.get('read_only', True)),
            }
            for item in (obj.cached_tools or [])
            if isinstance(item, dict)
        ]


class ExternalMcpServerWriteInput(serializers.Serializer):
    name = serializers.CharField(max_length=80)
    url = serializers.CharField(max_length=500)
    auth_type = serializers.ChoiceField(
        choices=[ExternalMcpServer.AUTH_NONE, ExternalMcpServer.AUTH_BEARER, ExternalMcpServer.AUTH_HEADER],
        default=ExternalMcpServer.AUTH_NONE,
    )
    auth_header_name = serializers.CharField(max_length=80, required=False, allow_blank=True, default='Authorization')
    auth_secret = serializers.CharField(max_length=2000, required=False, allow_blank=True, default='')
    enabled = serializers.BooleanField(required=False, default=True)
    allow_write_tools = serializers.BooleanField(required=False, default=False)

    def validate_name(self, value):
        cleaned = value.strip()
        if not cleaned:
            raise serializers.ValidationError('连接名称不能为空。')
        return cleaned

    def validate_url(self, value):
        return validate_mcp_server_url(value)


class ExternalMcpServerPatchInput(serializers.Serializer):
    name = serializers.CharField(max_length=80, required=False)
    url = serializers.CharField(max_length=500, required=False)
    auth_type = serializers.ChoiceField(
        choices=[ExternalMcpServer.AUTH_NONE, ExternalMcpServer.AUTH_BEARER, ExternalMcpServer.AUTH_HEADER],
        required=False,
    )
    auth_header_name = serializers.CharField(max_length=80, required=False, allow_blank=True)
    auth_secret = serializers.CharField(max_length=2000, required=False, allow_blank=True)
    enabled = serializers.BooleanField(required=False)
    allow_write_tools = serializers.BooleanField(required=False)

    def validate_name(self, value):
        cleaned = value.strip()
        if not cleaned:
            raise serializers.ValidationError('连接名称不能为空。')
        return cleaned

    def validate_url(self, value):
        return validate_mcp_server_url(value)


class ExternalMcpServerListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        _require_enabled()
        servers = ExternalMcpServer.objects.filter(user=request.user).order_by('-id')
        return Response({
            'servers': ExternalMcpServerSerializer(servers, many=True).data,
            'presets': list(MCP_PRESETS),
        })

    def post(self, request):
        _require_enabled()
        if ExternalMcpServer.objects.filter(user=request.user).count() >= MAX_SERVERS_PER_USER:
            return Response({'detail': f'每个学习空间最多连接 {MAX_SERVERS_PER_USER} 个外部 MCP 服务。'}, status=400)
        serializer = ExternalMcpServerWriteInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        existing_slugs = set(ExternalMcpServer.objects.filter(user=request.user).values_list('slug', flat=True))
        server = ExternalMcpServer.objects.create(
            user=request.user,
            slug=make_server_slug(data['name'], existing_slugs),
            **data,
        )
        return Response(ExternalMcpServerSerializer(server).data, status=status.HTTP_201_CREATED)


class ExternalMcpServerDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request, server_id):
        _require_enabled()
        server = get_object_or_404(ExternalMcpServer, pk=server_id, user=request.user)
        serializer = ExternalMcpServerPatchInput(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        for field, value in serializer.validated_data.items():
            setattr(server, field, value)
        server.save()
        return Response(ExternalMcpServerSerializer(server).data)

    def delete(self, request, server_id):
        _require_enabled()
        server = get_object_or_404(ExternalMcpServer, pk=server_id, user=request.user)
        server.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class ExternalMcpServerSyncView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, server_id):
        _require_enabled()
        server = get_object_or_404(ExternalMcpServer, pk=server_id, user=request.user)
        try:
            sync_server_tools(server)
        except McpClientError as exc:
            return Response({'detail': str(exc), 'server': ExternalMcpServerSerializer(server).data}, status=502)
        return Response(ExternalMcpServerSerializer(server).data)
