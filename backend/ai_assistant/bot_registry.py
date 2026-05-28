"""
Bot 注册表：bot_type → (ToolExecutor, tools_factory, prompt_dir, config)。

新增 bot 只需：
1. 写 prompt 文件到 prompts/ai_assistant/bots/{name}/
2. 在 BOT_REGISTRY 加一行
3. （可选）写 ToolExecutor 子类
"""
from dataclasses import dataclass
from typing import Callable


@dataclass
class BotProfile:
    name: str                          # 显示名称
    bot_type: str                      # Bot model 的 bot_type 值
    executor_class: type               # ToolExecutor 子类
    tools_factory: Callable            # get_planner_tools, etc.
    prompt_dir: str                    # prompts 文件目录名
    is_exclusive: bool = False         # 是否注入学生学术数据
    force_tool_choice: bool = False    # 是否强制 tool_choice="required"
    use_intent_router: bool = False    # 是否启用意图预筛选路由


def _get_executor_class(bot_type: str):
    """延迟导入 ToolExecutor 子类，避免循环引用。"""
    if bot_type == 'planner':
        from ai_assistant.services.tool_executor import PlannerToolExecutor
        return PlannerToolExecutor
    elif bot_type == 'exam_generator':
        from ai_assistant.services.exam_generator_tool_executor import ExamGeneratorToolExecutor
        return ExamGeneratorToolExecutor
    else:
        from ai_assistant.services.tool_executor import AssistantToolExecutor
        return AssistantToolExecutor


def _get_tools_factory(bot_type: str):
    """延迟导入 tools factory。"""
    if bot_type == 'planner':
        from ai_engine.tools import get_planner_tools
        return get_planner_tools
    elif bot_type == 'exam_generator':
        from ai_engine.tools import get_exam_generator_tools
        return get_exam_generator_tools
    else:
        from ai_engine.tools import get_assistant_tools
        return get_assistant_tools


BOT_REGISTRY: dict[str, BotProfile] = {
    'planner': BotProfile(
        name='小宇',
        bot_type='planner',
        executor_class=None,  # 延迟加载
        tools_factory=None,
        prompt_dir='xiaoyu',
        is_exclusive=True,
        force_tool_choice=True,
        use_intent_router=True,
    ),
    'exam_generator': BotProfile(
        name='命题官',
        bot_type='exam_generator',
        executor_class=None,
        tools_factory=None,
        prompt_dir='exam_generator',
        is_exclusive=False,
        force_tool_choice=True,
        use_intent_router=True,
    ),
    'assistant': BotProfile(
        name='AI 助教',
        bot_type='assistant',
        executor_class=None,
        tools_factory=None,
        prompt_dir='assistant',
        is_exclusive=False,
        force_tool_choice=False,
    ),
}


def get_bot_profile(bot_type: str) -> BotProfile:
    """获取 bot 配置，未知类型 fallback 到 assistant。"""
    profile = BOT_REGISTRY.get(bot_type, BOT_REGISTRY['assistant'])
    # 延迟加载 executor_class 和 tools_factory
    if profile.executor_class is None:
        profile.executor_class = _get_executor_class(profile.bot_type)
    if profile.tools_factory is None:
        profile.tools_factory = _get_tools_factory(profile.bot_type)
    return profile
