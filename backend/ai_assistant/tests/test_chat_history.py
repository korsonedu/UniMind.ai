import uuid
from types import SimpleNamespace

import pytest

from ai_assistant.models import AIChatMessage, Bot
from ai_assistant.views import process_ai_chat


@pytest.mark.django_db
def test_process_chat_keeps_earlier_repeated_message(monkeypatch, user):
    bot = Bot.objects.create(name="小宇", system_prompt="test", bot_type="planner")
    conversation_id = uuid.uuid4()
    AIChatMessage.objects.create(
        user=user,
        bot=bot,
        conversation_id=conversation_id,
        role="user",
        content="1",
    )
    AIChatMessage.objects.create(
        user=user,
        bot=bot,
        conversation_id=conversation_id,
        role="assistant",
        content="上一次回复",
    )
    current = AIChatMessage.objects.create(
        user=user,
        bot=bot,
        conversation_id=conversation_id,
        role="user",
        content="1",
    )
    pending = AIChatMessage.objects.create(
        user=user,
        bot=bot,
        conversation_id=conversation_id,
        role="assistant",
        content="[Thinking...]",
    )

    captured = {}

    def dispatch_bot_chat(**kwargs):
        captured["history"] = kwargs["history"]
        return {
            "result": {
                "choices": [{
                    "message": {"content": "本次回复"},
                    "finish_reason": "stop",
                }],
            },
            "tool_executor": SimpleNamespace(
                tool_call_log=[],
                tool_output_log=[],
                pending_visuals=[],
            ),
            "prompt_variant": "baseline",
        }

    monkeypatch.setattr(
        "ai_assistant.views.add_project_context",
        lambda user, conversation_id, history: history,
    )
    monkeypatch.setattr(
        "ai_assistant.services.memory_service.build_memory_context",
        lambda *args, **kwargs: ("", ""),
    )
    monkeypatch.setattr(
        "ai_assistant.services.chat_dispatch.dispatch_bot_chat",
        dispatch_bot_chat,
    )
    monkeypatch.setattr(
        "ai_assistant.services.memory_service.extract_memories_async",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        "ai_assistant.services.memory_service.extract_memories_with_mem0",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        "ai_assistant.services.trajectory_recorder.record_trajectory",
        lambda **kwargs: None,
    )

    process_ai_chat(
        user,
        bot,
        "1",
        pending.id,
        conversation_id=conversation_id,
        current_user_message_id=current.id,
    )

    assert captured["history"] == [
        {"role": "user", "content": "1"},
        {"role": "assistant", "content": "上一次回复"},
    ]
