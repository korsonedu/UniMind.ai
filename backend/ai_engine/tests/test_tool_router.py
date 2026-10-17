from ai_engine import tool_router
import pytest


def _tool(name):
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": name,
            "parameters": {"type": "object", "properties": {}},
        },
    }


def test_vocabulary_study_keeps_visual_tool_when_semantic_routes_miss(monkeypatch):
    monkeypatch.setattr(tool_router, "_retrieve_candidates", lambda *args, **kwargs: [])
    monkeypatch.setattr(tool_router, "_classify_intent_llm", lambda *args, **kwargs: "general")
    tools = [
        _tool("get_learning_stats"),
        _tool("get_due_reviews"),
        _tool("get_user_weak_points"),
        _tool("render_visual"),
    ]

    routed = tool_router.route_tools(
        "开始背单词",
        tools,
        bot_type="planner",
    )

    assert "render_visual" in {
        tool["function"]["name"] for tool in routed
    }


@pytest.mark.parametrize("bot_type", ["planner", "exam_generator"])
@pytest.mark.parametrize("candidates", [[], ["get_learning_stats"]])
def test_interaction_tool_survives_routing_for_unrecognized_requests(monkeypatch, bot_type, candidates):
    monkeypatch.setattr(tool_router, "_retrieve_candidates", lambda *args, **kwargs: candidates)
    monkeypatch.setattr(tool_router, "_classify_intent_llm", lambda *args, **kwargs: "general")
    tools = [_tool("get_learning_stats"), _tool("render_visual"), _tool("send_notification")]

    routed = tool_router.route_tools("我还没拿定主意", tools, bot_type=bot_type)

    assert [tool["function"]["name"] for tool in routed] == candidates + ["render_visual"]


def test_routing_does_not_restore_an_unauthorized_interaction_tool(monkeypatch):
    monkeypatch.setattr(tool_router, "_retrieve_candidates", lambda *args, **kwargs: ["render_visual"])
    monkeypatch.setattr(tool_router, "_classify_intent_llm", lambda *args, **kwargs: "general")

    assert tool_router.route_tools("让我选一个方向", [_tool("get_learning_stats")]) == []


def test_selected_business_tools_keep_visual_tool(monkeypatch):
    monkeypatch.setattr(tool_router, "_retrieve_candidates", lambda *args, **kwargs: ["search_knowledge"])
    monkeypatch.setattr(tool_router, "_classify_intent_llm", lambda *args, **kwargs: "weak_points")
    tools = [_tool("search_knowledge"), _tool("quick_generate"), _tool("render_visual"), _tool("send_notification")]

    routed = tool_router.route_tools("看看薄弱点", tools, bot_type="exam_generator")

    assert [tool["function"]["name"] for tool in routed] == ["search_knowledge", "quick_generate", "render_visual"]
