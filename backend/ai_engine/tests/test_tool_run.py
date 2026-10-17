import json
import time

from ai_engine.tool_run import ToolRunCoordinator


def _tool_definition(name="lookup", parameters=None):
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": f"Run {name}",
            "parameters": parameters or {
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
        },
    }


def _tool_call(name="lookup", arguments=None, call_id="upstream-call"):
    raw_arguments = arguments if isinstance(arguments, str) else json.dumps(arguments or {})
    return {
        "id": call_id,
        "type": "function",
        "function": {"name": name, "arguments": raw_arguments},
    }


class RecordingExecutor:
    def __init__(self, permitted_definitions):
        self._permitted_tool_definitions = {
            item["function"]["name"]: item for item in permitted_definitions
        }
        self._permitted_tool_names = set(self._permitted_tool_definitions)
        self.calls = []

    def __call__(self, name, arguments):
        self.calls.append((name, arguments))
        return json.dumps({"ok": True}, ensure_ascii=False)


def test_normalizes_legacy_handler_progress_into_current_tool_run():
    definition = _tool_definition("quick_generate")
    events = []

    class ProgressExecutor(RecordingExecutor):
        def __init__(self, permitted_definitions):
            super().__init__(permitted_definitions)
            self.on_step = events.append

        def __call__(self, name, arguments):
            self.on_step({
                "type": "step",
                "call_id": "legacy-call",
                "step": 0,
                "status": "calling",
                "name": name,
                "label": "正在生成第 1/2 批",
                "questions": [{"id": 1}],
            })
            return json.dumps({"ok": True})

    coordinator = ToolRunCoordinator(
        ProgressExecutor([definition]),
        [definition],
        on_step=events.append,
        run_id="run-progress",
    )

    coordinator.execute_batch(
        [_tool_call("quick_generate", call_id="current-call")],
        round_number=2,
    )

    progress = [event for event in events if event.get("questions")]
    assert len(progress) == 1
    assert progress[0] == {
        "type": "step",
        "run_id": "run-progress",
        "call_id": "current-call",
        "round": 2,
        "name": "quick_generate",
        "label": "正在生成第 1/2 批",
        "status": "running",
        "retry_of": None,
        "questions": [{"id": 1}],
    }


def test_normalizes_missing_duplicate_and_text_protocol_call_ids():
    definition = _tool_definition()
    executor = RecordingExecutor([definition])
    coordinator = ToolRunCoordinator(executor, [definition], read_only_tools={"lookup"})

    outcomes = coordinator.execute_batch(
        [
            _tool_call(call_id=""),
            _tool_call(call_id="shared"),
            _tool_call(call_id="shared"),
            _tool_call(call_id="dsml_generated"),
        ],
        round_number=1,
    )

    call_ids = [outcome.call.call_id for outcome in outcomes]
    assert call_ids[1] == "shared"
    assert all(call_ids[index].startswith("call_") for index in (0, 2, 3))
    assert len(set(call_ids)) == 4
    assert [outcome.call.tool_call["id"] for outcome in outcomes] == call_ids


def test_execution_evidence_tracks_only_current_request_confirmed_artifacts():
    definitions = [_tool_definition("render_visual"), _tool_definition("save")]

    class ArtifactExecutor(RecordingExecutor):
        pending_visuals = [{"type": "action_cards", "payload": {"cards": []}}]

        def __call__(self, name, arguments):
            if name == "save":
                return json.dumps({"error": "database rejected write"})
            return json.dumps({"status": "ok", "visual": {
                "type": "action_cards", "payload": {"cards": [{"action": {"type": "reply"}}]},
            }})

    coordinator = ToolRunCoordinator(ArtifactExecutor(definitions), definitions, run_id="run-evidence")
    assert coordinator.execution_evidence() == {
        "run_id": "run-evidence", "calls": [], "visuals": [], "waiting_for_user": False,
    }

    coordinator.execute_batch([_tool_call("save", call_id="failed-save")], round_number=1)
    failed = coordinator.execution_evidence()
    assert failed["calls"] == [{
        "call_id": "failed-save", "name": "save", "status": "failed", "error_code": "execution_error",
    }]
    assert failed["visuals"] == []

    coordinator.execute_batch([_tool_call("render_visual", call_id="choice")], round_number=2)
    generated = coordinator.execution_evidence()
    assert generated["calls"][-1] == {"call_id": "choice", "name": "render_visual", "status": "succeeded"}
    assert generated["visuals"] == [{"call_id": "choice", "type": "action_cards"}]
    assert generated["waiting_for_user"] is True

    another_request = ToolRunCoordinator(ArtifactExecutor(definitions), definitions)
    assert another_request.execution_evidence()["visuals"] == []


def test_visual_events_do_not_reuse_cached_artifacts_from_another_call():
    definition = _tool_definition("render_visual")
    executor = RecordingExecutor([definition])
    executor.pending_visuals = [{"type": "action_cards", "payload": {"cards": []}}]
    events = []
    coordinator = ToolRunCoordinator(executor, [definition], on_step=events.append)

    coordinator.execute_batch([_tool_call("render_visual")], round_number=1)

    assert "visual" not in events[-1]
    assert coordinator.execution_evidence()["visuals"] == []


def test_rejects_invalid_arguments_before_executor_runs():
    definition = _tool_definition(
        parameters={
            "type": "object",
            "properties": {
                "subject": {"type": "string"},
                "limit": {"type": "integer"},
                "scores": {"type": "array", "items": {"type": "number"}},
                "active": {"type": "boolean"},
            },
            "required": ["subject", "limit"],
            "additionalProperties": False,
        }
    )
    invalid_arguments = [
        "[]",
        {"limit": 2},
        {"subject": "数学", "limit": True},
        {"subject": "数学", "limit": 2, "scores": [1, "bad"]},
        {"subject": "数学", "limit": 2, "active": 1},
        {"subject": "数学", "limit": 2, "extra": "blocked"},
    ]
    executor = RecordingExecutor([definition])
    coordinator = ToolRunCoordinator(executor, [definition])

    outcomes = coordinator.execute_batch(
        [_tool_call(arguments=arguments, call_id=f"invalid-{index}") for index, arguments in enumerate(invalid_arguments)],
        round_number=1,
    )

    assert executor.calls == []
    assert [outcome.error["code"] for outcome in outcomes] == ["invalid_arguments"] * 6
    assert all(json.loads(outcome.result)["error"]["code"] == "invalid_arguments" for outcome in outcomes)


def test_distinguishes_unknown_tool_from_permission_denial():
    routed_definition = _tool_definition("routed")
    permitted_definition = _tool_definition("permitted")
    executor = RecordingExecutor([routed_definition])
    coordinator = ToolRunCoordinator(
        executor,
        [routed_definition, permitted_definition],
    )

    outcomes = coordinator.execute_batch(
        [
            _tool_call("missing", call_id="missing-call"),
            _tool_call("permitted", call_id="denied-call"),
        ],
        round_number=1,
    )

    assert executor.calls == []
    assert [outcome.error["code"] for outcome in outcomes] == [
        "unknown_tool",
        "permission_denied",
    ]


def test_prefers_executor_permission_schema_over_routed_definitions():
    strict_definition = _tool_definition(
        "lookup",
        {
            "type": "object",
            "properties": {"subject": {"type": "string"}},
            "required": ["subject"],
            "additionalProperties": False,
        },
    )
    loose_routed_definition = _tool_definition("lookup")
    executor = RecordingExecutor([strict_definition])
    coordinator = ToolRunCoordinator(executor, [loose_routed_definition])

    outcome = coordinator.execute_batch(
        [_tool_call("lookup", arguments={}, call_id="schema-call")],
        round_number=1,
    )[0]

    assert outcome.error["code"] == "invalid_arguments"
    assert executor.calls == []


def test_emits_monotonic_lifecycle_and_fails_invalid_call_without_running_it():
    definition = _tool_definition(
        parameters={
            "type": "object",
            "properties": {"subject": {"type": "string"}},
            "required": ["subject"],
            "additionalProperties": False,
        }
    )
    executor = RecordingExecutor([definition])
    events = []
    coordinator = ToolRunCoordinator(
        executor,
        [definition],
        on_step=events.append,
        read_only_tools={"lookup"},
        run_id="run-test",
    )

    coordinator.execute_batch(
        [
            _tool_call(arguments={"subject": "数学"}, call_id="valid-call"),
            _tool_call(arguments={}, call_id="invalid-call"),
        ],
        round_number=3,
    )

    assert [(event["call_id"], event["status"]) for event in events] == [
        ("valid-call", "queued"),
        ("invalid-call", "queued"),
        ("invalid-call", "failed"),
        ("valid-call", "running"),
        ("valid-call", "succeeded"),
    ]
    assert all(event["run_id"] == "run-test" for event in events)
    assert all(event["round"] == 3 for event in events)
    assert events[2]["error"]["code"] == "invalid_arguments"
    assert executor.calls == [("lookup", {"subject": "数学"})]


def test_executes_read_only_batch_concurrently_but_returns_input_order():
    definitions = [_tool_definition("slow"), _tool_definition("fast")]

    class TimedExecutor(RecordingExecutor):
        def __call__(self, name, arguments):
            time.sleep(0.12 if name == "slow" else 0.02)
            return json.dumps({"name": name})

    events = []
    coordinator = ToolRunCoordinator(
        TimedExecutor(definitions),
        definitions,
        on_step=events.append,
        read_only_tools={"slow", "fast"},
        max_workers=2,
    )

    started = time.monotonic()
    outcomes = coordinator.execute_batch(
        [_tool_call("slow", call_id="slow-call"), _tool_call("fast", call_id="fast-call")],
        round_number=1,
    )
    elapsed = time.monotonic() - started

    assert elapsed < 0.20
    assert [outcome.call.name for outcome in outcomes] == ["slow", "fast"]
    succeeded_names = [event["name"] for event in events if event["status"] == "succeeded"]
    assert succeeded_names == ["fast", "slow"]


def test_executes_entire_mixed_batch_serially():
    definitions = [_tool_definition("read"), _tool_definition("write")]

    class OrderedExecutor(RecordingExecutor):
        def __init__(self, permitted_definitions):
            super().__init__(permitted_definitions)
            self.sequence = []

        def __call__(self, name, arguments):
            self.sequence.append(f"start:{name}")
            time.sleep(0.01)
            self.sequence.append(f"end:{name}")
            return json.dumps({"ok": True})

    executor = OrderedExecutor(definitions)
    coordinator = ToolRunCoordinator(
        executor,
        definitions,
        read_only_tools={"read"},
        max_workers=2,
    )

    coordinator.execute_batch(
        [_tool_call("read", call_id="read-call"), _tool_call("write", call_id="write-call")],
        round_number=1,
    )

    assert executor.sequence == [
        "start:read",
        "end:read",
        "start:write",
        "end:write",
    ]


def test_classifies_raised_returned_and_timeout_errors(monkeypatch):
    definitions = [
        _tool_definition("raised"),
        _tool_definition("returned"),
        _tool_definition("blocked"),
    ]

    class ErrorExecutor(RecordingExecutor):
        def __call__(self, name, arguments):
            if name == "raised":
                raise RuntimeError("boom")
            if name == "returned":
                return json.dumps({"error": "bad result"})
            time.sleep(0.05)
            return json.dumps({"ok": True})

    monkeypatch.setattr("ai_engine.tool_run.TOOL_TIMEOUT_SECONDS", 0.005)
    coordinator = ToolRunCoordinator(ErrorExecutor(definitions), definitions)

    outcomes = coordinator.execute_batch(
        [
            _tool_call("raised", call_id="raised-call"),
            _tool_call("returned", call_id="returned-call"),
            _tool_call("blocked", call_id="blocked-call"),
        ],
        round_number=1,
    )

    assert [outcome.error["code"] for outcome in outcomes] == [
        "execution_error",
        "execution_error",
        "timeout",
    ]
    assert [json.loads(outcome.result)["error"]["code"] for outcome in outcomes] == [
        "execution_error",
        "execution_error",
        "timeout",
    ]


def test_links_model_retry_to_previous_failed_call_without_auto_retry():
    definition = _tool_definition()

    class RetryExecutor(RecordingExecutor):
        def __init__(self, permitted_definitions):
            super().__init__(permitted_definitions)
            self.attempts = 0

        def __call__(self, name, arguments):
            self.attempts += 1
            if self.attempts == 1:
                return json.dumps({"error": "try different arguments"})
            return json.dumps({"ok": True})

    executor = RetryExecutor([definition])
    events = []
    coordinator = ToolRunCoordinator(executor, [definition], on_step=events.append)

    first = coordinator.execute_batch(
        [_tool_call(arguments={}, call_id="first-call")],
        round_number=1,
    )[0]
    second = coordinator.execute_batch(
        [_tool_call(arguments={}, call_id="second-call")],
        round_number=2,
    )[0]

    assert first.failed is True
    assert second.failed is False
    assert second.call.retry_of == "first-call"
    assert executor.attempts == 2
    second_events = [event for event in events if event["call_id"] == "second-call"]
    assert all(event["retry_of"] == "first-call" for event in second_events)
