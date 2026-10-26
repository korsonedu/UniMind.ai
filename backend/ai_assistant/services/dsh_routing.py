"""Small model-visible groups; discovery only reveals already authorized tools."""
from ai_engine.tool_router import classify_intent_keywords


GROUPS = {
    'resources': ('课程与知识来源', '查课程、视频讲稿及知识点。', (
        'search_courses', 'search_asr', 'search_knowledge_tree')),
    'practice': ('题目与复习', '查错题、题目、到期复习，预览练习题及同类题。', (
        'get_user_wrong_questions', 'lookup_question', 'get_due_reviews',
        'get_practice_questions', 'search_similar_questions', 'search_knowledge_tree')),
    'progress': ('学习进度与结果', '查实际学习时段、统计、最近练习、历史成绩、报告及成就。', (
        'get_learning_stats', 'get_learning_sessions', 'get_recent_practice_result',
        'get_exam_history', 'get_report_card', 'get_my_achievements', 'get_knowledge_mastery_map')),
    'mastery': ('掌握度与薄弱点', '查掌握图谱、薄弱知识点、Memorix 分析和到期复习。', (
        'search_knowledge_tree', 'get_user_weak_points', 'get_knowledge_mastery_map',
        'get_knowledge_difficulty_analysis', 'get_due_reviews', 'get_learning_stats')),
}


def grouped_tools(allowed, message, recent_messages=None):
    definitions = {t['function']['name']: t for t in allowed}
    groups = {key: {'title': title, 'description': description,
                   'tools': [definitions[name] for name in names if name in definitions]}
              for key, (title, description, names) in GROUPS.items()}
    groups = {key: group for key, group in groups.items() if group['tools']}
    intent = classify_intent_keywords(message, recent_messages, bot_type='planner')
    initial = {'resource': 'resources', 'learning_sessions': 'progress', 'analysis': 'progress',
               'planning': 'mastery', 'quiz': 'practice', 'error_review': 'practice',
               'qa': 'practice', 'grading': 'practice', 'coach': 'progress'}.get(intent, '')
    if any(word in message for word in ('薄弱', '掌握率', '掌握度', '难度分析', '稳定性')):
        initial = 'mastery'
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
