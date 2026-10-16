import json
import threading
import time

from ai_engine.service import AIEngine


class _StreamingResponse:
    def __init__(self, chunks):
        self._chunks = chunks

    def raise_for_status(self):
        return None

    def iter_lines(self, decode_unicode=True):
        for chunk in self._chunks:
            payload = {
                "choices": [{"delta": {"content": chunk}, "finish_reason": None}],
            }
            yield f"data: {json.dumps(payload, ensure_ascii=False)}"
        yield 'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}'
        yield "data: [DONE]"


def test_streaming_function_calls_markup_executes_tools_without_leaking(monkeypatch):
    first_round = (
        "我先获取你目前的学习数据，以判断从何处切入。\n"
        '\\<function_calls>\n'
        '\\<invoke name="get_learning_stats">\\</invoke>\n'
        '\\<invoke name="get_knowledge_mastery_map">\\</invoke>\n'
        '\\<invoke name="get_due_reviews">\\</invoke>\n'
        '\\</function_calls>'
    )
    responses = iter([
        _StreamingResponse([
            first_round[:24],
            first_round[24:31],
            first_round[31:87],
            first_round[87:],
        ]),
        _StreamingResponse(["已经获取完成。"]),
    ])

    monkeypatch.setattr(
        "ai_engine.service.get_model_for_task",
        lambda operation: {
            "api_key": "test-key",
            "base_url": "https://example.invalid/chat",
            "model": "test-model",
            "thinking": False,
        },
    )
    monkeypatch.setattr(
        "ai_engine.service._session.post",
        lambda *args, **kwargs: next(responses),
    )
    monkeypatch.setattr(
        "ai_engine.circuit_breaker.AICircuitBreaker.check",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        "ai_engine.circuit_breaker.AICircuitBreaker.record_success",
        lambda *args, **kwargs: None,
    )

    executed = []
    emitted = []

    def execute_tool(name, args):
        executed.append((name, args))
        return json.dumps({"ok": True}, ensure_ascii=False)

    result = AIEngine.call_ai_with_streaming_tools(
        messages=[{"role": "user", "content": "1"}],
        tools=[],
        tool_executor=execute_tool,
        on_step=emitted.append,
        max_tool_rounds=2,
    )

    assert result == {"content": "已经获取完成。"}
    assert [name for name, _ in executed] == [
        "get_learning_stats",
        "get_knowledge_mastery_map",
        "get_due_reviews",
    ]
    visible_text = "".join(
        event["delta"] for event in emitted if event.get("type") == "text_delta"
    )
    assert "<function_calls>" not in visible_text
    assert "<invoke" not in visible_text


def test_tool_timeout_returns_without_waiting_for_worker_shutdown():
    release = threading.Event()

    def blocked_tool(name, args):
        release.wait(timeout=0.5)
        return "late result"

    started = time.monotonic()
    try:
        result = AIEngine._run_tool_with_timeout(
            blocked_tool,
            "blocked_tool",
            {},
            timeout=0.01,
        )
    finally:
        release.set()
    elapsed = time.monotonic() - started

    assert json.loads(result)["error"] == "timeout"
    assert elapsed < 0.1
