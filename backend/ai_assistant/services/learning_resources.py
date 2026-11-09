"""Read bounded public HTTPS text with DNS pinning; no cookies, proxies or private hosts."""
import http.client
import ipaddress
import socket
import ssl
from html.parser import HTMLParser
from urllib.parse import quote, urljoin, urlsplit, urlunsplit
from uuid import uuid4
from xml.etree import ElementTree

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from ai_assistant.models import ProjectLearning


def public_text(url):
    for _ in range(4):
        parts = urlsplit(url)
        if (parts.scheme != 'https' or not parts.hostname or parts.username or parts.password
                or parts.port not in (None, 443) or len(url) > 3000):
            raise ValidationError('来源必须是公开的 HTTPS 页面。')
        host = parts.hostname.encode('idna').decode('ascii')
        addresses = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
        if not addresses or any(not ipaddress.ip_address(row[4][0]).is_global for row in addresses):
            raise ValidationError('不能读取内网、本机或保留地址。')
        pinned = addresses[0][4][0]
        connection = http.client.HTTPSConnection(host, timeout=12, context=ssl.create_default_context())
        connection._create_connection = lambda address, timeout, source_address=None: socket.create_connection((pinned, 443), timeout, source_address)
        try:
            path = quote(parts.path or '/', safe='/%:@!$&\'()*+,;=-._~') + (('?' + parts.query) if parts.query else '')
            connection.request('GET', path, headers={'User-Agent': 'UniMind-Learning/1.0', 'Accept-Encoding': 'identity'})
            response = connection.getresponse()
            if response.status in (301, 302, 303, 307, 308):
                location = response.getheader('Location')
                if not location:
                    raise ValidationError('来源跳转缺少目标地址。')
                url = urljoin(url, location)
                continue
            if response.status != 200:
                raise ValidationError(f'来源暂时不可读取（HTTP {response.status}）。')
            kind = response.getheader('Content-Type', '').lower()
            if not any(token in kind for token in ('text/', 'xml', 'json')):
                raise ValidationError('首期仅支持网页和文本来源，请提供可读页面。')
            raw = response.read(512001)
            if len(raw) > 512000:
                raise ValidationError('页面过大，请选择更具体的知识页面。')
            text = raw.decode(response.headers.get_content_charset() or 'utf-8', errors='replace')
            return urlunsplit((parts.scheme, parts.netloc, parts.path, parts.query, '')), text
        finally:
            connection.close()
    raise ValidationError('来源跳转次数过多。')


class PageText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.hidden = 0
        self.in_title = False
        self.title = []
        self.text = []

    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style', 'nav', 'noscript'):
            self.hidden += 1
        if tag == 'title':
            self.in_title = True

    def handle_endtag(self, tag):
        if tag in ('script', 'style', 'nav', 'noscript'):
            self.hidden = max(0, self.hidden - 1)
        if tag == 'title':
            self.in_title = False

    def handle_data(self, data):
        if self.in_title:
            self.title.append(data.strip())
        if not self.hidden and data.strip():
            self.text.append(data.strip())


def find_resources(project, arguments):
    try:
        if arguments.get('url'):
            url, html = public_text(str(arguments['url']))
            parser = PageText()
            parser.feed(html)
            excerpt = '\n'.join(parser.text)[:10000]
            if not excerpt:
                raise ValidationError('没有取得可读文本，不能将页面标为已读取。')
            resource = {'id': uuid4().hex, 'url': url, 'title': ' '.join(parser.title)[:200] or url,
                        'excerpt': excerpt, 'read_at': timezone.now().isoformat(),
                        'notice': '已读取网页文本；内容、时效与许可仍须结合任务核对。'}
            with transaction.atomic():
                state, _ = ProjectLearning.objects.get_or_create(project=project)
                state = ProjectLearning.objects.select_for_update().get(pk=state.pk)
                previous = next((item for item in state.resources if item['url'] == url), None)
                if previous:
                    resource['id'] = previous['id']
                resources = [item for item in state.resources if item['url'] != url]
                used = {source for stage in state.plan.get('stages', []) for source in stage.get('sources', [])}
                used.update(source for stage in state.pending_plan.get('plan', {}).get('stages', []) for source in stage.get('sources', []))
                while len(resources) >= 25:
                    removable = next((item for item in resources if item['id'] not in used), None)
                    if removable is None:
                        raise ValidationError('当前项目的来源已满，请先收敛阶段引用再添加新来源。')
                    resources.remove(removable)
                state.resources = [*resources, resource]
                state.save(update_fields=['resources', 'updated_at'])
            return {'resource': resource, 'revision': state.revision}
        query = str(arguments.get('query', '')).strip()
        if not query or len(query) > 300:
            raise ValidationError('请提供具体的学习资源查询词，最多 300 字。')
        _, xml = public_text('https://www.bing.com/search?format=rss&q=' + quote(query))
        root = ElementTree.fromstring(xml)
        candidates = [{'title': row.findtext('title', '')[:200], 'url': row.findtext('link', ''),
                       'summary': row.findtext('description', '')[:600]} for row in root.findall('./channel/item')]
        return {'candidates': [item for item in candidates if item['url'].startswith('https://')][:5],
                'notice': '仅搜索候选；先使用 url 读取原文，再作为计划来源。'}
    except (OSError, http.client.HTTPException, ValueError, ElementTree.ParseError) as exc:
        raise ValidationError('公开资源暂时无法读取，请更换来源或提供学习材料。') from exc
