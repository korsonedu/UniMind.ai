from django.contrib import admin
from django.urls import path, include, re_path
from django.conf import settings
from django.conf.urls.static import static
from django.http import HttpResponse
from pathlib import Path

def serve_spa(request, *args, **kwargs):
    """Serve index.html for SPA client-side routing."""
    index_path = Path(settings.BASE_DIR) / 'static' / 'index.html'
    if index_path.exists():
        return HttpResponse(index_path.read_text(), content_type='text/html')
    return HttpResponse('SPA entrypoint not found.', status=404)

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/users/", include("users.urls")),
    path("api/quizzes/", include("quizzes.urls")),
    path("api/study/", include("study_room.urls")),
    path("api/courses/", include("courses.urls")),
    path("api/articles/", include("articles.urls")),
    path("api/ai/", include("ai_assistant.urls")),
    path("api/qa/", include("faq_system.urls")),
    path("api/notifications/", include("notifications.urls")),
    path("api/interviews/", include("interviews.urls")),
    re_path(r'^(?!api/|admin/|media/|static/).*$', serve_spa, name='spa-catchall'),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT) + static(settings.STATIC_URL, document_root=settings.BASE_DIR / 'static')
