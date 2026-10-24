from django.urls import path
from . import views

urlpatterns = [
    path('ai-settings/', views.NoteAISettingsView.as_view()),
    path('lookup/', views.NoteLookupView.as_view()),
    path('notebooks/', views.NotebookListView.as_view()),
    path('notebooks/<int:pk>/', views.NotebookDetailView.as_view()),
    path('notebooks/<int:pk>/export/', views.NotebookExportView.as_view()),
    path('items/', views.NoteListView.as_view()),
    path('items/<int:pk>/', views.NoteDetailView.as_view()),
    path('items/<int:pk>/restore/', views.RestoreNoteView.as_view()),
    path('items/<int:pk>/export/', views.NoteExportView.as_view()),
    path('tags/', views.TagListView.as_view()),
    path('bindings/', views.BindingListView.as_view()),
    path('bindings/<int:pk>/', views.BindingDetailView.as_view()),
    path('references/', views.ReferencesView.as_view()),
]
