"""Student feature access, independent of curriculum labels and service quotas."""
from .learning import LEARNING_FEATURES

FEATURE_AREAS = [
    {'key': 'ai.assistant', 'name': '小宇'},
    {'key': 'full.report', 'name': '学习记录'},
    {'key': 'course.video', 'name': '课程中心'},
    {'key': 'quiz.exam', 'name': '习题训练'},
    {'key': 'faq.system', 'name': '课程答疑'},
    {'key': 'study.room', 'name': '自习室'},
]
FEATURE_PARENTS = {'video.outline': 'course.video', 'wrong.review': 'quiz.exam',
                   'memorix.review': 'quiz.exam', 'quiz.manual': 'quiz.exam', 'pdf.mock': 'quiz.exam'}


def learning_features(user):
    if not user or not user.is_authenticated or not user.is_active:
        return []
    from .permissions import get_user_capabilities
    capabilities = get_user_capabilities(user)
    features = [key for key in LEARNING_FEATURES if key in capabilities]
    return [key for key in features if FEATURE_PARENTS.get(key, key) in features]


def has_learning_feature(user, feature):
    return feature in learning_features(user)


def request_feature(request):
    path = request.path
    for prefix, feature in (
        ('/api/courses/', 'course.video'), ('/api/qa/', 'faq.system'),
        ('/api/study/', 'study.room'), ('/api/users/me/report-card/', 'full.report'),
        ('/api/users/me/knowledge-mastery/', 'full.report'),
        ('/api/users/me/diagnostic/', 'quiz.exam'),
        ('/api/ai/dashboard/', 'full.report'), ('/api/ai/memory/', 'full.report'),
        ('/api/ai/practice/', 'quiz.exam'), ('/api/ai/grading/', 'quiz.exam'),
        ('/api/articles/', 'course.video'), ('/api/users/plans/', 'full.report'),
        ('/api/users/me/checkin/', 'full.report'), ('/api/users/achievements/', 'full.report'),
        ('/api/users/me/achievements/', 'full.report'),
    ):
        if path.startswith(prefix):
            return feature
    if path.startswith('/api/ai/') and path not in ('/api/ai/dashboard/',) and not path.startswith('/api/ai/workbench/'):
        return 'ai.assistant'
    if path.startswith('/api/quizzes/') and not path.startswith((
        '/api/quizzes/admin/', '/api/quizzes/workbench/', '/api/quizzes/marketplace/',
    )):
        return 'quiz.exam'
    return None
