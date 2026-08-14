from django.urls import path
from .views import (
    LegalDocumentView, LegalDocumentListView,
)

urlpatterns = [
    path('legal/', LegalDocumentListView.as_view(), name='legal-list'),
    path('legal/<str:doc_type>/', LegalDocumentView.as_view(), name='legal-detail'),
]
