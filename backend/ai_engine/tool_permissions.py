"""Tool permission sandbox: filter available tools based on institution plan."""

PLAN_TOOL_ACCESS = {
    "free": {
        "assistant": ["search_knowledge_tree", "get_user_weak_points"],
        "planner": [],
        "exam_generator": [],
    },
    "starter": {
        "assistant": [
            "search_knowledge_tree", "get_user_weak_points",
            "get_user_wrong_questions", "search_courses",
        ],
        "planner": [
            "get_learning_stats", "get_knowledge_mastery_map",
            "get_due_reviews",
        ],
        "exam_generator": [
            "search_knowledge_points", "generate_questions",
        ],
    },
    "growth": {"assistant": "all", "planner": "all", "exam_generator": "all"},
    "enterprise": {"assistant": "all", "planner": "all", "exam_generator": "all"},
}


def filter_tools(bot_type: str, institution, all_tools: list) -> list:
    """Filter tool list based on institution plan.

    Args:
        bot_type: One of 'assistant', 'planner', 'exam_generator'.
        institution: The Institution object (or None for free plan).
        all_tools: Full tool list from get_*_tools().

    Returns:
        Filtered tool list containing only tools the plan allows.
    """
    plan = getattr(institution, 'plan', 'free') if institution else 'free'
    allowed = PLAN_TOOL_ACCESS.get(plan, PLAN_TOOL_ACCESS["free"]).get(bot_type, [])
    if allowed == "all":
        return all_tools
    allowed_set = set(allowed)
    return [t for t in all_tools if t["function"]["name"] in allowed_set]
