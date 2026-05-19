from typing import Dict, Sequence


class AssistantChatService:
    @classmethod
    def build_system_prompt(cls, bot, student_context: str = '') -> str:
        prompt = (bot.system_prompt or '你是UniMind.ai的AI学术助教。') if bot else '你是UniMind.ai的AI学术助教。'
        if bot and bot.is_exclusive:
            prompt = prompt.replace('{student_context}', student_context or '暂无学业画像。')
        return prompt

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
