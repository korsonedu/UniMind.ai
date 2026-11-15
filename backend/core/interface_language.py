"""Translate fixed interface messages, leaving content and protocol fields intact."""
import json
import re
from pathlib import Path

from django.utils import translation
from django.utils.cache import patch_vary_headers
from django.utils.deprecation import MiddlewareMixin

CATALOG = json.loads((Path(__file__).parent / 'locales' / 'en.json').read_text())
PATTERNS = [(re.compile('^' + re.sub(r'\\\{\d+\\\}', '(.*?)', re.escape(source)) + '$'), target)
            for source, target in CATALOG.items() if re.search(r'\{\d+\}', source)]


def ui_text(value, language=None):
    if not isinstance(value, str) or (language or translation.get_language()) != 'en':
        return value
    if value in CATALOG:
        return CATALOG[value]
    for pattern, target in PATTERNS:
        match = pattern.fullmatch(value)
        if match:
            return re.sub(r'\{(\d+)\}', lambda part: match.group(int(part[1]) + 1), target)
    return value


def error_text(value, language=None):
    if isinstance(value, dict):
        return {key: error_text(item, language) for key, item in value.items()}
    if isinstance(value, list):
        return [error_text(item, language) for item in value]
    return ui_text(value, language)


def response_text(data, status):
    if status >= 400:
        return error_text(data)
    if isinstance(data, dict):
        return {key: ui_text(value) if key in {'message', 'detail', 'error'} else value for key, value in data.items()}
    return data


class InterfaceLanguageMiddleware(MiddlewareMixin):
    async_capable = False

    def __call__(self, request):
        if not request.path.startswith(('/api/', '/accounts/', '/account-api/')):
            return super().__call__(request)
        preference = request.COOKIES.get('unimind-language', '')
        if request.path.startswith('/accounts/'):
            preference = request.GET.get('ui_language', preference)
        header = request.headers.get('Accept-Language', '').split(',')[0].split(';')[0].strip()
        language = (header or preference) if request.path.startswith(('/api/', '/account-api/')) else (preference or header)
        request.ui_language = 'zh-CN' if not language or language.lower().startswith('zh') else 'en'
        with translation.override('en' if request.ui_language == 'en' else 'zh-hans'):
            response = super().__call__(request)
            if not getattr(response, 'streaming', False) and response.get('Content-Type', '').startswith('application/json') and not hasattr(response, 'data'):
                data = json.loads(response.content)
                translated = response_text(data, response.status_code)
                if translated != data:
                    response.content = json.dumps(translated, ensure_ascii=False)
                    if response.has_header('Content-Length'):
                        response['Content-Length'] = str(len(response.content))
            elif response.status_code >= 400 and not getattr(response, 'streaming', False) and response.get('Content-Type', '').startswith('text/html'):
                response.content = ui_text(response.content.decode(response.charset))
        patch_vary_headers(response, ('Accept-Language', 'Cookie'))
        response['Content-Language'] = request.ui_language
        if request.path.startswith('/accounts/') and request.GET.get('ui_language') in {'en', 'zh-CN'}:
            response.set_cookie('unimind-language', request.ui_language, max_age=31536000, samesite='Lax', secure=request.is_secure())
        return response

    def process_template_response(self, request, response):
        if hasattr(response, 'data'):
            translated = response_text(response.data, response.status_code)
            if translated != response.data:
                response.data = translated
        return response
