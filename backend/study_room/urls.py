from django.urls import path
from .views import ChatMessageListView, ImageUploadView, UndoBroadcastView, GiphySearchView

urlpatterns = [
    path('messages/', ChatMessageListView.as_view(), name='chat-messages'),
    path('messages/<int:pk>/undo/', UndoBroadcastView.as_view(), name='undo-broadcast'),
    path('upload-image/', ImageUploadView.as_view(), name='upload-image'),
    path('giphy/', GiphySearchView.as_view(), name='giphy-search'),
]
