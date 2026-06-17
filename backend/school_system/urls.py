import re
from django.contrib import admin
from django.urls import path, include, re_path
from django.conf import settings
from django.conf.urls.static import static
from django.http import HttpResponse, JsonResponse
from django.utils.html import escape
from pathlib import Path
from school_system.media_serve import media_serve
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView, SpectacularRedocView

_INTRO_PATH_RE = re.compile(r'^/intro/([^/]+)$')

_DEFAULT_META = {
    'title': 'UniMind.ai — Agent 驱动的新一代智能教育基础设施',
    'description': '从教师出题、学生刷题、评分批改到知识追踪，全链路 Agent 化。学生有专属 AI 教练，教师有对话式命题官。',
}


def _get_institution_meta(slug: str, request) -> dict | None:
    from users.models import Institution
    inst = Institution.objects.filter(slug=slug, is_active=True).first()
    if inst is None:
        return None
    name = escape(inst.name)
    desc = escape(inst.description) if inst.description else f'{name}，使用 UniMind.ai Agent 驱动的智能教育基础设施，AI 教练 + 对话式出题 + 自适应刷题。'
    meta = {
        'title': f'{name} - UniMind.ai — Agent 驱动的新一代智能教育基础设施',
        'description': desc,
    }
    if inst.logo:
        meta['og_image'] = request.build_absolute_uri(inst.logo.url)
    return meta


def _build_meta_html(meta: dict) -> str:
    lines = [f'    <title>{meta["title"]}</title>']
    lines.append(f'    <meta name="description" content="{meta["description"]}">')
    lines.append(f'    <meta property="og:title" content="{meta["title"]}">')
    lines.append(f'    <meta property="og:description" content="{meta["description"]}">')
    lines.append(f'    <meta property="og:type" content="website">')
    if meta.get('og_image'):
        lines.append(f'    <meta property="og:image" content="{meta["og_image"]}">')
    return '\n'.join(lines)


def serve_spa(request, *args, **kwargs):
    """Serve index.html for SPA client-side routing, injecting dynamic meta for intro pages."""
    index_path = Path(settings.BASE_DIR) / 'static' / 'index.html'
    if not index_path.exists():
        return HttpResponse('SPA entrypoint not found.', status=404)

    html = index_path.read_text()

    # Check if this is an institution intro page and inject dynamic meta
    path = request.path.rstrip('/')
    match = _INTRO_PATH_RE.match(path)
    if match:
        meta = _get_institution_meta(match.group(1), request) or _DEFAULT_META
    else:
        meta = _DEFAULT_META

    meta_html = _build_meta_html(meta)
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
    urlpatterns.append(path("api/users/", include("users.urls")))
if _APP_ON('quizzes'):
    urlpatterns.append(path("api/quizzes/", include("quizzes.urls")))
    urlpatterns.append(path("api/assignments/", include("quizzes.urls_assignments")))
if _APP_ON('study_room'):
    urlpatterns.append(path("api/study/", include("study_room.urls")))
if _APP_ON('courses'):
    urlpatterns.append(path("api/courses/", include("courses.urls")))
if _APP_ON('articles'):
    urlpatterns.append(path("api/articles/", include("articles.urls")))
if _APP_ON('ai_assistant'):
    urlpatterns.append(path("api/ai/", include("ai_assistant.urls")))
if _APP_ON('faq_system'):
    urlpatterns.append(path("api/qa/", include("faq_system.urls")))
if _APP_ON('notifications'):
    urlpatterns.append(path("api/notifications/", include("notifications.urls")))
if _APP_ON('interviews'):
    urlpatterns.append(path("api/interviews/", include("interviews.urls")))
if _APP_ON('payments'):
    urlpatterns.append(path("api/payments/", include("payments.urls")))
urlpatterns.append(path("api/", include("core.urls")))
urlpatterns += [
    re_path(r'^media/(?P<path>.*)$', media_serve, name='media-serve'),
    re_path(r'^(?!api/|admin/|media/|static/).*$', serve_spa, name='spa-catchall'),
] + static(settings.STATIC_URL, document_root=settings.BASE_DIR / 'static')
