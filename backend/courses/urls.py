from django.urls import path
from .views import (
    CourseListCreateView, CourseDetailView, CourseReorderView,
    AlbumListCreateView, AlbumDetailView, AlbumCoursesView,
    StartupMaterialListCreateView, StartupMaterialDetailView,
    VideoProgressUpdateView,
    CourseOutlineView, CourseTranscriptView,
    OSSMultipartInitView, OSSMultipartCompleteView, OSSMultipartAbortView,
    OSSMultipartResignView,
)
from .views_tags import TagListCreateView, TagDetailView, BatchAssignTagsView
from .portal import LearningProgressView, LearningActivityView, WatchLaterListView, WatchLaterDetailView
from .goal import LearningGoalView
from .modules import ModuleListCreateView, ModuleDetailView, ModuleAssignView
from .offline import OfflineManifestView, OfflineAccessView, OfflineProgressView

urlpatterns = [
    path('offline-access/', OfflineAccessView.as_view(), name='course-offline-access'),
    path('<int:pk>/offline-manifest/', OfflineManifestView.as_view(), name='course-offline-manifest'),
    path('<int:pk>/offline-progress/', OfflineProgressView.as_view(), name='course-offline-progress'),
    path('modules/', ModuleListCreateView.as_view(), name='course-module-list'),
    path('modules/assign/', ModuleAssignView.as_view(), name='course-module-assign'),
    path('modules/<int:pk>/', ModuleDetailView.as_view(), name='course-module-detail'),
    path('learning-goal/', LearningGoalView.as_view(), name='course-learning-goal'),
    path('learning-progress/', LearningProgressView.as_view(), name='course-learning-progress'),
    path('learning-activity/', LearningActivityView.as_view(), name='course-learning-activity'),
    path('watch-later/', WatchLaterListView.as_view(), name='course-watch-later'),
    path('<int:pk>/watch-later/', WatchLaterDetailView.as_view(), name='course-watch-later-detail'),
    path('', CourseListCreateView.as_view(), name='course-list'),
    path('oss/multipart/init/', OSSMultipartInitView.as_view(), name='oss-multipart-init'),
    path('oss/multipart/complete/', OSSMultipartCompleteView.as_view(), name='oss-multipart-complete'),
    path('oss/multipart/abort/', OSSMultipartAbortView.as_view(), name='oss-multipart-abort'),
    path('oss/multipart/resign/', OSSMultipartResignView.as_view(), name='oss-multipart-resign'),
    path('tags/', TagListCreateView.as_view(), name='tag-list'),
    path('tags/batch-assign/', BatchAssignTagsView.as_view(), name='tag-batch-assign'),
    path('tags/<int:pk>/', TagDetailView.as_view(), name='tag-detail'),
    path('reorder/', CourseReorderView.as_view(), name='course-reorder'),
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
