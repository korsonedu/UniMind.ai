"""M0 read-only bridge. Identity and data access stay in Django."""
import hashlib
import json
from pathlib import Path

from django.conf import settings
from rest_framework.exceptions import APIException, PermissionDenied, ValidationError

from ai_engine.tool_permissions import filter_tools
from ai_engine.tool_router import PLANNER_INTENT_MAP
from ai_engine.tool_run import validate_arguments
from ai_engine.config import get_model_for_task
from ai_engine.tools import get_planner_tools
from ai_assistant.models import AgentMemory
from .tool_executor import PlannerToolExecutor, set_permitted_tools


M0_TOOLS = frozenset({
    'get_learning_stats', 'get_recent_practice_result', 'get_user_weak_points',
    'search_courses', 'search_asr',
})


class MemoryContextChanged(APIException):
    status_code = 409
    default_detail = '学生记忆已更新，请刷新上下文后重新开始本轮对话。'


def memory_snapshot(user):
    rows = list(AgentMemory.objects.filter(user=user, is_active=True).order_by(
        '-confidence', '-updated_at', 'id',
    ).values('id', 'memory_type', 'key', 'value', 'source', 'updated_at')[:20])
    text = json.dumps(rows, ensure_ascii=False, sort_keys=True, default=str)
    return {'version': hashlib.sha256(text.encode()).hexdigest(), 'items': rows}


def permitted_tools(user):
    definitions = [t for t in get_planner_tools() if t['function']['name'] in M0_TOOLS]
    return filter_tools('planner', None, definitions, user=user)


def build_context(user, message):
    allowed = permitted_tools(user)
    names = {'get_learning_stats'}
    for group in PLANNER_INTENT_MAP.values():
        if any(word in message.lower() for word in group['keywords']):
            names.update(group['tools'])
    if not message.strip():
        names.update(M0_TOOLS)
    selected = [t for t in allowed if t['function']['name'] in names]
    return {
        'protocol': 'unimind.dsh.m0.v1',
        'student': {'id': user.pk, 'name': user.nickname or user.username},
        'memory': memory_snapshot(user),
        'tools': selected,
        'permitted_tool_count': len(allowed),
        'route': 'keywords-and-workflow-groups',
        'model_policy': {
            'operation': 'assistant.chat.planner', 'tier': 'fast',
            'model': get_model_for_task('assistant.chat.planner')['model'],
            'max_requests': 4, 'max_tokens': 1024, 'max_request_bytes': 65536,
        },
        'system_prompt': (Path(settings.BASE_DIR) / 'prompts/ai_assistant/bots/xiaoyu/dsh_system_prompt.txt').read_text(),
    }


def execute_tool(user, name, arguments, memory_version):
    definition = next((t for t in permitted_tools(user) if t['function']['name'] == name), None)
    if definition is None:
        raise PermissionDenied('当前账号无权使用此 M0 工具。')
    if memory_snapshot(user)['version'] != memory_version:
        raise MemoryContextChanged()
    error = validate_arguments(definition['function']['parameters'], arguments)
    if error:
        raise ValidationError({'arguments': error})
    executor = PlannerToolExecutor(user)
    set_permitted_tools(executor, [definition])
    executor._allowed_tool_names = {name}
    return json.loads(executor(name, arguments))
