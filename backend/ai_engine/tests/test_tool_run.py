import json

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
