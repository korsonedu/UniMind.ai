from django.urls import path
from .views import AIChatView, AIChatListView, AIChatResetView, BotListCreateView, BotDetailView

urlpatterns = [
    path('chat/', AIChatView.as_view(), name='ai-chat'),
    path('history/', AIChatListView.as_view(), name='ai-chat-history'),
    path('reset/', AIChatResetView.as_view(), name='ai-chat-reset'),
    path('bots/', BotListCreateView.as_view(), name='bot-list'),
    path('bots/<int:pk>/', BotDetailView.as_view(), name='bot-detail'),
]
