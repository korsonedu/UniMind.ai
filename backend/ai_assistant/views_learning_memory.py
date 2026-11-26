from json import dumps
from datetime import timedelta
from time import monotonic

from django.conf import settings
from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction
from django.db.models import Q
from django.db.models.functions import Coalesce
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.urls import reverse
from rest_framework import serializers
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed, NotFound, PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from ai_assistant.models import ConversationProject, LearningMemoryCheckpoint, LearningMemoryGrant, ProjectLearningEvent
from ai_assistant.services.learning_recall import (
    HISTORY_LOOKUP_MAX_TOPICS, RECALL_TOOL, SOURCE_TOOL, read_learning_source, recall,
)
from ai_assistant.services.learning_memory_oauth import (
    READ_SCOPE, digest as _digest, learner_account_active, memory_token, oauth_enabled, registered_client, resource_uri,
)
from ai_engine.observability import log_ai_operation, observe_runtime, resolve_trace_id
from users.workspaces.identity import account_user
from users.workspaces.access import membership_for


CHECKPOINT_TOOL = {
    'name': 'record_learning_checkpoint',
    'description': '经学生确认后保存一段外部学习活动或未解决的问题。它会出现在其他 Agent 的回顾中。',
    'inputSchema': {
        'type': 'object',
        'properties': {
            'text': {'type': 'string', 'minLength': 1, 'maxLength': 1200},
            'request_id': {'type': 'string', 'format': 'uuid'},
        },
        'required': ['text', 'request_id'],
        'additionalProperties': False,
    },
    'annotations': {'readOnlyHint': False, 'destructiveHint': False, 'idempotentHint': True, 'openWorldHint': False},
}

PROTOCOLS = ('2025-11-25', '2025-06-18', '2025-03-26')


def _enabled():
    if not settings.UNIMIND_LEARNING_MEMORY_CONNECTORS:
        raise Http404


class GrantInput(serializers.Serializer):
    name = serializers.CharField(max_length=80)
    can_write = serializers.BooleanField(default=False)
    share_notes = serializers.BooleanField(default=False)


class RecallInput(serializers.Serializer):
    topic = serializers.CharField(max_length=120, allow_blank=True, default='')
    project_id = serializers.IntegerField(min_value=1, required=False)


class CheckpointInput(serializers.Serializer):
    text = serializers.CharField(max_length=1200)
    request_id = serializers.UUIDField()


class SourceInput(serializers.Serializer):
    source = serializers.CharField(max_length=80)
    topic = serializers.CharField(max_length=120, allow_blank=True, default='')
    topics = serializers.ListField(child=serializers.CharField(max_length=120), min_length=1,
                                   max_length=HISTORY_LOOKUP_MAX_TOPICS, required=False)
    offset = serializers.IntegerField(min_value=0, max_value=1000000, default=0)
    start_seconds = serializers.FloatField(min_value=0, max_value=10000000, required=False)


def _grant_rows(user, project_id):
    rows = LearningMemoryGrant.objects.all()
    if project_id is not None:
        project = get_object_or_404(ConversationProject, pk=project_id, user=user)
        return rows.filter(project=project)
    return rows.filter(Q(learner=user) | Q(project__user=user))


def _absolute_source_links(request, result):
    practice = [item for group in result.get('practice_sources', []) for item in group['items']]
    for row in (result, result.get('exam', {}), *result.get('materials', []), *result.get('items', []), *practice):
        if row.get('href'):
            row['href'] = request.build_absolute_uri(row['href'])


class LearningMemoryGrantsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, project_id=None):
        _enabled()
        rows = _grant_rows(request.user, project_id).annotate(valid_until=Coalesce('oauth_authorized_until', 'expires_at')).filter(
            valid_until__gt=timezone.now(),
        ).order_by('-pk')
        return Response([{'expires_at': row.pop('valid_until'), 'project_name': row.pop('project__name'), **row}
                         for row in rows.values('id', 'name', 'can_write', 'share_notes', 'created_at', 'valid_until', 'project__name')])

    def post(self, request, project_id=None):
        _enabled()
        project = get_object_or_404(ConversationProject, pk=project_id, user=request.user) if project_id else None
        data = GrantInput(data=request.data)
        data.is_valid(raise_exception=True)
        token = memory_token()
        grant = LearningMemoryGrant.objects.create(
            project=project, learner=None if project else request.user,
            digest=_digest(token), expires_at=timezone.now() + timedelta(days=30),
            **data.validated_data,
        )
        return Response({'id': grant.pk, 'token': token, 'expires_at': grant.expires_at},
                        status=201, headers={'Cache-Control': 'no-store'})


class LearningMemoryGrantView(APIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request, grant_id, project_id=None):
        _enabled()
        get_object_or_404(_grant_rows(request.user, project_id), pk=grant_id).delete()
        return Response(status=204)


class MemoryGrantAuthentication(BaseAuthentication):
    def authenticate(self, request):
        _enabled()
        # The Bearer credential is the only authentication mechanism on the MCP route.
        if request.headers.get('Origin'):
            raise PermissionDenied('此入口仅接受 Agent 客户端的直接连接。')
        scheme, _, token = request.headers.get('Authorization', '').partition(' ')
        if scheme.lower() != 'bearer' or not token.startswith('umlm_') or len(token) != 48:
            raise AuthenticationFailed('学习记忆授权缺失或无效。')
        grant = LearningMemoryGrant.objects.select_related('learner', 'project__user').filter(
            digest=_digest(token), expires_at__gt=timezone.now(),
        ).first()
        if not grant or not grant.owner.is_active:
            raise AuthenticationFailed('学习记忆授权已撤销或到期。')
        user = grant.owner
        if grant.oauth_resource:
            account = account_user(user)
            if (not oauth_enabled(request) or grant.oauth_resource != resource_uri()
                    or not registered_client(grant.oauth_client_id)
                    or account.account_session_version != grant.oauth_account_session_version
                    or not learner_account_active(user, account)):
                raise AuthenticationFailed('学习记忆 OAuth 授权已失效。')
        else:
            membership_for(user)
        return user, grant

    def authenticate_header(self, request):
        if oauth_enabled(request):
            metadata = request.build_absolute_uri(reverse('learning-memory-oauth-resource'))
            return f'Bearer resource_metadata="{metadata}", scope="{READ_SCOPE}"'
        return 'Bearer realm="UniMind Learning Memory"'


class LearningMemoryMcpView(APIView):
    authentication_classes = [MemoryGrantAuthentication]
    permission_classes = [IsAuthenticated]

    def perform_content_negotiation(self, request, force=False):
        # This MCP endpoint only supports POST. An SSE GET should reach the 405 response.
        return super().perform_content_negotiation(request, force=force or request.method == 'GET')

    def post(self, request):
        data = request.data
        request_id = data.get('id') if isinstance(data, dict) else None
        trace_id = resolve_trace_id(request.headers.get('X-Trace-Id'))

        def reply(result=None, *, code=None, message=None, status=200):
            response = {'jsonrpc': '2.0', 'id': request_id}
            if code is None:
                response['result'] = result
            else:
                response['error'] = {'code': code, 'message': message}
            return JsonResponse(response, status=status, headers={'Cache-Control': 'no-store', 'X-Trace-Id': trace_id})

        if not isinstance(data, dict) or data.get('jsonrpc') != '2.0' or type(request_id) not in (int, str, type(None)):
            return reply(code=-32600, message='Invalid JSON-RPC request', status=400)
        method = data.get('method')
        params = data.get('params', {})
        if not isinstance(method, str) or not isinstance(params, dict):
            return reply(code=-32600, message='Invalid JSON-RPC request', status=400)
        if 'id' not in data:
            if method.startswith('notifications/'):
                return Response(status=202)
            return reply(code=-32600, message='Expected a request ID', status=400)
        if (protocol := request.headers.get('MCP-Protocol-Version')) and protocol not in PROTOCOLS:
            return reply(code=-32600, message='Unsupported MCP protocol version', status=400)
        if method == 'initialize':
            version = params.get('protocolVersion')
            return reply({'protocolVersion': version if version in PROTOCOLS else PROTOCOLS[0],
                          'capabilities': {'tools': {}},
                          'serverInfo': {'name': 'unimind-learning-memory', 'version': '1.0.0'}})
        if method == 'ping':
            return reply({})
        if method == 'tools/list':
            recall_tool = RECALL_TOOL
            if request.auth.learner_id:
                schema = RECALL_TOOL['inputSchema']
                recall_tool = {**RECALL_TOOL, 'description': '找回当前学习空间的项目、问答、笔记、课程进度和外部记录。',
                               'inputSchema': {**schema, 'properties': {**schema['properties'], 'project_id': {
                                   'type': 'integer', 'description': '可选。查看该项目的完整续学状态和任务。'}}}}
            tools = [recall_tool]
            if request.auth.learner_id:
                tools.append(SOURCE_TOOL)
            if request.auth.can_write:
                tools.append(CHECKPOINT_TOOL)
            return reply({'tools': tools})
        if method != 'tools/call':
            return reply(code=-32601, message='Method not found')
        name = params.get('name')
        if name == RECALL_TOOL['name']:
            inputs = RecallInput(data=params.get('arguments', {}))
        elif name == SOURCE_TOOL['name'] and request.auth.learner_id:
            inputs = SourceInput(data=params.get('arguments', {}))
        elif name == CHECKPOINT_TOOL['name'] and request.auth.can_write:
            inputs = CheckpointInput(data=params.get('arguments', {}))
        else:
            return reply(code=-32602, message='Tool unavailable for this grant')
        if not inputs.is_valid():
            return reply(code=-32602, message='Invalid tool arguments')
        if name == CHECKPOINT_TOOL['name'] and not request.headers.get('X-Trace-Id'):
            trace_id = resolve_trace_id(None, fallback=inputs.validated_data['request_id'])
        started_at = monotonic()
        with observe_runtime('mcp', f'mcp:{name}:{request_id}', trace_id=trace_id, grant_id=request.auth.pk):
            if name == RECALL_TOOL['name']:
                project = request.auth.project
                if project_id := inputs.validated_data.get('project_id'):
                    if request.auth.learner_id:
                        project = ConversationProject.objects.filter(pk=project_id, user=request.user).first()
                    if not project or project.pk != project_id:
                        log_ai_operation(f'mcp.{name}', False, (monotonic() - started_at) * 1000, 'permission')
                        return reply(code=-32602, message='Project unavailable for this grant')
                result = recall(project, request.user, inputs.validated_data['topic'], include_notes=request.auth.share_notes,
                                include_workspace_checkpoints=bool(request.auth.learner_id))
            elif name == SOURCE_TOOL['name']:
                try:
                    result = read_learning_source(None, request.user, include_practice=True, **inputs.validated_data)
                except ValidationError:
                    log_ai_operation(f'mcp.{name}', False, (monotonic() - started_at) * 1000, 'validation')
                    return reply(code=-32602, message='Invalid tool arguments')
                except NotFound:
                    log_ai_operation(f'mcp.{name}', False, (monotonic() - started_at) * 1000, 'not_found')
                    return reply(code=-32602, message='Learning source unavailable for this grant')
            else:
                key = _digest(f"memory-checkpoint:{request.auth.pk}:{inputs.validated_data['request_id']}")
                value = {'agent': request.auth.name, 'text': inputs.validated_data['text']}
                with transaction.atomic():
                    valid = LearningMemoryGrant.objects.select_for_update().filter(
                        pk=request.auth.pk, digest=request.auth.digest, expires_at__gt=timezone.now(),
                        can_write=True,
                    ).first()
                    if not valid:
                        log_ai_operation(f'mcp.{name}', False, (monotonic() - started_at) * 1000, 'auth')
                        raise AuthenticationFailed('学习记忆授权已撤销或到期。')
                    if valid.learner_id:
                        event, _ = LearningMemoryCheckpoint.objects.get_or_create(
                            request_key=key, defaults={'learner_id': valid.learner_id, 'content': value})
                        source = f'checkpoint:{event.pk}'
                    else:
                        event, _ = ProjectLearningEvent.objects.get_or_create(request_key=key, defaults={
                            'project_id': valid.project_id, 'kind': 'agent_checkpoint', 'content': value})
                        source = f'event:{event.pk}'
                if event.content != value:
                    log_ai_operation(f'mcp.{name}', False, (monotonic() - started_at) * 1000, 'conflict')
                    return reply(code=-32602, message='Request ID already used for different checkpoint text')
                result = {'source': source, 'kind': 'external_self_report', 'saved_at': event.created_at}
            log_ai_operation(f'mcp.{name}', True, (monotonic() - started_at) * 1000)
        _absolute_source_links(request, result)
        envelope = {'content': [{'type': 'text', 'text': dumps(result, cls=DjangoJSONEncoder, ensure_ascii=False)}]}
        if protocol != '2025-03-26':
            envelope['structuredContent'] = result
        return reply(envelope)
