"""可常驻提供、可并发执行的工具，不包含持久化写操作。"""


READ_ONLY_TOOLS = frozenset({
    'search_knowledge_tree', 'get_user_weak_points', 'get_user_wrong_questions',
    'lookup_question', 'get_report_card', 'get_my_achievements', 'render_visual',
    'get_learning_stats', 'get_knowledge_mastery_map', 'get_due_reviews',
    'get_practice_questions', 'get_exam_history',
    'search_courses', 'search_asr', 'search_articles',
    'get_knowledge_difficulty_analysis', 'search_knowledge',
    'check_pipeline_status', 'get_workbench_stats', 'get_student_detail',
    'list_courses', 'list_questions', 'list_articles',
    'get_study_status', 'get_focus_history', 'search_similar_questions',
})
