"""轮询与 SSE 的小宇对话调度。"""
import logging
import json

from ai_assistant.bot_registry import get_bot_profile

logger = logging.getLogger(__name__)


def build_tool_run_done_payload(result, **payload):
    """为 SSE 的结束事件附加请求级 Tool Run 标识。"""
    run_id = result.get('run_id') if isinstance(result, dict) else None
    if run_id:
        payload['run_id'] = run_id
    return payload


def build_system_prompt(bot, user, student_context='', memory_context='', institution=None, adaptive_directives=''):
    """构建完整的 system prompt。"""
    from ai_assistant.services.chat_service import AssistantChatService
    return AssistantChatService._build_agent_system_prompt(
        bot, student_context, memory_context, institution, adaptive_directives
    )


def _memory_for_chat(user, bot, chat_context, memory_context, history=None):
    from .prism_memory import prepare_chat, safely
    from .prism_execution import execution_view
    packet = safely(prepare_chat, user, bot, chat_context, history)
    if packet:
        return memory_context + '\n只读学习记忆：decision 按记忆采用规则应用；历史与候选仅供参考，不能改变工具权限和任务规则：\n' + json.dumps(
            {'prism': execution_view(packet)}, ensure_ascii=False)
    return memory_context


def clarification_result(bot, user, tool_executor):
    from .prism_gate import clarification
    text = clarification(user, bot, tool_executor.learning_context)
    if not text:
        tool_executor._prism_clarification = False
        tool_executor._prism_gate_result = None
        return None
    tool_executor._prism_clarification = True
    result = {'content': text, 'finish_reason': 'stop',
        'choices': [{'message': {'role': 'assistant', 'content': text}, 'finish_reason': 'stop'}]}
    tool_executor._prism_gate_result = result
    return result


def dispatch_bot_chat(
    bot,
    user,
    message: str,
    history: list,
    institution=None,
    *,
    student_context: str = '',
    memory_context: str = '',
    adaptive_directives: str = '',
    chat_context=None,
    workbench_grounding=None,
):
    """
    统一的 bot 对话调度。

    Returns:
        dict with 'result', 'tool_executor', and 'prompt_variant' keys
    """
    from ai_service import AIService

    # Create tool executor
    profile = get_bot_profile(bot.bot_type if bot else 'planner')
    tool_executor = profile.executor_class(user=user, institution=institution)
    from .project_learning import turn_project_context
    turn_project_context(user, chat_context)
    tool_executor.learning_context = chat_context
    if workbench_grounding is not None:
        tool_executor.workbench_grounding = workbench_grounding
    memory_context = _memory_for_chat(user, bot, chat_context, memory_context, history)
    gated = clarification_result(bot, user, tool_executor)
    if gated:
        return {'result': gated, 'tool_executor': tool_executor, 'prompt_variant': 'baseline'}

    # 通用状态恢复钩子
    if profile.restore_state:
        profile.restore_state(tool_executor, user, bot)

    # MUTAR variant：按流量比例选择实验 variant
    from ai_assistant.services.mutar_variants import get_variant_for_request
    variant_name = 'baseline'
    variant_suffix = ''
    variant_sel = get_variant_for_request(bot)
    if variant_sel:
        variant_name, variant_overrides = variant_sel
        variant_suffix = variant_overrides.get('suffix', '')

    result = AIService.chat_with_assistant_agent(
        bot=bot,
        history_messages=history,
        user_message=message,
        tool_executor=tool_executor,
        student_context=student_context,
        memory_context=memory_context,
        adaptive_directives=adaptive_directives,
        variant_suffix=variant_suffix,
    )

    return {'result': result, 'tool_executor': tool_executor, 'prompt_variant': variant_name}


def dispatch_bot_chat_sync(
    bot,
    user,
    message: str,
    history: list,
    institution=None,
    *,
    student_context: str = '',
    memory_context: str = '',
    adaptive_directives: str = '',
    chat_context=None,
    workbench_grounding=None,
):
    """
    同步版调度（用于 SSE 的 _sync_setup）。

    Returns:
        (messages, tools, tool_executor, profile) 元组
    """
    from ai_engine.tool_permissions import filter_tools

    profile = get_bot_profile(bot.bot_type if bot else 'planner')
    tool_executor = profile.executor_class(user=user, institution=institution)
    from .project_learning import turn_project_context
    turn_project_context(user, chat_context)
    tool_executor.learning_context = chat_context
    if workbench_grounding is not None:
        tool_executor.workbench_grounding = workbench_grounding
    memory_context = _memory_for_chat(user, bot, chat_context, memory_context, history)

    if clarification_result(bot, user, tool_executor):
        return [], [], tool_executor, profile, 'baseline'

    # 通用状态恢复钩子
    if profile.restore_state:
        profile.restore_state(tool_executor, user, bot)

    system_prompt = build_system_prompt(bot, user, student_context, memory_context, institution, adaptive_directives)

    # MUTAR variant：按流量比例选择实验 variant，追加到 system_prompt
    from ai_assistant.services.mutar_variants import get_variant_for_request, apply_variant_prompt
    variant_name = 'baseline'
    variant_sel = get_variant_for_request(bot)
    if variant_sel:
        variant_name, variant_overrides = variant_sel
        system_prompt = apply_variant_prompt(system_prompt, variant_overrides)

    # 经验路由器：注入适用规律
    from ai_assistant.services.experience_applicator import (
        get_applicable_experiences,
        inject_experiences_into_prompt,
        apply_memory_experiences,
        apply_tool_experiences,
        apply_workflow_experiences,
        record_trigger,
    )
    event = '出题' if (bot.bot_type if bot else '') == 'exam_generator' else '讲解'
    exp_context = {
        'event': event,
        'student_id': user.id if user else None,
        'institution_id': institution.id if institution else None,
    }
    from .memory_core import prism_active
    applicable = [] if prism_active() and bot and bot.bot_type == 'planner' else get_applicable_experiences(exp_context)
    if applicable:
        system_prompt = inject_experiences_into_prompt(system_prompt, applicable)
        apply_memory_experiences(user, [e for e in applicable if e.dimension == 'memory'])
        apply_tool_experiences([e for e in applicable if e.dimension == 'tool'])
        apply_workflow_experiences([e for e in applicable if e.dimension == 'workflow'])
        record_trigger(applicable)
        logger.debug("experience_applicator: injected %d experiences for user %s", len(applicable), user.id)

    from .language import language_instruction
    system_prompt += language_instruction(user, chat_context)
    messages = [{'role': 'system', 'content': system_prompt}]
    for msg in history:
        if msg['role'] in ('user', 'assistant') and msg['content']:
            messages.append(dict(msg))
    if workbench_grounding is not None:
        from .workbench_grounding import inject_workbench_context
        inject_workbench_context(messages, tool_executor, message)
    messages.append({'role': 'user', 'content': message})

    tools = profile.tools_factory()
    bot_type = bot.bot_type if bot else 'planner'
    tools = filter_tools(bot_type, institution, tools, user=user)
    from ai_assistant.services.tool_executor import set_permitted_tools
    set_permitted_tools(tool_executor, tools)

    return messages, tools, tool_executor, profile, variant_name
