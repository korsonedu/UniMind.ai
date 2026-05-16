from django.urls import path
from .views import (
    CourseListCreateView, CourseDetailView,
    AlbumListCreateView,
    StartupMaterialListCreateView,
    VideoProgressUpdateView, ChunkedUploadInitView,
    ChunkedUploadChunkView, ChunkedUploadCompleteView,
    CourseOutlineView, CourseTranscriptView,
)

urlpatterns = [
    path('', CourseListCreateView.as_view(), name='course-list'),
    path('chunked/init/', ChunkedUploadInitView.as_view(), name='course-chunked-init'),
    path('chunked/<str:upload_id>/chunk/', ChunkedUploadChunkView.as_view(), name='course-chunked-chunk'),
    path('chunked/<str:upload_id>/complete/', ChunkedUploadCompleteView.as_view(), name='course-chunked-complete'),
    path('<int:pk>/', CourseDetailView.as_view(), name='course-detail'),
    path('<int:pk>/outline/', CourseOutlineView.as_view(), name='course-outline'),
    path('<int:pk>/transcript/', CourseTranscriptView.as_view(), name='course-transcript'),
    path('albums/', AlbumListCreateView.as_view(), name='album-list'),
    path('startup-materials/', StartupMaterialListCreateView.as_view(), name='startup-material-list'),
    path('<int:pk>/progress/', VideoProgressUpdateView.as_view(), name='video-progress-update'),
]
