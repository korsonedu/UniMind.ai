# 智能工具路由 — 实现 Plan

> 2026-05-28
> 理论基础：SkillRouter (arXiv:2603.22455, Alibaba Group, 2026)

## Phase 1：工具元数据增强（impl_summary）

**目标**：为每个工具补充实现级摘要，将 description 从"做什么"扩展为"做什么 + 怎么做"。

### Step 1.1：修改 `_make_tool()` 支持 impl_summary

**文件**：`backend/ai_engine/tools.py:621`

```python
# 当前
def _make_tool(name, description, schema):
    return {"type": "function", "function": {"name": name, "description": description, "parameters": schema}}

# 改为
def _make_tool(name, description, schema, impl_summary=""):
    desc = f"{description}\n\n实现逻辑：{impl_summary}" if impl_summary else description
    return {"type": "function", "function": {"name": name, "description": desc, "parameters": schema}}
```

**为什么改 description 而不是新增字段**：OpenAI function calling 只认 `function.name`、`function.description`、`function.parameters`。LLM 看不到自定义字段。impl_summary 必须拼进 description。

**验证**：`python manage.py check` 通过。

### Step 1.2：为所有工具编写 impl_summary

**文件**：`backend/ai_engine/tools.py`

**编写规范**（基于论文 Section 3.3）：
- 描述行为逻辑（查什么表/做什么计算），不重复用途
- 包含关键参数约束
- 2-3 句，≤100 字

**Assistant 工具（9 个）**：

```python
# L627 — search_knowledge_tree
_make_tool("search_knowledge_tree",
    "搜索知识点树，按名称或描述查找匹配的知识点。用于回答'XX是什么''有哪些XX'等需要查知识点的问题。",
    SEARCH_KNOWLEDGE_TREE_SCHEMA,
    impl_summary="模糊匹配 knowledge_point 表的 name 和 description 字段，返回按 relevance 排序的节点列表。支持 subject 过滤。")

# L628 — get_user_weak_points
_make_tool("get_user_weak_points",
    "获取当前用户的薄弱知识点（错题最多的前几个知识点）。用于个性化辅导和复习建议。",
    GET_USER_WEAK_POINTS_SCHEMA,
    impl_summary="查询 quiz_attempt 表，按 knowledge_point 分组统计正确率，返回正确率最低的前 N 个知识点及错误次数。需要 user_id。")

# L629 — get_user_wrong_questions
_make_tool("get_user_wrong_questions",
    "获取当前用户最近的错题列表。用于分析错误模式、针对性讲解。",
    GET_USER_WRONG_QUESTIONS_SCHEMA,
    impl_summary="查询 quiz_attempt 表 WHERE is_correct=false，按 created_at 降序返回最近 N 条，包含题干、用户答案、正确答案。需要 user_id。")

# L630 — lookup_question
_make_tool("lookup_question",
    "根据题目 ID 查询题目详情（题干、答案、解析）。用于讨论具体题目时获取准确信息。",
    LOOKUP_QUESTION_SCHEMA,
    impl_summary="主键查询 question 表，返回完整题目记录（题干、选项、答案、解析、知识点关联）。需要 question_id。")

# L631 — get_class_weak_points
_make_tool("get_class_weak_points",
    "获取班级最薄弱的知识点（按正确率排序）。仅教师/机构主可用，用于了解班级整体学习情况。",
    GET_CLASS_WEAK_POINTS_SCHEMA,
    impl_summary="查询 quiz_attempt 表 JOIN class 关联，按 knowledge_point 聚合班级平均正确率，返回最低的前 N 个。需要 class_id。")

# L632 — get_class_performance_summary
_make_tool("get_class_performance_summary",
    "获取班级整体学习数据概览（学生数、活跃率、正确率、薄弱知识点数）。仅教师/机构主可用。",
    GET_CLASS_PERFORMANCE_SUMMARY_SCHEMA,
    impl_summary="聚合查询：COUNT(DISTINCT student)、最近7天活跃率、全局正确率、正确率<60%的知识点数。需要 class_id。")

# L633 — search_courses
_make_tool("search_courses",
    "搜索课程库，按关键词或学科查找推荐课程。用于在建议学习资源时提供具体课程链接。",
    SEARCH_COURSES_SCHEMA,
    impl_summary="全文搜索 course 表的 title 和 description，支持 subject 过滤，返回按 relevance 排序的课程列表（含 slug 用于前端链接）。")

# L634 — search_asr
_make_tool("search_asr",
    "搜索课程视频的 ASR 转录文本，找到某个知识点在视频中的具体时间位置。用于告诉学生'XX概念在课程YY的ZZ分ZZ秒处讲解'。",
    SEARCH_ASR_SCHEMA,
    impl_summary="查询 asr_segment 表的 transcript 字段做全文匹配，返回包含关键词的片段及对应时间戳（start_time），关联 course 和 video 信息。")

# L635 — search_articles
_make_tool("search_articles",
    "搜索深度文章库，按关键词查找相关文章。用于推荐学习资料和扩展阅读。",
    SEARCH_ARTICLES_SCHEMA,
    impl_summary="全文搜索 article 表的 title 和 body，返回按 relevance 排序的文章列表（含 slug 用于前端链接）。")
```

**Planner 专用工具（9 个）**：

```python
# L642 — get_learning_stats
_make_tool("get_learning_stats",
    "获取用户学习统计概览（总做题量、正确率、学习连续天数、学科覆盖）。用于制定计划前了解学生现状。",
    GET_LEARNING_STATS_SCHEMA,
    impl_summary="聚合查询：COUNT(quiz_attempt)、AVG(is_correct)、计算最长连续学习天数、COUNT(DISTINCT subject)。需要 user_id。")

# L643 — get_knowledge_mastery_map
_make_tool("get_knowledge_mastery_map",
    "获取用户知识点掌握度地图，按学科/模块分组。用于识别薄弱环节，制定针对性计划。",
    GET_KNOWLEDGE_MASTERY_MAP_SCHEMA,
    impl_summary="查询 knowledge_mastery 表，按 subject → chapter → section 分组返回掌握度百分比。支持 subject 过滤。需要 user_id。")

# L644 — get_due_reviews
_make_tool("get_due_reviews",
    "获取今日待复习的题目列表（来自间隔重复调度）。用于安排今日复习任务。",
    GET_DUE_REVIEWS_SCHEMA,
    impl_summary="查询 memorix_schedule 表 WHERE next_review <= today AND user_id=current_user，按 priority 降序返回待复习题目列表。")

# L645 — get_exam_history
_make_tool("get_exam_history",
    "获取用户的考试成绩历史和趋势。用于评估学习进展。",
    GET_EXAM_HISTORY_SCHEMA,
    impl_summary="查询 exam_record 表 WHERE user_id=current_user，按 created_at 降序返回最近 N 次考试成绩（分数、科目、日期）。")

# L646 — save_study_plan
_make_tool("save_study_plan",
    "将生成的学习计划持久化到数据库。调用后用户可在计划页面查看。",
    SAVE_STUDY_PLAN_SCHEMA,
    impl_summary="创建 study_plan 记录和关联的 plan_task 列表，设置 status='active'。如果已有 active plan，先标记为 superseded。需要 user_id。")

# L647 — get_active_plan
_make_tool("get_active_plan",
    "获取用户当前进行中的学习计划。用于查看已有计划或在修改前获取当前状态。",
    GET_ACTIVE_PLAN_SCHEMA,
    impl_summary="查询 study_plan 表 WHERE user_id=current_user AND status='active'，返回计划详情及关联的 plan_task 列表。")

# L648 — update_plan_task
_make_tool("update_plan_task",
    "更新学习计划中某个任务的状态（完成/跳过/重置）。",
    UPDATE_PLAN_TASK_SCHEMA,
    impl_summary="更新 plan_task 表的 status 字段（completed/skipped/pending），同时更新关联 study_plan 的 progress 百分比。需要 task_id。")

# L649 — set_dashboard_layout
_make_tool("set_dashboard_layout",
    "配置小宇 Dashboard 面板的布局。根据学生当前状态决定展示哪些区块、排列顺序和高亮重点。每次对话后应调用此工具更新面板。",
    SET_DASHBOARD_LAYOUT_SCHEMA,
    impl_summary="创建或更新 dashboard_config 记录，存储 JSON 格式的布局配置（区块列表、排列顺序、高亮规则）。需要 user_id。")

# L650 — create_indicator_card
_make_tool("create_indicator_card",
    "在 Dashboard 中创建自定义指标卡片。根据学生当前数据生成个性化的指标概览，如学习进度、薄弱点统计等。每次对话可创建多张卡片。",
    CREATE_INDICATOR_CARD_SCHEMA,
    impl_summary="创建 indicator_card 记录，包含 title、metric_type、data_source（SQL 或聚合查询引用）、display_config。需要 user_id。")
```

**Reviewer 工具（2 个）**：

```python
# L657 — lookup_knowledge_point_definition
_make_tool("lookup_knowledge_point_definition",
    "查询知识点的标准定义、范围和核心内容。用于验证题目是否准确命中目标知识点。",
    LOOKUP_KNOWLEDGE_POINT_SCHEMA,
    impl_summary="主键查询 knowledge_point 表，返回 name、description、parent 关联。用于 Reviewer 验证题目与知识点的匹配度。")

# L658 — search_similar_questions
_make_tool("search_similar_questions",
    "搜索同一知识点下的已有题目。用于检查是否与现有题目雷同或重复。",
    SEARCH_SIMILAR_QUESTIONS_SCHEMA,
    impl_summary="查询 question 表 WHERE knowledge_point_id IN (...)，返回同知识点下的已有题目列表（题干、答案），用于去重检查。")
```

**Exam Generator 工具（5 个）**：

```python
# L764 — search_knowledge_points
_make_tool("search_knowledge_points",
    "搜索可用知识点，按名称或编码查找。出题前先用此工具确认知识点存在。",
    SEARCH_KP_SCHEMA,
    impl_summary="模糊匹配 knowledge_point 表的 name 和 code 字段，支持 subject 过滤。返回知识点 ID 和名称，用于后续 generate_questions 的 kp_ids 参数。")

# L765 — generate_questions
_make_tool("generate_questions",
    "快速生成题目（同步，约 10 秒）。根据知识点、难度、题型生成候选题目。",
    GENERATE_QUESTIONS_SCHEMA,
    impl_summary="调用 LLM 根据知识点描述生成题目 JSON，验证 schema 后存入内存候选池。返回生成的题目列表供用户审阅。支持 count、difficulty、types 参数。")

# L766 — launch_arc_pipeline
_make_tool("launch_arc_pipeline",
    "启动 ARC 精修管线（异步，2-5 分钟）。4-agent 对抗循环：Author→Reviewer→Revise→Classifier，质量更高。",
    LAUNCH_ARC_PIPELINE_SCHEMA,
    impl_summary="创建 PipelineTask 记录并 dispatch Celery 异步任务。执行 Author→Reviewer→AuthorRevise→Classifier 四阶段对抗，每阶段调用 LLM。返回 task_id 用于轮询进度。")

# L767 — check_pipeline_status
_make_tool("check_pipeline_status",
    "查询 ARC 管线的执行进度。",
    CHECK_PIPELINE_STATUS_SCHEMA,
    impl_summary="主键查询 pipeline_task 表，返回 status（pending/running/completed/failed）、current_stage、progress 百分比、已生成题目数。")

# L768 — save_questions_to_library
_make_tool("save_questions_to_library",
    "将最近一次生成的题目存入机构题库。可选择保存全部或部分题目。",
    SAVE_QUESTIONS_TO_LIBRARY_SCHEMA,
    impl_summary="将候选池中的题目批量插入 question 表，关联 knowledge_point 和 institution。支持通过 question_indices 选择性保存。")
```

**验证**：
- `python manage.py check` 通过
- 手动测试：在 Django shell 中调用 `get_planner_tools()[0]` 确认 description 包含 impl_summary
- 对比有/无 impl_summary 时 Agent 的工具选择行为

---

## Phase 2：意图预筛选路由

**目标**：小宇（18 工具）启用意图路由，从 18 个缩减为 5-8 个候选。

### Step 2.1：创建 `tool_router.py`

**文件**：`backend/ai_engine/tool_router.py`（新建）

```python
"""轻量级意图路由器：根据用户消息预筛选候选工具组。"""

import re
from typing import List, Dict


# ── 意图→工具组映射 ──────────────────────────────────────────

INTENT_TOOL_MAP = {
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
            "set_dashboard_layout", "create_indicator_card",
        ],
    },
}


def classify_intent(user_message: str, recent_messages: List[Dict[str, str]] = None) -> str:
    """分类用户意图，返回 intent category 名称。

    优先匹配用户消息，fallback 到最近 3 轮对话上下文。
    """
    text = user_message.lower()

    # 第一轮：匹配用户当前消息
    for intent, config in INTENT_TOOL_MAP.items():
        for kw in config["keywords"]:
            if kw in text:
                return intent

    # 第二轮：匹配最近 3 轮对话上下文
    if recent_messages:
        context_text = " ".join(
            m.get("content", "") for m in recent_messages[-6:]  # 最近 3 轮（user+assistant）
        ).lower()
        for intent, config in INTENT_TOOL_MAP.items():
            for kw in config["keywords"]:
                if kw in context_text:
                    return intent

    return "general"


def route_tools(
    user_message: str,
    all_tools: List[dict],
    recent_messages: List[Dict[str, str]] = None,
) -> List[dict]:
    """根据用户意图从全量工具中筛选候选子集。

    返回值：筛选后的工具列表（保持 OpenAI function calling 格式）。
    如果意图分类为 general 或匹配不到，返回全量工具。
    """
    intent = classify_intent(user_message, recent_messages)
    allowed_names = INTENT_TOOL_MAP.get(intent, {}).get("tools", [])

    if not allowed_names:
        return all_tools

    allowed_set = set(allowed_names)
    filtered = [t for t in all_tools if t["function"]["name"] in allowed_set]

    # Fallback：如果筛选后少于 2 个工具，返回全量（防止漏选）
    return filtered if len(filtered) >= 2 else all_tools
```

**验证**：
- 单元测试：构造测试用例覆盖每个 intent category + general fallback
- 确认 `route_tools("帮我规划下周学习", all_18_tools)` 返回 ≤8 个工具
- 确认 `route_tools("你好", all_18_tools)` 返回全量 18 个工具

### Step 2.2：接入 chat_service.py

**文件**：`backend/ai_assistant/services/chat_service.py:107-113`

```python
# 当前（L107-113）
profile = get_bot_profile(bot.bot_type if bot else 'assistant')
tools = profile.tools_factory()
bot_type = bot.bot_type if bot else 'assistant'
tools = filter_tools(bot_type, institution, tools)

# 改为
profile = get_bot_profile(bot.bot_type if bot else 'assistant')
tools = profile.tools_factory()
bot_type = bot.bot_type if bot else 'assistant'
tools = filter_tools(bot_type, institution, tools)

# Phase 2: 意图预筛选（仅 planner 启用，其他 bot_type 跳过）
if bot_type == 'planner' and user_message:
    from ai_engine.tool_router import route_tools
    tools = route_tools(user_message, tools, recent_messages=history_messages)
```

**插入位置**：`filter_tools` 之后、`forced_tool_choice` 之前（L114 之前）。

**为什么只对 planner 启用**：
- planner 有 18 个工具，选择复杂度最高
- exam_generator 只有 5 个，全量即可
- assistant 有 9 个，暂不需要

**验证**：
- `python manage.py check` 通过
- 手动测试：小宇对话 "帮我规划下周学习"，确认 LLM 只收到规划类工具
- 对比 token 消耗：路由前 vs 路由后

### Step 2.3：BotProfile 增加 router 配置（可选）

**文件**：`backend/ai_assistant/bot_registry.py:14`

```python
@dataclass
class BotProfile:
    name: str
    bot_type: str
    executor_class: type
    tools_factory: Callable
    prompt_dir: str
    is_exclusive: bool = False
    force_tool_choice: bool = False
    use_intent_router: bool = False  # 新增
```

```python
# BOT_REGISTRY 中 planner 条目
'planner': BotProfile(
    ...
    force_tool_choice=True,
    use_intent_router=True,  # 新增
),
```

chat_service.py 改为读 profile.use_intent_router 而不是硬编码 bot_type == 'planner'。

**验证**：`python manage.py check` 通过。

---

## 验证清单

### Phase 1 验证

- [ ] `python manage.py check` 通过
- [ ] Django shell: `from ai_engine.tools import get_planner_tools; t = get_planner_tools()[0]; assert '实现逻辑' in t['function']['description']`
- [ ] 手动测试小宇对话，确认 Agent 能正确使用带 impl_summary 的工具
- [ ] `make backend-check` 通过

### Phase 2 验证

- [ ] 单元测试 `test_tool_router.py`：
  - `classify_intent("帮我规划下周学习")` == "planning"
  - `classify_intent("出5道高数题")` == "quiz"
  - `classify_intent("你好")` == "general"
  - `route_tools("分析我的薄弱点", all_tools)` 长度 < 18
  - `route_tools("你好", all_tools)` 长度 == 18
- [ ] 集成测试：小宇对话，确认工具选择正确且对话轮次减少
- [ ] `make full-check` 通过
