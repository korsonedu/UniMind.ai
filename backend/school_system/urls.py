import re
from django.contrib import admin
from django.urls import path, include, re_path
from django.conf import settings
from django.contrib.staticfiles.urls import staticfiles_urlpatterns
from django.http import FileResponse, Http404, HttpResponse, JsonResponse
from school_system.media_serve import media_serve
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView, SpectacularRedocView

_DEFAULT_META = {
    'title': 'UniMind.ai 智能学习平台',
    'description': 'UniMind.ai 智能学习平台，提供练习、错题复习、学习记录和 AI 对话。',
}


def _build_meta_html(meta: dict) -> str:
    lines = [f'    <title>{meta["title"]}</title>']
    lines.append(f'    <meta name="description" content="{meta["description"]}">')
    lines.append(f'    <meta property="og:title" content="{meta["title"]}">')
    lines.append(f'    <meta property="og:description" content="{meta["description"]}">')
    lines.append(f'    <meta property="og:type" content="website">')
    if meta.get('og_image'):
        lines.append(f'    <meta property="og:image" content="{meta["og_image"]}">')
    return '\n'.join(lines)


def serve_spa(request, path):
    """Serve the current Vite build and support client-side routing."""
    dist = (settings.BASE_DIR.parent / 'frontend' / 'dist').resolve()
    asset = (dist / path).resolve()
    if not asset.is_relative_to(dist):
        raise Http404
    index_path = dist / 'index.html'
    if asset != index_path and asset.is_file():
        return FileResponse(asset.open('rb'))
    if path.startswith('assets/'):
        raise Http404

    if not index_path.exists():
        return HttpResponse('SPA entrypoint not found.', status=404)

    html = index_path.read_text()

    meta_html = _build_meta_html(_DEFAULT_META)
    html = re.sub(r'^\s*<title>.*?</title>\s*$', meta_html, html, flags=re.MULTILINE)

    return HttpResponse(html, content_type='text/html')

def health_check(request):
    """K8s / load balancer readiness probe."""
    from django.db import connections
    from django.core.cache import cache

    db_ok = True
    try:
        connections['default'].cursor().execute('SELECT 1')
    except Exception:
        db_ok = False

    cache_ok = True
    try:
        cache.set('health_check', 1, 10)
        cache_ok = cache.get('health_check') == 1
    except Exception:
        cache_ok = False

    status = 200 if (db_ok and cache_ok) else 503
    return JsonResponse({
        'status': 'ok' if status == 200 else 'degraded',
        'database': db_ok,
        'cache': cache_ok,
    }, status=status)


_ENABLED = settings.ENABLED_APPS
_APP_ON = lambda name: _ENABLED is None or name in _ENABLED

urlpatterns = [
    path("health/", health_check, name='health-check'),
    path("admin/", admin.site.urls),
    path("api/schema/", SpectacularAPIView.as_view(), name='schema'),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path("api/redoc/", SpectacularRedocView.as_view(url_name='schema'), name='redoc'),
]
if _APP_ON('users'):
    urlpatterns.append(path("", include("users.accounts.urls")))
    urlpatterns.append(path("api/users/", include("users.urls")))
if _APP_ON('quizzes'):
    urlpatterns.append(path("api/quizzes/", include("quizzes.urls")))
if _APP_ON('courses'):
    urlpatterns.append(path("api/courses/", include("courses.urls")))
    urlpatterns.append(path("api/backoffice/", include("backoffice.urls")))
if _APP_ON('articles'):
    urlpatterns.append(path("api/articles/", include("articles.urls")))
if _APP_ON('ai_assistant'):
    urlpatterns.append(path("api/ai/", include("ai_assistant.urls")))
    from ai_assistant import views_learning_memory_oauth
    urlpatterns.extend([
        path(".well-known/oauth-protected-resource/api/ai/learning-memory/mcp/",
             views_learning_memory_oauth.resource_metadata, name="learning-memory-oauth-resource"),
        path(".well-known/oauth-authorization-server",
             views_learning_memory_oauth.server_metadata, name="learning-memory-oauth-metadata"),
        path("api/ai/learning-memory/oauth/authorize/",
             views_learning_memory_oauth.authorize, name="learning-memory-oauth-authorize"),
        path("api/ai/learning-memory/oauth/token/", views_learning_memory_oauth.token, name="learning-memory-oauth-token"),
        path("api/ai/learning-memory/oauth/register/",
             views_learning_memory_oauth.register_client, name="learning-memory-oauth-register"),
    ])
if _APP_ON('notes'):
    urlpatterns.append(path("api/notes/", include("notes.urls")))
if _APP_ON('notifications'):
    urlpatterns.append(path("api/notifications/", include("notifications.urls")))
if _APP_ON('payments'):
    urlpatterns.append(path("api/payments/", include("payments.urls")))
if _APP_ON('knowledge_builder'):
    urlpatterns.append(path("api/knowledge-builder/", include("knowledge_builder.urls")))
# API v1 (external, API Key auth)
from users.views_institution import RetiredInstitutionView
urlpatterns += [
    path("api/v1/questions/", RetiredInstitutionView.as_view(), name='v1-questions'),
    path("api/v1/analytics/overview/", RetiredInstitutionView.as_view(), name='v1-analytics'),
]
urlpatterns.append(path("api/", include("core.urls")))
urlpatterns += [
    re_path(r'^media/(?P<path>.*)$', media_serve, name='media-serve'),
    re_path(r'^(?!api/|admin/|media/|static/|accounts/|account-api/)(?P<path>.*)$', serve_spa, name='spa-catchall'),
]
if settings.DEBUG:
    urlpatterns += staticfiles_urlpatterns()
