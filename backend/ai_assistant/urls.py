from django.urls import path
from .views import (
    AIChatView, AIChatListView, AIChatResetView, AIChatDeleteConversationView, AIChatStreamView,
    AgentMemoryListCreateView, AgentMemoryDetailView,
    BotListView,
    ConversationListView,
    ExternalAudioSnippetView,
    SemanticMemoryListView, SemanticMemoryDeleteView,
    ActionCardInteractionView,
)
from .views_recovery import ChatRequestStatusView
from .views_dashboard import XiaoYuDashboardView
from .views_projects import ConversationDetailView, ProjectListCreateView, ProjectDetailView
from .views_dsh import DshContextView, DshToolView, DshChatView, DshSessionView, DshStatusView, DshChatStreamView, DshSessionListView, DshConfirmView, DshSubmissionView
from .views_api import (
    grade_view, profile_view, due_view, stats_view,
    practice_start_view, practice_pre_grade_view, practice_submit_view, practice_session_view,
    feedback_view,
)
from .views_learning_experiments import LearningExperimentView

from .views_learning import ProjectLearningView, ProjectLearningLibraryView, ProjectLearningKnowledgeView
from .views_learning_tasks import ProjectLearningTaskListView, ProjectLearningTaskDetailView
from .views_workbench import (
    ProjectSourceBatchSelectView, ProjectSourceDetailView, ProjectSourceFileView,
    ProjectSourceImportView, ProjectSourceListView, ProjectSourceUploadView, ProjectWorkbenchOverviewView,
)

urlpatterns = [
    path('projects/<int:pk>/learning/tasks/', ProjectLearningTaskListView.as_view(), name='project-learning-tasks'),
    path('projects/<int:pk>/learning/tasks/<uuid:task_id>/', ProjectLearningTaskDetailView.as_view(), name='project-learning-task'),
    path('projects/<int:pk>/learning/knowledge/', ProjectLearningKnowledgeView.as_view(), name='project-learning-knowledge'),
    path('projects/<int:pk>/learning/library/', ProjectLearningLibraryView.as_view(), name='project-learning-library'),
    path('projects/<int:pk>/learning/', ProjectLearningView.as_view(), name='project-learning'),
    path('learning-experiments/<uuid:conversation_id>/<uuid:experiment_id>/', LearningExperimentView.as_view(), name='learning-experiment'),
    path('dsh/actions/confirm/', DshConfirmView.as_view(), name='dsh-confirm'),
    path('dsh/actions/<uuid:request_id>/', DshSubmissionView.as_view(), name='dsh-submission'),
    path('dsh/context/', DshContextView.as_view(), name='dsh-context'),
    path('dsh/tools/<str:name>/', DshToolView.as_view(), name='dsh-tool'),
    path('dsh/status/', DshStatusView.as_view(), name='dsh-status'),
    path('dsh/chat/stream/', DshChatStreamView.as_view(), name='dsh-chat-stream'),
    path('dsh/chat/', DshChatView.as_view(), name='dsh-chat'),
    path('dsh/sessions/', DshSessionListView.as_view(), name='dsh-sessions'),
    path('dsh/session/<str:action>/', DshSessionView.as_view(), name='dsh-session'),
    path('dashboard/', XiaoYuDashboardView.as_view(), name='xiaoyu-dashboard'),
    path('chat/', AIChatView.as_view(), name='ai-chat'),
    path('chat/stream/', AIChatStreamView.as_view(), name='ai-chat-stream'),
    path('external-audio-snippet/', ExternalAudioSnippetView.as_view(), name='external-audio-snippet'),
    path('chat-requests/<uuid:request_id>/', ChatRequestStatusView.as_view(), name='ai-chat-request-status'),
    path('history/', AIChatListView.as_view(), name='ai-chat-history'),
    path('conversations/', ConversationListView.as_view(), name='conversation-list'),
    path('conversations/<uuid:conversation_id>/', ConversationDetailView.as_view(), name='conversation-detail'),
    path('projects/', ProjectListCreateView.as_view(), name='conversation-project-list'),
    path('projects/<int:pk>/', ProjectDetailView.as_view(), name='conversation-project-detail'),
    path('projects/<int:pk>/workbench-overview/', ProjectWorkbenchOverviewView.as_view(), name='project-workbench-overview'),
    path('projects/<int:pk>/sources/', ProjectSourceListView.as_view(), name='project-source-list'),
    path('projects/<int:pk>/sources/upload/', ProjectSourceUploadView.as_view(), name='project-source-upload'),
    path('projects/<int:pk>/sources/import/', ProjectSourceImportView.as_view(), name='project-source-import'),
    path('projects/<int:pk>/sources/batch-select/', ProjectSourceBatchSelectView.as_view(), name='project-source-batch-select'),
    path('projects/<int:pk>/sources/<uuid:source_id>/', ProjectSourceDetailView.as_view(), name='project-source-detail'),
    path('projects/<int:pk>/sources/<uuid:source_id>/file/', ProjectSourceFileView.as_view(), name='project-source-file'),
    path('reset/', AIChatResetView.as_view(), name='ai-chat-reset'),
    path('delete-conversation/', AIChatDeleteConversationView.as_view(), name='ai-chat-delete-conversation'),
    path('memories/', AgentMemoryListCreateView.as_view(), name='agent-memory-list'),
    path('memories/<int:pk>/', AgentMemoryDetailView.as_view(), name='agent-memory-detail'),
    path('memories/semantics/', SemanticMemoryListView.as_view(), name='semantic-memory-list'),
    path('memories/semantics/clear/', SemanticMemoryDeleteView.as_view(), name='semantic-memory-clear'),
    path('memories/semantics/<str:memory_id>/', SemanticMemoryDeleteView.as_view(), name='semantic-memory-detail'),
    path('bots/', BotListView.as_view(), name='bot-list'),
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
