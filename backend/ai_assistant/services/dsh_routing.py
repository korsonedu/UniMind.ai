"""Small model-visible groups; discovery only reveals already authorized tools."""
from ai_engine.tool_router import classify_intent_keywords


GROUPS = {
    'project': ('目标学习与跟进', '读取当前项目；规划阶段、查公开资源、记录实际学习反馈、调整与主动跟进。', (
        'read_learning_project', 'plan_learning_project', 'record_learning_progress',
        'set_learning_followup', 'find_learning_resources', 'manage_learning_resources', 'manage_learning_strategies')),
    'knowledge': ('知识地图与证据路径', '组织带来源知识单元、有向前置关系与目标深度；登记检查任务并更新贝叶斯证据。', (
        'read_learning_project', 'manage_learning_knowledge', 'manage_learning_tasks', 'plan_learning_project', 'record_learning_progress',
        'manage_learning_resources', 'find_learning_resources')),
    'tasks': ('项目任务与成果复盘', '准备本人项目开放任务或题库练习，读取已提交原作答、评价标准和结果，安排补救与换题检验。无需先建知识地图。', (
        'read_learning_project', 'manage_learning_tasks', 'record_learning_progress', 'set_learning_followup',
        'get_practice_questions', 'lookup_question', 'search_knowledge_tree')),
    'interactive': ('交互讲题', '取题并编写交互实验，在同一分组内完成题目讲解和可操作实验。', (
        'get_practice_questions', 'lookup_question', 'search_knowledge_tree', 'build_learning_experiment',
        'read_learning_experiment', 'register_session_tool', 'read_session_tool')),
    'authoring': ('编写交互与计算工具', '根据学习任务编写、检查或修改交互实验，以及注册新的会话计算工具。', (
        'build_learning_experiment', 'read_learning_experiment', 'register_session_tool', 'read_session_tool')),
    'presentation': ('教学展示与回复选项', '展示公式推导、解题步骤、函数采样图和回复选项，不改变学生数据。', ('present_learning_visual',)),
    'support': ('人工答疑', '准备需要学生核对确认的人工答疑草稿，不自动发布。', ('create_faq_ticket',)),
    'focus': ('自习专注', '查自习室当前专注状态与每日专注历史，区别于听课和做题记录。', (
        'get_study_status', 'get_focus_history', 'get_learning_sessions')),
    'resources': ('课程与知识来源', '查课程、视频讲稿及知识点。', (
        'search_courses', 'search_asr', 'search_knowledge_tree')),
    'practice': ('题目与复习', '查错题、题目、到期复习、练习题和同类题，准备首次诊断作答卡。', (
        'get_user_wrong_questions', 'lookup_question', 'get_due_reviews',
        'get_practice_questions', 'search_similar_questions', 'search_knowledge_tree', 'run_diagnostic')),
    'progress': ('学习进度与结果', '查实际学习时段、统计、最近练习、历史成绩、报告及成就。', (
        'get_learning_stats', 'get_learning_sessions', 'get_recent_practice_result',
        'get_exam_history', 'get_report_card', 'get_my_achievements', 'get_knowledge_mastery_map')),
    'mastery': ('掌握度与薄弱点', '查掌握图谱、薄弱知识点、Memorix 分析和到期复习。', (
        'search_knowledge_tree', 'get_user_weak_points', 'get_knowledge_mastery_map',
        'get_knowledge_difficulty_analysis', 'get_due_reviews', 'get_learning_stats')),
}


def grouped_tools(allowed, message, recent_messages=None, project=False):
    definitions = {t['function']['name']: t for t in allowed}
    groups = {key: {'title': title, 'description': description,
                   'tools': [definitions[name] for name in names if name in definitions]}
              for key, (title, description, names) in GROUPS.items()}
    groups = {key: group for key, group in groups.items() if group['tools']}
    if 'build_learning_experiment' not in definitions:
        groups.pop('interactive', None)
    if 'read_session_tool' in definitions:
        groups['session'] = {'title': '当前对话的计算工具', 'description': '调用本对话已经注册的计算工具，或读取源码和版本。',
            'tools': [definitions['read_session_tool'], *[tool for name, tool in definitions.items() if name.startswith('session_')]]}
    intent = classify_intent_keywords(message, recent_messages, bot_type='planner')
    initial = {'resource': 'resources', 'learning_sessions': 'progress', 'analysis': 'progress',
               'planning': 'mastery', 'quiz': 'practice', 'error_review': 'practice',
               'qa': 'practice', 'grading': 'practice', 'coach': 'progress'}.get(intent, '')
    if any(word in message for word in ('薄弱', '掌握率', '掌握度', '难度分析', '稳定性')):
        initial = 'mastery'
    if any(word in message for word in ('自习', '专注', '番茄钟')):
        initial = 'focus'
    if any(word in message for word in ('诊断', '初始评估')):
        initial = 'practice'
    if any(word in message for word in ('公式推导', '函数图', '解题步骤', '选项卡')):
        initial = 'presentation'
    if any(word in message for word in ('人工', '老师答疑', '工单')):
        initial = 'support'
    if 'authoring' in groups and any(word in message for word in ('计算工具', '会话工具', '交互实验', '注册工具')):
        initial = 'authoring'
    if 'interactive' in groups and '交互' in message and '题' in message:
        initial = 'interactive'
    if project and any(word in message for word in ('知识地图', '知识单元', '先修', '贝叶斯', '证据路径')):
        initial = 'knowledge'
    if project and initial not in ('interactive', 'authoring', 'presentation', 'practice', 'knowledge'):
        initial = 'project'
    if any(word in message for word in ('学习目标', '阶段计划', '跟进', '暂停学习', '恢复学习', '学习安排')):
        initial = 'project'
    if project and initial not in ('interactive', 'authoring', 'presentation', 'knowledge') and any(word in message for word in ('任务', '原作答', '评价', '成果', '复盘', '补救', '复测', '提交')):
        initial = 'tasks'
    initial = initial if initial in groups else ''
    selected = list(groups[initial]['tools']) if initial else []
    if groups:
        selected.append({'type': 'function', 'function': {
            'name': 'find_learning_tools',
            'description': '需要的学习能力不在当前工具中时，选择一个分组。它会替换当前分组；其他已取得的结果继续可用。' +
                           '；'.join(f"{key}：{group['description']}" for key, group in groups.items()),
            'parameters': {'type': 'object', 'properties': {'group': {'type': 'string', 'enum': list(groups)}},
                           'required': ['group'], 'additionalProperties': False},
        }})
    return selected, groups, initial
