from django.urls import path
from .views_question import (
    QuestionListView, QuestionDetailView,
    AdminQuestionListView, ExportStructuredQuestionsView, ImportCSVQuestionsView,
)
from .views_exam import (
    TeacherExamListView, TeacherExamCreateView, TeacherExamDeleteView,
    StudentExamSubmissionView, TeacherExamSubmissionsView, TeacherGradeSubmissionView,
    SubmitExamView, ExamDetailView,
)
from .views_memorix import (
    ToggleFavoriteView, ToggleMasteredView, QuizStatsView,
    MemorixCurveView, MemorixOptimizationHistoryView,
    PersonalizedMockExamView,
    WrongQuestionInsightsView,
)
from .views_knowledge import (
    KnowledgePointListView, KnowledgePointDetailView,
    KnowledgePointImportMDView, KnowledgePointExportMDView,
    KnowledgePointSubjectsView,
)
from .views_ai import (
    AIPreviewParseView,
    AdversarialPipelineView, PipelineReviewListView, PipelineReviewActionView,
    WorkbenchTaskListView, WorkbenchTaskStatusView,
    WorkbenchSaveQuestionsView, WorkbenchLaunchArcView,
)
from .views_templates import ExamTemplateListCreateView, ExamTemplateDetailView
from .views_admin import (
    AdminContentPipelineTaskListCreateView, AdminContentPipelineMetricsView,
    AdminContentPipelineTaskDetailView, AdminContentPipelineTaskRetryView,
    AdminPromptTemplateListView, AdminPromptTemplateDetailView, AdminPromptTemplateRollbackView,
)
from .views_knowledge_edge import (
    KnowledgeEdgeListCreateView, KnowledgeEdgeDetailView,
    KnowledgeEdgeBulkCreateView, KnowledgeEdgeLLMAnalyzeView,
    KnowledgeEdgeReviewListView, KnowledgeEdgeReviewActionView,
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
    path('memorix/curve/', MemorixCurveView.as_view(), name='memorix-curve'),
    path('memorix/optimization-history/', MemorixOptimizationHistoryView.as_view(), name='memorix-optimization-history'),
    path('personalized-mock-exams/', PersonalizedMockExamView.as_view(), name='personalized-mock-exams'),
    path('favorite/toggle/', ToggleFavoriteView.as_view(), name='favorite-toggle'),
    path('mastered/toggle/', ToggleMasteredView.as_view(), name='mastered-toggle'),
    path('wrong-questions/insights/', WrongQuestionInsightsView.as_view(), name='wrong-questions-insights'),
    # 出题模板
    path('templates/', ExamTemplateListCreateView.as_view(), name='exam-template-list'),
    path('templates/<int:pk>/', ExamTemplateDetailView.as_view(), name='exam-template-detail'),
    path('knowledge-points/subjects/', KnowledgePointSubjectsView.as_view(), name='knowledge-point-subjects'),
    path('knowledge-points/', KnowledgePointListView.as_view(), name='knowledge-point-list'),
    path('knowledge-points/<int:pk>/', KnowledgePointDetailView.as_view(), name='knowledge-point-detail'),
    path('knowledge-points/import-md/', KnowledgePointImportMDView.as_view(), name='knowledge-point-import-md'),
    path('knowledge-points/export-md/', KnowledgePointExportMDView.as_view(), name='knowledge-point-export-md'),
    # 知识图边（教师端）
    path('knowledge-edges/', KnowledgeEdgeListCreateView.as_view(), name='knowledge-edge-list'),
    path('knowledge-edges/bulk/', KnowledgeEdgeBulkCreateView.as_view(), name='knowledge-edge-bulk'),
    path('knowledge-edges/llm-analyze/', KnowledgeEdgeLLMAnalyzeView.as_view(), name='knowledge-edge-llm-analyze'),
    path('knowledge-edges/review/', KnowledgeEdgeReviewListView.as_view(), name='knowledge-edge-review-list'),
    path('knowledge-edges/review/action/', KnowledgeEdgeReviewActionView.as_view(), name='knowledge-edge-review-action'),
    path('knowledge-edges/<int:pk>/', KnowledgeEdgeDetailView.as_view(), name='knowledge-edge-detail'),
    # 智能出题工作流
    path('ai-parse-raw-text/', AIPreviewParseView.as_view(), name='ai-parse-raw-text'),
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
    # 工作台
    path('workbench/tasks/', WorkbenchTaskListView.as_view(), name='workbench-task-list'),
    path('workbench/tasks/<int:pk>/status/', WorkbenchTaskStatusView.as_view(), name='workbench-task-status'),
    path('workbench/save-questions/', WorkbenchSaveQuestionsView.as_view(), name='workbench-save-questions'),
    path('workbench/launch-arc/', WorkbenchLaunchArcView.as_view(), name='workbench-launch-arc'),
    path('admin/prompt-templates/', AdminPromptTemplateListView.as_view(), name='admin-prompt-template-list'),
    path('admin/prompt-templates/detail/', AdminPromptTemplateDetailView.as_view(), name='admin-prompt-template-detail'),
    path('admin/prompt-templates/rollback/', AdminPromptTemplateRollbackView.as_view(), name='admin-prompt-template-rollback'),
]
