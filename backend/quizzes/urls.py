from django.urls import path
from .views_question import (
    QuestionListView, QuestionDetailView,
    BulkImportQuestionsView,
    AdminQuestionListView, ExportStructuredQuestionsView, ImportCSVQuestionsView,
)
from .views_exam import (
    TeacherExamListView, TeacherExamCreateView, TeacherExamDeleteView,
    StudentExamSubmissionView, TeacherExamSubmissionsView, TeacherGradeSubmissionView,
    SubmitExamView, ExamDetailView,
)
from .views_fsrs import (
    ToggleFavoriteView, ToggleMasteredView, QuizStatsView,
    StudyPlanView, FSRSCurveView,
    FSRSOptimizationHistoryView,
    PersonalizedMockExamView,
    WrongQuestionInsightsView,
)
from .views_knowledge import (
    KnowledgePointListView, KnowledgePointDetailView,
    KnowledgePointImportMDView, KnowledgePointExportMDView,
)
from .views_ai import (
    AIPreviewGenerateView, AIConfirmSaveQuestionsView, AIPreviewParseView,
    AdversarialPipelineView, PipelineReviewListView, PipelineReviewActionView,
)
from .views_admin import (
    AdminContentPipelineTaskListCreateView, AdminContentPipelineMetricsView,
    AdminContentPipelineTaskDetailView, AdminContentPipelineTaskRetryView,
    AdminPromptTemplateListView, AdminPromptTemplateDetailView, AdminPromptTemplateRollbackView,
)

urlpatterns = [
    path('questions/', QuestionListView.as_view(), name='question-list'),
    path('questions/<int:pk>/', QuestionDetailView.as_view(), name='question-detail'),
    path('submit-exam/', SubmitExamView.as_view(), name='quiz-submit-exam'),
    path('exams/<int:pk>/', ExamDetailView.as_view(), name='exam-detail'),
    path('teacher-exams/', TeacherExamListView.as_view(), name='teacher-exam-list'),
    path('teacher-exams/create/', TeacherExamCreateView.as_view(), name='teacher-exam-create'),
    path('teacher-exams/<int:pk>/delete/', TeacherExamDeleteView.as_view(), name='teacher-exam-delete'),
    path('teacher-exams/<int:pk>/submit/', StudentExamSubmissionView.as_view(), name='teacher-exam-submit'),
    path('teacher-exams/<int:pk>/submissions/', TeacherExamSubmissionsView.as_view(), name='teacher-exam-submissions'),
    path('teacher-exams/submissions/<int:pk>/grade/', TeacherGradeSubmissionView.as_view(), name='teacher-exam-grade'),
    path('stats/', QuizStatsView.as_view(), name='quiz-stats'),
    path('fsrs/curve/', FSRSCurveView.as_view(), name='fsrs-curve'),
    path('fsrs/optimization-history/', FSRSOptimizationHistoryView.as_view(), name='fsrs-optimization-history'),
    path('study-plan/', StudyPlanView.as_view(), name='study-plan'),
    path('personalized-mock-exams/', PersonalizedMockExamView.as_view(), name='personalized-mock-exams'),
    path('favorite/toggle/', ToggleFavoriteView.as_view(), name='favorite-toggle'),
    path('mastered/toggle/', ToggleMasteredView.as_view(), name='mastered-toggle'),
    path('wrong-questions/insights/', WrongQuestionInsightsView.as_view(), name='wrong-questions-insights'),
    path('knowledge-points/', KnowledgePointListView.as_view(), name='knowledge-point-list'),
    path('knowledge-points/<int:pk>/', KnowledgePointDetailView.as_view(), name='knowledge-point-detail'),
    path('knowledge-points/import-md/', KnowledgePointImportMDView.as_view(), name='knowledge-point-import-md'),
    path('knowledge-points/export-md/', KnowledgePointExportMDView.as_view(), name='knowledge-point-export-md'),
    # 智能出题工作流
    path('ai-smart-generate-preview/', AIPreviewGenerateView.as_view(), name='ai-smart-generate-preview'),
    path('ai-smart-generate-confirm/', AIConfirmSaveQuestionsView.as_view(), name='ai-smart-generate-confirm'),
    path('ai-parse-raw-text/', AIPreviewParseView.as_view(), name='ai-parse-raw-text'),
    path('ai-bulk-import/', BulkImportQuestionsView.as_view(), name='ai-bulk-import'),
    path('import-csv/', ImportCSVQuestionsView.as_view(), name='import-csv'),
    path('admin/questions/', AdminQuestionListView.as_view(), name='admin-question-list'),
    path('admin/export-structured/', ExportStructuredQuestionsView.as_view(), name='export-structured'),
    # 教研任务中心
    path('admin/pipeline-tasks/', AdminContentPipelineTaskListCreateView.as_view(), name='admin-pipeline-task-list-create'),
    path('admin/pipeline-metrics/', AdminContentPipelineMetricsView.as_view(), name='admin-pipeline-metrics'),
    path('admin/pipeline-tasks/<int:pk>/', AdminContentPipelineTaskDetailView.as_view(), name='admin-pipeline-task-detail'),
    path('admin/pipeline-tasks/<int:pk>/retry/', AdminContentPipelineTaskRetryView.as_view(), name='admin-pipeline-task-retry'),
    path('admin/pipeline-review/', PipelineReviewListView.as_view(), name='admin-pipeline-review-list'),
    path('admin/pipeline-review/<int:pk>/', PipelineReviewActionView.as_view(), name='admin-pipeline-review-action'),
    path('admin/adversarial-pipeline/', AdversarialPipelineView.as_view(), name='admin-adversarial-pipeline'),
    path('admin/prompt-templates/', AdminPromptTemplateListView.as_view(), name='admin-prompt-template-list'),
    path('admin/prompt-templates/detail/', AdminPromptTemplateDetailView.as_view(), name='admin-prompt-template-detail'),
    path('admin/prompt-templates/rollback/', AdminPromptTemplateRollbackView.as_view(), name='admin-prompt-template-rollback'),
]
