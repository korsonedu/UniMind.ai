from django.urls import path
from .views import (
    CourseListCreateView, CourseDetailView,
    AlbumListCreateView, AlbumDetailView, AlbumCoursesView,
    StartupMaterialListCreateView, StartupMaterialDetailView,
    VideoProgressUpdateView, ChunkedUploadInitView,
    ChunkedUploadChunkView, ChunkedUploadCompleteView,
    CourseOutlineView, CourseTranscriptView,
)
from .views_tags import TagListCreateView, TagDetailView, BatchAssignTagsView

urlpatterns = [
    path('', CourseListCreateView.as_view(), name='course-list'),
    path('chunked/init/', ChunkedUploadInitView.as_view(), name='course-chunked-init'),
    path('chunked/<str:upload_id>/chunk/', ChunkedUploadChunkView.as_view(), name='course-chunked-chunk'),
    path('chunked/<str:upload_id>/complete/', ChunkedUploadCompleteView.as_view(), name='course-chunked-complete'),
    path('tags/', TagListCreateView.as_view(), name='tag-list'),
    path('tags/batch-assign/', BatchAssignTagsView.as_view(), name='tag-batch-assign'),
    path('tags/<int:pk>/', TagDetailView.as_view(), name='tag-detail'),
    path('<int:pk>/', CourseDetailView.as_view(), name='course-detail'),
    path('<int:pk>/outline/', CourseOutlineView.as_view(), name='course-outline'),
    path('<int:pk>/transcript/', CourseTranscriptView.as_view(), name='course-transcript'),
    path('albums/', AlbumListCreateView.as_view(), name='album-list'),
    path('albums/<int:pk>/', AlbumDetailView.as_view(), name='album-detail'),
    path('albums/<int:album_id>/courses/', AlbumCoursesView.as_view(), name='album-courses'),
    path('startup-materials/', StartupMaterialListCreateView.as_view(), name='startup-material-list'),
    path('startup-materials/<int:pk>/', StartupMaterialDetailView.as_view(), name='startup-material-detail'),
    path('<int:pk>/progress/', VideoProgressUpdateView.as_view(), name='video-progress-update'),
]
