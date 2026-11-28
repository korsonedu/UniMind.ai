"""Resolve inline references against evidence actually supplied this turn."""
import json
import re
from hashlib import sha256
from urllib.parse import urlencode

WORKBENCH_KEY = r'S[1-9]\d*#C\d+'
INLINE_KEY = rf'(?:{WORKBENCH_KEY}(?:[LT][1-9]\d*)?|[NAW][1-9]\d*#L[1-9]\d*|V[1-9]\d*#T[1-9]\d*)'
INLINE_MARKER = re.compile(rf'\[({INLINE_KEY}(?:\s*[,，]\s*{INLINE_KEY})*)\]')


def citation_keys(content):
    return dict.fromkeys(key for group in INLINE_MARKER.findall(content or '')
                         for key in re.split(r'\s*[,，]\s*', group))


def note_citation_rows(sources, context):
    rows = []
    for source in sources or ():
        for number, line in source.get('citation_lines', ()):
            key = f"{source['source_id']}#L{number}"
            if f'{line} [{key}]' in context:
                rows.append({'key': key, 'kind': 'note', 'title': source['title'], 'line': number,
                             'href': f"/notes/{source['note_id']}?line={number}&version={source['version']}"})
    return rows


def matching_article_lines(content, query, alias, *, limit=4):
    lines = [(number, line) for number, line in enumerate(
        content.replace('\r\n', '\n').replace('\r', '\n').split('\n'), 1) if line.strip()]
    folded = query.casefold()
    matches = [(number, line) for number, line in lines if folded and folded in line.casefold()]
    return [
        {'line': number, 'text': line[max(0, line.casefold().find(folded) - 220):][:500],
         'citation': f'[{alias}#L{number}]'}
        for number, line in (matches or lines)[:limit]
    ]


def read_web_article(url, query):
    from .workbench_parsers import WorkbenchParseError, parse_web_url

    try:
        chunks, source_url, title = parse_web_url(url)
    except WorkbenchParseError as exc:
        return {'error': str(exc)}
    alias = f'W{int(sha256(source_url.encode()).hexdigest()[:12], 16) + 1}'
    content = '\n'.join(chunk['content'] for chunk in chunks)
    return {'web_article': {'title': title, 'url': source_url,
                            'lines': matching_article_lines(content, query, alias, limit=12)}}


def tool_citation_rows(result):
    rows = []
    for article in result.get('articles', ()):
        for line in article.get('lines', ()):
            number = line['line']
            params = urlencode({'line': number, 'version': article['version']})
            rows.append({'key': line['citation'][1:-1], 'kind': 'article', 'title': article['title'],
                         'line': number, 'href': f"{article['url']}?{params}"})
    if web := result.get('web_article'):
        for line in web['lines']:
            rows.append({'key': line['citation'][1:-1], 'kind': 'web', 'title': web['title'],
                         'line': line['line'], 'text': line['text'], 'href': web['url']})
    for segment in result.get('segments', ()):
        if marker := segment.get('citation'):
            rows.append({'key': marker[1:-1], 'kind': 'video', 'title': segment['course_title'],
                         'seconds': segment['start_seconds'], 'href': segment['url']})
    return rows


def asset_citations(content, rows):
    registry = {row['key']: row for row in rows}
    return [registry[key] for key in citation_keys(content) if key in registry]


def legacy_asset_citations(content, sources, note_context, executor):
    rows = note_citation_rows(sources, note_context)
    for call, output in zip(getattr(executor, 'tool_call_log', ()), getattr(executor, 'tool_output_log', ())):
        if call['name'] in ('search_asr', 'search_articles', 'read_web_article'):
            rows.extend(tool_citation_rows(json.loads(output)))
    return asset_citations(content, rows)
