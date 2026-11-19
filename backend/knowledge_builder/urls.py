from django.urls import path

from .views import (
    AtomMicroLessonView,
    BlockQuizView,
    BlockResourceView,
    BuildCreateView,
    BuildDetailView,
    BuildIntakeView,
    BuildStatusView,
    SourceAlignmentDetailView,
    TreePublicAssetView,
    TreeSourceAlignView,
    TreeSourceDetailView,
    TreeSourceListView,
)

app_name = 'knowledge_builder'
urlpatterns = [
    path('', BuildCreateView.as_view(), name='create'),
    path('intake/', BuildIntakeView.as_view(), name='knowledge-builder-intake'),
    path('<uuid:build_id>/status/', BuildStatusView.as_view(), name='status'),
    path('<uuid:build_id>/', BuildDetailView.as_view(), name='detail'),
    path('<uuid:build_id>/public-assets/', TreePublicAssetView.as_view(), name='knowledge-builder-public-assets'),
    path('<uuid:build_id>/sources/', TreeSourceListView.as_view(), name='knowledge-builder-sources'),
    path('<uuid:build_id>/sources/<int:source_id>/', TreeSourceDetailView.as_view(), name='knowledge-builder-source-detail'),
    path('<uuid:build_id>/sources/<int:source_id>/align/', TreeSourceAlignView.as_view(), name='knowledge-builder-source-align'),
    path('<uuid:build_id>/sources/<int:source_id>/alignments/<int:alignment_id>/', SourceAlignmentDetailView.as_view(), name='knowledge-builder-source-alignment-detail'),
    path('<uuid:build_id>/atoms/<int:atom_id>/micro-lesson/', AtomMicroLessonView.as_view(), name='knowledge-builder-atom-micro-lesson'),
    path('<uuid:build_id>/blocks/<int:block_id>/resources/', BlockResourceView.as_view(), name='knowledge-builder-block-resources'),
    path('<uuid:build_id>/blocks/<int:block_id>/quiz/', BlockQuizView.as_view(), name='knowledge-builder-block-quiz'),
]
