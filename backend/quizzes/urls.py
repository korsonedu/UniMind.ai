from django.urls import path
from .views_question import (
    QuestionListView, QuestionDetailView,
    BulkImportQuestionsView,
    AdminQuestionListView, ExportStructuredQuestionsView, ImportCSVQuestionsView,
)
from .views_exam import (
    QuizAttemptCreateView,
    LeaderboardView, GradeSubjectiveView,
    TeacherExamListView,
    StudentExamSubmissionView,
    SubmitExamView, LatestExamReportView, ExamDetailView,
)
from .views_fsrs import (
    ToggleFavoriteView, ToggleMasteredView, QuizStatsView,
    StudyPlanView, FSRSCurveView,
    FSRSOptimizationHistoryView,
    PersonalizedMockExamView,
    WrongQuestionListView, WrongQuestionInsightsView, FavoriteQuestionListView,
)
from .views_knowledge import (
    KnowledgePointListView, KnowledgePointDetailView,
    MyKnowledgePointAnnotationView, MyKnowledgePointAnnotationListView,
    GenerateBulkQuestionsView,
)
from .views_ai import (
    GenerateFromTextView, AIPreviewParseView,
    AIPreviewGenerateView, AIConfirmSaveQuestionsView,
)
from .views_admin import (
    AdminContentPipelineTaskListCreateView, AdminContentPipelineMetricsView,
    AdminContentPipelineTaskDetailView, AdminContentPipelineTaskRetryView,
    AdminPromptTemplateListView, AdminPromptTemplateDetailView, AdminPromptTemplateRollbackView,
)

urlpatterns = [
    path('questions/', QuestionListView.as_view(), name='question-list'),
    path('questions/<int:pk>/', QuestionDetailView.as_view(), name='question-detail'),
    path('submit/', QuizAttemptCreateView.as_view(), name='quiz-submit'),
    path('submit-exam/', SubmitExamView.as_view(), name='quiz-submit-exam'),
    path('exams/<int:pk>/', ExamDetailView.as_view(), name='exam-detail'),
    path('latest-report/', LatestExamReportView.as_view(), name='latest-exam-report'),
    path('leaderboard/', LeaderboardView.as_view(), name='leaderboard'),
    path('grade-subjective/', GradeSubjectiveView.as_view(), name='grade-subjective'),
    path('stats/', QuizStatsView.as_view(), name='quiz-stats'),
    path('fsrs/curve/', FSRSCurveView.as_view(), name='fsrs-curve'),
    path('fsrs/optimization-history/', FSRSOptimizationHistoryView.as_view(), name='fsrs-optimization-history'),
    path('study-plan/', StudyPlanView.as_view(), name='study-plan'),
    path('personalized-mock-exams/', PersonalizedMockExamView.as_view(), name='personalized-mock-exams'),
    path('favorite/toggle/', ToggleFavoriteView.as_view(), name='favorite-toggle'),
    path('mastered/toggle/', ToggleMasteredView.as_view(), name='mastered-toggle'),
    path('wrong-questions/', WrongQuestionListView.as_view(), name='wrong-questions'),
    path('wrong-questions/insights/', WrongQuestionInsightsView.as_view(), name='wrong-questions-insights'),
    path('favorites/', FavoriteQuestionListView.as_view(), name='favorites-list'),
    path('knowledge-points/', KnowledgePointListView.as_view(), name='knowledge-point-list'),
    path('knowledge-points/annotations/me/', MyKnowledgePointAnnotationListView.as_view(), name='knowledge-point-annotation-list-me'),
    path('knowledge-points/<int:pk>/', KnowledgePointDetailView.as_view(), name='knowledge-point-detail'),
    path('knowledge-points/<int:pk>/annotation/', MyKnowledgePointAnnotationView.as_view(), name='knowledge-point-annotation-me'),
    path('knowledge-points/<int:pk>/generate/', GenerateBulkQuestionsView.as_view(), name='knowledge-point-generate'),
    # 智能出题工作流
    path('ai-smart-generate-preview/', AIPreviewGenerateView.as_view(), name='ai-smart-generate-preview'),
    path('ai-smart-generate-confirm/', AIConfirmSaveQuestionsView.as_view(), name='ai-smart-generate-confirm'),
    
    path('ai-generate-from-text/', GenerateFromTextView.as_view(), name='ai-generate-from-text'),
    path('ai-parse-raw-text/', AIPreviewParseView.as_view(), name='ai-parse-raw-text'),
    path('ai-bulk-import/', BulkImportQuestionsView.as_view(), name='ai-bulk-import'),
    path('import-csv/', ImportCSVQuestionsView.as_view(), name='import-csv'),
    # 管理员专用：分页题目列表
    path('admin/questions/', AdminQuestionListView.as_view(), name='admin-question-list'),
    # 管理员专用：导出结构化 AI 可读格式
    path('admin/export-structured/', ExportStructuredQuestionsView.as_view(), name='export-structured'),
    # 教研任务中心
    path('admin/pipeline-tasks/', AdminContentPipelineTaskListCreateView.as_view(), name='admin-pipeline-task-list-create'),
    path('admin/pipeline-metrics/', AdminContentPipelineMetricsView.as_view(), name='admin-pipeline-metrics'),
    path('admin/pipeline-tasks/<int:pk>/', AdminContentPipelineTaskDetailView.as_view(), name='admin-pipeline-task-detail'),
    path('admin/pipeline-tasks/<int:pk>/retry/', AdminContentPipelineTaskRetryView.as_view(), name='admin-pipeline-task-retry'),
    path('admin/prompt-templates/', AdminPromptTemplateListView.as_view(), name='admin-prompt-template-list'),
    path('admin/prompt-templates/detail/', AdminPromptTemplateDetailView.as_view(), name='admin-prompt-template-detail'),
    path('admin/prompt-templates/rollback/', AdminPromptTemplateRollbackView.as_view(), name='admin-prompt-template-rollback'),
]
