"""按用户能力限制工具，机构套餐不再授予学习或管理能力。"""

TOOL_FEATURES = {
    'search_knowledge_tree': 'quiz.exam', 'get_user_weak_points': 'full.report',
    'get_user_wrong_questions': 'wrong.review', 'lookup_question': 'quiz.exam',
    'search_courses': 'course.video', 'search_asr': 'course.video',
    'search_articles': 'course.video', 'get_learning_stats': 'basic.stats',
    'get_knowledge_mastery_map': 'full.report', 'get_due_reviews': 'memorix.review',
    'get_knowledge_difficulty_analysis': 'memorix.review',
    'get_practice_questions': 'quiz.exam', 'get_exam_history': 'full.report',
    'get_recent_practice_result': 'quiz.exam',
    'get_learning_sessions': 'basic.stats',
    'render_visual': 'ai.assistant', 'grade_student_answer': 'quiz.exam',
    'run_diagnostic': 'quiz.exam', 'get_report_card': 'full.report',
    'get_my_achievements': 'full.report', 'create_faq_ticket': 'faq.system',
    'search_similar_questions': 'quiz.exam', 'get_study_status': 'study.room',
    'get_focus_history': 'study.room', 'save_session_note': 'study.room',
}


def filter_tools(bot_type: str, institution, all_tools: list, user=None) -> list:
    """保留三参数调用兼容；缺少用户身份时不授予工具。"""
    from users.permissions import is_platform_admin
    from users.learning import is_course_student
    from users.feature_access import learning_features

    if not user or not user.is_authenticated or not user.is_active:
        return []
    if is_platform_admin(user):
        return all_tools
    if bot_type not in ('assistant', 'planner') or not is_course_student(user):
        return []
    features = set(learning_features(user))
    return [tool for tool in all_tools
            if TOOL_FEATURES.get(tool['function']['name']) in features]
