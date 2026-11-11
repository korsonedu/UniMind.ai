from django.urls import path
from .desktop import DesktopReleaseView
from .views import (
    LegalDocumentView, LegalDocumentListView, CsrfTokenView,
)

urlpatterns = [
    path('csrf/', CsrfTokenView.as_view(), name='csrf-token'),
    path('desktop-release/', DesktopReleaseView.as_view(), name='desktop-release'),
    path('legal/', LegalDocumentListView.as_view(), name='legal-list'),
    path('legal/<str:doc_type>/', LegalDocumentView.as_view(), name='legal-detail'),
]
