"""
意图路由器：基于 SkillRouter 论文的 embedding 检索 + 关键词 fallback。

核心洞察（SkillRouter arXiv:2603.22455）：
  tool body 是路由决策的决定性信号（91.7% 注意力集中在 body），
  仅用 name+description 会导致 29-44pp 精度下降。

路由链：Retrieve（embedding）→ Workflow Expansion → 关键词 fallback
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
    ToolMeta(
        name="get_knowledge_difficulty_analysis",
        description="获取知识点的Memorix难度分析",
        body="获取指定知识点的Memorix遗忘曲线分析数据。参数: kp_name(str)=知识点名称, user_id(int)=用户ID。返回: avg_difficulty、avg_stability、mastery_level、memorix_insight。适用于：学生问'为什么记不住''我哪些知识点最薄弱'。不适用于：查看整体统计数据。",
    ),
    ToolMeta(
        name="grade_student_answer",
        description="批改学生对主观题的回答",
        body="批改学生提交的主观题答案。参数: question_id(int)=题目ID, user_answer(str)=学生答案。返回: score、max_score、feedback、analysis、memorix_rating。适用于：学生说'帮我批改''对不对'、提交主观题答案。不适用于：客观题自动批改、批量批改。",
    ),
    ToolMeta(
        name="run_diagnostic",
        description="为学生运行诊断测试",
        body="为新用户或需要重新评估的学生启动诊断测试。参数: user_id(int)=用户ID, subject(str)=学科(可选)。返回: 诊断题目列表。适用于：新用户首次使用、需要重新评估学习水平。不适用于：日常练习（用get_practice_questions）。",
    ),
    ToolMeta(
        name="get_report_card",
        description="获取学生学习报告/成绩单",
        body="查看完整学习报告。触发词：学习报告、成绩单、我学得怎么样、我的学习数据、学习统计。参数: 无。返回：打卡天数、总答题量、正确率、已掌握知识点、ELO分数、最近考试、已解锁成就。适用于：学生主动询问学习进展时。",
    ),
    ToolMeta(
        name="get_my_courses",
        description="获取学生当前班级的课程列表",
        body="查看我的课程。触发词：我的课程、我在学什么、有什么课、课程列表。参数: 无。返回：课程标题、学科、班级名称。适用于：学生询问课程相关问题时。未加入班级时提示联系老师。",
    ),
    ToolMeta(
        name="get_my_achievements",
        description="获取学生成就列表和进度",
        body="查看成就/徽章。触发词：我的成就、徽章、拿到了什么、成就进度。参数: 无。返回：已解锁成就列表、全部成就及解锁状态。适用于：学生询问成就进展时。",
    ),
]

EXAM_GENERATOR_TOOLS_META = [
    ToolMeta(
        name="search_knowledge",
        description="搜索知识点或知识树结构",
        body="搜索知识点或知识树。触发词：搜索、查、找、有哪些知识点、XX属于哪个知识点。参数: query(str)=搜索关键词, subject(str)=学科(可选), mode(str)=搜索模式(kp/tree/auto,默认auto)。auto模式先搜知识点，无结果则搜知识树。返回：知识点ID和名称，或知识树节点。出题前必须先搜索获取知识点ID。不适用于：搜索题目（用list_questions）、搜索课程（用list_courses）、搜索文章（用list_articles）。",
    ),
    ToolMeta(
        name="quick_generate",
        description="快速生成新题目（Author单步，约5-10秒）",
        body="生成全新题目。触发词：出题、生成、出几道、来几道、给我出、新题、再来一组、换一道、再出。参数: kp_ids(list)=知识点ID列表, count(int)=总题数(默认5)。调用AI生成全新题目，不会从题库中选取已有题目。不适用于：随机抽题/抽取/选题/从题库选（用list_questions random=true）、精修题目（用launch_arc_pipeline）。",
    ),
    ToolMeta(
        name="launch_arc_pipeline",
        description="启动ARC对抗精修管线",
        body="对已有题目进行精修审核。触发词：精修、ARC、润色、改进、提升质量、对抗审核、管线。参数: kp_ids(list)=知识点ID列表, questions_per_kp(int)=每知识点题数(默认3), difficulty(str)=难度, types(list)=题型, title(str)=任务标题。返回：task_id用于追踪进度。不适用于：快速出题（用quick_generate）。",
    ),
    ToolMeta(
        name="check_pipeline_status",
        description="检查ARC管线执行状态",
        body="查询管线任务进度。触发词：进度、跑完没、好了吗、状态、结果、完成没。参数: task_id(int)=管线任务ID。返回：状态(pending/running/completed/failed)、当前阶段、进度百分比。",
    ),
    ToolMeta(
        name="get_workbench_stats",
        description="获取题库统计数据",
        body="查看题库概况。触发词：统计、多少题、出题情况、分布、题库统计、题库概况、出了多少。参数: scope(str)=数据范围(summary/recent/insights,默认summary)。summary返回总题数和分布；recent返回最近20道题；insights返回教师出题偏好。不适用于：出题、搜索知识点。",
    ),
    ToolMeta(
        name="get_student_detail",
        description="获取指定学生的详细学习数据（仅教师/机构主）",
        body="查询学生个人学习数据。触发词：学生、学员、学得怎么样、学习情况、成绩、表现、某某的数据、看一下谁、查一下谁。参数: student_name(str)=学生姓名模糊匹配, student_id(int)=学生ID精确匹配。需要teacher/owner角色。不适用于：查看全班数据（用get_class_weak_points或get_class_gradebook）。",
    ),
    ToolMeta(
        name="get_assignment_progress",
        description="查询指定作业的提交和批改进度（仅教师/机构主）",
        body="查询作业提交和批改情况。触发词：作业交了没、还有谁没交、提交进度、批改进度、作业#N进度。参数: assignment_id(int)=作业ID。返回：提交数/总人数、已批改数、待批改数、作业标题和截止日期。需要teacher/owner角色。不适用于：批改作业（用grade_submissions）。",
    ),
    ToolMeta(
        name="assign_practice",
        description="创建作业并布置给学生（仅教师/机构主）",
        body="创建作业记录并发布给学生。触发词：布置、发布、发下去、分配、下发、布置给、发给、安排练习。参数: title(str)=作业标题, question_ids(list)=题目ID列表（需先从list_questions获取或save_questions_to_bank入库）, class_names(list)=目标班级名, due_date(str)=截止日期(ISO), points_per_question(int)=每题分值。需要teacher/owner角色。不适用于：出题（先用list_questions抽题或quick_generate生成）。",
    ),
    ToolMeta(
        name="send_notification",
        description="向指定学生发送学习提醒通知（仅教师/机构主）",
        body="发送站内通知提醒。触发词：提醒、通知、告知、跟XX说。参数: student_name(str)或student_id(int)=目标学生, title(str)=通知标题, content(str)=通知正文。需要teacher/owner角色。不适用于：群发通知、查看通知。",
    ),
    ToolMeta(
        name="list_courses",
        description="浏览或查找机构课程库",
        body="从已有课程库中查找课程。触发词：看看课程、有什么课、找课程、选课、浏览课程、有哪些视频课。参数: subject(str)=学科筛选(可选), query(str)=关键词搜索(可选), limit(int)=数量上限(默认10)。返回：课程标题、学科、难度、时长。从机构已有课程中检索，不会创建新课程。不适用于：搜索知识点（用search_knowledge）。",
    ),
    ToolMeta(
        name="list_questions",
        description="从题库中浏览或随机抽题",
        body="从机构已有题库中选取题目。触发词：随机抽、抽取、抽几道、选题、选几道、从题库选、看看题库、有没有题、找题、浏览题库。这是从已有题库检索，不会生成新题目。参数: kp_name(str)=知识点搜索(可选), subject(str)=学科筛选(可选), q_type(str)=题型筛选(可选), difficulty(str)=难度筛选(可选), random(bool)=是否随机排列(默认false), limit(int)=数量上限(默认20)。返回：题目ID、题干摘要、题型、难度、知识点。教师说随机或抽取时必须传random=true。返回的题目ID可直接用于assign_practice。不适用于：生成新题（用quick_generate）、精修题目（用launch_arc_pipeline）。",
    ),
    ToolMeta(
        name="list_articles",
        description="浏览或查找机构文章库",
        body="从已有文章库中查找文章。触发词：看看文章、找文章、选文章、浏览文章、有没有文章。参数: query(str)=关键词搜索(可选), limit(int)=数量上限(默认10)。返回：标题、摘要、发布日期。从机构已有文章中检索，不会创建新文章。不适用于：搜索知识点（用search_knowledge）。",
    ),
    ToolMeta(
        name="get_class_weak_points",
        description="获取班级知识点薄弱分析",
        body="分析班级整体薄弱知识点。触发词：薄弱、弱项、薄弱点、薄弱知识、学情、正确率低、哪些知识点弱。参数: institution_id(int)=机构ID, class_name(str)=班级名(可选)。返回：班级各知识点正确率、最薄弱知识点。需要teacher/owner角色。不适用于：查看单个学生（用get_student_detail）。",
    ),
    ToolMeta(
        name="list_classes",
        description="获取机构下的所有班级列表，可按名称筛选",
        body="查询机构班级。触发词：有哪些班、班级列表、找XX班、查班级、看看班级。参数: name(str)=班级名称筛选(可选，模糊匹配)。返回：班级ID、名称、学生数。仅用于查找/列出班级，不会修改班级。不适用于：查看班级成绩（用get_class_gradebook）、搜索知识点（用search_knowledge）。",
    ),
    ToolMeta(
        name="assign_class_course",
        description="将课程分配给指定班级",
        body="建立班级与课程的关联。触发词：分配课程、给XX班加课、把XX课给XX班。参数: class_id(int)=班级ID, course_id(int)=课程ID。返回：分配结果。需要teacher/owner角色。不适用于：查看班级课程列表。",
    ),
    ToolMeta(
        name="get_class_gradebook",
        description="获取班级成绩册（学生×作业矩阵）",
        body="查看班级成绩。触发词：成绩册、看看X班成绩、班级成绩、X班学得怎么样。参数: class_id(int)=班级ID。返回：学生列表、作业列表、每个学生在每项作业的得分及统计。需要teacher/owner角色。不适用于：查看单个学生详情（用get_student_detail）。",
    ),
    ToolMeta(
        name="grade_submissions",
        description="批改学生作业提交",
        body="为学生作业打分。触发词：批改、判分、给XX分、批作业、判作业。参数: submission_id(int)=提交ID, score(number)=评分, feedback(str)=评语(可选)。返回：更新后的提交信息。需要teacher/owner角色。不适用于：查看作业进度（用get_assignment_progress）。",
    ),
    ToolMeta(
        name="create_teaching_plan",
        description="创建或更新班级教学计划",
        body="为班级设定教学目标并规划周进度。触发词：制定教学计划、设定目标、教学规划、XX班XX学科教学计划。参数: class_id(int)=班级ID(必填), subject(str)=学科, semester(str)=学期, week_count(int)=周数, goal(str)=目标(如'1年内高考130分'), deadline(str)=截止日期, target_score(int)=目标分数, current_level(str)=当前水平。返回：教学计划ID和目标信息。需要teacher/owner角色。",
    ),
    ToolMeta(
        name="get_teaching_plan_kps",
        description="查询教学计划列表或某周的知识点",
        body="不传 teaching_plan_id 时浏览机构所有教学计划。传入 teaching_plan_id 时查询该计划指定周的知识点。触发词：按教学计划出题、教案出题、有哪些教学计划、第X周出题。参数: teaching_plan_id(int)=教学计划ID(可选), week_number(int)=周号(可选)。",
    ),
    ToolMeta(
        name="render_visual",
        description="在对话中渲染可视化卡片（确认操作、选项选择、数据摘要）",
        body="渲染交互式卡片。触发词：展示卡片、让我选择、确认操作。参数: type(str)=可视化类型, payload(dict)=卡片数据。action_cards类型：导航卡片点击跳转页面，reply卡片点击发送消息到对话。适用于：需要教师确认操作、选择分支、展示数据摘要时。",
    ),
    ToolMeta(
        name="save_questions_to_bank",
        description="将生成的题目存入题库",
        body="把quick_generate生成的题目正式入库。触发词：入库、保存、存入题库、确认保留。参数: 无（自动使用最近一次quick_generate生成的题目）。返回：入库数量、题目ID列表（可用于assign_practice）。调用前应先render_visual让教师确认。不适用于：从题库抽题（用list_questions）。",
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

# ── 本地 Embedding 模型（sentence-transformers，优先级高于 API）──

_local_model = None
_LOCAL_MODEL_NAME = "BAAI/bge-small-zh-v1.5"


def _get_local_model():
    """Lazy-load 本地 embedding 模型，加载一次全局复用。"""
    global _local_model
    if _local_model is None:
        try:
            from sentence_transformers import SentenceTransformer
            _local_model = SentenceTransformer(_LOCAL_MODEL_NAME)
            logger.info("Local embedding model loaded: %s", _LOCAL_MODEL_NAME)
        except ImportError:
            logger.warning(
                "sentence-transformers not installed; embedding routing falls back to API"
            )
            return None
        except Exception:
            logger.exception("Failed to load local embedding model")
            return None
    return _local_model


def preload_embedding_model():
    """预加载本地 embedding 模型（Django 启动时调用）。"""
    _get_local_model()


def _call_embedding_local(texts: List[str]) -> List[List[float]]:
    """本地 sentence-transformers embedding，返回 float 向量列表。"""
    model = _get_local_model()
    if model is None:
        raise RuntimeError("Local embedding model not available")
    embeddings = model.encode(texts, normalize_embeddings=True)
    return [emb.tolist() for emb in embeddings]


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
    """获取文本的 embedding 向量：本地模型优先，HTTP API 降级。"""
    # Stage 1: 本地 sentence-transformers
    try:
        return _call_embedding_local(texts)
    except Exception:
        pass  # 静默降级到 API

    # Stage 2: HTTP API fallback
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
            "update_plan_task", "get_user_weak_points", "render_visual",
        ],
    },
    "analysis": {
        "keywords": ["分析", "掌握率", "薄弱", "趋势", "成绩", "正确率", "统计", "报告", "难度", "成就", "徽章", "学习报告", "学得怎么样"],
        "tools": [
            "get_learning_stats", "get_knowledge_mastery_map",
            "get_class_weak_points", "get_class_performance_summary",
            "get_exam_history", "get_knowledge_difficulty_analysis",
            "get_user_weak_points", "get_user_wrong_questions", "render_visual",
            "get_report_card", "get_my_achievements",
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
        "keywords": ["课程", "视频", "文章", "资料", "推荐", "学习资源", "我的课程", "有什么课", "我在学什么"],
        "tools": [
            "search_courses", "search_asr", "search_articles", "render_visual",
            "get_my_courses",
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
            "launch_arc_pipeline", "check_pipeline_status", "render_visual",
        ],
    },
    "generate": {
        "keywords": ["出题", "生成", "命题", "出一组", "出几道", "给我出", "来几道", "新题",
                     "再来", "换", "调整", "改", "不同", "其他", "再难", "更难", "简单"],
        "tools": [
            "search_knowledge", "quick_generate", "launch_arc_pipeline",
            "get_teaching_plan_kps", "get_class_weak_points",
            "render_visual",
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
            "get_assignment_progress", "get_class_gradebook",
        ],
    },
    "assignment": {
        "keywords": ["作业", "提交", "进度", "交了没", "批改", "交作业", "布置", "发布",
                     "分配", "下发", "发下去", "布置给", "安排练习", "选", "选题",
                     "教学计划", "教学规划", "设定目标", "制定计划", "学期规划"],
        "tools": [
            "get_assignment_progress", "assign_practice",
            "assign_class_course", "grade_submissions",
            "list_classes", "create_teaching_plan",
            "render_visual",
        ],
    },
    "browse": {
        "keywords": ["课程", "视频", "看看课程", "有什么课", "文章", "看看文章",
                     "看看题库", "有什么题", "搜索题", "浏览", "资产", "有没有", "有哪些",
                     "教案", "教学计划", "看看教案"],
        "tools": [
            "list_courses", "list_questions", "list_articles",
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

# 工作流延续信号：AI 上一轮在等用户回复来完成某工作流时，
# 当前消息的语义路由可能遗漏该工作流的关键工具。
_WORKFLOW_SIGNALS = {
    "assignment": ["作业", "标题", "截止", "班级", "布置", "发下去", "发"],
    "generate":   ["出题", "题目", "生成", "精修", "调整", "换"],
    "student_lookup": ["学生", "学得", "数据", "成绩"],
}


def _detect_active_workflow(recent_messages, bot_type: str) -> set:
    """检测 AI 是否在等待用户回复来完成工作流。返回需补充的工具名集合。"""
    if not recent_messages:
        return set()

    last_ai = ""
    for m in reversed(recent_messages[-4:]):
        if m.get("role") == "assistant" and m.get("content"):
            last_ai = m["content"]
            break
    if not last_ai:
        return set()

    if not any(m in last_ai for m in ["?", "？", "吗", "确认", "选择", "可以"]):
        return set()

    intent_map = BOT_INTENT_MAP.get(bot_type, PLANNER_INTENT_MAP)
    for wf_name, keywords in _WORKFLOW_SIGNALS.items():
        if any(kw in last_ai for kw in keywords):
            wf_tools = set(intent_map.get(wf_name, {}).get("tools", []))
            if wf_tools:
                logger.info(
                    "Workflow expansion: active=%s, injecting %d tools",
                    wf_name, len(wf_tools),
                )
                return wf_tools
    return set()


def route_tools(
    user_message: str,
    all_tools: List[dict],
    recent_messages: List[Dict[str, str]] = None,
    bot_type: str = "planner",
) -> List[dict]:
    """工具路由：Retrieve（embedding） + Workflow Expansion + 关键词保底。

    对齐 SkillRouter 两段式架构，但 Stage 2 做的是召回补全而非精度重排：
    1. Embedding 检索 top-k（纯语义，不混上下文）
    2. Workflow Expansion（AI 在等回复时补入该工作流的工具集）
    3. 合并意图关键词 → 输出；失败则关键词 fallback
    """
    _dbg = logging.getLogger("agent_debug")

    candidates = _retrieve_candidates(user_message, bot_type, top_k=8)
    intent = classify_intent(user_message, recent_messages, bot_type=bot_type)
    intent_map = BOT_INTENT_MAP.get(bot_type, PLANNER_INTENT_MAP)
    intent_tools = set(intent_map.get(intent, {}).get("tools", []))

    # Stage 2: Workflow Expansion
    workflow_tools = _detect_active_workflow(recent_messages, bot_type)

    if candidates:
        merged = set(candidates) | intent_tools | workflow_tools
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
