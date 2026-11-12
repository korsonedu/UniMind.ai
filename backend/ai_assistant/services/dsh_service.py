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
from ai_assistant.models import AgentMemory, AIChatMessage
from .tool_executor import PlannerToolExecutor, set_permitted_tools
from .dsh_cards import build_tool_card, build_learning_visual, PRESENTATION_TOOL
from .dsh_routing import grouped_tools


M0_TOOLS = frozenset({
    'manage_learning_resources', 'manage_learning_strategies', 'manage_learning_knowledge', 'manage_learning_tasks',
    'read_learning_project', 'plan_learning_project', 'record_learning_progress', 'set_learning_followup', 'find_learning_resources',
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
            parameters = tool['function']['parameters']
            parameters['properties']['purpose'] = {'type': 'string', 'enum': ['practice', 'explanation'],
                'description': '讲解取题选 explanation，只读取题目，不展示作答卡片；练习选 practice（默认）。'}
            tool['function']['description'] = '从题库读取题目并展示可作答的练习卡片。支持 q_type/subjective_type 题型过滤；学生直接在卡片内作答和提交，提交走站内练习接口并触发后台批改。若 questions 为空或 total_found=0，直接给出一道符合要求的题，可以用一句话说明考查范围，但不要说明题目来源；先给题干，等学生作答后按评分点给分和讲解；这道题的评分只在对话内有效，不写入练习记录、错题本、掌握度、ELO 或 Memorix，不伪造题目ID，不调用评分工具。本工具本身不提交答案。'
            tool['function']['description'] += '用于讲解时必须传 purpose=explanation，只读取题目，不要求学生作答，也不展示练习卡片；无匹配时直接用合成示例讲解。'
    return filter_tools('planner', None, definitions, user=user)


def permitted_tools(user):
    allowed = [t for t in student_catalog(user) if t['function']['name'] in M0_TOOLS]
    return [*allowed, PRESENTATION_TOOL] if allowed else []


def prototype_executor(user, chat_context):
    from .learning_experiments import available_to, allows_interaction, EXPERIMENT_TOOLS
    from .session_tools import SESSION_TOOLS, refresh
    if not chat_context or not available_to(user):
        return None
    current = AIChatMessage.objects.filter(user=user, pk=chat_context.get('message_id'), role='user',
        conversation_id=chat_context.get('conversation_id'), bot_id=chat_context.get('bot_id')).first()
    if not current:
        return None
    executor = PlannerToolExecutor(user)
    executor.experiment_context = chat_context
    experiments = [tool for tool in EXPERIMENT_TOOLS
        if tool['function']['name'] != 'build_learning_experiment' or allows_interaction(current)]
    set_permitted_tools(executor, [*experiments, *SESSION_TOOLS])
    executor._allowed_tool_names = set(executor._permitted_tool_definitions)
    refresh(executor, [])
    return executor


def session_registry(executor):
    return {'tools': executor._session_tool_offered,
            'versions': executor._session_tool_versions}


def build_context(user, message, recent_messages=None, chat_context=None):
    from users.learning import cohort_info
    cohort = cohort_info(user)
    catalog = student_catalog(user)
    candidates = route_tools(message, catalog, recent_messages=recent_messages,
                             bot_type='planner', intent_classifier=classify_intent_keywords)
    allowed = [t for t in catalog if t['function']['name'] in M0_TOOLS]
    if allowed:
        allowed.append(PRESENTATION_TOOL)
    executor = prototype_executor(user, chat_context)
    if executor:
        allowed.extend(executor._permitted_tool_definitions.values())
    # Runtime additions change the registry, not the underlying account authorization.
    authorization = [t for t in allowed if not t['function']['name'].startswith('session_')]
    from .project_learning import turn_project_context
    learning = turn_project_context(user, chat_context)
    selected, groups, initial = grouped_tools(allowed, message, recent_messages, project=bool(learning))
    context = {
        'protocol': 'unimind.dsh.m0.v1',
        'student': {'id': user.pk, 'name': user.nickname or user.username, 'cohort': cohort},
        'memory': memory_snapshot(user),
        'tools': selected,
        'available_tools': allowed, 'tool_groups': groups,
        'permitted_tool_count': len(allowed),
        'permissions_version': hashlib.sha256(json.dumps({'tools': authorization, 'cohort': cohort}, sort_keys=True).encode()).hexdigest(),
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
    if learning:
        context['learning_project'] = learning
        context['model_policy'].update(operation='assistant.chat.planner.learning', max_requests=6, max_tokens=4096, max_request_bytes=262144)
        context['system_prompt'] += (Path(settings.BASE_DIR) / 'prompts/ai_assistant/bots/xiaoyu/project_learning.txt').read_text() + learning
    if executor:
        from .learning_experiments import conversation_experiments
        context['session_registry'] = session_registry(executor)
        context['learning_experiments'] = conversation_experiments(user, chat_context['conversation_id'])
        context['model_policy'].update(operation='assistant.chat.planner.prototype', max_requests=6, max_tokens=8192)
        for filename in ('experiment_prototype.txt', 'session_tool_prototype.txt'):
            context['system_prompt'] += (Path(settings.BASE_DIR) / 'prompts/ai_assistant/bots/xiaoyu' / filename).read_text()
        if 'build_learning_experiment' not in executor._permitted_tool_definitions:
            context['system_prompt'] += '\n本轮不属于解答讲解，不生成交互卡片。出题、统计、计划等使用原有工具和文字。'
        context['system_prompt'] += '\n已有工具直接调用，不重复发现。仅当所需工具不在当前列表时，才通过 find_learning_tools 选择分组：编写或注册能力选 authoring；调用已有会话工具选 session。尚未注册工具时不要进入 session。每次最多使用一个分组。'
    return context


def execute_tool(user, name, arguments, memory_version, source=None, chat_context=None, tool_revision=None):
    prototype_names = {'build_learning_experiment', 'read_learning_experiment', 'register_session_tool', 'read_session_tool'}
    if name in prototype_names or name.startswith('session_'):
        executor = prototype_executor(user, chat_context)
        if not executor or name not in executor._permitted_tool_definitions:
            raise PermissionDenied('当前对话无权使用此工具。')
        if memory_snapshot(user)['version'] != memory_version:
            raise MemoryContextChanged()
        if name.startswith('session_') and (type(tool_revision) is not int
                or executor._session_tool_versions.get(name) != tool_revision):
            from .learning_experiments import ExperimentConflict
            raise ExperimentConflict('工具版本已变化，请重新读取后调用。')
        result = json.loads(executor(name, arguments))
        if source and name == 'build_learning_experiment' and result.get('error'):
            from users.models import AIUsageReservation
            failure = {'tool': name, 'arguments': arguments, 'result': result}
            if len(json.dumps(failure, ensure_ascii=False).encode()) <= 131072:
                AIUsageReservation.objects.filter(pk=source, user=user, status='pending').update(
                    response={'learning_failure': failure})
        if name in {'register_session_tool', 'read_session_tool'} and not result.get('error'):
            result['session_registry'] = session_registry(executor)
        return result
    definition = next((t for t in permitted_tools(user) if t['function']['name'] == name), None)
    if definition is None:
        raise PermissionDenied('当前账号无权使用此 M0 工具。')
    if memory_snapshot(user)['version'] != memory_version:
        raise MemoryContextChanged()
    error = validate_arguments(definition['function']['parameters'], arguments)
    if error:
        raise ValidationError({'arguments': error})
    if name == 'present_learning_visual':
        visual = build_learning_visual(arguments)
        return {'presented': True, 'visual': visual}
    if name == 'run_diagnostic':
        from .dsh_actions import prepare_diagnostic
        return prepare_diagnostic(user, source)
    if name == 'create_faq_ticket':
        from .dsh_actions import prepare_faq
        return prepare_faq(user, arguments, source)
    executor = PlannerToolExecutor(user)
    executor.learning_context = chat_context
    set_permitted_tools(executor, [definition])
    executor._allowed_tool_names = {name}
    result = json.loads(executor(name, arguments))
    if not result.get('error'):
        card = build_tool_card(name, result)
        if card:
            result['visual'] = card
    return result
