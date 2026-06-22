from django.urls import path
from .views import (
    CourseListCreateView, CourseDetailView,
    AlbumListCreateView, AlbumDetailView, AlbumCoursesView,
    StartupMaterialListCreateView, StartupMaterialDetailView,
    VideoProgressUpdateView,
    CourseOutlineView, CourseTranscriptView,
    OSSMultipartInitView, OSSMultipartCompleteView,
    TeachingPlanListCreateView, TeachingPlanDetailView,
    AIGenerateWeeklyPlansView,
    TeachingPlanAnalyticsView, LessonPlanPDFView,
)
from .views_tags import TagListCreateView, TagDetailView, BatchAssignTagsView

urlpatterns = [
    path('', CourseListCreateView.as_view(), name='course-list'),
    path('oss/multipart/init/', OSSMultipartInitView.as_view(), name='oss-multipart-init'),
    path('oss/multipart/complete/', OSSMultipartCompleteView.as_view(), name='oss-multipart-complete'),
    path('tags/', TagListCreateView.as_view(), name='tag-list'),
    path('tags/batch-assign/', BatchAssignTagsView.as_view(), name='tag-batch-assign'),
    path('tags/<int:pk>/', TagDetailView.as_view(), name='tag-detail'),
    path('teaching-plans/', TeachingPlanListCreateView.as_view(), name='teaching-plan-list'),
    path('teaching-plans/<int:pk>/', TeachingPlanDetailView.as_view(), name='teaching-plan-detail'),
    path('teaching-plans/<int:pk>/analytics/', TeachingPlanAnalyticsView.as_view(), name='teaching-plan-analytics'),
    path('teaching-plans/<int:pk>/ai-generate-weeks/', AIGenerateWeeklyPlansView.as_view(), name='teaching-plan-ai-weeks'),
    path('teaching-plans/<int:pk>/pdf/', LessonPlanPDFView.as_view(), name='teaching-plan-pdf'),
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
