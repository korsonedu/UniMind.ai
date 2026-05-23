from typing import Dict, Sequence

from ai_engine.tools import get_assistant_tools


class AssistantChatService:
    @classmethod
    def build_system_prompt(cls, bot, student_context: str = '') -> str:
        prompt = (bot.system_prompt or '你是UniMind.ai的AI学术助教。') if bot else '你是UniMind.ai的AI学术助教。'
        if bot and bot.is_exclusive:
            prompt = prompt.replace('{student_context}', student_context or '暂无学业画像。')
        return prompt

    @classmethod
    def _build_agent_system_prompt(cls, bot, student_context: str = '') -> str:
        """为 Agent 模式构建包含工具使用指引的 system prompt。"""
        base = cls.build_system_prompt(bot, student_context)
        tool_guide = (
            "\n\n## 可用工具\n"
            "你可以调用以下工具来获取实时信息，提升回答质量：\n"
            "- `search_knowledge_tree`: 搜索知识点定义、公式、例题。当学生问概念、定理、公式时，先搜索再回答。\n"
            "- `get_user_weak_points`: 查看学生薄弱知识点。当学生问'我哪里弱''怎么复习'时使用。\n"
            "- `get_user_wrong_questions`: 查看学生最近的错题。当学生问'我错在哪''帮我分析'时使用。\n"
            "- `lookup_question`: 根据题目 ID 查询详情。当学生提到具体题号时使用。\n\n"
            "使用原则：\n"
            "1. 需要具体数据（知识点内容、学生情况、题目详情）时，先调工具再回答，不要凭记忆编造。\n"
            "2. 简单问候、闲聊、通用学习建议不需要调工具。\n"
            "3. 工具返回的数据是 JSON，请将关键信息用中文自然表达。"
        )
        return base + tool_guide

    @classmethod
    def chat_with_assistant(
        cls,
        ai,
        bot,
        history_messages: Sequence[Dict[str, str]],
        user_message: str,
        student_context: str = '',
    ):
        system_prompt = cls.build_system_prompt(bot, student_context)

        messages = [{'role': 'system', 'content': system_prompt}]

        for msg in history_messages or []:
            role = str(msg.get('role', '')).strip()
            content = str(msg.get('content', '')).strip()
            if role in {'user', 'assistant'} and content:
                messages.append({'role': role, 'content': content})

        messages.append({'role': 'user', 'content': user_message})

        return ai.call_ai(
            messages,
            temperature=0.6,
            max_tokens=2500,
            operation='assistant.chat',
        )

    @classmethod
    def chat_with_assistant_agent(
        cls,
        bot,
        history_messages: Sequence[Dict[str, str]],
        user_message: str,
        tool_executor,
        student_context: str = '',
    ):
        """Agent 化对话：模型可自主调用工具获取信息后再回答。"""
        from ai_engine.service import AIEngine

        system_prompt = cls._build_agent_system_prompt(bot, student_context)

        messages = [{'role': 'system', 'content': system_prompt}]

        for msg in history_messages or []:
            role = str(msg.get('role', '')).strip()
            content = str(msg.get('content', '')).strip()
            if role in {'user', 'assistant'} and content:
                messages.append({'role': role, 'content': content})

        messages.append({'role': 'user', 'content': user_message})

        tools = get_assistant_tools()
        return AIEngine.call_ai_with_tools(
            messages=messages,
            tools=tools,
            tool_executor=tool_executor,
            tool_choice="auto",
            temperature=0.6,
            max_tokens=2500,
            operation='assistant.chat',
            max_tool_rounds=5,
        )
