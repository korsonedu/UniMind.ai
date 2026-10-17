from ai_engine import tool_router


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
