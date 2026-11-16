"""Resolve public learning pages into clickable, source-local learning segments."""

import json
import http.client
import re
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlencode, urljoin, urlsplit, urlunsplit


_SEED_PATH = Path(__file__).resolve().parents[1] / 'prompts/knowledge_builder/public_assets_seed.json'


def _host(url):
    return (urlsplit(url).hostname or '').lower().rstrip('.')


def _domain(host, domain):
    return host == domain or host.endswith('.' + domain)


def detect_source_kind(url: str) -> str:
    host = _host(url)
    for kind, domains in (
        ('bilibili', ('bilibili.com', 'b23.tv')),
        ('github', ('github.com',)),
        ('wikipedia', ('wikipedia.org', 'oi-wiki.org')),
        ('youtube', ('youtube.com', 'youtu.be')),
    ):
        if any(_domain(host, domain) for domain in domains):
            return kind
    return 'web'


def infer_region_scope(url: str, source_kind: str = '') -> str:
    kind, host = source_kind or detect_source_kind(url), _host(url)
    if kind == 'bilibili' or host in ('zh.wikipedia.org', 'oi-wiki.org') or _domain(host, 'oi-wiki.org') or host.endswith('.cn'):
        return 'cn'
    if kind == 'youtube' or host == 'en.wikipedia.org':
        return 'intl'
    return 'global'


def _time_locator(value):
    if re.fullmatch(r'\d+(?:\.\d+)?s?', value):
        seconds = int(float(value.rstrip('s')))
    elif re.fullmatch(r'(?:\d+h)?(?:\d+m)?(?:\d+s)?', value) and value:
        seconds = sum(int(number) * {'h': 3600, 'm': 60, 's': 1}[unit]
                      for number, unit in re.findall(r'(\d+)([hms])', value))
    else:
        return ''
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f'{hours:02d}:{minutes:02d}:{seconds:02d}' if hours else f'{minutes:02d}:{seconds:02d}'


def extract_locator_from_url(url: str, source_kind: str = '') -> str:
    parts = urlsplit(url)
    query = parse_qs(parts.query)
    labels = []
    page = query.get('p', [''])[0]
    if page.isdigit() and int(page) > 0:
        labels.append(f'P{int(page)}')
    timestamp = query.get('t', query.get('start', ['']))[0]
    if timestamp and (label := _time_locator(timestamp)):
        labels.append(label)
    if labels:
        return ' · '.join(labels)
    if parts.fragment:
        return '#' + unquote(parts.fragment)
    if (source_kind or detect_source_kind(url)) == 'github' and '/blob/' in parts.path:
        return unquote(parts.path.rsplit('/', 1)[-1])
    return ''


def _https_url(url):
    parts = urlsplit(url)
    if parts.scheme != 'https' or not parts.hostname or parts.username or parts.password or parts.port not in (None, 443):
        raise ValueError('Public assets require an HTTPS URL.')
    return url


def _public_text(url):
    # Keep seed loading usable without initializing Django; the existing fetcher
    # owns DNS pinning, private-address rejection, redirects and response limits.
    from ai_assistant.services.learning_resources import public_text
    return public_text(url)


def _clean(text):
    return ' '.join(unescape(re.sub(r'<[^>]*>', ' ', text)).split())


class _Page(HTMLParser):
    def __init__(self, content):
        super().__init__(convert_charrefs=True)
        self.title = ''
        self.description = ''
        self.first_paragraph = ''
        self.h1 = ''
        self.links = []
        self.headings = []
        self.pages = []
        self._captures = []
        self.feed(content)
        for label, href in re.findall(r'\[([^\]\n]+)\]\(([^\s)]+)(?:\s+"[^"]*")?\)', content):
            self.links.append((label, unescape(href)))
        if not self.title:
            match = re.search(r'^#\s+(.+)$', content, re.M)
            self.title = match.group(1).strip() if match else ''

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'meta' and attrs.get('name', attrs.get('property', '')).lower() in ('description', 'og:description'):
            self.description = attrs.get('content', '')
        if tag in ('title', 'h1', 'h2', 'p', 'a') or (tag == 'li' and 'data-page' in attrs):
            self._captures.append({'tag': tag, 'attrs': attrs, 'text': [], 'anchor': attrs.get('id', '')})
        if attrs.get('id'):
            for capture in self._captures:
                if capture['tag'] == 'h2' and not capture['anchor']:
                    capture['anchor'] = attrs['id']

    def handle_data(self, data):
        for capture in self._captures:
            capture['text'].append(data)

    def handle_endtag(self, tag):
        for index in range(len(self._captures) - 1, -1, -1):
            if self._captures[index]['tag'] != tag:
                continue
            capture = self._captures.pop(index)
            label = _clean(' '.join(capture['text']))
            attrs = capture['attrs']
            if tag == 'title':
                self.title = label
            elif tag == 'h1' and not self.h1:
                self.h1 = label
            elif tag == 'p' and label and not self.first_paragraph:
                self.first_paragraph = label
            elif tag == 'h2' and capture['anchor']:
                self.headings.append((label, capture['anchor']))
            elif tag == 'a' and attrs.get('href'):
                self.links.append((label, attrs['href']))
            elif tag == 'li' and attrs.get('data-page', '').isdigit():
                self.pages.append((int(attrs['data-page']), label))
            break


def _bvid_url(url):
    match = re.search(r'BV[0-9A-Za-z]+', urlsplit(url).path)
    return f'https://www.bilibili.com/video/{match.group()}' if match else ''


def _segment(index, title, url, locator, summary=''):
    return {'index': index, 'title': title, 'url': url, 'locator': locator, 'summary': summary or title}


def parse_custom_outline_segments(base_url: str, outline_text: str) -> list[dict]:
    bvid_url = _bvid_url(base_url) if detect_source_kind(base_url) == 'bilibili' else ''
    segments = []
    for line in outline_text.splitlines():
        line = line.strip()
        if not line:
            continue
        number = re.match(r'^(?:[-*]\s*)?(?:[Pp]\s*(\d+)|第\s*(\d+)\s*[讲章节]|(\d+)[.、)）])\s*', line)
        index = next((int(value) for value in number.groups() if value), len(segments) + 1) if number else len(segments) + 1
        match = re.search(r'https://[^\s<>"\]]+', line)
        url = match.group().rstrip('.，,；;') if match else ''
        while url.endswith(')') and url.count(')') > url.count('('):
            url = url[:-1]
        if not url and bvid_url:
            url = f'{bvid_url}?p={index}'
        if not url:
            continue
        _https_url(url)
        title = line[number.end():] if number else line
        if match:
            title = title.replace(match.group(), '').strip(' \t-:：[]()')
        title = title or f'第 {index} 讲'
        locator = extract_locator_from_url(url) or (f'P{index}' if bvid_url else title)
        segments.append(_segment(index, title, url, locator))
    return segments


def _bilibili_pages(content, page):
    decoder = json.JSONDecoder()
    for match in re.finditer(r'__INITIAL_STATE__\s*=\s*|["\']pages["\']\s*:\s*', content):
        try:
            value, _ = decoder.raw_decode(content[match.end():].lstrip())
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            video = value.get('videoData', value)
            pages = video.get('pages', [])
            if video.get('title'):
                page.title = str(video['title'])
        else:
            pages = value
        if isinstance(pages, list):
            found = [(int(item['page']), str(item['part'])) for item in pages
                     if isinstance(item, dict) and str(item.get('page', '')).isdigit() and item.get('part')]
            if found:
                return found
    if page.pages:
        return page.pages
    found = []
    for line in content.splitlines():
        match = re.match(r'^\s*(?:[-*]\s*)?(?:[Pp]\s*(\d+)|第\s*(\d+)\s*[讲章节]|(\d+)[.、)）])\s*[：:.-]?\s*(.+)', line)
        if match:
            number = next(int(value) for value in match.groups()[:3] if value)
            title = re.sub(r'\[([^\]]+)\]\([^)]*\)', r'\1', match.group(4))
            title = re.sub(r'https://\S+', '', title).strip()
            found.append((number, _clean(title)))
    return found


def _github_link(base_url, href):
    parts = urlsplit(base_url)
    path = parts.path.strip('/').split('/')
    if len(path) < 2:
        return ''
    if not href.startswith(('/', 'https://', 'http://', '#', '?')):
        if len(path) >= 4 and path[2] in ('blob', 'tree'):
            directory = parts.path.rsplit('/', 1)[0] if path[2] == 'blob' else parts.path.rstrip('/')
            base_url = f'https://github.com{directory}/'
        else:
            # HEAD is GitHub's default-branch reference, including master repos.
            base_url = f'https://github.com/{path[0]}/{path[1]}/blob/HEAD/'
    url = urljoin(base_url, href)
    target = urlsplit(url)
    target_path = target.path.strip('/').split('/')
    if (target.scheme != 'https' or target.hostname != 'github.com' or len(target_path) < 5
            or target_path[:2] != path[:2] or target_path[2] not in ('blob', 'tree')):
        return ''
    document = bool(re.search(r'\.(?:md|mdx|rst|ipynb|html?)$', target.path, re.I))
    if not href.startswith(('/', 'https://', 'http://', '#', '?')):
        target_path[2] = 'blob' if document else 'tree'
        url = urlunsplit(target._replace(path='/' + '/'.join(target_path)))
    if target_path[2] == 'blob' and not document:
        return ''
    return url


def resolve_public_asset_url(url: str, preferred_lang: str = 'zh', html_fetcher=None) -> dict:
    if url == '/courses' or url.startswith('/courses/'):
        return {'title': '课程', 'url': url, 'source_kind': 'web', 'asset_track': 'spotlight',
                'pedagogical_role': 'concept_intuition', 'locator': '', 'region_scope': 'global',
                'description': '', 'segments': []}
    _https_url(url)
    final_url, content = (html_fetcher or _public_text)(url)
    _https_url(final_url)
    kind = detect_source_kind(final_url)
    page = _Page(content)
    original_parts = urlsplit(url)
    final_parts = urlsplit(final_url)
    resolved_url = urlunsplit(final_parts._replace(fragment=original_parts.fragment or final_parts.fragment))
    result = {'title': page.h1 or page.title or unquote(final_parts.path.rstrip('/').rsplit('/', 1)[-1]) or final_parts.hostname,
              'url': resolved_url, 'source_kind': kind, 'asset_track': 'spotlight',
              'pedagogical_role': 'concept_intuition', 'locator': extract_locator_from_url(resolved_url, kind),
              'region_scope': infer_region_scope(resolved_url, kind),
              'description': _clean(page.description or page.first_paragraph), 'segments': []}
    if kind == 'bilibili':
        base_url = _bvid_url(final_url) or _bvid_url(url)
        if not base_url:
            raise ValueError('Bilibili page does not identify a BV video.')
        query = parse_qs(final_parts.query)
        query.update({key: values for key, values in parse_qs(original_parts.query).items() if key in ('p', 't')})
        result['url'] = base_url + ('?' + urlencode({key: values[0] for key, values in query.items() if key in ('p', 't')}) if any(key in query for key in ('p', 't')) else '')
        pages = dict(_bilibili_pages(content, page))
        result['title'] = page.title or result['title']
        result['locator'] = extract_locator_from_url(result['url'], kind) or 'P1'
        if len(pages) >= 2:
            result.update(asset_track='spine', pedagogical_role='series_episode')
            result['segments'] = [_segment(number, title, f'{base_url}?p={number}', f'P{number}',
                                           f"{result['title']} · 第 {number} 讲：{title}")
                                  for number, title in sorted(pages.items())]
    elif kind == 'github':
        result['pedagogical_role'] = 'core_derivation'
        links = {}
        for label, href in page.links:
            target = _github_link(final_url, href)
            if target and urlsplit(target).path != final_parts.path:
                links.setdefault(target, label or unquote(urlsplit(target).path.rsplit('/', 1)[-1]))
        if len(links) >= 2:
            result.update(asset_track='spine', pedagogical_role='series_episode')
            result['segments'] = [_segment(index, title, target, extract_locator_from_url(target, kind) or title)
                                  for index, (target, title) in enumerate(links.items(), 1)]
    elif kind == 'wikipedia':
        result.update(asset_track='wiki', pedagogical_role='wiki_reference')
        base_url = urlunsplit(final_parts._replace(fragment=''))
        headings = list(page.headings)
        if not headings:
            headings = [(label, unquote(href[1:])) for label, href in page.links if href.startswith('#') and len(href) > 1]
        seen = set()
        for title, anchor in headings:
            if anchor in seen:
                continue
            seen.add(anchor)
            result['segments'].append(_segment(len(seen), title, f'{base_url}#{quote(unquote(anchor), safe="")}', f'#{title}'))
    else:
        links = {}
        if kind == 'youtube':
            decoder = json.JSONDecoder()
            for match in re.finditer(r'"playlistVideoRenderer"\s*:\s*', content):
                try:
                    video, _ = decoder.raw_decode(content[match.end():].lstrip())
                except json.JSONDecodeError:
                    continue
                video_id = video.get('videoId', '')
                title_data = video.get('title', {})
                title = title_data.get('simpleText') or ''.join(run.get('text', '') for run in title_data.get('runs', []))
                if re.fullmatch(r'[A-Za-z0-9_-]+', video_id) and title:
                    links.setdefault('https://www.youtube.com/watch?' + urlencode({'v': video_id}), title)
        for title, href in page.links:
            target = urljoin(final_url, href)
            target_parts = urlsplit(target)
            if target_parts.scheme != 'https' or target == resolved_url:
                continue
            if kind == 'youtube':
                is_section = detect_source_kind(target) == 'youtube' and (target_parts.path == '/watch' or _host(target) == 'youtu.be')
            else:
                is_section = target_parts.hostname == final_parts.hostname and (href.startswith('#') or re.search(r'/(?:lectures?|lessons?|chapters?|sessions?|units?|videos?|resources?)[/-]', target_parts.path, re.I))
            if is_section:
                links.setdefault(target, title or extract_locator_from_url(target) or target_parts.path.rsplit('/', 1)[-1])
        if len(links) >= 2:
            result.update(asset_track='spine', pedagogical_role='series_episode')
            result['segments'] = [_segment(index, title, target, extract_locator_from_url(target) or title)
                                  for index, (target, title) in enumerate(links.items(), 1)]
    return result


def _subject_matches(subject, asset):
    subject = subject.strip().casefold()
    candidate = str(asset.get('subject', '')).casefold()
    if not subject or subject in candidate or candidate in subject:
        return True
    aliases = {'金融431': ('431', '金融', '公司理财', '货币银行', '投资学'),
               '计算机408': ('408', '计算机', '操作系统', '数据结构', '计算机网络', '计算机组成'),
               '微积分': ('微积分', '高数', '高等数学', '极限', '导数', '积分'),
               '线性代数': ('线性代数', '线代', '矩阵', '特征值', '向量空间')}
    return any(alias.casefold() in subject for alias in aliases.get(asset.get('subject'), ()))


def load_seed_public_assets(subject: str = '', region_pref: str = 'cn') -> list[dict]:
    with _SEED_PATH.open(encoding='utf-8') as source:
        assets = json.load(source)['assets']
    scopes = ('intl', 'global') if region_pref == 'intl' else ('cn', 'global')
    matches = [asset for asset in assets if asset.get('region_scope') in scopes and _subject_matches(subject, asset)]
    if region_pref == 'intl':
        matches.sort(key=lambda asset: asset['region_scope'] != 'intl')
    return matches


def search_wikipedia_concepts(query: str, lang: str = 'zh', limit: int = 5, fetcher=None) -> list[dict]:
    if lang not in ('zh', 'en'):
        raise ValueError('Wikipedia search language must be zh or en.')
    if limit <= 0 or not query.strip():
        return []
    base_url = f'https://{lang}.wikipedia.org'
    endpoint = base_url + '/w/api.php?' + urlencode({'action': 'query', 'list': 'search', 'srsearch': query,
                                                   'srlimit': min(limit, 50), 'format': 'json', 'utf8': 1})
    from django.core.exceptions import ImproperlyConfigured
    from rest_framework.exceptions import ValidationError

    try:
        _, content = (fetcher or _public_text)(endpoint)
        payload = json.loads(content)
        results = []
        query_result = payload.get('query', {})
        rows = query_result.get('search', [])
        if not rows:
            pages = query_result.get('pages', {})
            rows = list(pages.values()) if isinstance(pages, dict) else pages
        for row in rows[:limit]:
            if 'missing' in row:
                continue
            title = row['title']
            results.append({'title': title, 'url': base_url + '/wiki/' + quote(title.replace(' ', '_'), safe=''),
                            'locator': '#' + title, 'summary': _clean(row.get('snippet', row.get('extract', ''))),
                            'asset_track': 'wiki', 'source_kind': 'wikipedia',
                            'region_scope': 'cn' if lang == 'zh' else 'intl'})
        if results:
            return results
    except (OSError, http.client.HTTPException, ValueError, ValidationError, ImproperlyConfigured):
        # Offline seed lookup is part of the public search contract.
        pass
    terms = [word.casefold() for word in re.split(r'\s+', query.strip())]
    seeds = load_seed_public_assets('', 'cn' if lang == 'zh' else 'intl')
    results = []
    for asset in seeds:
        if asset.get('asset_track') != 'wiki' or _host(asset.get('url', '')) != f'{lang}.wikipedia.org':
            continue
        haystack = ' '.join([asset.get('title', ''), asset.get('subject', ''), asset.get('description', ''), *asset.get('topic_keywords', [])]).casefold()
        if all(term in haystack for term in terms):
            results.append({'title': asset['title'], 'url': asset['url'], 'locator': asset.get('locator', ''),
                            'summary': asset.get('summary', asset.get('description', '')), 'asset_track': 'wiki',
                            'source_kind': 'wikipedia', 'region_scope': 'cn' if lang == 'zh' else 'intl'})
            if len(results) >= limit:
                break
    return results
