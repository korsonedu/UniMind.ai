"""
出题管线 Agent 的 JSON Schema 工具定义。

通过 tool_choice="required" 强制模型输出符合 schema 的结构化 JSON，
消除 regex-based extract_json() 的脆弱性。
"""

from copy import deepcopy

# ── 公共字段 ────────────────────────────────────────────────

_QUESTION_SCHEMA = {
    "type": "object",
    "properties": {
        "question": {"type": "string", "description": "题干（清晰、严谨、符合学科标准）"},
        "q_type": {"type": "string", "enum": ["objective", "subjective"]},
        "subjective_type": {
            "type": ["string", "null"],
            "enum": ["noun", "short", "essay", "calculate", None],
        },
        "options": {
            "type": ["array", "null"],
            "items": {"type": "string"},
            "description": "客观题为 [A.xx, B.xx, C.xx, D.xx]，主观题为 null",
        },
        "answer": {"type": "string", "description": "正确答案"},
        "grading_points": {
            "type": ["array", "null"],
            "items": {"type": "string"},
            "description": "主观题判分点，客观题为 null",
        },
        "difficulty_level": {
            "type": "string",
            "enum": ["entry", "easy", "normal", "hard", "extreme"],
        },
    },
    "required": [
        "question", "q_type", "subjective_type", "options",
        "answer", "grading_points", "difficulty_level",
    ],
}

_REVIEW_DIMENSIONS_SCHEMA = {
    "type": "object",
    "properties": {
        "discrimination": {
            "type": "number", "minimum": 0, "maximum": 1,
            "description": "区分度：是否能有效区分掌握者和未掌握者",
        },
        "clarity": {
            "type": "number", "minimum": 0, "maximum": 1,
            "description": "表述清晰度：题干是否无歧义，选项是否互斥",
        },
        "coverage": {
            "type": "number", "minimum": 0, "maximum": 1,
            "description": "知识覆盖度：是否准确命中目标知识点的核心内容",
        },
    },
    "required": ["discrimination", "clarity", "coverage"],
}

# ── Agent 工具定义 ───────────────────────────────────────────

AUTHOR_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "questions": {
            "type": "array",
            "items": deepcopy(_QUESTION_SCHEMA),
            "description": "生成的题目列表",
        },
    },
    "required": ["questions"],
}

REVIEWER_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "score": {
            "type": "number", "minimum": 0, "maximum": 1,
            "description": "综合质量分 (三维度均值)",
        },
        "feedback": {
            "type": "string",
            "description": "具体可操作的修改建议",
        },
        "dimensions": deepcopy(_REVIEW_DIMENSIONS_SCHEMA),
    },
    "required": ["score", "feedback", "dimensions"],
}

AUTHOR_REVISE_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "revised_question": deepcopy(_QUESTION_SCHEMA),
    },
    "required": ["revised_question"],
}

CLASSIFIER_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "detected_difficulty": {
            "type": "string",
            "enum": ["entry", "easy", "normal", "hard", "extreme"],
            "description": "AI 判定的题目实际难度",
        },
        "difficulty_match": {
            "type": "boolean",
            "description": "实际难度是否与目标难度一致",
        },
        "difficulty_mismatch_reason": {
            "type": "string",
            "description": "难度不一致时的具体原因（一致时为空字符串）",
        },
        "knowledge_tags": {
            "type": "array",
            "items": {"type": "string"},
            "description": "知识标签编码列表，1-5 个",
        },
        "question_type": {
            "type": "string",
            "enum": ["objective", "subjective"],
        },
        "subjective_type": {
            "type": ["string", "null"],
            "enum": ["noun", "short", "essay", "calculate", None],
        },
        "answer_correct": {
            "type": "boolean",
            "description": "题目答案是否事实正确（客观题检查正确选项是否确实正确，主观题检查参考答案是否覆盖核心要点且无误）",
        },
        "answer_accuracy_note": {
            "type": "string",
            "description": "答案不正确时的具体说明（正确时为空字符串）",
        },
        "bloom_level": {
            "type": "string",
            "enum": ["remember", "understand", "apply", "analyze", "evaluate", "create"],
            "description": "Bloom 认知层级",
        },
    },
    "required": ["detected_difficulty", "difficulty_match", "difficulty_mismatch_reason", "knowledge_tags", "question_type", "subjective_type", "answer_correct", "answer_accuracy_note", "bloom_level"],
}

BATCH_DIVERSITY_REPORT_SCHEMA = {
    "type": "object",
    "properties": {
        "similar_pairs": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "q1_index": {"type": "integer", "description": "题目 1 的序号（从 0 开始）"},
                    "q2_index": {"type": "integer", "description": "题目 2 的序号（从 0 开始）"},
                    "reason": {"type": "string", "description": "相似原因"},
                },
                "required": ["q1_index", "q2_index", "reason"],
            },
            "description": "高度相似的题目对",
        },
        "overall_assessment": {
            "type": "string",
            "description": "批次整体评价（100 字以内）",
        },
    },
    "required": ["similar_pairs", "overall_assessment"],
}

# ── 便捷包装 ─────────────────────────────────────────────────

def get_author_tool():
    return {
        "type": "function",
        "function": {
            "name": "submit_questions",
            "description": "提交生成的题目列表",
            "parameters": AUTHOR_OUTPUT_SCHEMA,
        },
    }

def get_reviewer_tool():
    return {
        "type": "function",
        "function": {
            "name": "submit_review",
            "description": "提交题目评审结果，含三维度评分和修改建议",
            "parameters": REVIEWER_OUTPUT_SCHEMA,
        },
    }

def get_author_revise_tool():
    return {
        "type": "function",
        "function": {
            "name": "submit_revised_question",
            "description": "提交根据 Reviewer 反馈修改后的题目",
            "parameters": AUTHOR_REVISE_OUTPUT_SCHEMA,
        },
    }

def get_classifier_tool():
    return {
        "type": "function",
        "function": {
            "name": "submit_classification",
            "description": "提交题目审计结果（难度审计 + 知识标签 + 题型分类 + 答案正确性 + Bloom 认知层级）",
            "parameters": CLASSIFIER_OUTPUT_SCHEMA,
        },
    }

def get_batch_diversity_tool():
    return {
        "type": "function",
        "function": {
            "name": "submit_diversity_report",
            "description": "提交批次多样性报告（相似题目 + 覆盖缺口 + 整体评价）",
            "parameters": BATCH_DIVERSITY_REPORT_SCHEMA,
        },
    }


# ── 通用任务输出 Schema ─────────────────────────────────────────

QUESTION_LIST_SCHEMA = {
    "type": "array",
    "items": deepcopy(_QUESTION_SCHEMA),
    "description": "题目列表",
}

GRADING_RESULT_SCHEMA = {
    "type": "object",
    "properties": {
        "score": {"type": "number", "description": "得分 (0 到 max_score)"},
        "feedback": {"type": "string", "description": "判分依据和深度解析"},
        "analysis": {"type": "string", "description": "标准答案（满分示范作答）"},
        "memorix_rating": {
            "type": "integer", "minimum": 1, "maximum": 4,
            "description": "Memorix 记忆评级: 1=完全不会, 2=困难回忆, 3=犹豫正确, 4=熟练正确",
        },
    },
    "required": ["score", "feedback", "analysis", "memorix_rating"],
}

OBJECTIVE_ANALYSIS_SCHEMA = {
    "type": "object",
    "properties": {
        "why_correct": {"type": "string", "description": "为什么正确答案是对的"},
        "why_wrong": {"type": "string", "description": "用户答案为什么错（答对时为空）"},
        "pitfalls": {"type": "string", "description": "易错点和避坑指南"},
    },
    "required": ["why_correct", "why_wrong", "pitfalls"],
}

BATCH_REVIEW_SCHEMA = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "index": {"type": "integer", "minimum": 1, "description": "题目序号（从 1 开始）"},
            "pass": {"type": "boolean", "description": "是否通过审查"},
            "issues": {
                "type": "array", "items": {"type": "string"},
                "description": "发现的问题列表",
            },
            "severity": {
                "type": "string", "enum": ["low", "medium", "high"],
                "description": "最严重问题的等级",
            },
        },
        "required": ["index", "pass", "issues", "severity"],
    },
    "description": "批量题目审核结果",
}

RESUME_TUNE_SCHEMA = {
    "type": "object",
    "properties": {
        "score": {"type": "integer", "minimum": 0, "maximum": 100, "description": "简历综合评分"},
        "diagnostics": {"type": "string", "description": "简历致命问题和改进方向"},
        "optimized_content": {
            "type": "object",
            "description": "润色后的简历内容",
            "properties": {
                "experience": {"type": "string", "description": "润色后的经历描述"},
            },
            "required": ["experience"],
        },
        "predicted_questions": {
            "type": "array", "items": {"type": "string"},
            "description": "面试官可能追问的深挖问题",
        },
    },
    "required": ["score", "diagnostics", "optimized_content", "predicted_questions"],
}

INTERVIEW_RADAR_SCHEMA = {
    "type": "object",
    "properties": {
        "radar_scores": {
            "type": "object",
            "description": "五维评分 (0-100)",
            "properties": {
                "theory": {"type": "integer", "minimum": 0, "maximum": 100},
                "logic": {"type": "integer", "minimum": 0, "maximum": 100},
                "stress": {"type": "integer", "minimum": 0, "maximum": 100},
                "fluency": {"type": "integer", "minimum": 0, "maximum": 100},
                "english": {"type": "integer", "minimum": 0, "maximum": 100},
            },
            "required": ["theory", "logic", "stress", "fluency", "english"],
        },
        "overall_feedback": {"type": "string", "description": "整体评价，150 字左右"},
    },
    "required": ["radar_scores", "overall_feedback"],
}

OUTLINE_ITEMS_SCHEMA = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "章节标题"},
            "timestamp_seconds": {"type": "number", "minimum": 0, "description": "起始时间戳（秒）"},
            "description": {"type": "string", "description": "章节内容概述"},
        },
        "required": ["title", "timestamp_seconds", "description"],
    },
    "description": "课程大纲条目列表",
}

# ── AI Assistant Agent 工具 Schema ─────────────────────────────

SEARCH_KNOWLEDGE_TREE_SCHEMA = {
    "type": "object",
    "properties": {
        "query": {
            "type": "string",
            "description": "搜索关键词，匹配知识点名称或描述",
        },
        "subject": {
            "type": "string",
            "description": "可选，限定学科（如'金融431''高中数学'），不传则搜索全部",
        },
    },
    "required": ["query"],
}

GET_USER_WEAK_POINTS_SCHEMA = {
    "type": "object",
    "properties": {},
    "description": "获取当前用户的薄弱知识点列表（按错误次数排序）",
}

GET_USER_WRONG_QUESTIONS_SCHEMA = {
    "type": "object",
    "properties": {
        "limit": {
            "type": "integer",
            "minimum": 1,
            "maximum": 10,
            "description": "返回数量，默认 5",
        },
    },
}

LOOKUP_QUESTION_SCHEMA = {
    "type": "object",
    "properties": {
        "question_id": {
            "type": "integer",
            "description": "题目 ID",
        },
    },
    "required": ["question_id"],
}

GET_CLASS_WEAK_POINTS_SCHEMA = {
    "type": "object",
    "properties": {
        "limit": {
            "type": "integer",
            "minimum": 1,
            "maximum": 10,
            "description": "返回数量，默认 5",
        },
    },
}

GET_CLASS_PERFORMANCE_SUMMARY_SCHEMA = {
    "type": "object",
    "properties": {},
}

# ── Planner Agent 工具 Schema ──────────────────────────────────

GET_LEARNING_STATS_SCHEMA = {
    "type": "object",
    "properties": {},
}

GET_KNOWLEDGE_MASTERY_MAP_SCHEMA = {
    "type": "object",
    "properties": {
        "subject": {
            "type": "string",
            "description": "可选，限定学科。不传则返回全部学科的掌握度地图。",
        },
    },
}

GET_DUE_REVIEWS_SCHEMA = {
    "type": "object",
    "properties": {
        "limit": {
            "type": "integer",
            "minimum": 1,
            "maximum": 50,
            "description": "返回数量，默认 20",
        },
    },
}

GET_EXAM_HISTORY_SCHEMA = {
    "type": "object",
    "properties": {
        "limit": {
            "type": "integer",
            "minimum": 1,
            "maximum": 20,
            "description": "返回考试次数，默认 10",
        },
    },
}

SAVE_STUDY_PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string", "description": "计划标题"},
        "summary": {"type": "string", "description": "计划摘要说明"},
        "tasks": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "description": {"type": "string"},
                    "day": {"type": "integer", "minimum": 1},
                    "subject": {"type": "string"},
                    "estimated_minutes": {"type": "integer", "minimum": 5},
                    "knowledge_point_ids": {
                        "type": "array", "items": {"type": "integer"},
                    },
                },
                "required": ["title", "day"],
            },
            "description": "任务列表",
        },
        "total_days": {"type": "integer", "minimum": 1, "description": "计划总天数"},
    },
    "required": ["title", "tasks"],
}

GET_ACTIVE_PLAN_SCHEMA = {
    "type": "object",
    "properties": {},
}

UPDATE_PLAN_TASK_SCHEMA = {
    "type": "object",
    "properties": {
        "plan_id": {"type": "integer", "description": "计划 ID"},
        "task_id": {"type": "string", "description": "任务 ID（如 task_1）"},
        "status": {
            "type": "string",
            "enum": ["completed", "skipped", "pending"],
            "description": "新状态",
        },
    },
    "required": ["plan_id", "task_id", "status"],
}

SET_DASHBOARD_LAYOUT_SCHEMA = {
    "type": "object",
    "properties": {
        "section_order": {
            "type": "array",
            "items": {
                "type": "string",
                "enum": ["plan", "stats", "mastery", "reviews", "exams", "custom_cards"],
            },
            "description": "Dashboard 区块排列顺序，从上到下。未列出的区块自动隐藏。custom_cards 是自定义数据卡片区块。",
        },
        "highlight": {
            "type": "string",
            "enum": ["plan", "stats", "mastery", "reviews", "exams", "custom_cards"],
            "description": "高亮（强调）的区块，该区块会以更醒目的样式展示。",
        },
    },
    "required": ["section_order"],
}

CREATE_DASHBOARD_CARD_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {
            "type": "string",
            "description": "卡片标题（如'本周学习概览'、'薄弱知识点 Top5'）",
        },
        "subtitle": {
            "type": "string",
            "description": "副标题/时间范围（如'5.22 - 5.28'），可选",
        },
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "label": {"type": "string", "description": "项目名称"},
                    "value": {"type": "string", "description": "项目值"},
                    "trend": {
                        "type": "string",
                        "enum": ["up", "down", "neutral"],
                        "description": "趋势方向（可选）",
                    },
                    "progress": {
                        "type": "number",
                        "minimum": 0,
                        "maximum": 100,
                        "description": "进度百分比 0-100，渲染为进度条（可选）",
                    },
                    "emphasis": {
                        "type": "boolean",
                        "description": "是否大字高亮展示（可选，适合关键数字）",
                    },
                    "action_link": {
                        "type": "string",
                        "description": "点击该数据项后跳转的前端路由（如'/tests/review'、'/knowledge-map'），可选",
                    },
                },
                "required": ["label", "value"],
            },
            "description": "数据项列表，2-8 个。每个项可自由组合 trend/progress/emphasis 来决定展示样式",
        },
        "cta": {
            "type": "object",
            "properties": {
                "label": {"type": "string", "description": "按钮文字（如'立即复习'、'查看详情'）"},
                "link": {"type": "string", "description": "点击后跳转的前端路由"},
            },
            "description": "卡片底部的行动按钮（可选），引导学生采取具体行动",
        },
    },
    "required": ["title", "items"],
}

SEARCH_COURSES_SCHEMA = {
    "type": "object",
    "properties": {
        "query": {
            "type": "string",
            "description": "搜索关键词（课程标题、知识点名称）",
        },
        "subject": {
            "type": "string",
            "description": "可选，限定学科（如'金融431''高中数学'）",
        },
        "limit": {
            "type": "integer",
            "minimum": 1,
            "maximum": 10,
            "description": "返回数量，默认 5",
        },
    },
    "required": ["query"],
}

SEARCH_ASR_SCHEMA = {
    "type": "object",
    "properties": {
        "query": {
            "type": "string",
            "description": "搜索关键词（知识点名称、概念）",
        },
        "course_id": {
            "type": "integer",
            "description": "可选，限定在某个课程内搜索",
        },
        "limit": {
            "type": "integer",
            "minimum": 1,
            "maximum": 10,
            "description": "返回数量，默认 5",
        },
    },
    "required": ["query"],
}

SEARCH_ARTICLES_SCHEMA = {
    "type": "object",
    "properties": {
        "query": {
            "type": "string",
            "description": "搜索关键词（文章标题、内容、标签）",
        },
        "limit": {
            "type": "integer",
            "minimum": 1,
            "maximum": 10,
            "description": "返回数量，默认 5",
        },
    },
    "required": ["query"],
}

# ── Reviewer Agent 研究工具 Schema ──────────────────────────────

LOOKUP_KNOWLEDGE_POINT_SCHEMA = {
    "type": "object",
    "properties": {
        "code": {
            "type": "string",
            "description": "知识点编码（如 MB-1001）",
        },
    },
    "required": ["code"],
}

SEARCH_SIMILAR_QUESTIONS_SCHEMA = {
    "type": "object",
    "properties": {
        "kp_code": {
            "type": "string",
            "description": "知识点编码（如 MB-1001），查找该知识点下已有题目",
        },
        "limit": {
            "type": "integer",
            "minimum": 1,
            "maximum": 10,
            "description": "返回数量，默认 5",
        },
    },
    "required": ["kp_code"],
}

# ── 工具工厂函数 ────────────────────────────────────────────────

def _make_tool(name, description, schema, impl_summary=""):
    desc = f"{description}\n\n实现逻辑：{impl_summary}" if impl_summary else description
    return {"type": "function", "function": {"name": name, "description": desc, "parameters": schema}}

def get_assistant_tools():
    """AI 助教 Agent 工具集。"""
    return [
        _make_tool("search_knowledge_tree", "搜索知识点树，按名称或描述查找匹配的知识点。用于回答'XX是什么''有哪些XX'等需要查知识点的问题。", SEARCH_KNOWLEDGE_TREE_SCHEMA,
            impl_summary="模糊匹配 knowledge_point 表的 name 和 description 字段，返回按 relevance 排序的节点列表。支持 subject 过滤。"),
        _make_tool("get_user_weak_points", "获取当前用户的薄弱知识点（错题最多的前几个知识点）。用于个性化辅导和复习建议。", GET_USER_WEAK_POINTS_SCHEMA,
            impl_summary="查询 quiz_attempt 表，按 knowledge_point 分组统计正确率，返回正确率最低的前 N 个知识点及错误次数。需要 user_id。"),
        _make_tool("get_user_wrong_questions", "获取当前用户最近的错题列表。用于分析错误模式、针对性讲解。", GET_USER_WRONG_QUESTIONS_SCHEMA,
            impl_summary="查询 quiz_attempt 表 WHERE is_correct=false，按 created_at 降序返回最近 N 条，包含题干、用户答案、正确答案。需要 user_id。"),
        _make_tool("lookup_question", "根据题目 ID 查询题目详情（题干、答案、解析）。用于讨论具体题目时获取准确信息。", LOOKUP_QUESTION_SCHEMA,
            impl_summary="主键查询 question 表，返回完整题目记录（题干、选项、答案、解析、知识点关联）。需要 question_id。"),
        _make_tool("get_class_weak_points", "获取班级最薄弱的知识点（按正确率排序）。仅教师/机构主可用，用于了解班级整体学习情况。", GET_CLASS_WEAK_POINTS_SCHEMA,
            impl_summary="查询 quiz_attempt 表 JOIN class 关联，按 knowledge_point 聚合班级平均正确率，返回最低的前 N 个。需要 class_id。"),
        _make_tool("get_class_performance_summary", "获取班级整体学习数据概览（学生数、活跃率、正确率、薄弱知识点数）。仅教师/机构主可用。", GET_CLASS_PERFORMANCE_SUMMARY_SCHEMA,
            impl_summary="聚合查询：COUNT(DISTINCT student)、最近7天活跃率、全局正确率、正确率<60%的知识点数。需要 class_id。"),
        _make_tool("search_courses", "搜索课程库，按关键词或学科查找推荐课程。用于在建议学习资源时提供具体课程链接。", SEARCH_COURSES_SCHEMA,
            impl_summary="全文搜索 course 表的 title 和 description，支持 subject 过滤，返回按 relevance 排序的课程列表（含 slug 用于前端链接）。"),
        _make_tool("search_asr", "搜索课程视频的 ASR 转录文本，找到某个知识点在视频中的具体时间位置。用于告诉学生'XX概念在课程YY的ZZ分ZZ秒处讲解'。", SEARCH_ASR_SCHEMA,
            impl_summary="查询 asr_segment 表的 transcript 字段做全文匹配，返回包含关键词的片段及对应时间戳（start_time），关联 course 和 video 信息。"),
        _make_tool("search_articles", "搜索深度文章库，按关键词查找相关文章。用于推荐学习资料和扩展阅读。", SEARCH_ARTICLES_SCHEMA,
            impl_summary="全文搜索 article 表的 title 和 body，返回按 relevance 排序的文章列表（含 slug 用于前端链接）。"),
    ]

def get_planner_tools():
    """学习规划师 Agent 工具集（含助教工具 + 规划专用工具）。"""
    assistant = get_assistant_tools()
    planner_only = [
        _make_tool("get_learning_stats", "获取用户学习统计概览（总做题量、正确率、学习连续天数、学科覆盖）。用于制定计划前了解学生现状。", GET_LEARNING_STATS_SCHEMA,
            impl_summary="聚合查询：COUNT(quiz_attempt)、AVG(is_correct)、计算最长连续学习天数、COUNT(DISTINCT subject)。需要 user_id。"),
        _make_tool("get_knowledge_mastery_map", "获取用户知识点掌握度地图，按学科/模块分组。用于识别薄弱环节，制定针对性计划。", GET_KNOWLEDGE_MASTERY_MAP_SCHEMA,
            impl_summary="查询 knowledge_mastery 表，按 subject → chapter → section 分组返回掌握度百分比。支持 subject 过滤。需要 user_id。"),
        _make_tool("get_due_reviews", "获取今日待复习的题目列表（来自间隔重复调度）。用于安排今日复习任务。", GET_DUE_REVIEWS_SCHEMA,
            impl_summary="查询 memorix_schedule 表 WHERE next_review <= today AND user_id=current_user，按 priority 降序返回待复习题目列表。"),
        _make_tool("get_exam_history", "获取用户的考试成绩历史和趋势。用于评估学习进展。", GET_EXAM_HISTORY_SCHEMA,
            impl_summary="查询 exam_record 表 WHERE user_id=current_user，按 created_at 降序返回最近 N 次考试成绩（分数、科目、日期）。"),
        _make_tool("save_study_plan", "将生成的学习计划持久化到数据库。调用后用户可在计划页面查看。", SAVE_STUDY_PLAN_SCHEMA,
            impl_summary="创建 study_plan 记录和关联的 plan_task 列表，设置 status='active'。如果已有 active plan，先标记为 superseded。需要 user_id。"),
        _make_tool("get_active_plan", "获取用户当前进行中的学习计划。用于查看已有计划或在修改前获取当前状态。", GET_ACTIVE_PLAN_SCHEMA,
            impl_summary="查询 study_plan 表 WHERE user_id=current_user AND status='active'，返回计划详情及关联的 plan_task 列表。"),
        _make_tool("update_plan_task", "更新学习计划中某个任务的状态（完成/跳过/重置）。", UPDATE_PLAN_TASK_SCHEMA,
            impl_summary="更新 plan_task 表的 status 字段（completed/skipped/pending），同时更新关联 study_plan 的 progress 百分比。需要 task_id。"),
        _make_tool("set_dashboard_layout", "配置小宇 Dashboard 面板的布局。根据学生当前状态决定展示哪些区块、排列顺序和高亮重点。每次对话后应调用此工具更新面板。", SET_DASHBOARD_LAYOUT_SCHEMA,
            impl_summary="创建或更新 dashboard_config 记录，存储 JSON 格式的布局配置（区块列表、排列顺序、高亮规则）。需要 user_id。"),
        _make_tool("create_dashboard_card", "在 Dashboard 中创建自定义数据卡片。根据学生当前数据自由组织展示内容：可包含趋势指标、进度条、高亮数字、普通文本等。每个 item 通过 trend/progress/emphasis 字段控制渲染样式。每次对话可创建多张卡片。", CREATE_DASHBOARD_CARD_SCHEMA,
            impl_summary="将卡片数据写入 user.dashboard_config.custom_cards[]，保留最近 10 张。前端根据 items 的字段自动选择渲染样式（进度条/趋势/高亮/普通行）。"),
    ]
    return assistant + planner_only

def get_reviewer_research_tools():
    """Reviewer Agent 研究工具集——在评分前查知识点定义和已有题目。"""
    return [
        _make_tool("lookup_knowledge_point_definition", "查询知识点的标准定义、范围和核心内容。用于验证题目是否准确命中目标知识点。", LOOKUP_KNOWLEDGE_POINT_SCHEMA,
            impl_summary="主键查询 knowledge_point 表，返回 name、description、parent 关联。用于 Reviewer 验证题目与知识点的匹配度。"),
        _make_tool("search_similar_questions", "搜索同一知识点下的已有题目。用于检查是否与现有题目雷同或重复。", SEARCH_SIMILAR_QUESTIONS_SCHEMA,
            impl_summary="查询 question 表 WHERE knowledge_point_id IN (...)，返回同知识点下的已有题目列表（题干、答案），用于去重检查。"),
    ]

# ── Exam Generator Agent 工具 Schema ──────────────────────────

SEARCH_KP_SCHEMA = {
    "type": "object",
    "properties": {
        "query": {
            "type": "string",
            "description": "搜索关键词（知识点名称或编码）",
        },
        "subject": {
            "type": "string",
            "description": "可选，限定学科（如'金融431''高中数学'）",
        },
    },
    "required": ["query"],
}

GENERATE_QUESTIONS_SCHEMA = {
    "type": "object",
    "properties": {
        "kp_ids": {
            "type": "array",
            "items": {"type": "integer"},
            "description": "知识点 ID 列表",
        },
        "count_per_kp": {
            "type": "integer",
            "minimum": 1,
            "maximum": 10,
            "description": "每个知识点生成的题数，默认 3",
        },
        "difficulty": {
            "type": "string",
            "enum": ["entry", "easy", "normal", "hard", "extreme", "mixed"],
            "description": "目标难度，默认 normal",
        },
        "types": {
            "type": "array",
            "items": {"type": "string"},
            "description": "题型筛选，如 ['objective', 'subjective:short']，不传则全题型",
        },
    },
    "required": ["kp_ids"],
}

LAUNCH_ARC_PIPELINE_SCHEMA = {
    "type": "object",
    "properties": {
        "kp_ids": {
            "type": "array",
            "items": {"type": "integer"},
            "description": "知识点 ID 列表",
        },
        "questions_per_kp": {
            "type": "integer",
            "minimum": 1,
            "maximum": 10,
            "description": "每个知识点的目标题数，默认 3",
        },
        "difficulty": {
            "type": "string",
            "enum": ["entry", "easy", "normal", "hard", "extreme"],
            "description": "目标难度，默认 normal",
        },
        "types": {
            "type": "array",
            "items": {"type": "string"},
            "description": "题型筛选",
        },
        "title": {
            "type": "string",
            "description": "任务标题，如'期中模拟卷 - 微积分'",
        },
    },
    "required": ["kp_ids"],
}

CHECK_PIPELINE_STATUS_SCHEMA = {
    "type": "object",
    "properties": {
        "task_id": {
            "type": "integer",
            "description": "管线任务 ID",
        },
    },
    "required": ["task_id"],
}

SAVE_QUESTIONS_TO_LIBRARY_SCHEMA = {
    "type": "object",
    "properties": {
        "question_indices": {
            "type": "array",
            "items": {"type": "integer"},
            "description": "要保存的题目序号（从 0 开始），不传则全部保存",
        },
    },
}


def get_exam_generator_tools():
    """出题 Agent 工具集。"""
    return [
        _make_tool("search_knowledge_points", "搜索可用知识点，按名称或编码查找。出题前先用此工具确认知识点存在。", SEARCH_KP_SCHEMA,
            impl_summary="模糊匹配 knowledge_point 表的 name 和 code 字段，支持 subject 过滤。返回知识点 ID 和名称，用于后续 generate_questions 的 kp_ids 参数。"),
        _make_tool("generate_questions", "快速生成题目（同步，约 10 秒）。根据知识点、难度、题型生成候选题目。", GENERATE_QUESTIONS_SCHEMA,
            impl_summary="调用 LLM 根据知识点描述生成题目 JSON，验证 schema 后存入内存候选池。返回生成的题目列表供用户审阅。支持 count、difficulty、types 参数。"),
        _make_tool("launch_arc_pipeline", "启动 ARC 精修管线（异步，2-5 分钟）。4-agent 对抗循环：Author→Reviewer→Revise→Classifier，质量更高。", LAUNCH_ARC_PIPELINE_SCHEMA,
            impl_summary="创建 PipelineTask 记录并 dispatch Celery 异步任务。执行 Author→Reviewer→AuthorRevise→Classifier 四阶段对抗，每阶段调用 LLM。返回 task_id 用于轮询进度。"),
        _make_tool("check_pipeline_status", "查询 ARC 管线的执行进度。", CHECK_PIPELINE_STATUS_SCHEMA,
            impl_summary="主键查询 pipeline_task 表，返回 status（pending/running/completed/failed）、current_stage、progress 百分比、已生成题目数。"),
        _make_tool("save_questions_to_library", "将最近一次生成的题目存入机构题库。可选择保存全部或部分题目。", SAVE_QUESTIONS_TO_LIBRARY_SCHEMA,
            impl_summary="将候选池中的题目批量插入 question 表，关联 knowledge_point 和 institution。支持通过 question_indices 选择性保存。"),
    ]
