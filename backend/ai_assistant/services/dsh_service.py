"""Student bridge. Identity, data access and confirmed writes stay in Django."""
import hashlib
import json
from pathlib import Path

from django.conf import settings
from rest_framework.exceptions import APIException, PermissionDenied, ValidationError

from ai_engine.tool_permissions import filter_tools
from ai_engine.tool_router import classify_intent_keywords, route_tools
from ai_engine.tool_run import validate_arguments
from ai_engine.config import get_model_for_task
from ai_engine.tools import get_planner_tools
from ai_assistant.models import AgentMemory
from .tool_executor import PlannerToolExecutor, set_permitted_tools
from .dsh_cards import build_tool_card
from .dsh_routing import grouped_tools


M0_TOOLS = frozenset({
    'get_learning_stats', 'get_recent_practice_result', 'get_user_weak_points',
    'get_study_status', 'get_focus_history', 'run_diagnostic', 'create_faq_ticket',
    'search_courses', 'search_asr',
    'search_knowledge_tree', 'get_user_wrong_questions', 'lookup_question',
    'get_learning_sessions', 'get_knowledge_mastery_map', 'get_due_reviews',
    'get_knowledge_difficulty_analysis', 'get_practice_questions', 'get_exam_history',
    'get_report_card', 'get_my_achievements', 'search_similar_questions',
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


def student_catalog(user):
    # Retired Agent note writes stay excluded even when legacy permissions allow them.
    definitions = [t for t in get_planner_tools() if t['function']['name'] != 'save_session_note']
    for tool in definitions:
        if tool['function']['name'] == 'run_diagnostic':
            tool['function']['description'] = '准备首次诊断作答卡片，学生自行作答并确认提交后才评分。已完成首次诊断的学生进入原诊断页重新评估。本工具不接受或提交答案。'
            tool['function']['parameters'] = {'type': 'object', 'properties': {'mode': {'type': 'string', 'enum': ['generate']}}, 'required': ['mode'], 'additionalProperties': False}
        if tool['function']['name'] == 'create_faq_ticket':
            tool['function']['description'] = '准备人工答疑草稿，尚未发布；学生核对、编辑并明确确认后才能发布。本工具不创建已提交工单。'
            tool['function']['parameters'] = {**tool['function']['parameters'], 'additionalProperties': False}
        if tool['function']['name'] == 'get_practice_questions':
            tool['function']['description'] = '从题库读取题目并展示可作答的练习卡片。学生直接在卡片内作答和提交，提交走站内练习接口并触发后台批改；本工具本身不提交答案。'
    return filter_tools('planner', None, definitions, user=user)


def permitted_tools(user):
    return [t for t in student_catalog(user) if t['function']['name'] in M0_TOOLS]


def build_context(user, message, recent_messages=None):
    from users.learning import cohort_info
    cohort = cohort_info(user)
    catalog = student_catalog(user)
    candidates = route_tools(message, catalog, recent_messages=recent_messages,
                             bot_type='planner', intent_classifier=classify_intent_keywords)
    allowed = [t for t in catalog if t['function']['name'] in M0_TOOLS]
    selected, groups, initial = grouped_tools(allowed, message, recent_messages)
    return {
        'protocol': 'unimind.dsh.m0.v1',
        'student': {'id': user.pk, 'name': user.nickname or user.username, 'cohort': cohort},
        'memory': memory_snapshot(user),
        'tools': selected,
        'available_tools': allowed, 'tool_groups': groups,
        'permitted_tool_count': len(allowed),
        'permissions_version': hashlib.sha256(json.dumps({'tools': allowed, 'cohort': cohort}, sort_keys=True).encode()).hexdigest(),
        'route': 'grouped-native-tool-discovery',
        'routing': {
            'catalog_count': len(catalog), 'candidate_count': len(candidates),
            'candidate_names': [t['function']['name'] for t in candidates],
            'pending_names': [t['function']['name'] for t in candidates if t['function']['name'] not in M0_TOOLS],
            'candidate_schema_bytes': len(json.dumps(candidates, ensure_ascii=False).encode()),
            'executable_schema_bytes': len(json.dumps(selected, ensure_ascii=False).encode()),
            'available_schema_bytes': len(json.dumps(allowed, ensure_ascii=False).encode()),
            'initial_group': initial, 'max_visible_tools': 8,
            'model_intent': 'native-tool-discovery-quality-pending',
            'semantic_retrieval': 'available-for-large-catalogs' if len(catalog) > 32 else 'not-used-small-catalog',
        },
        'model_policy': {
            'operation': 'assistant.chat.planner', 'tier': 'fast',
            'model': get_model_for_task('assistant.chat.planner')['model'],
            'max_requests': 4, 'max_tokens': 1024, 'max_request_bytes': 65536,
        },
        'system_prompt': (Path(settings.BASE_DIR) / 'prompts/ai_assistant/bots/xiaoyu/dsh_system_prompt.txt').read_text(),
    }


def execute_tool(user, name, arguments, memory_version, source=None):
    definition = next((t for t in permitted_tools(user) if t['function']['name'] == name), None)
    if definition is None:
        raise PermissionDenied('当前账号无权使用此 M0 工具。')
    if memory_snapshot(user)['version'] != memory_version:
        raise MemoryContextChanged()
    error = validate_arguments(definition['function']['parameters'], arguments)
    if error:
        raise ValidationError({'arguments': error})
    if name == 'run_diagnostic':
        from .dsh_actions import prepare_diagnostic
        return prepare_diagnostic(user, source)
    if name == 'create_faq_ticket':
        from .dsh_actions import prepare_faq
        return prepare_faq(user, arguments, source)
    executor = PlannerToolExecutor(user)
    set_permitted_tools(executor, [definition])
    executor._allowed_tool_names = {name}
    result = json.loads(executor(name, arguments))
    if not result.get('error'):
        card = build_tool_card(name, result)
        if card:
            result['visual'] = card
    return result
