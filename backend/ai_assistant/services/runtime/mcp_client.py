"""ULR Runtime Spine — Streamable HTTP MCP Client for connecting external tools into XiaoYu."""

import hashlib
import ipaddress
import json
import re
import socket
import urllib.error
import urllib.request
from time import monotonic
from urllib.parse import urlsplit

from django.conf import settings
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from ai_assistant.models import ExternalMcpServer
from ai_engine.observability import log_ai_operation, observe_runtime, resolve_trace_id

MCP_CLIENT_PROTOCOL = '2025-11-25'
MAX_TOOLS_PER_SERVER = 20
MAX_TOOLS_PER_USER = 32
MAX_RESULT_CHARS = 12_000
DEFAULT_HTTP_TIMEOUT = 15

MCP_PRESETS = (
    {
        'id': 'notion',
        'name': 'Notion',
        'category': 'notes',
        'url': 'https://mcp.notion.com/mcp',
        'auth_type': ExternalMcpServer.AUTH_BEARER,
        'description': '读取和检索 Notion 笔记与知识库页面。',
    },
    {
        'id': 'github',
        'name': 'GitHub',
        'category': 'code',
        'url': 'https://api.githubcopilot.com/mcp/',
        'auth_type': ExternalMcpServer.AUTH_BEARER,
        'description': '检索代码仓库、Issue 与文档。',
    },
    {
        'id': 'obsidian',
        'name': 'Obsidian',
        'category': 'notes',
        'url': '',
        'auth_type': ExternalMcpServer.AUTH_BEARER,
        'description': '连接你的 Obsidian 远程/自托管 MCP 笔记库。',
    },
    {
        'id': 'google-drive',
        'name': 'Google Drive',
        'category': 'files',
        'url': '',
        'auth_type': ExternalMcpServer.AUTH_BEARER,
        'description': '连接 Google Drive MCP 读取课件、论文与文档。',
    },
    {
        'id': 'feishu',
        'name': '飞书文档',
        'category': 'collab',
        'url': '',
        'auth_type': ExternalMcpServer.AUTH_BEARER,
        'description': '连接飞书 MCP 检索云文档与学习日程。',
    },
    {
        'id': 'zotero',
        'name': 'Zotero',
        'category': 'research',
        'url': '',
        'auth_type': ExternalMcpServer.AUTH_BEARER,
        'description': '连接 Zotero MCP 检索文献题录与阅读笔记。',
    },
    {
        'id': 'anki',
        'name': 'Anki',
        'category': 'memory',
        'url': '',
        'auth_type': ExternalMcpServer.AUTH_BEARER,
        'description': '连接 Anki MCP 同步外部卡片与复习进度。',
    },
    {
        'id': 'custom',
        'name': '自定义 MCP 服务',
        'category': 'custom',
        'url': '',
        'auth_type': ExternalMcpServer.AUTH_BEARER,
        'description': '接入任意符合 Streamable HTTP 规范的远程 MCP 服务。',
    },
)


class McpClientError(Exception):
    """Raised when an external MCP server call fails."""


def mcp_client_enabled() -> bool:
    return bool(
        getattr(settings, 'UNIMIND_MCP_CLIENT_ENABLED', False)
        or getattr(settings, 'UNIMIND_LEARNING_MEMORY_CONNECTORS', False)
    )


def _allow_private_urls() -> bool:
    return bool(getattr(settings, 'UNIMIND_MCP_CLIENT_ALLOW_PRIVATE_URLS', False))


def _is_forbidden_ip(ip_obj) -> bool:
    return bool(
        ip_obj.is_private
        or ip_obj.is_loopback
        or ip_obj.is_link_local
        or ip_obj.is_multicast
        or ip_obj.is_reserved
        or ip_obj.is_unspecified
    )


def validate_mcp_server_url(url: str, *, resolve_dns: bool = False) -> str:
    if not isinstance(url, str) or not url.strip() or len(url) > 500:
        raise ValidationError('MCP 服务地址必须为 1–500 字符的有效 URL。')
    cleaned = url.strip()
    try:
        parsed = urlsplit(cleaned)
    except ValueError as exc:
        raise ValidationError('MCP 服务地址无法解析。') from exc
    allow_private = _allow_private_urls()
    if parsed.scheme not in ('https', 'http'):
        raise ValidationError('MCP 服务地址仅支持 HTTPS 协议。')
    if parsed.scheme == 'http' and not allow_private:
        raise ValidationError('生产环境仅允许 HTTPS 远程 MCP 服务地址。')
    if not parsed.hostname or parsed.username or parsed.password or parsed.fragment:
        raise ValidationError('MCP 服务地址不能包含凭据、空主机名或片段。')
    host = parsed.hostname.lower()
    if not allow_private:
        if host in ('localhost', 'localhost.localdomain') or host.endswith('.local') or host.endswith('.internal'):
            raise ValidationError('不允许连接本机或内网域名。')
        try:
            ip = ipaddress.ip_address(host)
        except ValueError:
            ip = None
        if ip is not None and _is_forbidden_ip(ip):
            raise ValidationError('不允许连接内网或保留 IP 地址。')
        if resolve_dns and ip is None:
            try:
                infos = socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == 'https' else 80))
            except OSError as exc:
                raise McpClientError(f'无法解析外部 MCP 主机地址：{host}') from exc
            for _, _, _, _, sockaddr in infos:
                resolved = ipaddress.ip_address(sockaddr[0])
                if _is_forbidden_ip(resolved):
                    raise McpClientError('外部 MCP 主机解析到受限内网地址，已拒绝连接。')
    return cleaned


def make_server_slug(name: str, existing_slugs: set[str] | None = None) -> str:
    raw = re.sub(r'[^a-z0-9]+', '_', (name or '').lower()).strip('_')
    if not raw:
        raw = 'srv_' + hashlib.sha256((name or 'mcp').encode('utf-8')).hexdigest()[:8]
    base = raw[:20].strip('_') or 'srv'
    taken = existing_slugs or set()
    if base not in taken:
        return base
    for index in range(2, 100):
        candidate = f'{base[:16]}_{index}'
        if candidate not in taken:
            return candidate
    return f'{base[:11]}_{hashlib.sha256(name.encode("utf-8")).hexdigest()[:6]}'


def namespace_tool_name(slug: str, tool_name: str) -> str:
    safe_tool = re.sub(r'[^a-zA-Z0-9_-]+', '_', tool_name).strip('_') or 'tool'
    candidate = f'mcp__{slug}__{safe_tool}'
    if len(candidate) <= 64:
        return candidate
    suffix = hashlib.sha256(f'{slug}:{tool_name}'.encode('utf-8')).hexdigest()[:6]
    return f'{candidate[:57]}_{suffix}'


def _default_http_post(url: str, headers: dict, body_bytes: bytes, timeout: int = DEFAULT_HTTP_TIMEOUT):
    req = urllib.request.Request(url, data=body_bytes, headers=headers, method='POST')
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read(262_144)
            resp_headers = {k.lower(): v for k, v in resp.headers.items()}
            return resp.status, resp_headers, raw.decode('utf-8', errors='replace')
    except urllib.error.HTTPError as exc:
        body = exc.read(4096).decode('utf-8', errors='replace') if exc.fp else ''
        return exc.code, {k.lower(): v for k, v in (exc.headers.items() if exc.headers else ())}, body
    except OSError as exc:
        raise McpClientError(f'连接外部 MCP 服务失败：{exc}') from exc


def _parse_mcp_http_payload(status: int, headers: dict, text: str):
    if status in (202, 204):
        return None
    if status >= 400:
        raise McpClientError(f'外部 MCP 服务返回 HTTP {status}。')
    if not text.strip():
        return None
    content_type = headers.get('content-type', '').lower()
    if 'text/event-stream' in content_type:
        last_msg = None
        for line in text.splitlines():
            if line.startswith('data:'):
                data = line[5:].strip()
                if data and data != '[DONE]':
                    try:
                        last_msg = json.loads(data)
                    except json.JSONDecodeError:
                        continue
        return last_msg
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise McpClientError('外部 MCP 服务返回了非 JSON 响应。') from exc


class StreamableHttpMcpClient:
    """Minimal, bounded Streamable HTTP JSON-RPC 2.0 MCP client."""

    def __init__(self, server: ExternalMcpServer, *, transport=None, timeout: int = DEFAULT_HTTP_TIMEOUT):
        self.server = server
        self.transport = transport or _default_http_post
        self.timeout = timeout
        self.session_id = None
        self.protocol_version = MCP_CLIENT_PROTOCOL
        self._seq = 0

    def _headers(self, trace_id: str | None = None) -> dict:
        headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json, text/event-stream',
            'MCP-Protocol-Version': self.protocol_version,
            'User-Agent': 'UniMind-MCP-Client/1.0',
        }
        if trace_id:
            headers['X-Trace-Id'] = trace_id
        if self.session_id:
            headers['Mcp-Session-Id'] = self.session_id
        secret = (self.server.auth_secret or '').strip()
        if self.server.auth_type == ExternalMcpServer.AUTH_BEARER and secret:
            headers['Authorization'] = f'Bearer {secret}'
        elif self.server.auth_type == ExternalMcpServer.AUTH_HEADER and secret:
            header_name = (self.server.auth_header_name or '').strip()
            if header_name and re.fullmatch(r'[A-Za-z0-9-]+', header_name):
                headers[header_name] = secret
        return headers

    def _rpc(self, method: str, params: dict | None = None, *, notify: bool = False, trace_id: str | None = None):
        validate_mcp_server_url(self.server.url, resolve_dns=self.transport is _default_http_post)
        payload = {'jsonrpc': '2.0', 'method': method, 'params': params or {}}
        if not notify:
            self._seq += 1
            payload['id'] = self._seq
        body = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        status, headers, text = self.transport(self.server.url, self._headers(trace_id), body, self.timeout)
        if sid := headers.get('mcp-session-id'):
            self.session_id = sid
        if notify:
            return None
        parsed = _parse_mcp_http_payload(status, headers, text)
        if not isinstance(parsed, dict):
            raise McpClientError('外部 MCP 响应为空或格式异常。')
        if 'error' in parsed:
            err = parsed['error']
            msg = err.get('message') if isinstance(err, dict) else str(err)
            raise McpClientError(f'外部 MCP 错误：{msg}')
        return parsed.get('result', {})

    def initialize(self, *, trace_id: str | None = None) -> dict:
        result = self._rpc(
            'initialize',
            {
                'protocolVersion': MCP_CLIENT_PROTOCOL,
                'capabilities': {},
                'clientInfo': {'name': 'unimind-xiaoyu', 'version': '1.0.0'},
            },
            trace_id=trace_id,
        )
        if isinstance(result.get('protocolVersion'), str):
            self.protocol_version = result['protocolVersion']
        try:
            self._rpc('notifications/initialized', {}, notify=True, trace_id=trace_id)
        except McpClientError:
            pass
        return result

    def list_tools(self, *, trace_id: str | None = None) -> list[dict]:
        result = self._rpc('tools/list', {}, trace_id=trace_id)
        raw_tools = result.get('tools', [])
        if not isinstance(raw_tools, list):
            return []
        return raw_tools[:MAX_TOOLS_PER_SERVER]

    def call_tool(self, name: str, arguments: dict, *, trace_id: str | None = None) -> dict:
        result = self._rpc('tools/call', {'name': name, 'arguments': arguments or {}}, trace_id=trace_id)
        return result if isinstance(result, dict) else {'content': [{'type': 'text', 'text': str(result)}]}


def _sanitize_input_schema(schema) -> dict:
    if not isinstance(schema, dict) or schema.get('type') != 'object':
        return {'type': 'object', 'properties': {}}
    cleaned = {'type': 'object', 'properties': schema.get('properties') if isinstance(schema.get('properties'), dict) else {}}
    if isinstance(schema.get('required'), list):
        cleaned['required'] = [str(item) for item in schema['required']]
    if 'additionalProperties' in schema and isinstance(schema['additionalProperties'], bool):
        cleaned['additionalProperties'] = schema['additionalProperties']
    return cleaned


def _is_read_only_tool(raw_tool: dict) -> bool:
    annotations = raw_tool.get('annotations')
    if isinstance(annotations, dict):
        if annotations.get('destructiveHint') is True:
            return False
        if 'readOnlyHint' in annotations:
            return bool(annotations['readOnlyHint'])
    name = str(raw_tool.get('name', '')).lower()
    write_prefixes = ('create_', 'update_', 'delete_', 'remove_', 'write_', 'append_', 'post_', 'put_', 'patch_', 'send_', 'drop_')
    return not name.startswith(write_prefixes)


def sync_server_tools(server: ExternalMcpServer, *, transport=None) -> list[dict]:
    trace_id = resolve_trace_id(None)
    started = monotonic()
    client = StreamableHttpMcpClient(server, transport=transport)
    try:
        with observe_runtime('mcp_client', f'mcp_client:sync:{server.slug}', trace_id=trace_id, server_id=server.pk):
            client.initialize(trace_id=trace_id)
            raw_tools = client.list_tools(trace_id=trace_id)
            normalized = []
            seen_names = set()
            for item in raw_tools:
                if not isinstance(item, dict) or not isinstance(item.get('name'), str) or not item['name'].strip():
                    continue
                orig_name = item['name'].strip()[:120]
                ns_name = namespace_tool_name(server.slug, orig_name)
                if ns_name in seen_names:
                    continue
                seen_names.add(ns_name)
                normalized.append({
                    'name': orig_name,
                    'namespaced_name': ns_name,
                    'description': str(item.get('description') or f'调用 {server.name} 的 {orig_name} 工具')[:400],
                    'inputSchema': _sanitize_input_schema(item.get('inputSchema')),
                    'read_only': _is_read_only_tool(item),
                })
            server.cached_tools = normalized
            server.last_synced_at = timezone.now()
            server.last_error = ''
            server.save(update_fields=['cached_tools', 'last_synced_at', 'last_error', 'updated_at'])
            log_ai_operation('mcp_client.sync', True, (monotonic() - started) * 1000)
            return normalized
    except McpClientError as exc:
        server.last_error = str(exc)[:300]
        server.save(update_fields=['last_error', 'updated_at'])
        log_ai_operation('mcp_client.sync', False, (monotonic() - started) * 1000, 'transport')
        raise


def external_mcp_tools_for_user(user) -> list[dict]:
    if not mcp_client_enabled() or not getattr(user, 'pk', None):
        return []
    servers = ExternalMcpServer.objects.filter(user=user, enabled=True).order_by('id')
    definitions = []
    for server in servers:
        for tool in server.cached_tools or []:
            if not isinstance(tool, dict):
                continue
            if not tool.get('read_only', True) and not server.allow_write_tools:
                continue
            ns_name = tool.get('namespaced_name')
            if not ns_name:
                continue
            definitions.append({
                'type': 'function',
                'function': {
                    'name': ns_name,
                    'description': f"[{server.name}] {tool.get('description', '')}".strip(),
                    'parameters': _sanitize_input_schema(tool.get('inputSchema')),
                },
            })
            if len(definitions) >= MAX_TOOLS_PER_USER:
                return definitions
    return definitions


def _extract_tool_content(result: dict) -> str:
    if 'structuredContent' in result and result['structuredContent'] is not None:
        text = json.dumps(result['structuredContent'], ensure_ascii=False, default=str)
    else:
        blocks = result.get('content')
        if isinstance(blocks, list):
            parts = []
            for block in blocks:
                if isinstance(block, dict) and block.get('type') == 'text':
                    parts.append(str(block.get('text', '')))
                else:
                    parts.append(json.dumps(block, ensure_ascii=False, default=str))
            text = '\n'.join(part for part in parts if part)
        else:
            text = json.dumps(result, ensure_ascii=False, default=str)
    if len(text) > MAX_RESULT_CHARS:
        return text[:MAX_RESULT_CHARS] + '\n...[外部 MCP 返回内容已截断]'
    return text


def call_external_mcp_tool(user, namespaced_name: str, arguments: dict, *, trace_id: str | None = None, transport=None) -> dict:
    if not mcp_client_enabled():
        raise PermissionDenied('外部 MCP 工具连接未开启。')
    target_server = None
    target_tool = None
    for server in ExternalMcpServer.objects.filter(user=user, enabled=True).order_by('id'):
        for tool in server.cached_tools or []:
            if isinstance(tool, dict) and tool.get('namespaced_name') == namespaced_name:
                target_server = server
                target_tool = tool
                break
        if target_server:
            break
    if not target_server or not target_tool:
        raise PermissionDenied('当前账号未启用或未授权此外部 MCP 工具。')
    if not target_tool.get('read_only', True) and not target_server.allow_write_tools:
        raise PermissionDenied('该外部 MCP 连接当前为只读模式，不允许调用写入工具。')

    resolved_trace = resolve_trace_id(trace_id)
    started = monotonic()
    client = StreamableHttpMcpClient(target_server, transport=transport)
    with observe_runtime('mcp_client', f'mcp_client:call:{namespaced_name}', trace_id=resolved_trace, server_id=target_server.pk):
        try:
            client.initialize(trace_id=resolved_trace)
            raw = client.call_tool(target_tool['name'], arguments or {}, trace_id=resolved_trace)
            is_error = bool(raw.get('isError'))
            log_ai_operation('mcp_client.call', not is_error, (monotonic() - started) * 1000)
            return {
                'source': f"mcp:{target_server.slug}:{target_tool['name']}",
                'server': target_server.name,
                'external_data': True,
                'is_error': is_error,
                'content': _extract_tool_content(raw),
            }
        except McpClientError as exc:
            log_ai_operation('mcp_client.call', False, (monotonic() - started) * 1000, 'transport')
            return {
                'source': f"mcp:{target_server.slug}:{target_tool['name']}",
                'server': target_server.name,
                'external_data': True,
                'is_error': True,
                'error': str(exc),
            }
