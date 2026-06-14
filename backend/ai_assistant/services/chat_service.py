from typing import Dict, Sequence

from ai_engine.tools import get_assistant_tools, get_planner_tools, get_exam_generator_tools


class AssistantChatService:
    @classmethod
    def build_system_prompt(cls, bot, student_context: str = '') -> str:
        """从文件加载 system prompt，fallback 到 DB。"""
        if not bot:
            return '你是UniMind.ai的AI学术助教。'

        from ai_assistant.prompt_sync import load_system_prompt
        prompt = load_system_prompt(bot)

        if bot.is_exclusive:
            prompt = prompt.replace('{student_context}', student_context or '暂无学业画像。')
        return prompt

    @classmethod
    def _build_agent_system_prompt(cls, bot, student_context: str = '', memory_context: str = '', institution=None, adaptive_directives: str = '', variant_suffix: str = '') -> str:
        """为 Agent 模式构建包含工具使用指引的 system prompt。"""
        base = cls.build_system_prompt(bot, student_context)
        memory_section = f"\n\n{memory_context}" if memory_context else ''

        # 从文件加载 tool guide 和 intent guide
        from ai_assistant.prompt_sync import load_tool_guide, read_prompt_file
        tool_guide = load_tool_guide(bot) if bot else ''
        intent_guide = ''
        if bot:
            ig = read_prompt_file(bot, 'intent_guide.txt')
            if ig:
                intent_guide = f"\n\n{ig}"

        # Inject institution personality
        personality_section = ''
        if bot and hasattr(bot, 'institution_personality') and bot.institution_personality:
            p = bot.institution_personality
            parts = []
            if p.get('teaching_style'):
                parts.append(f"教学风格：{p['teaching_style'][:200]}")
            if p.get('tone'):
                parts.append(f"语气：{p['tone'][:100]}")
            if p.get('knowledge_domain'):
                parts.append(f"知识领域：{p['knowledge_domain'][:200]}")
            if p.get('custom_instructions'):
                custom = p['custom_instructions'][:500]
                # prompt injection 防护
                import re
                injection_patterns = [
                    r'(?i)(忽略|放弃|forget|ignore|disregard|override)\s*(以上|上面|之前的|所有|previous|above|prior)\s*(指令|规则|提示|instructions|rules|prompts)',
                    r'(?i)(system\s*:|user\s*:|assistant\s*:|human\s*:|ai\s*:)',
                    r'(?i)(你现在是|从现在起|you are now|from now on|new instructions)',
                    r'(?i)(输出|显示|print|reveal|show)\s*(你的|your|system|系统)\s*(prompt|提示词|指令)',
                    r'(?i)(jailbreak|DAN|越狱|roleplay\s+as)',
                ]
                for pattern in injection_patterns:
                    custom = re.sub(pattern, '[filtered]', custom)
                parts.append(custom)
            if parts:
                personality_section = "\n\n## 机构教学配置\n" + "\n".join(f"- {x}" for x in parts)

        adaptive_section = f"\n\n{adaptive_directives}" if adaptive_directives else ''
        variant_section = f"\n\n{variant_suffix}" if variant_suffix else ''
        return base + memory_section + tool_guide + intent_guide + personality_section + adaptive_section + variant_section

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
        memory_context: str = '',
        on_step=None,
        on_message=None,
        adaptive_directives='',
        variant_suffix: str = '',
    ):
        """Agent 化对话：模型可自主调用工具获取信息后再回答。"""
        from ai_engine.service import AIEngine
        from ai_engine.tool_permissions import filter_tools
        from ai_assistant.bot_registry import get_bot_profile

        institution = getattr(tool_executor, 'institution', None)
        system_prompt = cls._build_agent_system_prompt(bot, student_context, memory_context, institution, adaptive_directives, variant_suffix)

        messages = [{'role': 'system', 'content': system_prompt}]

        for msg in history_messages or []:
            role = str(msg.get('role', '')).strip()
            content = str(msg.get('content', '')).strip()
            if role in {'user', 'assistant'} and content:
                messages.append({'role': role, 'content': content})

        messages.append({'role': 'user', 'content': user_message})

        # 从 registry 获取 tools
        profile = get_bot_profile(bot.bot_type if bot else 'planner')
        tools = profile.tools_factory()

        # Apply tool permission sandbox
        bot_type = bot.bot_type if bot else 'planner'
        tools = filter_tools(bot_type, institution, tools)

        # 意图预筛选（仅启用 use_intent_router 的 bot）
        if profile.use_intent_router and user_message:
            from ai_engine.tool_router import route_tools
            tools = route_tools(user_message, tools, recent_messages=history_messages, bot_type=bot_type)

        # 设置工具白名单，防止 LLM 被注入后调用非预期工具
        tool_executor._allowed_tool_names = {t['function']['name'] for t in tools}

        # Force tool usage for agent bots
        # 意图路由后工具为空时，降级为 auto，让 LLM 自由回复文本
        # 全部用 auto 而非 required：prompt 规定边界比硬约束更灵活，
        # required 会导致任务完成后模型无法停止（如命题官无限循环出题）
        if tools and profile.force_tool_choice:
            forced_tool_choice = "auto"
        else:
            forced_tool_choice = "auto"

        if on_step:
            return AIEngine.call_ai_with_streaming_tools(
                messages=messages,
                tools=tools,
                tool_executor=tool_executor,
                on_step=on_step,
                on_message=on_message,
                tool_choice=forced_tool_choice,
                temperature=0.6,
                max_tokens=2500,
                operation=f'assistant.chat.{bot_type}',
                max_tool_rounds=8 if bot_type == 'exam_generator' else 12,
            )
        else:
            return AIEngine.call_ai_with_tools(
                messages=messages,
                tools=tools,
                tool_executor=tool_executor,
                tool_choice=forced_tool_choice,
                temperature=0.6,
                max_tokens=2500,
                operation=f'assistant.chat.{bot_type}',
                max_tool_rounds=8 if bot_type == 'exam_generator' else 12,
            )
