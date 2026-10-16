import json
from types import SimpleNamespace

from ai_assistant.services.tool_executor import BaseToolExecutor


class _Executor(BaseToolExecutor):
    def _handle_allowed(self, args):
        return {"tool": "allowed"}

    def _handle_permitted_but_unrouted(self, args):
        return {"tool": "permitted_but_unrouted"}

    def _handle_forbidden(self, args):
        return {"tool": "forbidden"}


def test_executor_can_expand_route_only_within_plan_permissions():
    executor = _Executor(user=SimpleNamespace(institution=None))
    executor._allowed_tool_names = {"allowed"}
    executor._permitted_tool_names = {"allowed", "permitted_but_unrouted"}

    routed_result = json.loads(executor("allowed", {}))
    recovered_result = json.loads(executor("permitted_but_unrouted", {}))
    blocked_result = json.loads(executor("forbidden", {}))

    assert routed_result == {"tool": "allowed"}
    assert recovered_result == {"tool": "permitted_but_unrouted"}
    assert blocked_result == {"error": "Tool not allowed: forbidden"}
