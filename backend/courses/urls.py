from django.urls import path
from .views import (
    CourseListCreateView, CourseDetailView, AwardEloView,
    AlbumListCreateView, AlbumDetailView,
    StartupMaterialListCreateView, StartupMaterialDetailView,
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
    path('<int:pk>/award-elo/', AwardEloView.as_view(), name='course-award-elo'),
    path('<int:pk>/outline/', CourseOutlineView.as_view(), name='course-outline'),
    path('<int:pk>/transcript/', CourseTranscriptView.as_view(), name='course-transcript'),
    path('albums/', AlbumListCreateView.as_view(), name='album-list'),
    path('albums/<int:pk>/', AlbumDetailView.as_view(), name='album-detail'),
    path('startup-materials/', StartupMaterialListCreateView.as_view(), name='startup-material-list'),
    path('startup-materials/<int:pk>/', StartupMaterialDetailView.as_view(), name='startup-material-detail'),
    path('<int:pk>/progress/', VideoProgressUpdateView.as_view(), name='video-progress-update'),
]
