"""轻量级意图路由器：根据用户消息预筛选候选工具组。"""

import re
from typing import List, Dict


# ── 意图→工具组映射 ──────────────────────────────────────────

PLANNER_INTENT_MAP = {
    "planning": {
        "keywords": ["规划", "安排", "计划", "复习", "备考", "学习计划", "日程", "每周", "今天做什么"],
        "tools": [
            "get_learning_stats", "get_knowledge_mastery_map",
            "get_due_reviews", "save_study_plan", "get_active_plan",
            "update_plan_task",
        ],
    },
    "quiz": {
        "keywords": ["出题", "做题", "练习", "测试", "考试", "刷题", "模拟", "真题"],
        "tools": [
            "search_knowledge_points", "generate_questions",
            "launch_arc_pipeline", "check_pipeline_status",
            "save_questions_to_library",
        ],
    },
    "analysis": {
        "keywords": ["分析", "掌握率", "薄弱", "趋势", "成绩", "正确率", "统计", "报告"],
        "tools": [
            "get_learning_stats", "get_knowledge_mastery_map",
            "get_class_weak_points", "get_class_performance_summary",
            "get_exam_history",
        ],
    },
    "knowledge": {
        "keywords": ["知识点", "概念", "定义", "解释", "是什么", "有哪些", "搜索"],
        "tools": [
            "search_knowledge_tree", "search_knowledge_points",
            "lookup_question", "lookup_knowledge_point_definition",
            "search_similar_questions",
        ],
    },
    "resource": {
        "keywords": ["课程", "视频", "文章", "资料", "推荐", "学习资源"],
        "tools": [
            "search_courses", "search_asr", "search_articles",
        ],
    },
    "error_review": {
        "keywords": ["错题", "错误", "做错了", "哪里错", "错因"],
        "tools": [
            "get_user_wrong_questions", "get_user_weak_points",
            "lookup_question",
        ],
    },
    "dashboard": {
        "keywords": ["面板", "仪表盘", "dashboard", "卡片", "指标"],
        "tools": [
            "set_dashboard_layout", "create_dashboard_card",
        ],
    },
}

EXAM_GENERATOR_INTENT_MAP = {
    "generate": {
        "keywords": ["出题", "生成", "命题", "出一组", "出几道", "给我出", "来几道", "新题", "题目"],
        "tools": [
            "search_knowledge_points", "generate_questions",
        ],
    },
    "refine": {
        "keywords": ["精修", "arc", "润色", "改进", "提升质量", "高质量", "对抗", "审核"],
        "tools": [
            "launch_arc_pipeline", "check_pipeline_status",
        ],
    },
    "save": {
        "keywords": ["入库", "存下来", "保存", "收录", "存题库", "存到题库"],
        "tools": [
            "save_questions_to_library",
        ],
    },
    "status": {
        "keywords": ["进度", "跑完没", "状态", "结果", "完成没", "好了吗"],
        "tools": [
            "check_pipeline_status",
        ],
    },
}

BOT_INTENT_MAP: Dict[str, Dict] = {
    "planner": PLANNER_INTENT_MAP,
    "exam_generator": EXAM_GENERATOR_INTENT_MAP,
}


def classify_intent(user_message: str, recent_messages: List[Dict[str, str]] = None,
                    bot_type: str = "planner") -> str:
    """分类用户意图，返回 intent category 名称。

    优先匹配用户消息，fallback 到最近 3 轮对话上下文。
    """
    intent_map = BOT_INTENT_MAP.get(bot_type, PLANNER_INTENT_MAP)
    text = user_message.lower()

    # 第一轮：匹配用户当前消息
    for intent, config in intent_map.items():
        for kw in config["keywords"]:
            if kw in text:
                return intent

    # 第二轮：匹配最近 3 轮对话上下文
    if recent_messages:
        context_text = " ".join(
            m.get("content", "") for m in recent_messages[-6:]  # 最近 3 轮（user+assistant）
        ).lower()
        for intent, config in intent_map.items():
            for kw in config["keywords"]:
                if kw in context_text:
                    return intent

    return "general"


def route_tools(
    user_message: str,
    all_tools: List[dict],
    recent_messages: List[Dict[str, str]] = None,
    bot_type: str = "planner",
) -> List[dict]:
    """根据用户意图从全量工具中筛选候选子集。

    返回值：筛选后的工具列表（保持 OpenAI function calling 格式）。
    如果意图分类为 general 或匹配不到，返回全量工具。
    """
    intent = classify_intent(user_message, recent_messages, bot_type=bot_type)
    intent_map = BOT_INTENT_MAP.get(bot_type, PLANNER_INTENT_MAP)
    allowed_names = intent_map.get(intent, {}).get("tools", [])

    if not allowed_names:
        return all_tools

    allowed_set = set(allowed_names)
    filtered = [t for t in all_tools if t["function"]["name"] in allowed_set]

    # Fallback：如果筛选后少于 2 个工具，返回全量（防止漏选）
    return filtered if len(filtered) >= 2 else all_tools
