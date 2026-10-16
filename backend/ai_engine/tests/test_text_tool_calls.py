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


class _StreamingToolResponse:
    def __init__(self, tool_calls):
        self._tool_calls = tool_calls

    def raise_for_status(self):
        return None

    def iter_lines(self, decode_unicode=True):
        payload = {
            "choices": [{
                "delta": {"tool_calls": self._tool_calls},
                "finish_reason": "tool_calls",
            }],
        }
        yield f"data: {json.dumps(payload, ensure_ascii=False)}"
        yield "data: [DONE]"


def _tool_definition(name="lookup"):
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": f"Run {name}",
            "parameters": {
                "type": "object",
                "properties": {"subject": {"type": "string"}},
                "required": ["subject"],
                "additionalProperties": False,
            },
        },
    }


def _tool_call_chunk(name, arguments, call_id):
    return {
        "index": 0,
        "id": call_id,
        "type": "function",
        "function": {"name": name, "arguments": json.dumps(arguments, ensure_ascii=False)},
    }


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
        tools=[
            {
                "type": "function",
                "function": {
                    "name": name,
                    "description": name,
                    "parameters": {"type": "object", "properties": {}},
                },
            }
            for name in (
                "get_learning_stats",
                "get_knowledge_mastery_map",
                "get_due_reviews",
            )
        ],
        tool_executor=execute_tool,
        on_step=emitted.append,
        max_tool_rounds=2,
    )

    assert result["content"] == "已经获取完成。"
    assert result["run_id"].startswith("run_")
    assert sorted(name for name, _ in executed) == sorted([
        "get_learning_stats",
        "get_knowledge_mastery_map",
        "get_due_reviews",
    ])
    visible_text = "".join(
        event["delta"] for event in emitted if event.get("type") == "text_delta"
    )
    assert "<function_calls>" not in visible_text
    assert "<invoke" not in visible_text


def test_streaming_rounds_share_run_id_and_keep_call_ids_unique(monkeypatch):
    responses = iter([
        _StreamingToolResponse([_tool_call_chunk("lookup", {"subject": "数学"}, "reused")]),
        _StreamingToolResponse([_tool_call_chunk("lookup", {"subject": "物理"}, "reused")]),
        _StreamingResponse(["分析完成。"]),
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
    monkeypatch.setattr("ai_engine.service._session.post", lambda *args, **kwargs: next(responses))
    monkeypatch.setattr("ai_engine.circuit_breaker.AICircuitBreaker.check", lambda *args, **kwargs: None)
    monkeypatch.setattr("ai_engine.circuit_breaker.AICircuitBreaker.record_success", lambda *args, **kwargs: None)

    emitted = []
    result = AIEngine.call_ai_with_streaming_tools(
        messages=[{"role": "user", "content": "分析两个学科"}],
        tools=[_tool_definition()],
        tool_executor=lambda name, arguments: json.dumps({"subject": arguments["subject"]}),
        on_step=emitted.append,
        max_tool_rounds=3,
    )

    step_events = [event for event in emitted if event.get("type") == "step"]
    terminal_events = [event for event in step_events if event["status"] == "succeeded"]
    assert result["content"] == "分析完成。"
    assert {event["run_id"] for event in step_events} == {result["run_id"]}
    assert [event["call_id"] for event in terminal_events][0] == "reused"
    assert [event["call_id"] for event in terminal_events][1].startswith("call_")
    assert len({event["call_id"] for event in terminal_events}) == 2
    assert all(event["status"] != "batch_start" for event in step_events)


def test_invalid_arguments_are_returned_to_model_before_retry(monkeypatch):
    responses = iter([
        _StreamingToolResponse([_tool_call_chunk("lookup", {}, "invalid-call")]),
        _StreamingToolResponse([_tool_call_chunk("lookup", {"subject": "数学"}, "retry-call")]),
        _StreamingResponse(["已修正。"]),
    ])
    request_bodies = []

    def post(*args, **kwargs):
        request_bodies.append(kwargs["json"])
        return next(responses)

    monkeypatch.setattr(
        "ai_engine.service.get_model_for_task",
        lambda operation: {
            "api_key": "test-key",
            "base_url": "https://example.invalid/chat",
            "model": "test-model",
            "thinking": False,
        },
    )
    monkeypatch.setattr("ai_engine.service._session.post", post)
    monkeypatch.setattr("ai_engine.circuit_breaker.AICircuitBreaker.check", lambda *args, **kwargs: None)
    monkeypatch.setattr("ai_engine.circuit_breaker.AICircuitBreaker.record_success", lambda *args, **kwargs: None)

    executed = []
    emitted = []

    def execute(name, arguments):
        executed.append((name, arguments))
        return json.dumps({"ok": True})

    result = AIEngine.call_ai_with_streaming_tools(
        messages=[{"role": "user", "content": "查询"}],
        tools=[_tool_definition()],
        tool_executor=execute,
        on_step=emitted.append,
        max_tool_rounds=3,
    )

    second_request_tool_messages = [
        message for message in request_bodies[1]["messages"] if message["role"] == "tool"
    ]
    assert json.loads(second_request_tool_messages[-1]["content"])["error"]["code"] == "invalid_arguments"
    assert executed == [("lookup", {"subject": "数学"})]
    retry_queued = next(
        event for event in emitted
        if event.get("call_id") == "retry-call" and event.get("status") == "queued"
    )
    assert retry_queued["retry_of"] == "invalid-call"
    assert result["content"] == "已修正。"


def test_reply_visual_in_parallel_batch_stops_follow_up_tool_calls(monkeypatch):
    visual_definition = {
        "type": "function",
        "function": {
            "name": "render_visual",
            "description": "Render a visual",
            "parameters": {
                "type": "object",
                "properties": {"kind": {"type": "string"}},
                "required": ["kind"],
                "additionalProperties": False,
            },
        },
    }
    responses = iter([
        _StreamingToolResponse([
            {**_tool_call_chunk("render_visual", {"kind": "reply"}, "reply-call"), "index": 0},
            {**_tool_call_chunk("render_visual", {"kind": "data"}, "data-call"), "index": 1},
        ]),
        _StreamingResponse(["请点击上方卡片确认。"]),
    ])
    request_bodies = []

    def post(*args, **kwargs):
        request_bodies.append(kwargs["json"])
        return next(responses)

    class VisualExecutor:
        def __init__(self):
            self.pending_visuals = []

        def __call__(self, name, arguments):
            if arguments["kind"] == "reply":
                time.sleep(0.01)
                visual = {
                    "type": "action_cards",
                    "payload": {"cards": [{"action": {"type": "reply"}}]},
                }
            else:
                time.sleep(0.02)
                visual = {"type": "data_card", "payload": {"value": 1}}
            self.pending_visuals.append(visual)
            return json.dumps({"status": "ok", "visual": visual})

    monkeypatch.setattr(
        "ai_engine.service.get_model_for_task",
        lambda operation: {
            "api_key": "test-key",
            "base_url": "https://example.invalid/chat",
            "model": "test-model",
            "thinking": False,
        },
    )
    monkeypatch.setattr("ai_engine.service._session.post", post)
    monkeypatch.setattr("ai_engine.circuit_breaker.AICircuitBreaker.check", lambda *args, **kwargs: None)
    monkeypatch.setattr("ai_engine.circuit_breaker.AICircuitBreaker.record_success", lambda *args, **kwargs: None)

    result = AIEngine.call_ai_with_streaming_tools(
        messages=[{"role": "user", "content": "执行需要确认的操作"}],
        tools=[visual_definition],
        tool_executor=VisualExecutor(),
        max_tool_rounds=2,
    )

    assert result["content"] == "请点击上方卡片确认。"
    assert request_bodies[1].get("tool_choice") == "none"
    assert "tools" not in request_bodies[1]
    assert any(
        message.get("role") == "system" and "点击卡片确认" in message.get("content", "")
        for message in request_bodies[1]["messages"]
    )


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
