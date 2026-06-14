"""
统一的 bot 对话调度。

3 个入口（polling/SSE/WS）共用此模块，消除重复的 bot_type if/elif 逻辑。
"""
import logging
from typing import Callable, Optional

from ai_assistant.bot_registry import get_bot_profile

logger = logging.getLogger(__name__)


def resolve_tool_choice(profile, bot_type=None):
    """根据 bot profile 决定 tool_choice 值。
    
    全部用 auto：prompt 规定边界比硬约束更灵活，
    required 会导致任务完成后模型无法停止（如命题官无限循环出题）。
    """
    return "auto"


def create_tool_executor(bot, user):
    """根据 bot_type 创建 ToolExecutor 实例。"""
    profile = get_bot_profile(bot.bot_type if bot else 'planner')
    return profile.executor_class(user=user)


def create_tools(bot, user, institution=None):
    """根据 bot_type 创建 tools 列表。"""
    from ai_engine.tool_permissions import filter_tools
    profile = get_bot_profile(bot.bot_type if bot else 'planner')
    tools = profile.tools_factory()
    bot_type = bot.bot_type if bot else 'planner'
    return filter_tools(bot_type, institution, tools)


def build_system_prompt(bot, user, student_context='', memory_context='', institution=None, adaptive_directives=''):
    """构建完整的 system prompt。"""
    from ai_assistant.services.chat_service import AssistantChatService
    return AssistantChatService._build_agent_system_prompt(
        bot, student_context, memory_context, institution, adaptive_directives
    )


def dispatch_bot_chat(
    bot,
    user,
    message: str,
    history: list,
    institution=None,
    *,
    stream: bool = False,
    on_step: Optional[Callable] = None,
    on_message: Optional[Callable] = None,
    student_context: str = '',
    memory_context: str = '',
    adaptive_directives: str = '',
):
    """
    统一的 bot 对话调度。

    Returns:
        dict with 'result', 'tool_executor', and 'prompt_variant' keys
    """
    from ai_service import AIService

    # Create tool executor
    profile = get_bot_profile(bot.bot_type if bot else 'planner')
    tool_executor = profile.executor_class(user=user)

    # 通用状态恢复钩子
    if profile.restore_state:
        profile.restore_state(tool_executor, user, bot)

    # GEPA variant：按流量比例选择实验 variant
    from ai_assistant.services.gepa_variants import get_variant_for_request
    variant_name = 'baseline'
    variant_suffix = ''
    variant_sel = get_variant_for_request(bot)
    if variant_sel:
        variant_name, variant_overrides = variant_sel
        variant_suffix = variant_overrides.get('suffix', '')

    if stream and on_step:
        result = AIService.chat_with_assistant_agent(
            bot=bot,
            history_messages=history,
            user_message=message,
            tool_executor=tool_executor,
            student_context=student_context,
            memory_context=memory_context,
            on_step=on_step,
            on_message=on_message,
            adaptive_directives=adaptive_directives,
            variant_suffix=variant_suffix,
        )
    else:
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
):
    """
    同步版调度（用于 SSE 的 _sync_setup）。

    Returns:
        (messages, tools, tool_executor, profile) 元组
    """
    from ai_engine.tool_permissions import filter_tools

    profile = get_bot_profile(bot.bot_type if bot else 'planner')
    tool_executor = profile.executor_class(user=user)

    # 通用状态恢复钩子
    if profile.restore_state:
        profile.restore_state(tool_executor, user, bot)

    system_prompt = build_system_prompt(bot, user, student_context, memory_context, institution, adaptive_directives)

    # GEPA variant：按流量比例选择实验 variant，追加到 system_prompt
    from ai_assistant.services.gepa_variants import get_variant_for_request, apply_variant_prompt
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
    applicable = get_applicable_experiences(exp_context)
    if applicable:
        system_prompt = inject_experiences_into_prompt(system_prompt, applicable)
        apply_memory_experiences(user, [e for e in applicable if e.dimension == 'memory'])
        apply_tool_experiences([e for e in applicable if e.dimension == 'tool'])
        apply_workflow_experiences([e for e in applicable if e.dimension == 'workflow'])
        record_trigger(applicable)
        logger.debug("experience_applicator: injected %d experiences for user %s", len(applicable), user.id)

    messages = [{'role': 'system', 'content': system_prompt}]
    for msg in history:
        if msg['role'] in ('user', 'assistant') and msg['content']:
            messages.append(msg)
    messages.append({'role': 'user', 'content': message})

    tools = profile.tools_factory()
    bot_type = bot.bot_type if bot else 'planner'
    tools = filter_tools(bot_type, institution, tools)

    return messages, tools, tool_executor, profile, variant_name
