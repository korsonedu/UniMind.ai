"""
统一的 bot 对话调度。

3 个入口（polling/SSE/WS）共用此模块，消除重复的 bot_type if/elif 逻辑。
"""
import logging
from typing import Callable, Optional

from ai_assistant.bot_registry import get_bot_profile

logger = logging.getLogger(__name__)


def resolve_tool_choice(profile):
    """根据 bot profile 决定 tool_choice 值。"""
    if profile.force_tool_choice:
        return "required"
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
        dict with 'result' and 'tool_executor' keys
    """
    from ai_service import AIService

    # Create tool executor
    profile = get_bot_profile(bot.bot_type if bot else 'planner')
    tool_executor = profile.executor_class(user=user)

    # 通用状态恢复钩子
    if profile.restore_state:
        profile.restore_state(tool_executor, user, bot)

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
        )

    return {'result': result, 'tool_executor': tool_executor}


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
    messages = [{'role': 'system', 'content': system_prompt}]
    for msg in history:
        if msg['role'] in ('user', 'assistant') and msg['content']:
            messages.append(msg)
    messages.append({'role': 'user', 'content': message})

    tools = profile.tools_factory()
    bot_type = bot.bot_type if bot else 'planner'
    tools = filter_tools(bot_type, institution, tools)

    return messages, tools, tool_executor, profile
