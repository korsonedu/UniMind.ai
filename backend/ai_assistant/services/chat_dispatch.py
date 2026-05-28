"""
统一的 bot 对话调度。

3 个入口（polling/SSE/WS）共用此模块，消除重复的 bot_type if/elif 逻辑。
"""
import logging
from typing import Callable, Optional

from ai_assistant.bot_registry import get_bot_profile

logger = logging.getLogger(__name__)


def create_tool_executor(bot, user):
    """根据 bot_type 创建 ToolExecutor 实例。"""
    profile = get_bot_profile(bot.bot_type if bot else 'assistant')
    return profile.executor_class(user=user)


def create_tools(bot, user, institution=None):
    """根据 bot_type 创建 tools 列表。"""
    from ai_engine.tool_permissions import filter_tools
    profile = get_bot_profile(bot.bot_type if bot else 'assistant')
    tools = profile.tools_factory()
    bot_type = bot.bot_type if bot else 'assistant'
    return filter_tools(bot_type, institution, tools)


def build_system_prompt(bot, user, student_context='', memory_context='', institution=None, adaptive_directives=''):
    """构建完整的 system prompt。"""
    from ai_assistant.services.chat_service import AssistantChatService
    return AssistantChatService._build_agent_system_prompt(
        bot, student_context, memory_context, institution, adaptive_directives
    )


def _restore_exam_cache(tool_executor, user, bot):
    """从最近一条助手消息的 metadata 中恢复已生成的题目缓存。"""
    from ai_assistant.models import AIChatMessage
    try:
        last_with_questions = AIChatMessage.objects.filter(
            user=user, bot=bot, role='assistant',
        ).exclude(metadata={}).order_by('-timestamp').first()
        if last_with_questions:
            cached = last_with_questions.metadata.get('generated_questions')
            if cached:
                tool_executor._last_generated = cached
    except Exception:
        pass


def dispatch_bot_chat(
    bot,
    user,
    message: str,
    history: list,
    institution=None,
    *,
    stream: bool = False,
    on_step: Optional[Callable] = None,
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
    tool_executor = create_tool_executor(bot, user)

    # ExamGenerator cache recovery
    if bot and bot.bot_type == 'exam_generator':
        _restore_exam_cache(tool_executor, user, bot)

    if stream and on_step:
        result = AIService.chat_with_assistant_agent(
            bot=bot,
            history_messages=history,
            user_message=message,
            tool_executor=tool_executor,
            student_context=student_context,
            memory_context=memory_context,
            on_step=on_step,
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

    profile = get_bot_profile(bot.bot_type if bot else 'assistant')
    tool_executor = profile.executor_class(user=user)

    if bot and bot.bot_type == 'exam_generator':
        _restore_exam_cache(tool_executor, user, bot)

    system_prompt = build_system_prompt(bot, user, student_context, memory_context, institution, adaptive_directives)
    messages = [{'role': 'system', 'content': system_prompt}]
    for msg in history:
        if msg['role'] in ('user', 'assistant') and msg['content']:
            messages.append(msg)
    messages.append({'role': 'user', 'content': message})

    tools = profile.tools_factory()
    bot_type = bot.bot_type if bot else 'assistant'
    tools = filter_tools(bot_type, institution, tools)

    return messages, tools, tool_executor, profile
