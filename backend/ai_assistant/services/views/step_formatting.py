"""L4 View Layer — human-readable tool step labels, summaries and action extraction for SSE/UI."""
import json


def generate_step_label(tool_name: str, args: dict) -> str:
    """根据 tool name 和 args 动态生成中文步骤描述。"""
    labels = {
        'manage_learning_resources': lambda a: '整理与复用我的学习资料',
        'manage_learning_strategies': lambda a: '查阅教学方法与后续表现',
        'manage_learning_tasks': lambda a: '安排正式学习任务与查看结果',
        'manage_learning_knowledge': lambda a: '组织知识地图与证据检查',
        'read_learning_project': lambda a: '读取这个项目的学习安排',
        'plan_learning_project': lambda a: '整理阶段路径与下一步',
        'record_learning_progress': lambda a: '记录这次表现与学习反馈',
        'set_learning_followup': lambda a: '调整后续学习与跟进',
        'find_learning_resources': lambda a: '查找并核对学习资料',
        'search_workbench_sources': lambda a: '检索本轮选中的项目资料',
        'read_workbench_source_chunks': lambda a: '阅读项目资料原文',
        'register_session_tool': lambda a: '编写并注册会话计算工具',
        'read_session_tool': lambda a: '读取会话工具代码与版本',
        'build_learning_experiment': lambda a: f"编写并检查「{a.get('title', '交互实验')}」",
        'read_learning_experiment': lambda a: "读取实验代码和当前操作状态",
        'search_knowledge_tree': lambda a: f"检索「{a.get('query', '')}」相关知识点",
        'get_user_weak_points': lambda a: "分析你的薄弱知识点",
        'get_user_wrong_questions': lambda a: f"查看{a.get('topic', '')}错题" if a.get('topic') else "查看你的错题记录",
        'lookup_question': lambda a: f"查找题目（ID: {a.get('question_id', '')}）",
        'get_learning_stats': lambda a: "获取学习统计数据",
        'get_learning_sessions': lambda a: "读取听课和做题时间记录",
        'get_knowledge_mastery_map': lambda a: f"生成{a.get('subject', '')}知识掌握图谱" if a.get('subject') else "生成知识掌握图谱",
        'get_due_reviews': lambda a: "查询到期待复习的题目",
        'get_exam_history': lambda a: "查询考试历史",
        'search_courses': lambda a: f"搜索课程「{a.get('query', '')}」",
        'search_asr': lambda a: f"搜索视频字幕「{a.get('query', '')}」",
        'run_course_tools': lambda a: '查找课程并定位讲稿',
        'locate_current_course_transcript': lambda a: '定位当前课程的讲稿',
        'search_articles': lambda a: f"搜索文章「{a.get('query', '')}」",
        'search_knowledge': lambda a: f"搜索知识点「{a.get('query', '')}」",
        'get_practice_questions': lambda a: f"抽取{a.get('kp_name', '')}相关练习题" if a.get('kp_name') else "抽取练习题",
        'get_recent_practice_result': lambda a: "读取最近一次练习结果",
        'grade_student_answer': lambda a: f"批改题目 #{a.get('question_id', '')}",
        'run_diagnostic': lambda a: "生成诊断题目" if a.get('mode') == 'generate' else "提交诊断答案",
        'quick_generate': lambda a: f"快速生成{a.get('count', 5)}道题",
        'render_visual': lambda a: f"渲染{a.get('type', '可视化')}",
        'launch_arc_pipeline': lambda a: "启动 ARC 精修管线",
        'check_pipeline_status': lambda a: "检查管线执行进度",
        'get_workbench_stats': lambda a: "获取题库统计",
        'get_student_detail': lambda a: f"查看「{a.get('student_name', a.get('student_id', '学生'))}」学习数据",
        'send_notification': lambda a: f"发送提醒给「{a.get('student_name', a.get('student_id', '学生'))}」",
        'list_courses': lambda a: "浏览课程库" + (f"（{a.get('subject', '')}）" if a.get('subject') else ""),
        'list_questions': lambda a: "浏览题库" + (f"（{a.get('kp_name', '')}）" if a.get('kp_name') else ""),
        'list_articles': lambda a: "浏览文章库" + (f"（搜索: {a.get('query', '')}）" if a.get('query') else ""),
        'get_report_card': lambda a: "生成学习报告",
        'generate_student_report': lambda a: f"生成「{a.get('student_name', a.get('student_id', '学生'))}」学情报告",
    }
    generator = labels.get(tool_name)
    if generator:
        try:
            return generator(args)
        except Exception:
            pass
    return f"执行 {tool_name}"


def extract_step_actions(result) -> list | None:
    """从工具结果 JSON 中提取 _actions 数组，用于前端渲染操作链接。"""
    if isinstance(result, str):
        try:
            result = json.loads(result)
        except Exception:
            return None
    if isinstance(result, dict):
        actions = result.get('_actions')
        if isinstance(actions, list) and len(actions) > 0:
            return actions
    return None


def summarize_tool_result(tool_name: str, result) -> str:
    """将工具结果转为人类可读摘要（用于前端步骤卡片展示）。"""
    if isinstance(result, str):
        try:
            result = json.loads(result)
        except Exception:
            return result[:200]

    if not isinstance(result, dict):
        return str(result)[:200]

    summaries = {
        'search_knowledge_tree': lambda r: f"找到 {r.get('found', 0)} 个知识点",
        'get_user_weak_points': lambda r: f"发现 {len(r.get('weak_points', []))} 个薄弱点",
        'get_learning_stats': lambda r: (
            f"已练 {r.get('attempted_questions', 0)} 题 · 最近正确率 {r.get('last_accuracy')}%"
            if r.get('has_attempts') else "尚未开始练习"
        ),
        'get_knowledge_mastery_map': lambda r: (
            f"诊断掌握 {(r.get('mastery') or {}).get('kp_count', 0)} 个知识点"
            if (r.get('mastery') or {}).get('kp_count') else "暂无诊断掌握数据"
        ),
        'get_due_reviews': lambda r: f"{r.get('due_count', 0)} 个待复习",
        'get_learning_sessions': lambda r: f"查到 {r.get('total_sessions', 0)} 次学习记录",
        'get_exam_history': lambda r: f"共 {len(r.get('exams', []))} 次考试",
        'get_recent_practice_result': lambda r: (
            f"最近练习 {r.get('total_score', 0)}/{r.get('max_score', 0)} · {r.get('status_text', '')}"
            if r.get('has_result') else r.get('message', '暂无练习记录')
        ),
        'search_courses': lambda r: f"找到 {len(r.get('courses', []))} 门课程",
        'search_articles': lambda r: f"找到 {len(r.get('articles', []))} 篇文章",
        'quick_generate': lambda r: f"生成 {r.get('count', len(r.get('questions', [])))} 道题",
        'render_visual': lambda r: (
            f"渲染失败: {r.get('error', '')}" if r.get('error')
            else f"渲染可视化: {(r.get('visual', {}) if isinstance(r.get('visual'), dict) else {}).get('type', r.get('type', ''))}"
        ),
        'get_user_wrong_questions': lambda r: f"找到 {r.get('total_found', 0)} 道错题",
        'search_asr': lambda r: f"找到 {r.get('total_found', 0)} 个视频片段",
        'search_workbench_sources': lambda r: f"找到 {len(r.get('chunks', []))} 个相关片段",
        'read_workbench_source_chunks': lambda r: f"已读取 {len(r.get('chunks', []))} 个片段",
        'get_practice_questions': lambda r: f"抽取 {len(r.get('questions', []))} 道练习题",
        'grade_student_answer': lambda r: f"得分 {r.get('score', 0)}/{r.get('max_score', 0)}" + (
            ' · ' + {'concept_error': '概念错误', 'calculation_error': '计算失误', 'careless_mistake': '审题失误'}.get(
                r.get('error_analysis', {}).get('type', ''), ''
            ) if r.get('error_analysis', {}).get('type') else ''
        ) + (f" · 推荐{len(r.get('remediation_questions', []))}道变式题" if r.get('remediation_questions') else ''),
        'run_diagnostic': lambda r: f"诊断完成，答对 {r.get('total_correct', 0)}/{r.get('total_questions', 0)}" if 'total_correct' in r else f"已生成 {len(r.get('questions', []))} 道诊断题",
        'get_student_detail': lambda r: f"{r.get('name', '')} 正确率 {r.get('accuracy', 0)}%" + (
            f"，{len(r.get('weak_points', []))} 个薄弱点" if r.get('weak_points') else ""),
        'send_notification': lambda r: f"已发送提醒给 {r.get('count', 0)} 人",
        'list_courses': lambda r: f"共 {r.get('total', 0)} 门课程",
        'list_questions': lambda r: f"共 {r.get('total', 0)} 道题",
        'list_articles': lambda r: f"共 {r.get('total', 0)} 篇文章",
        'get_report_card': lambda r: (
            f"已练 {r.get('attempted_questions', 0)} 题 · 最近正确率 {r.get('last_accuracy')}%"
            if r.get('has_attempts') else "尚未开始练习"
        ),
        'generate_student_report': lambda r: f"{r.get('student_name', '学生')} 学情报告 · {r.get('action', 'preview')}",
    }

    fn = summaries.get(tool_name)
    if fn:
        try:
            return fn(result)
        except Exception:
            pass

    for key in ('found', 'count', 'total', 'due_count', 'accuracy'):
        if key in result:
            return f"{key}: {result[key]}"
    return str(result)[:150]
