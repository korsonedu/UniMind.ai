from django.urls import path
from .views import (
    AIChatView, AIChatListView, AIChatResetView, AIChatDeleteConversationView, AIChatStreamView,
    AgentMemoryListCreateView, AgentMemoryDetailView,
    BotListCreateView, BotDetailView, BotVisibilityView,
    StudyPlanListView, StudyPlanDetailView, StudyPlanTaskUpdateView,
    SemanticMemoryListView, SemanticMemoryDeleteView,
    ActionCardInteractionView,
)
from .views_dashboard import XiaoYuDashboardView, ExamWorkbenchDashboardView
from .views_api import (
    grade_view, profile_view, due_view, stats_view,
    practice_start_view, practice_pre_grade_view, practice_submit_view,
    feedback_view,
)

urlpatterns = [
    path('dashboard/', XiaoYuDashboardView.as_view(), name='xiaoyu-dashboard'),
    path('workbench/dashboard/', ExamWorkbenchDashboardView.as_view(), name='exam-workbench-dashboard'),
    path('chat/', AIChatView.as_view(), name='ai-chat'),
    path('chat/stream/', AIChatStreamView.as_view(), name='ai-chat-stream'),
    path('history/', AIChatListView.as_view(), name='ai-chat-history'),
    path('reset/', AIChatResetView.as_view(), name='ai-chat-reset'),
    path('delete-conversation/', AIChatDeleteConversationView.as_view(), name='ai-chat-delete-conversation'),
    path('memories/', AgentMemoryListCreateView.as_view(), name='agent-memory-list'),
    path('memories/<int:pk>/', AgentMemoryDetailView.as_view(), name='agent-memory-detail'),
    path('memories/semantics/', SemanticMemoryListView.as_view(), name='semantic-memory-list'),
    path('memories/semantics/clear/', SemanticMemoryDeleteView.as_view(), name='semantic-memory-clear'),
    path('memories/semantics/<str:memory_id>/', SemanticMemoryDeleteView.as_view(), name='semantic-memory-detail'),
    path('bots/', BotListCreateView.as_view(), name='bot-list'),
    path('bots/<int:pk>/', BotDetailView.as_view(), name='bot-detail'),
    path('bots/visibility/', BotVisibilityView.as_view(), name='bot-visibility'),
    path('plans/', StudyPlanListView.as_view(), name='study-plan-list'),
    path('plans/<int:pk>/', StudyPlanDetailView.as_view(), name='study-plan-detail'),
    path('plans/<int:plan_id>/tasks/<str:task_id>/', StudyPlanTaskUpdateView.as_view(), name='study-plan-task-update'),
    path('card-interactions/', ActionCardInteractionView.as_view(), name='card-interactions'),

    # Phase 5: Grading & Memory API
    path('grading/grade/', grade_view, name='grading-grade'),
    path('memory/profile/', profile_view, name='memory-profile'),
    path('memory/due/', due_view, name='memory-due'),
    path('memory/stats/', stats_view, name='memory-stats'),

    # Practice session
    path('practice/start/', practice_start_view, name='practice-start'),
    path('practice/pre-grade/', practice_pre_grade_view, name='practice-pre-grade'),
    path('practice/submit/', practice_submit_view, name='practice-submit'),

    # Feedback
    path('feedback/', feedback_view, name='ai-feedback'),
]
