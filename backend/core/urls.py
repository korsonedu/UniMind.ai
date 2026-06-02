from django.urls import path
from .views import (
    LegalDocumentView, LegalDocumentListView,
    FeedbackAdminListView, FeedbackAdminDetailView,
)

urlpatterns = [
    path('legal/', LegalDocumentListView.as_view(), name='legal-list'),
    path('legal/<str:doc_type>/', LegalDocumentView.as_view(), name='legal-detail'),
    path('admin/feedback/', FeedbackAdminListView.as_view(), name='admin-feedback-list'),
    path('admin/feedback/<int:pk>/', FeedbackAdminDetailView.as_view(), name='admin-feedback-detail'),
]
