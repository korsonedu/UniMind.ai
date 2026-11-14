from django.urls import path

from .views import BuildCreateView, BuildDetailView, BuildStatusView

app_name = 'knowledge_builder'
urlpatterns = [
    path('', BuildCreateView.as_view(), name='create'),
    path('<uuid:build_id>/status/', BuildStatusView.as_view(), name='status'),
    path('<uuid:build_id>/', BuildDetailView.as_view(), name='detail'),
]
