from django.urls import path
from .views_question import (
    QuestionListView, QuestionDetailView,
    AdminQuestionListView,
)
from .views_exam import (
    SubmitExamView, ExamDetailView,
)
from .views_memorix import (
    ToggleFavoriteView, ToggleMasteredView, QuizStatsView,
    MemorixCurveView, MemorixOptimizationHistoryView,
    WrongQuestionInsightsView,
)
from .views_knowledge import (
    KnowledgePointListView, KnowledgePointDetailView,
    KnowledgePointImportMDView, KnowledgePointExportMDView,
    KnowledgePointSubjectsView,
)
from .views_ai import (
    AdversarialPipelineView, BulkPipelineView, PipelineReviewListView, PipelineReviewActionView,
    WorkbenchTaskStatusView,
    WorkbenchSaveQuestionsView, WorkbenchLaunchArcView,
)
from .views_admin import (
    AdminContentPipelineTaskListCreateView, AdminContentPipelineMetricsView,
    AdminContentPipelineTaskDetailView, AdminContentPipelineTaskRetryView,
    AdminPromptTemplateListView, AdminPromptTemplateDetailView, AdminPromptTemplateRollbackView,
)
from .views_knowledge_edge import (
    KnowledgeEdgeListCreateView, KnowledgeEdgeDetailView,
    KnowledgeEdgeBulkCreateView,
)
from .views_marketplace import (
    MarketplaceListView, MarketplaceDetailView, MarketplacePublishView,
    MarketplaceManageView, MarketplacePurchaseView,
)

urlpatterns = [
    path('questions/', QuestionListView.as_view(), name='question-list'),
    path('questions/<int:pk>/', QuestionDetailView.as_view(), name='question-detail'),
    path('submit-exam/', SubmitExamView.as_view(), name='quiz-submit-exam'),
    path('exams/<int:pk>/', ExamDetailView.as_view(), name='exam-detail'),
    path('stats/', QuizStatsView.as_view(), name='quiz-stats'),
    path('memorix/curve/', MemorixCurveView.as_view(), name='memorix-curve'),
    path('memorix/optimization-history/', MemorixOptimizationHistoryView.as_view(), name='memorix-optimization-history'),
    path('favorite/toggle/', ToggleFavoriteView.as_view(), name='favorite-toggle'),
    path('mastered/toggle/', ToggleMasteredView.as_view(), name='mastered-toggle'),
    path('wrong-questions/insights/', WrongQuestionInsightsView.as_view(), name='wrong-questions-insights'),
    path('knowledge-points/subjects/', KnowledgePointSubjectsView.as_view(), name='knowledge-point-subjects'),
    path('knowledge-points/', KnowledgePointListView.as_view(), name='knowledge-point-list'),
    path('knowledge-points/<int:pk>/', KnowledgePointDetailView.as_view(), name='knowledge-point-detail'),
    path('knowledge-points/import-md/', KnowledgePointImportMDView.as_view(), name='knowledge-point-import-md'),
    path('knowledge-points/export-md/', KnowledgePointExportMDView.as_view(), name='knowledge-point-export-md'),
    # 知识图边（教师端）
    path('knowledge-edges/', KnowledgeEdgeListCreateView.as_view(), name='knowledge-edge-list'),
    path('knowledge-edges/bulk/', KnowledgeEdgeBulkCreateView.as_view(), name='knowledge-edge-bulk'),
    path('knowledge-edges/<int:pk>/', KnowledgeEdgeDetailView.as_view(), name='knowledge-edge-detail'),
    path('admin/questions/', AdminQuestionListView.as_view(), name='admin-question-list'),
    # 教研任务中心
    path('admin/pipeline-tasks/', AdminContentPipelineTaskListCreateView.as_view(), name='admin-pipeline-task-list-create'),
    path('admin/pipeline-metrics/', AdminContentPipelineMetricsView.as_view(), name='admin-pipeline-metrics'),
    path('admin/pipeline-tasks/<int:pk>/', AdminContentPipelineTaskDetailView.as_view(), name='admin-pipeline-task-detail'),
    path('admin/pipeline-tasks/<int:pk>/retry/', AdminContentPipelineTaskRetryView.as_view(), name='admin-pipeline-task-retry'),
    path('admin/pipeline-review/', PipelineReviewListView.as_view(), name='admin-pipeline-review-list'),
    path('admin/pipeline-review/<int:pk>/', PipelineReviewActionView.as_view(), name='admin-pipeline-review-action'),
    path('admin/adversarial-pipeline/', AdversarialPipelineView.as_view(), name='admin-adversarial-pipeline'),
    path('admin/bulk-pipeline/', BulkPipelineView.as_view(), name='admin-bulk-pipeline'),
    # 工作台
    path('workbench/tasks/<int:pk>/status/', WorkbenchTaskStatusView.as_view(), name='workbench-task-status'),
    path('workbench/save-questions/', WorkbenchSaveQuestionsView.as_view(), name='workbench-save-questions'),
    path('workbench/launch-arc/', WorkbenchLaunchArcView.as_view(), name='workbench-launch-arc'),
    path('admin/prompt-templates/', AdminPromptTemplateListView.as_view(), name='admin-prompt-template-list'),
    path('admin/prompt-templates/detail/', AdminPromptTemplateDetailView.as_view(), name='admin-prompt-template-detail'),
    path('admin/prompt-templates/rollback/', AdminPromptTemplateRollbackView.as_view(), name='admin-prompt-template-rollback'),
    # 内容市场
    path('marketplace/', MarketplaceListView.as_view(), name='marketplace-list'),
    path('marketplace/publish/', MarketplacePublishView.as_view(), name='marketplace-publish'),
    path('marketplace/manage/<int:pk>/', MarketplaceManageView.as_view(), name='marketplace-manage'),
    path('marketplace/<int:pk>/', MarketplaceDetailView.as_view(), name='marketplace-detail'),
    path('marketplace/<int:pk>/purchase/', MarketplacePurchaseView.as_view(), name='marketplace-purchase'),
]
