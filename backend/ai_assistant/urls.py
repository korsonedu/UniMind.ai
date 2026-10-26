from django.urls import path
from .views import (
    AIChatView, AIChatListView, AIChatResetView, AIChatDeleteConversationView, AIChatStreamView,
    AgentMemoryListCreateView, AgentMemoryDetailView,
    BotListCreateView, BotDetailView, BotVisibilityView,
    ConversationListView,
    SemanticMemoryListView, SemanticMemoryDeleteView,
    ActionCardInteractionView,
)
from .views_dashboard import XiaoYuDashboardView, ExamWorkbenchDashboardView
from .views_projects import ConversationDetailView, ProjectListCreateView, ProjectDetailView
from .views_dsh import DshContextView, DshToolView, DshChatView, DshSessionView, DshStatusView, DshChatStreamView, DshSessionListView
from .views_api import (
    grade_view, profile_view, due_view, stats_view,
    practice_start_view, practice_pre_grade_view, practice_submit_view, practice_session_view,
    feedback_view,
)

urlpatterns = [
    path('dsh/context/', DshContextView.as_view(), name='dsh-context'),
    path('dsh/tools/<str:name>/', DshToolView.as_view(), name='dsh-tool'),
    path('dsh/status/', DshStatusView.as_view(), name='dsh-status'),
    path('dsh/chat/stream/', DshChatStreamView.as_view(), name='dsh-chat-stream'),
    path('dsh/chat/', DshChatView.as_view(), name='dsh-chat'),
    path('dsh/sessions/', DshSessionListView.as_view(), name='dsh-sessions'),
    path('dsh/session/<str:action>/', DshSessionView.as_view(), name='dsh-session'),
    path('dashboard/', XiaoYuDashboardView.as_view(), name='xiaoyu-dashboard'),
    path('workbench/dashboard/', ExamWorkbenchDashboardView.as_view(), name='exam-workbench-dashboard'),
    path('chat/', AIChatView.as_view(), name='ai-chat'),
    path('chat/stream/', AIChatStreamView.as_view(), name='ai-chat-stream'),
    path('history/', AIChatListView.as_view(), name='ai-chat-history'),
    path('conversations/', ConversationListView.as_view(), name='conversation-list'),
    path('conversations/<uuid:conversation_id>/', ConversationDetailView.as_view(), name='conversation-detail'),
    path('projects/', ProjectListCreateView.as_view(), name='conversation-project-list'),
    path('projects/<int:pk>/', ProjectDetailView.as_view(), name='conversation-project-detail'),
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
    path('card-interactions/', ActionCardInteractionView.as_view(), name='card-interactions'),

    # Phase 5: Grading & Memory API
    path('grading/grade/', grade_view, name='grading-grade'),
    path('memory/profile/', profile_view, name='memory-profile'),
    path('memory/due/', due_view, name='memory-due'),
    path('memory/stats/', stats_view, name='memory-stats'),

    # Practice session
    path('practice/session/<str:session_id>/', practice_session_view, name='practice-session'),
    path('practice/start/', practice_start_view, name='practice-start'),
    path('practice/pre-grade/', practice_pre_grade_view, name='practice-pre-grade'),
    path('practice/submit/', practice_submit_view, name='practice-submit'),

    # Feedback
    path('feedback/', feedback_view, name='ai-feedback'),
]
