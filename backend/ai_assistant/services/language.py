"""Resolve a turn's interface language from its saved, authorized user message."""
from pathlib import Path

from django.conf import settings


def request_language(request):
    selected = getattr(request, 'ui_language', None)
    if selected in {'en', 'zh-CN'}:
        return selected
    language = request.headers.get('Accept-Language', '').split(',')[0].split(';')[0].strip().lower()
    return 'en' if language.startswith('en') else 'zh-CN'


def message_language(message):
    return 'en' if (message.metadata or {}).get('ui_language') == 'en' else 'zh-CN'


def language_instruction(user, chat_context):
    if not chat_context:
        return ''
    from ai_assistant.models import AIChatMessage
    message = AIChatMessage.objects.filter(
        user=user, pk=chat_context.get('message_id'), role='user',
        conversation_id=chat_context.get('conversation_id'), bot_id=chat_context.get('bot_id'),
    ).first()
    if not message:
        return ''
    language = 'English' if message_language(message) == 'en' else 'Simplified Chinese'
    prompt = (Path(settings.BASE_DIR) / 'prompts/ai_assistant/language_preferences.txt').read_text()
    return '\n\n' + prompt.replace('{language}', language)
