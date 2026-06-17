"""
意图路由器：基于 SkillRouter 论文的 embedding 检索 + 关键词 fallback。

核心洞察（SkillRouter arXiv:2603.22455）：
  tool body 是路由决策的决定性信号（91.7% 注意力集中在 body），
  仅用 name+description 会导致 29-44pp 精度下降。

路由链：embedding 检索 → 关键词匹配 → 全量工具
"""

import logging
import math
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# ── ToolMeta: 工具的路由元数据 ────────────────────────────────

@dataclass
class ToolMeta:
    """工具的路由元数据，包含 body 用于 embedding 检索。"""
    name: str
    description: str  # 一句话用途
    body: str         # 完整使用说明（路由的关键信号）


# ── 工具注册表 ────────────────────────────────────────────────

PLANNER_TOOLS_META = [
    ToolMeta(
        name="search_knowledge_tree",
        description="搜索知识树，按主题或编码查找知识点节点",
        body="在知识树中搜索指定主题的节点。参数: query(str)=搜索关键词, subject(str)=学科名(可选)。返回匹配的知识点列表，含 id、name、编码、层级。适用于：需要定位具体知识点、浏览知识结构、确认知识点是否存在。不适用于：查找具体题目、查找课程资源。",
    ),
    ToolMeta(
        name="get_learning_stats",
        description="获取用户学习统计数据",
        body="获取指定用户的学习统计概览。参数: user_id(int)=用户ID。返回：总做题数、正确率、连续学习天数、各知识点掌握率等。适用于：分析学习进度、回答'我学得怎么样'、生成学习报告。不适用于：查看具体错题、查找知识点。",
    ),
    ToolMeta(
        name="get_knowledge_mastery_map",
        description="获取用户各知识点掌握率热力图数据",
        body="获取用户在各知识点上的掌握率。参数: user_id(int)=用户ID, subject(str)=学科(可选)。返回：知识点名称 → 掌握率(0-1)的映射。适用于：识别薄弱环节、生成掌握率可视化、对比不同知识点。不适用于：查看具体错题内容。",
    ),
    ToolMeta(
        name="get_due_reviews",
        description="获取用户今日到期的间隔重复复习任务",
        body="获取用户今日到期的复习任务。参数: user_id(int)=用户ID。返回：待复习题目列表，含知识点、上次正确率、到期时间。适用于：提醒复习、规划今日学习、了解复习压力。不适用于：查看新题、查看历史成绩。",
    ),
    ToolMeta(
        name="save_study_plan",
        description="保存用户学习计划（自动归档旧计划）",
        body="为用户创建新的学习计划。参数: title(str)=计划标题, tasks(list)=任务列表, total_days(int)=总天数。每次调用会将旧计划标记为archived。适用于：制定学习计划、安排复习日程、设置学习目标。不适用于：修改现有计划（用update_plan_task）、查看计划（用get_active_plan）。",
    ),
    ToolMeta(
        name="get_active_plan",
        description="获取用户当前生效的学习计划",
        body="获取用户当前活跃的学习计划。参数: user_id(int)=用户ID。返回：计划详情含tasks列表及各task完成状态。适用于：查看当前计划进度、确认计划内容。不适用于：创建新计划、修改计划。",
    ),
    ToolMeta(
        name="update_plan_task",
        description="更新学习计划中单个任务的状态",
        body="更新计划中某个任务的完成状态。参数: user_id(int)=用户ID, task_id(str)=任务ID, status(str)=completed/skipped/pending。适用于：标记任务完成、更新进度。不适用于：创建计划、删除计划。",
    ),
    ToolMeta(
        name="get_user_wrong_questions",
        description="获取用户最近的错题列表",
        body="获取用户最近做错的题目。参数: user_id(int)=用户ID, limit(int)=返回数量(默认5,最大10)。返回：题目内容、知识点、错误次数、上次作答。适用于：错题回顾、分析错误模式、针对性练习。不适用于：查看正确题、查找知识点。",
    ),
    ToolMeta(
        name="get_user_weak_points",
        description="获取用户薄弱知识点排名",
        body="获取用户错误率最高的知识点。参数: user_id(int)=用户ID。返回：薄弱知识点列表，含错误率、涉及题目数。适用于：识别薄弱环节、制定针对性复习。不适用于：查看整体统计、查看具体题目。",
    ),
    ToolMeta(
        name="lookup_question",
        description="查询具体题目的详情和解析",
        body="查询指定题目的完整信息。参数: question_id(int)=题目ID。返回：题干、选项、正确答案、解析、知识点。适用于：查看题目详情、讲解题目、核对答案。不适用于：批量查找、搜索题目。",
    ),
    ToolMeta(
        name="get_class_weak_points",
        description="获取班级知识点薄弱分析（仅教师/机构主）",
        body="分析班级整体知识点掌握情况。参数: institution_id(int)=机构ID, class_name(str)=班级名(可选)。返回：班级各知识点正确率、最薄弱知识点。需要teacher/owner角色。适用于：班级学情分析、教学调整。不适用于：查看单个学生、查看个人统计。",
    ),
    ToolMeta(
        name="get_class_performance_summary",
        description="获取班级整体表现摘要（仅教师/机构主）",
        body="获取班级整体学习表现。参数: institution_id(int)=机构ID。返回：平均正确率、活跃学生数、学习时长分布。需要teacher/owner角色。适用于：班级整体评估、教学效果分析。不适用于：查看单个学生详情。",
    ),
    ToolMeta(
        name="get_exam_history",
        description="获取用户考试/测验历史记录",
        body="获取用户的历史考试记录。参数: user_id(int)=用户ID, limit(int)=返回数量(默认10)。返回：考试名称、时间、得分、题目数。适用于：查看历史成绩、追踪进步趋势。不适用于：查看具体错题、查看知识点掌握率。",
    ),
    ToolMeta(
        name="search_courses",
        description="搜索课程资源",
        body="搜索平台课程。参数: query(str)=搜索关键词, subject(str)=学科(可选)。返回：课程列表含标题、简介、难度。适用于：推荐学习资源、查找视频课程。不适用于：查找题目、查找知识点。",
    ),
    ToolMeta(
        name="search_asr",
        description="搜索课程视频的ASR转录文本",
        body="搜索视频课程的语音转录文本。参数: query(str)=搜索关键词, course_id(int)=课程ID(可选)。返回：匹配的转录片段及时间戳。适用于：查找视频中讲到某个知识点的时间点。不适用于：查找文字课程、查找题目。",
    ),
    ToolMeta(
        name="search_articles",
        description="搜索深度学习文章",
        body="搜索平台文章。参数: query(str)=搜索关键词。返回：文章列表含标题、摘要、难度。适用于：推荐扩展阅读、查找学习资料。不适用于：查找题目、查找视频。",
    ),
    ToolMeta(
        name="render_visual",
        description="在画布上渲染可视化内容",
        body="将数据以可视化形式渲染到前端画布。参数: type(str)=可视化类型(data_card/latex_derivation/step_solution/knowledge_map/action_cards), payload(dict)=可视化数据。适用于：即时展示数据、推导过程可视化、数据分析结果展示。",
    ),
    ToolMeta(
        name="get_practice_questions",
        description="从题库中抽取相关题目供学生练习",
        body="从题库中按知识点或学科抽取题目。参数: kp_name(str)=知识点名称, subject(str)=学科(可选), difficulty(str)=难度(可选), limit(int)=题数(默认5)。优先返回做错过的题目。适用于：给学生出题练习、'我想做XX题'、薄弱知识点强化训练。不适用于：查看错题记录（用get_user_wrong_questions）、查看复习任务（用get_due_reviews）。",
    ),
]

EXAM_GENERATOR_TOOLS_META = [
    ToolMeta(
        name="search_knowledge",
        description="搜索知识点或知识树结构",
        body="搜索知识点或知识树。参数: query(str)=搜索关键词, subject(str)=学科(可选), mode(str)=搜索模式(kp/tree/auto,默认auto)。auto模式先搜知识点，无结果则搜知识树。返回：知识点ID和名称，或知识树节点。出题前必须先搜索获取知识点ID。适用于：确认知识点、查找相关知识点。不适用于：搜索题目。",
    ),
    ToolMeta(
        name="quick_generate",
        description="快速出题（Author单步，约5-10秒）",
        body="根据知识点快速生成题目。参数: kp_ids(list)=知识点ID列表, count(int)=总题数(默认5)。调用Author单步生成+去重+校验，跳过Reviewer。返回：题目列表存入候选池，前端QuestionPanel展示。适用于：快速出题、教师审阅。不适用于：高质量出题（用launch_arc_pipeline精修）。",
    ),
    ToolMeta(
        name="launch_arc_pipeline",
        description="启动ARC对抗精修管线",
        body="启动Author→Reviewer→AuthorRevise→Classifier四阶段管线。参数: kp_ids(list)=知识点ID列表, questions_per_kp(int)=每知识点题数(默认3), difficulty(str)=难度, types(list)=题型, title(str)=任务标题。返回：task_id用于追踪进度。适用于：精修已有题目、高质量出题。不适用于：快速出题（用quick_generate）。",
    ),
    ToolMeta(
        name="check_pipeline_status",
        description="检查ARC管线执行状态",
        body="查询管线任务状态。参数: task_id(int)=管线任务ID。返回：状态(pending/running/completed/failed)、当前阶段、进度百分比。适用于：追踪管线进度。不适用于：启动管线。",
    ),
    ToolMeta(
        name="get_workbench_stats",
        description="获取题库统计数据",
        body="获取题库统计。参数: scope(str)=数据范围(summary/recent/insights,默认summary)。summary返回总题数和分布；recent返回最近20道题；insights返回教师出题偏好。适用于：了解题库情况、查看出题统计。不适用于：出题、搜索。",
    ),
    ToolMeta(
        name="get_student_detail",
        description="获取指定学生的详细学习数据（仅教师/机构主）",
        body="查询学生答题统计、薄弱知识点、ELO、周活跃度。参数: student_name(str)=学生姓名模糊匹配, student_id(int)=学生ID精确匹配。需要teacher/owner角色。适用于：教师问'某某学得怎么样'、查看学生个人数据。不适用于：查看全班数据（用get_class_weak_points）。",
    ),
    ToolMeta(
        name="get_assignment_progress",
        description="查询指定作业的提交和批改进度（仅教师/机构主）",
        body="查询作业提交状态。参数: assignment_id(int)=作业ID。返回：提交数/总人数、已批改数、待批改数、作业标题和截止日期。需要teacher/owner角色。适用于：教师问'作业交了没''还有谁没交'。不适用于：批改作业。",
    ),
    ToolMeta(
        name="assign_practice",
        description="创建作业并布置给学生（仅教师/机构主）",
        body="创建作业记录并发布给学生。参数: title(str)=作业标题, question_ids(list)=题目ID列表, class_names(list)=目标班级名, due_date(str)=截止日期(ISO), points_per_question(int)=每题分值。需要teacher/owner角色。适用于：教师说'布置给X班''把这些题发下去'。不适用于：出题（先用quick_generate）。",
    ),
    ToolMeta(
        name="send_notification",
        description="向指定学生发送学习提醒通知（仅教师/机构主）",
        body="发送站内通知。参数: student_name(str)或student_id(int)=目标学生, title(str)=通知标题, content(str)=通知正文。需要teacher/owner角色。适用于：教师说'提醒一下某某''通知学生'。不适用于：群发通知。",
    ),
    ToolMeta(
        name="list_courses",
        description="浏览机构课程库",
        body="查询本机构课程。参数: subject(str)=学科筛选(可选), query(str)=关键词搜索(可选), limit(int)=数量上限(默认10)。返回：课程标题、学科、难度、时长。适用于：教师说'看看我的课程''有哪些视频课'。不适用于：搜索知识点。",
    ),
    ToolMeta(
        name="list_questions",
        description="浏览机构题库",
        body="查询本机构题目。参数: kp_name(str)=知识点搜索(可选), subject(str)=学科筛选(可选), q_type(str)=题型筛选(可选), difficulty(str)=难度筛选(可选), limit(int)=数量上限(默认20)。返回：题干摘要、题型、难度、知识点。适用于：教师说'看看题库''有没有关于X的题'。不适用于：出题（用quick_generate）。",
    ),
    ToolMeta(
        name="list_articles",
        description="浏览机构文章库",
        body="查询本机构文章。参数: query(str)=关键词搜索(可选), limit(int)=数量上限(默认10)。返回：标题、摘要、发布日期。适用于：教师说'看看文章''有没有关于X的文章'。不适用于：搜索知识点。",
    ),
    ToolMeta(
        name="list_classes",
        description="获取机构下的所有班级列表",
        body="查询当前机构的所有班级。参数: 无。返回：班级ID、名称、学生数。适用于：教师说'有哪些班''班级列表'。不适用于：查看班级成绩（用get_class_gradebook）。",
    ),
    ToolMeta(
        name="assign_class_course",
        description="将课程分配给指定班级",
        body="创建班级与课程的关联。参数: class_id(int)=班级ID, course_id(int)=课程ID。返回：分配结果。适用于：教师说'把XX课程分配给X班''给X班加XX课'。不适用于：查看班级课程列表。",
    ),
    ToolMeta(
        name="get_class_gradebook",
        description="获取班级成绩册（学生×作业矩阵）",
        body="查询班级内所有学生的作业成绩。参数: class_id(int)=班级ID。返回：学生列表、作业列表、每个学生在每项作业的得分。适用于：教师说'看看X班成绩''成绩册''X班学得怎么样'。不适用于：查看单个学生详情（用get_student_detail）。",
    ),
    ToolMeta(
        name="grade_submissions",
        description="批改学生作业提交",
        body="为学生的作业提交打分。参数: submission_id(int)=提交ID, score(number)=评分, feedback(str)=评语(可选)。返回：更新后的提交信息。适用于：教师说'给XX分''批改这份作业'。不适用于：查看作业进度（用get_assignment_progress）。",
    ),
]

# bot_type → 工具元数据列表
BOT_TOOL_REGISTRY: Dict[str, List[ToolMeta]] = {
    "planner": PLANNER_TOOLS_META,
    "exam_generator": EXAM_GENERATOR_TOOLS_META,
}

# ── Embedding 检索（Stage 1）──────────────────────────────────

_embedding_cache: Dict[str, List[List[float]]] = {}  # bot_type → embeddings
_tool_names_cache: Dict[str, List[str]] = {}          # bot_type → tool names


def _cosine_similarity(a: List[float], b: List[float]) -> float:
    """计算余弦相似度。"""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _get_embedding_api_url() -> str:
    """获取 embedding API URL。"""
    from ai_engine.config import EMBEDDING_BASE_URL
    return f"{EMBEDDING_BASE_URL}/embeddings"


def _call_embedding_api(texts: List[str]) -> List[List[float]]:
    """调用 DeepSeek embedding API 获取向量。"""
    import httpx
    api_url = _get_embedding_api_url()
    api_key = os.getenv('LLM_API_KEY', '')
    resp = httpx.post(
        api_url,
        json={"model": os.getenv('AI_EMBEDDING_MODEL', 'deepseek-embedding'), "input": texts},
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    # 按 index 排序确保顺序一致
    embeddings = sorted(data["data"], key=lambda x: x["index"])
    return [e["embedding"] for e in embeddings]


def _ensure_embeddings(bot_type: str) -> bool:
    """预计算并缓存工具 body embeddings。返回是否成功。"""
    # DeepSeek 不支持 /v1/embeddings 端点，暂禁用 embedding 路由，
    # 所有工具路由走关键词匹配 fallback。
    # 后续切换到支持 embedding 的 provider 时移除此行即可。
    return False

    if bot_type in _embedding_cache:
        return True

    tools_meta = BOT_TOOL_REGISTRY.get(bot_type, [])
    if not tools_meta:
        return False

    try:
        texts = [f"{t.name}: {t.description}\n{t.body}" for t in tools_meta]
        embeddings = _call_embedding_api(texts)
        _embedding_cache[bot_type] = embeddings
        _tool_names_cache[bot_type] = [t.name for t in tools_meta]
        logger.info("Embedded %d tools for bot_type=%s", len(tools_meta), bot_type)
        return True
    except Exception:
        logger.exception("Failed to compute tool embeddings for bot_type=%s", bot_type)
        return False


def _retrieve_candidates(query: str, bot_type: str, top_k: int = 8,
                         min_score: float = 0.35) -> List[str]:
    """Stage 1: 用 embedding 相似度检索 top-k 候选工具名。

    当最高相似度低于 min_score 时返回空列表，避免无意义输入
    匹配到不相关工具。
    """
    if not _ensure_embeddings(bot_type):
        return []

    try:
        query_emb = _call_embedding_api([query])[0]
        tool_embs = _embedding_cache[bot_type]
        tool_names = _tool_names_cache[bot_type]

        scores = [(name, _cosine_similarity(query_emb, emb))
                  for name, emb in zip(tool_names, tool_embs)]
        scores.sort(key=lambda x: x[1], reverse=True)

        if scores[0][1] < min_score:
            logger.info("route_tools: top score %.3f < %.3f, skipping embedding candidates",
                        scores[0][1], min_score)
            return []

        return [name for name, _ in scores[:top_k]]
    except Exception:
        logger.exception("Embedding retrieval failed")
        return []


# ── 关键词匹配 Fallback ───────────────────────────────────────

PLANNER_INTENT_MAP = {
    "planning": {
        "keywords": ["规划", "安排", "计划", "复习", "备考", "学习计划", "日程", "每周", "今天做什么"],
        "tools": [
            "get_learning_stats", "get_knowledge_mastery_map",
            "get_due_reviews", "save_study_plan", "get_active_plan",
            "update_plan_task", "render_visual",
        ],
    },
    "analysis": {
        "keywords": ["分析", "掌握率", "薄弱", "趋势", "成绩", "正确率", "统计", "报告", "难度"],
        "tools": [
            "get_learning_stats", "get_knowledge_mastery_map",
            "get_class_weak_points", "get_class_performance_summary",
            "get_exam_history", "get_knowledge_difficulty_analysis", "render_visual",
        ],
    },
    "quiz": {
        "keywords": ["出题", "出几道", "做题", "练习", "测试", "考试", "刷题", "模拟", "真题"],
        "tools": [
            "get_user_wrong_questions", "get_due_reviews",
            "lookup_question", "search_knowledge_tree",
            "get_practice_questions", "get_user_weak_points", "render_visual",
        ],
    },
    "resource": {
        "keywords": ["课程", "视频", "文章", "资料", "推荐", "学习资源"],
        "tools": [
            "search_courses", "search_asr", "search_articles", "render_visual",
        ],
    },
    "error_review": {
        "keywords": ["错题", "错误", "做错了", "哪里错", "错因"],
        "tools": [
            "get_user_wrong_questions", "get_user_weak_points",
            "lookup_question", "render_visual",
        ],
    },
    "dashboard": {
        "keywords": ["面板", "仪表盘", "dashboard", "卡片", "指标"],
        "tools": [
            "render_visual",
        ],
    },
    "grading": {
        "keywords": ["批改", "判分", "评分", "对不对", "我的答案", "帮我改", "帮我批"],
        "tools": [
            "grade_student_answer", "lookup_question", "render_visual",
        ],
    },
}

EXAM_GENERATOR_INTENT_MAP = {
    "weak_points": {
        "keywords": ["薄弱", "弱项", "薄弱点", "薄弱知识", "针对薄弱", "班级", "学情", "正确率低"],
        "tools": [
            "get_class_weak_points", "search_knowledge", "quick_generate",
            "get_class_gradebook",
        ],
    },
    "refine": {
        "keywords": ["精修", "arc", "润色", "改进", "提升", "高质量", "对抗", "审核", "题目质量"],
        "tools": [
            "launch_arc_pipeline", "check_pipeline_status",
        ],
    },
    "generate": {
        "keywords": ["出题", "生成", "命题", "出一组", "出几道", "给我出", "来几道", "新题",
                     "再来", "换", "调整", "改", "不同", "其他", "再难", "更难", "简单"],
        "tools": [
            "search_knowledge", "quick_generate", "launch_arc_pipeline",
            "get_workbench_stats", "get_class_weak_points",
        ],
    },
    "status": {
        "keywords": ["进度", "跑完没", "跑完了", "管线", "状态", "结果", "完成没", "好了吗"],
        "tools": [
            "check_pipeline_status",
        ],
    },
    "stats": {
        "keywords": ["统计", "多少题", "出题情况", "分布", "面板", "题库统计", "出题统计"],
        "tools": [
            "get_workbench_stats",
        ],
    },
    "student_lookup": {
        "keywords": ["学生", "学员", "学得怎么样", "学习情况", "成绩", "表现", "看看谁",
                     "看一下", "查一下", "某某", "错误多", "没交"],
        "tools": [
            "get_student_detail", "send_notification", "get_class_weak_points",
        ],
    },
    "assignment": {
        "keywords": ["作业", "提交", "进度", "交了没", "批改", "交作业", "布置", "发布",
                     "分配", "下发", "发下去", "布置给", "安排练习"],
        "tools": [
            "get_assignment_progress", "assign_practice",
            "assign_class_course", "grade_submissions",
        ],
    },
    "browse": {
        "keywords": ["课程", "视频", "看看课程", "有什么课", "文章", "看看文章",
                     "看看题库", "有什么题", "搜索题", "浏览", "资产", "有没有", "有哪些"],
        "tools": [
            "list_courses", "list_questions", "list_articles",
            "list_classes",
        ],
    },
}

BOT_INTENT_MAP: Dict[str, Dict] = {
    "planner": PLANNER_INTENT_MAP,
    "exam_generator": EXAM_GENERATOR_INTENT_MAP,
}


def _classify_intent_llm(user_message: str, bot_type: str = "planner") -> str | None:
    """使用 fast model 分类意图。返回 None 表示需要 fallback 到关键词。

    一次轻量调用，temperature=0，max_tokens=20，约 5-10ms。
    """
    from ai_engine.service import AIEngine

    intent_map = BOT_INTENT_MAP.get(bot_type, PLANNER_INTENT_MAP)
    labels = list(intent_map.keys()) + ["general"]

    # 为每个 label 准备简短提示
    label_hints = []
    for label in labels:
        config = intent_map.get(label, {})
        hints = config.get("keywords", [])
        hint_text = ", ".join(hints[:3]) if hints else "anything not matching other intents"
        label_hints.append(f"- {label}: {hint_text}")

    system = (
        "Classify the user message into one intent label. "
        "Reply ONLY the label, nothing else.\n"
        "If the message is meaningless, ambiguous, or does not clearly match any intent, reply 'general'.\n\n"
        + "\n".join(label_hints)
    )

    try:
        result = AIEngine.call_ai(
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_message},
            ],
            temperature=0.0,
            max_tokens=20,
            operation="intent_classify",
        )
        if result and "choices" in result:
            raw = result["choices"][0]["message"]["content"]
            content = (raw or "").strip().lower()
            # 提取第一个词/行
            label = content.split("\n")[0].split()[0].strip(" .,;:")
            if label in labels:
                return label
            logger.warning("LLM intent classification returned unexpected label %r", raw)
    except Exception:
        logger.exception("LLM intent classification failed, falling back to keywords")

    return None


def classify_intent(user_message: str, recent_messages: List[Dict[str, str]] = None,
                    bot_type: str = "planner") -> str:
    """分类用户意图：LLM 优先，关键词匹配保底。"""
    # LLM 优先
    result = _classify_intent_llm(user_message, bot_type)
    if result:
        return result

    # 关键词保底
    intent_map = BOT_INTENT_MAP.get(bot_type, PLANNER_INTENT_MAP)
    text = user_message.lower()

    for intent, config in intent_map.items():
        for kw in config["keywords"]:
            if kw in text:
                return intent

    if recent_messages:
        context_text = " ".join(
            m.get("content", "") for m in recent_messages[-6:]
        ).lower()
        for intent, config in intent_map.items():
            for kw in config["keywords"]:
                if kw in context_text:
                    return intent

    return "general"


def _keyword_fallback(user_message: str, all_tools: List[dict],
                      recent_messages: List[dict] = None,
                      bot_type: str = "planner") -> List[dict]:
    """关键词匹配 fallback：根据意图筛选工具。

    当意图是 general（无关键词命中）时返回空列表，让 LLM 自由决定
    是否调用工具，而非强制绑定全量工具。
    """
    intent = classify_intent(user_message, recent_messages, bot_type=bot_type)
    intent_map = BOT_INTENT_MAP.get(bot_type, PLANNER_INTENT_MAP)
    allowed_names = intent_map.get(intent, {}).get("tools", [])

    if not allowed_names:
        return [] if intent == "general" else all_tools

    allowed_set = set(allowed_names)
    filtered = [t for t in all_tools if t["function"]["name"] in allowed_set]
    return filtered if len(filtered) >= 2 else all_tools


# ── 主路由函数 ─────────────────────────────────────────────────

def route_tools(
    user_message: str,
    all_tools: List[dict],
    recent_messages: List[Dict[str, str]] = None,
    bot_type: str = "planner",
) -> List[dict]:
    """工具路由：embedding 检索 + 关键词意图保底。

    路由链：embedding 检索 top-k → 合并关键词意图匹配的工具 → 全量工具
    """
    _dbg = logging.getLogger("agent_debug")
    all_names = [t["function"]["name"] for t in all_tools]

    # Stage 1: Embedding 检索
    candidates = _retrieve_candidates(user_message, bot_type, top_k=8)

    # Stage 2: 关键词意图匹配（始终执行，作为保底）
    intent = classify_intent(user_message, recent_messages, bot_type=bot_type)
    intent_map = BOT_INTENT_MAP.get(bot_type, PLANNER_INTENT_MAP)
    intent_tools = set(intent_map.get(intent, {}).get("tools", []))

    if candidates:
        # 合并 embedding 候选 + 意图关键工具
        merged = set(candidates) | intent_tools
        filtered = [t for t in all_tools if t["function"]["name"] in merged]
        if filtered:
            filtered_names = [t["function"]["name"] for t in filtered]
            has_rv = "render_visual" in filtered_names
            _dbg.info("route_tools(merged): msg=%r intent=%s tools=%d→%d render_visual=%s candidates=%s intent_tools=%s",
                       user_message[:60], intent, len(all_tools), len(filtered), has_rv, candidates, sorted(intent_tools))
            return filtered

    # Fallback: 纯关键词匹配
    result = _keyword_fallback(user_message, all_tools, recent_messages, bot_type)
    result_names = [t["function"]["name"] for t in result]
    has_rv = "render_visual" in result_names
    _dbg.info("route_tools(keyword): msg=%r intent=%s tools=%d→%d render_visual=%s",
              user_message[:60], intent, len(all_tools), len(result), has_rv)
    return result
