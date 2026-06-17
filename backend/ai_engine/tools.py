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
        "error_analysis": {
            "type": "object",
            "description": "错因分析。仅当 score < max_score * 0.6 时填写；否则设为 null",
            "properties": {
                "type": {
                    "type": "string",
                    "enum": ["concept_error", "calculation_error", "careless_mistake"],
                    "description": "错因类型",
                },
                "reasoning": {"type": "string", "description": "错因详细分析"},
                "suggested_focus": {"type": "string", "description": "针对性强化建议"},
            },
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

GET_KNOWLEDGE_DIFFICULTY_ANALYSIS_SCHEMA = {
    "type": "object",
    "properties": {
        "subject": {
            "type": "string",
            "description": "可选，限定学科。不传则返回全部学科的难度分析。",
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

GET_PRACTICE_QUESTIONS_SCHEMA = {
    "type": "object",
    "properties": {
        "kp_name": {
            "type": "string",
            "description": "知识点名称（模糊匹配）",
        },
        "subject": {
            "type": "string",
            "description": "学科过滤，如'高中数学'",
        },
        "difficulty": {
            "type": "string",
            "enum": ["entry", "easy", "normal", "hard", "extreme"],
            "description": "难度等级过滤",
        },
        "limit": {
            "type": "integer",
            "minimum": 1,
            "maximum": 10,
            "description": "抽取题数，默认 5",
        },
        "exclude_mastered": {
            "type": "boolean",
            "description": "是否排除已掌握题目，默认 true",
        },
    },
}

GRADE_STUDENT_ANSWER_SCHEMA = {
    "type": "object",
    "properties": {
        "question_id": {
            "type": "integer",
            "description": "题目ID（来自 get_practice_questions 返回的题目 id）",
        },
        "user_answer": {
            "type": "string",
            "description": "学生的回答文本或选项（如 'A' 或完整作答文本）",
        },
    },
    "required": ["question_id", "user_answer"],
}

RUN_DIAGNOSTIC_SCHEMA = {
    "type": "object",
    "properties": {
        "mode": {
            "type": "string",
            "enum": ["generate", "submit"],
            "description": "generate=获取诊断题目，submit=提交诊断答案",
        },
        "answers": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "question_id": {"type": "integer", "description": "题目ID"},
                    "answer": {"type": "string", "description": "学生答案（选项字母或文本）"},
                },
                "required": ["question_id", "answer"],
            },
            "description": "submit 模式下必填，学生答案列表",
        },
    },
    "required": ["mode"],
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
        _make_tool("get_knowledge_difficulty_analysis", "获取知识点的 Memorix 难度分析，识别薄弱知识点。用于回答'我哪些知识点最薄弱'等问题。", GET_KNOWLEDGE_DIFFICULTY_ANALYSIS_SCHEMA,
            impl_summary="查询 UserQuestionStatus 表，按知识点聚合 avg_difficulty、avg_stability、total_reviews，返回掌握程度和 Memorix 洞察。"),
        _make_tool("get_practice_questions", "从题库中抽取相关题目供学生练习。支持按知识点、学科、难度筛选，优先返回做错过的题目。用于'给我出几道题''我想练练XX'等场景。", GET_PRACTICE_QUESTIONS_SCHEMA,
            impl_summary="查询 question 表，按知识点/学科/难度过滤，排除已掌握题目。优先返回 UserQuestionStatus 中 wrong_count>0 的薄弱题，再补充新题。随机抽取，返回题目列表（不含答案）。"),
        _make_tool("get_exam_history", "获取用户的考试成绩历史和趋势。用于评估学习进展。", GET_EXAM_HISTORY_SCHEMA,
            impl_summary="查询 exam_record 表 WHERE user_id=current_user，按 created_at 降序返回最近 N 次考试成绩（分数、科目、日期）。"),
        _make_tool("save_study_plan", "将生成的学习计划持久化到数据库。调用后用户可在计划页面查看。", SAVE_STUDY_PLAN_SCHEMA,
            impl_summary="创建 study_plan 记录和关联的 plan_task 列表，设置 status='active'。如果已有 active plan，先标记为 superseded。需要 user_id。"),
        _make_tool("get_active_plan", "获取用户当前进行中的学习计划。用于查看已有计划或在修改前获取当前状态。", GET_ACTIVE_PLAN_SCHEMA,
            impl_summary="查询 study_plan 表 WHERE user_id=current_user AND status='active'，返回计划详情及关联的 plan_task 列表。"),
        _make_tool("update_plan_task", "更新学习计划中某个任务的状态（完成/跳过/重置）。", UPDATE_PLAN_TASK_SCHEMA,
            impl_summary="更新 plan_task 表的 status 字段（completed/skipped/pending），同时更新关联 study_plan 的 progress 百分比。需要 task_id。"),
        _make_tool("render_visual", "在 Dashboard 画布上渲染可视化内容。用于展示数学推导过程、解题步骤、知识图谱、数据统计等需要视觉呈现的内容。纯文字问答不需要调用此工具。", RENDER_VISUAL_SCHEMA,
            impl_summary="将可视化数据（type + payload）返回给前端，前端根据 type 渲染到 Dashboard 画布。"),
        _make_tool("grade_student_answer", "批改学生对某道题的回答。传入题目ID和学生答案，返回评分、反馈、解析、变式题推荐和知识点掌握度。用于模拟考试和练习批改场景。", GRADE_STUDENT_ANSWER_SCHEMA,
            impl_summary="查找题目→GradingEngine.grade 判分→返回 score/feedback/analysis/remediation_questions/kp_breakdown。需要 question_id 和 user_answer。"),
        _make_tool("run_diagnostic", "启动诊断测试。generate 模式返回题目列表和时间限制；submit 模式提交答案，返回评分结果和学习计划建议。用于新用户首次评估。", RUN_DIAGNOSTIC_SCHEMA,
            impl_summary="调用 diagnostic_service 的 generate_diagnostic_questions 和 grade_diagnostic_answers。generate 从题库随机抽取客观题；submit 评分后初始化 Memorix 状态并生成学习建议。"),
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

SEARCH_KNOWLEDGE_SCHEMA = {
    "type": "object",
    "properties": {
        "query": {
            "type": "string",
            "description": "搜索关键词（知识点名称、编码或知识树节点名称）",
        },
        "subject": {
            "type": "string",
            "description": "可选，限定学科（如'金融431''高中数学'）",
        },
        "mode": {
            "type": "string",
            "enum": ["kp", "tree", "auto"],
            "description": "搜索模式：kp=仅搜知识点，tree=仅搜知识树，auto=先搜kp再搜tree（默认）",
        },
    },
    "required": ["query"],
}

QUICK_GENERATE_SCHEMA = {
    "type": "object",
    "properties": {
        "kp_ids": {
            "type": "array",
            "items": {"type": "integer"},
            "description": "知识点 ID 列表",
        },
        "count": {
            "type": "integer",
            "minimum": 1,
            "maximum": 20,
            "description": "总题数，默认 5",
        },
        "difficulty": {
            "type": "string",
            "enum": ["entry", "easy", "normal", "hard", "extreme"],
            "description": "题目难度。用户说「简单/基础」→ easy，「适中/中等」→ normal，「困难/难题」→ hard，「极难」→ extreme。默认 normal。",
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
            "description": "任务标题，如'期中模拟卷'",
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

GET_WORKBENCH_STATS_SCHEMA = {
    "type": "object",
    "properties": {
        "scope": {
            "type": "string",
            "enum": ["summary", "recent", "insights"],
            "description": "数据范围：summary=题库统计（默认），recent=最近出题，insights=教师偏好",
        },
    },
}

GET_STUDENT_DETAIL_SCHEMA = {
    "type": "object",
    "properties": {
        "student_name": {"type": "string", "description": "学生姓名/昵称（模糊匹配）"},
        "student_id": {"type": "integer", "description": "学生 ID（精确匹配，优先级高于 name）"},
    },
}

GET_ASSIGNMENT_PROGRESS_SCHEMA = {
    "type": "object",
    "properties": {
        "assignment_id": {"type": "integer", "description": "作业 ID"},
    },
    "required": ["assignment_id"],
}

ASSIGN_PRACTICE_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string", "description": "作业标题"},
        "question_ids": {"type": "array", "items": {"type": "integer"}, "description": "题目 ID 列表"},
        "class_names": {"type": "array", "items": {"type": "string"}, "description": "目标班级名称列表"},
        "due_date": {"type": "string", "description": "截止日期（ISO 格式，如 2026-06-20）"},
        "points_per_question": {"type": "integer", "description": "每题分值，默认 1"},
    },
    "required": ["title", "question_ids"],
}

SEND_NOTIFICATION_SCHEMA = {
    "type": "object",
    "properties": {
        "student_name": {"type": "string", "description": "学生姓名（模糊匹配）"},
        "student_id": {"type": "integer", "description": "学生 ID（精确匹配，优先级高于 name）"},
        "title": {"type": "string", "description": "通知标题"},
        "content": {"type": "string", "description": "通知正文内容"},
    },
    "required": ["content"],
}

LIST_COURSES_SCHEMA = {
    "type": "object",
    "properties": {
        "subject": {"type": "string", "description": "按学科筛选"},
        "query": {"type": "string", "description": "按标题/描述搜索关键词"},
        "limit": {"type": "integer", "description": "返回数量上限，默认 10"},
    },
}

LIST_QUESTIONS_SCHEMA = {
    "type": "object",
    "properties": {
        "kp_name": {"type": "string", "description": "按知识点名称搜索"},
        "subject": {"type": "string", "description": "按学科筛选"},
        "q_type": {"type": "string", "description": "题型筛选：objective/subjective/calculation/short/essay"},
        "difficulty": {"type": "string", "description": "难度筛选：entry/easy/normal/hard/extreme"},
        "limit": {"type": "integer", "description": "返回数量上限，默认 20"},
    },
}

LIST_ARTICLES_SCHEMA = {
    "type": "object",
    "properties": {
        "query": {"type": "string", "description": "按标题/内容搜索关键词"},
        "limit": {"type": "integer", "description": "返回数量上限，默认 10"},
    },
}

LIST_CLASSES_SCHEMA = {
    "type": "object",
    "properties": {},
}

ASSIGN_CLASS_COURSE_SCHEMA = {
    "type": "object",
    "properties": {
        "class_id": {"type": "integer", "description": "班级 ID"},
        "course_id": {"type": "integer", "description": "课程 ID"},
    },
    "required": ["class_id", "course_id"],
}

GET_CLASS_GRADEBOOK_SCHEMA = {
    "type": "object",
    "properties": {
        "class_id": {"type": "integer", "description": "班级 ID"},
    },
    "required": ["class_id"],
}

GRADE_SUBMISSIONS_SCHEMA = {
    "type": "object",
    "properties": {
        "submission_id": {"type": "integer", "description": "提交 ID"},
        "score": {"type": "number", "description": "评分"},
        "feedback": {"type": "string", "description": "评语（可选）"},
    },
    "required": ["submission_id", "score"],
}


def get_exam_generator_tools():
    """教师 Agent 工具集（18 个工具）。"""
    return [
        _make_tool("search_knowledge", "搜索知识点或知识树结构。出题前先用此工具确认知识点存在并获取 ID。", SEARCH_KNOWLEDGE_SCHEMA,
            impl_summary="合并搜索：mode=kp 时模糊匹配 knowledge_point 表的 name 和 code；mode=tree 时搜索知识树结构（sub/ch/sec 层级）；mode=auto 时先搜 kp，无结果则自动搜 tree。支持 subject 过滤。返回知识点 ID 和名称。"),
        _make_tool("quick_generate", "快速出题（Author 单步，约 5-10 秒）。根据知识点生成候选题目，教师审阅后可选择 ARC 精修。", QUICK_GENERATE_SCHEMA,
            impl_summary="调用 single_generate_pipeline 的 Author 阶段（skip_review=True），仅做 LLM 生成 + 去重 + schema 校验 + 本地完整性检查。返回题目列表存入内存候选池，通过 metadata 传给前端 QuestionPanel 展示。"),
        _make_tool("launch_arc_pipeline", "启动 ARC 精修管线（异步，2-5 分钟）。对已出的题目进行 4-agent 对抗精修：Author→Reviewer→Revise→Classifier。", LAUNCH_ARC_PIPELINE_SCHEMA,
            impl_summary="创建 PipelineTask 记录并 dispatch Celery 异步任务。返回 task_id 用于轮询进度。前端 QuestionPanel 有进度条实时展示。"),
        _make_tool("check_pipeline_status", "查询 ARC 管线的执行进度。", CHECK_PIPELINE_STATUS_SCHEMA,
            impl_summary="主键查询 pipeline_task 表，返回 status（pending/running/completed/failed）、current_stage、progress 百分比、已生成题目数。"),
        _make_tool("get_workbench_stats", "获取题库统计数据。教师问'出了多少题''题库情况'时使用。", GET_WORKBENCH_STATS_SCHEMA,
            impl_summary="scope=summary 返回总题数和按学科/难度/题型分布；scope=recent 返回最近 20 道题；scope=insights 返回教师出题偏好分析。所有数据按机构隔离。"),
        _make_tool("get_class_weak_points", "获取班级最薄弱的知识点（按正确率排序）。仅教师/机构主可用。教师说'针对薄弱点出题'时先调用此工具获取实际薄弱知识点，再用 search_knowledge 确认知识点 ID，最后 quick_generate。", GET_CLASS_WEAK_POINTS_SCHEMA,
            impl_summary="查询 UserQuestionStatus 表，按 knowledge_point 聚合学生正确率，返回最低的前 N 个知识点（含正确率、尝试次数、涉及学生数）。数据按机构隔离。"),
        # ── 新增数据类 ──
        _make_tool("get_student_detail", "获取指定学生的详细学习数据：正确率、薄弱知识点、ELO、周活跃度。教师提到学生名字或问'某某学得怎么样'时使用。", GET_STUDENT_DETAIL_SCHEMA,
            impl_summary="通过学生姓名或 ID 查找学生，汇总 UserQuestionStatus 中的答题正确率，聚合按知识点的错误计数，返回 ELO、周活跃度、Top 5 薄弱点。"),
        _make_tool("get_assignment_progress", "查询指定作业的提交和批改进度。教师问'作业交了没''还有谁没交'时使用。", GET_ASSIGNMENT_PROGRESS_SCHEMA,
            impl_summary="查询 Assignment 及其 target_classes 的学生总数，对比 AssignmentSubmission 的提交数和已批改数，返回 submitted/unsubmitted/graded/pending_grade 四维统计。"),
        # ── 新增行动类 ──
        _make_tool("assign_practice", "创建作业并发布给学生。教师出题后说'布置给X班'时使用，会同时在学生端刷题套件中展示。", ASSIGN_PRACTICE_SCHEMA,
            impl_summary="创建 Assignment 记录（status=published），关联指定题目和目标班级，可选设置截止日期。成功后学生端刷题套件的推题区域立即可见。"),
        _make_tool("send_notification", "向指定学生发送学习提醒通知。教师说'提醒一下某某'时使用。", SEND_NOTIFICATION_SCHEMA,
            impl_summary="查找目标学生（按姓名或 ID），创建 Notification 记录（n_type=system），推送至学生端通知中心。"),
        # ── 新增内容浏览类 ──
        _make_tool("list_courses", "浏览机构课程库。教师说'看看我的课程'或'有哪些视频课'时使用。", LIST_COURSES_SCHEMA,
            impl_summary="查询 Course 表（按机构隔离），支持 subject 筛选和 title/description 搜索，返回课程 ID、标题、简介、学科和链接。"),
        _make_tool("list_questions", "浏览机构题库。教师说'看看题库'或'有没有关于X的题'时使用。", LIST_QUESTIONS_SCHEMA,
            impl_summary="查询 Question 表（按机构隔离），支持 kp_name/subject/q_type/difficulty 多维度筛选，返回题目 ID、文本预览、题型、难度和知识点。"),
        _make_tool("list_articles", "浏览机构文章库。教师说'看看文章'时使用。", LIST_ARTICLES_SCHEMA,
            impl_summary="查询 Article 表（按机构隔离），支持标题/内容搜索，返回文章 ID、标题、作者、标签和链接。"),
        _make_tool("list_classes", "获取机构下的所有班级列表。教师说'有哪些班''班级列表'时使用。", LIST_CLASSES_SCHEMA,
            impl_summary="查询 Class 表（按机构隔离），返回班级 ID、名称、学生数。"),
        _make_tool("assign_class_course", "将课程分配给班级。教师说'把XX课程分配给X班'时使用。", ASSIGN_CLASS_COURSE_SCHEMA,
            impl_summary="创建 ClassCourse 记录关联班级和课程，返回分配结果。"),
        _make_tool("get_class_gradebook", "获取班级成绩册：每个学生在每次作业中的得分。教师说'看看X班成绩''成绩册'时使用。", GET_CLASS_GRADEBOOK_SCHEMA,
            impl_summary="查询 Assignment 和 AssignmentSubmission 表，按学生汇总作业得分，返回成绩矩阵。"),
        _make_tool("grade_submissions", "批改学生作业提交。教师说'给XX分''批改'时使用。", GRADE_SUBMISSIONS_SCHEMA,
            impl_summary="更新 AssignmentSubmission 的 score、graded_by、graded_at 字段，返回更新后的提交信息。"),
    ]

# ── 小宇可视化工具 Schema ──────────────────────────────────────

RENDER_VISUAL_SCHEMA = {
    "type": "object",
    "properties": {
        "type": {
            "type": "string",
            "enum": ["data_card", "latex_derivation", "step_solution", "knowledge_map", "action_cards"],
            "description": "可视化类型。data_card=数据卡片，latex_derivation=数学推导，step_solution=解题步骤，knowledge_map=知识图谱，action_cards=行动引导卡片",
        },
        "payload": {
            "type": "object",
            "description": (
                "可视化内容，结构由 type 决定：\n"
                "• data_card: {title: string, subtitle?: string, items: [{label, value, trend?: 'up'|'down'|'neutral', progress?: 0-100, emphasis?: bool, action_link?: string}], cta?: {label, link}}\n"
                "• latex_derivation: {title: string, steps: [{latex: string, note?: string}]}\n"
                "• step_solution: {title: string, steps: [{text: string, latex?: string}]}\n"
                "• knowledge_map: {title?: string, nodes: [{id: string, label: string, mastery?: 0-1}], edges: [{from: string, to: string}], highlights?: [string]}\n"
                "• action_cards: {title?: string, cards: [{title, description, icon(video/quiz/review/course/chart/plan/exam), action: {type, url, label}, priority?(high/normal/low)}]}"
            ),
        },
        "priority": {
            "type": "string",
            "enum": ["high", "normal", "low"],
            "description": "可视化优先级。high 占满整行，normal/low 各占半行。默认 normal。",
        },
    },
    "required": ["type", "payload"],
}
