from typing import Dict, Sequence

from ai_engine.tools import get_assistant_tools, get_planner_tools, get_exam_generator_tools


class AssistantChatService:
    @classmethod
    def build_system_prompt(cls, bot, student_context: str = '') -> str:
        prompt = (bot.system_prompt or '你是UniMind.ai的AI学术助教。') if bot else '你是UniMind.ai的AI学术助教。'
        if bot and bot.is_exclusive:
            prompt = prompt.replace('{student_context}', student_context or '暂无学业画像。')
        return prompt

    @classmethod
    def _build_agent_system_prompt(cls, bot, student_context: str = '', memory_context: str = '', institution=None) -> str:
        """为 Agent 模式构建包含工具使用指引的 system prompt。"""
        base = cls.build_system_prompt(bot, student_context)
        memory_section = f"\n\n{memory_context}" if memory_context else ''
        if bot and bot.bot_type == 'planner':
            tool_guide = cls._build_planner_tool_guide()
        elif bot and bot.bot_type == 'exam_generator':
            tool_guide = cls._build_exam_generator_tool_guide()
        else:
            tool_guide = (
                "\n\n## 可用工具\n"
                "你可以调用以下工具来获取实时信息，提升回答质量：\n"
                "- `search_knowledge_tree`: 搜索知识点定义、公式、例题。当学生问概念、定理、公式时，先搜索再回答。\n"
                "- `get_user_weak_points`: 查看学生薄弱知识点。当学生问'我哪里弱''怎么复习'时使用。\n"
                "- `get_user_wrong_questions`: 查看学生最近的错题。当学生问'我错在哪''帮我分析'时使用。\n"
                "- `lookup_question`: 根据题目 ID 查询详情。当学生提到具体题号时使用。\n"
                "- `get_class_weak_points`: 获取班级最薄弱知识点（仅教师可用）。当教师问'班级哪里弱''学生整体情况'时使用。\n"
                "- `get_class_performance_summary`: 获取班级整体数据概览（仅教师可用）。当教师问'班级整体表现'时使用。\n\n"
                "使用原则：\n"
                "1. 需要具体数据（知识点内容、学生情况、题目详情）时，先调工具再回答，不要凭记忆编造。\n"
                "2. 简单问候、闲聊、通用学习建议不需要调工具。\n"
                "3. 工具返回的数据是 JSON，请将关键信息用中文自然表达。"
            )
        # Inject institution personality if configured
        personality_section = ''
        if bot and hasattr(bot, 'institution_personality') and bot.institution_personality:
            p = bot.institution_personality
            parts = []
            if p.get('teaching_style'):
                parts.append(f"教学风格：{p['teaching_style']}")
            if p.get('tone'):
                parts.append(f"语气：{p['tone']}")
            if p.get('knowledge_domain'):
                parts.append(f"知识领域：{p['knowledge_domain']}")
            if p.get('custom_instructions'):
                parts.append(p['custom_instructions'])
            if parts:
                personality_section = "\n\n## 机构教学配置\n" + "\n".join(f"- {x}" for x in parts)

        return base + memory_section + tool_guide + personality_section

    @classmethod
    def _build_exam_generator_tool_guide(cls) -> str:
        return (
            "\n\n## 可用工具（必须使用）\n"
            "你有以下工具可用，收到出题需求时**必须调用工具**，不能只回复文字：\n\n"
            "- `search_knowledge_points`: 搜索知识点获取 ID。出题前必须先调用此工具。\n"
            "- `generate_questions`: 根据知识点 ID 快速生成题目（同步约 10 秒）。搜索拿到 ID 后**必须立即调用**此工具。\n"
            "- `launch_arc_pipeline`: 启动 ARC 精修管线（异步 2-5 分钟）。教师要求高质量时使用。\n"
            "- `check_pipeline_status`: 查询 ARC 管线进度。\n"
            "- `save_questions_to_library`: 将题目存入题库。教师说\"入库\"\"保存\"\"存入题库\"时调用。\n\n"
            "工作流程（严格遵守）：\n"
            "1. 收到出题需求 → 调用 search_knowledge_points 获取知识点 ID\n"
            "2. 拿到知识点 ID → **立即**调用 generate_questions 生成题目\n"
            "3. 将工具返回的题目用 Markdown 格式呈现给教师\n"
            "4. 教师说\"入库/保存\" → 调用 save_questions_to_library\n\n"
            "口语化指令识别：\n"
            "- \"入库/存库/保存/存入题库\" → save_questions_to_library\n"
            "- \"ARC精修/精修/用ARC跑\" → launch_arc_pipeline\n"
            "- \"看看进度/跑完没\" → check_pipeline_status\n"
            "- \"再来一组/换XX出题\" → 重新 search + generate\n"
            "- \"难度改hard/加到10题\" → 用新参数重新 generate\n\n"
            "注意：这些指令直接执行，不要反问确认。搜索无结果时告知可用范围。"
        )

    @classmethod
    def _build_planner_tool_guide(cls) -> str:
        return (
            "\n\n## 可用工具\n"
            "你可以调用以下工具来获取实时信息和管理学习计划：\n\n"
            "**数据查询工具：**\n"
            "- `search_knowledge_tree`: 搜索知识点定义。\n"
            "- `get_user_weak_points`: 查看薄弱知识点。\n"
            "- `get_user_wrong_questions`: 查看错题列表。\n"
            "- `lookup_question`: 查询题目详情。\n"
            "- `get_learning_stats`: 获取学习统计概览（做题量、正确率、学习天数）。\n"
            "- `get_knowledge_mastery_map`: 获取知识点掌握度地图。\n"
            "- `get_due_reviews`: 获取今日待复习题目。\n"
            "- `get_exam_history`: 获取考试成绩历史。\n\n"
            "**计划管理工具：**\n"
            "- `save_study_plan`: 保存生成的学习计划到数据库。\n"
            "- `get_active_plan`: 查看当前进行中的计划。\n"
            "- `update_plan_task`: 更新计划中某个任务的状态。\n\n"
            "使用原则：\n"
            "1. 制定计划前，先用数据工具了解学生现状。\n"
            "2. 每次制定计划必须调用 save_study_plan 保存。\n"
            "3. 新用户无数据时，建议先做诊断测试。\n"
            "4. 简单问候不需要调工具。\n"
            "5. 工具返回的数据是 JSON，请将关键信息用中文自然表达。"
        )

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
    ):
        """Agent 化对话：模型可自主调用工具获取信息后再回答。"""
        from ai_engine.service import AIEngine
        from ai_engine.tool_permissions import filter_tools

        institution = getattr(tool_executor, 'institution', None)
        system_prompt = cls._build_agent_system_prompt(bot, student_context, memory_context, institution)

        messages = [{'role': 'system', 'content': system_prompt}]

        for msg in history_messages or []:
            role = str(msg.get('role', '')).strip()
            content = str(msg.get('content', '')).strip()
            if role in {'user', 'assistant'} and content:
                messages.append({'role': role, 'content': content})

        messages.append({'role': 'user', 'content': user_message})

        if bot and bot.bot_type == 'planner':
            tools = get_planner_tools()
        elif bot and bot.bot_type == 'exam_generator':
            tools = get_exam_generator_tools()
        else:
            tools = get_assistant_tools()

        # Apply tool permission sandbox
        bot_type = bot.bot_type if bot else 'assistant'
        tools = filter_tools(bot_type, institution, tools)

        if on_step:
            return AIEngine.call_ai_with_streaming_tools(
                messages=messages,
                tools=tools,
                tool_executor=tool_executor,
                on_step=on_step,
                tool_choice="auto",
                temperature=0.6,
                max_tokens=2500,
                operation='assistant.chat',
                max_tool_rounds=5,
            )
        else:
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
