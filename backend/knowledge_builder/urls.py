from django.urls import path

from .views import BuildCreateView, BuildDetailView, BuildStatusView, BuildIntakeView, BlockResourceView, BlockQuizView

app_name = 'knowledge_builder'
urlpatterns = [
    path('', BuildCreateView.as_view(), name='create'),
    path('intake/', BuildIntakeView.as_view(), name='knowledge-builder-intake'),
    path('<uuid:build_id>/status/', BuildStatusView.as_view(), name='status'),
    path('<uuid:build_id>/', BuildDetailView.as_view(), name='detail'),
    path('<uuid:build_id>/blocks/<int:block_id>/resources/', BlockResourceView.as_view(), name='knowledge-builder-block-resources'),
    path('<uuid:build_id>/blocks/<int:block_id>/quiz/', BlockQuizView.as_view(), name='knowledge-builder-block-quiz'),
]
