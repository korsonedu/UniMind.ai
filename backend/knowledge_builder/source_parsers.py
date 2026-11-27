"""Source-First document and series parsers producing PageIndex-style TOC trees."""
import json
import logging
import os
import re
import urllib.request
import zlib
from html import unescape

from rest_framework.exceptions import ValidationError

from . import public_asset_resolvers

logger = logging.getLogger(__name__)

MAX_SECTION_CHARS = 4000
MAX_SUMMARY_CHARS = 120
MAX_TOC_NODES = 120

_HTML_TAG_RE = re.compile(r'<[^>]+>')
_MD_LINK_RE = re.compile(r'\[([^\]]+)\]\((?:https?://|/)[^)]*\)')
_MD_IMAGE_RE = re.compile(r'!\[([^\]]*)\]\([^)]*\)')
_MD_DECOR_RE = re.compile(r'(?:^|\s)[#>*`~_]{1,4}(?=\s|$)')
_CN_HEADING_RE = re.compile(
    r'^(?:第[一二三四五六七八九十百千0-9]+[篇部章节讲单元课]|'
    r'[一二三四五六七八九十]+[、.．]|'
    r'(?:Chapter|Section|Part|Unit|Module)\s+\d+|'
    r'\d+(?:\.\d+){0,2}[、.\s]+)(.{1,120})$',
    re.I,
)


def clean_resource_excerpt(text: str, max_len: int = 600) -> str:
    """Clean raw HTML/Markdown/boilerplate fragments into readable plain text."""
    if not text:
        return ''
    value = unescape(str(text))
    value = re.sub(r'<(script|style)[^>]*>.*?</\1>', ' ', value, flags=re.I | re.S)
    value = _HTML_TAG_RE.sub(' ', value)
    value = _MD_IMAGE_RE.sub(lambda m: m.group(1) or ' ', value)
    value = _MD_LINK_RE.sub(r'\1', value)
    value = re.sub(r'```[\s\S]*?```', ' ', value)
    value = re.sub(r'`([^`]+)`', r'\1', value)
    value = re.sub(r'[*_~]+', '', value)
    value = _MD_DECOR_RE.sub(' ', value)
    value = re.sub(r'\bhttps?://\S+', '', value)
    lines = []
    for raw_line in value.splitlines():
        line = ' '.join(raw_line.split())
        if not line:
            continue
        if len(line) <= 2 and not re.search(r'[\u4e00-\u9fffA-Za-z0-9]', line):
            continue
        lines.append(line)
    cleaned = ' '.join(lines)
    cleaned = re.sub(r'\s{2,}', ' ', cleaned).strip()
    if max_len and len(cleaned) > max_len:
        return cleaned[: max_len - 1].rstrip() + '…'
    return cleaned


def _make_summary(text: str) -> str:
    return clean_resource_excerpt(text, max_len=MAX_SUMMARY_CHARS)


def _node_dict(node_id, parent_id, title, locator, body_text, url=''):
    cleaned_body = clean_resource_excerpt(body_text, max_len=MAX_SECTION_CHARS)
    return {
        'node_id': node_id,
        'parent_id': parent_id,
        'title': clean_resource_excerpt(title, max_len=160) or node_id,
        'locator': str(locator or '').strip()[:120],
        'summary': _make_summary(cleaned_body or title),
        'char_count': len(cleaned_body),
        'url': str(url or '').strip()[:1000],
        'children': [],
    }, cleaned_body


def flatten_toc_nodes(toc_tree: list[dict]) -> list[dict]:
    """Flatten a hierarchical toc_tree into a deterministic pre-order list."""
    flat = []

    def _walk(nodes):
        for node in nodes or []:
            if not isinstance(node, dict) or not node.get('node_id'):
                continue
            flat.append({
                'node_id': str(node['node_id']),
                'parent_id': node.get('parent_id'),
                'title': str(node.get('title') or ''),
                'locator': str(node.get('locator') or ''),
                'summary': str(node.get('summary') or ''),
                'char_count': int(node.get('char_count') or 0),
                'url': str(node.get('url') or ''),
            })
            _walk(node.get('children') or [])

    _walk(toc_tree)
    return flat


def parse_markdown_or_text(content: str, title: str = '', kind: str = 'markdown') -> tuple[list[dict], dict[str, str]]:
    """Parse Markdown or structured plain text into a PageIndex-style TOC tree + raw_sections."""
    text = (content or '').replace('\r\n', '\n').replace('\r', '\n').strip()
    if not text:
        raise ValidationError('请提供非空的 Markdown 或文本内容。')

    sections: list[dict] = []
    current = None
    in_code = False

    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        if stripped.startswith('```'):
            in_code = not in_code
            if current is not None:
                current['lines'].append(raw_line)
            continue

        heading_level = None
        heading_title = ''
        if not in_code:
            md_match = re.match(r'^(#{1,4})\s+(.+?)\s*#*$', stripped)
            if md_match:
                heading_level = len(md_match.group(1))
                heading_title = md_match.group(2).strip()
            elif kind == 'text' or not any(s['level'] <= 2 for s in sections):
                if len(stripped) <= 90 and not stripped.endswith(('。', '；', ';', '.', '，', ',')):
                    cn_match = _CN_HEADING_RE.match(stripped)
                    if cn_match:
                        if re.match(r'^第.+[篇部章]|^(?:Chapter|Part)\s+\d+|^[一二三四五六七八九十]+[、.．]', stripped, re.I):
                            heading_level = 1
                        elif re.match(r'^\d+\.\d+\.\d+', stripped):
                            heading_level = 3
                        elif re.match(r'^\d+\.\d+|第.+[节讲课]', stripped):
                            heading_level = 2
                        else:
                            heading_level = 2
                        heading_title = stripped

        if heading_level is not None and heading_title:
            if len(sections) >= MAX_TOC_NODES:
                if current is not None:
                    current['lines'].append(raw_line)
                continue
            current = {'level': heading_level, 'title': heading_title, 'lines': []}
            sections.append(current)
        else:
            if current is None:
                current = {'level': 1, 'title': title or '全文概览', 'lines': []}
                sections.append(current)
            current['lines'].append(raw_line)

    # If plain text had no headings and is long, chunk into readable paragraphs/parts.
    if len(sections) == 1 and len(text) > 1600:
        paragraphs = [p.strip() for p in re.split(r'\n{2,}', text) if p.strip()]
        if len(paragraphs) >= 2:
            sections = []
            buf = []
            buf_len = 0
            part_idx = 1
            for para in paragraphs:
                if buf and buf_len + len(para) > 1200 and len(sections) < MAX_TOC_NODES - 1:
                    first_line = buf[0].splitlines()[0][:48]
                    sections.append({'level': 1, 'title': f'第 {part_idx} 段 · {first_line}', 'lines': buf})
                    part_idx += 1
                    buf, buf_len = [], 0
                buf.append(para)
                buf_len += len(para)
            if buf:
                first_line = buf[0].splitlines()[0][:48]
                sections.append({'level': 1, 'title': f'第 {part_idx} 段 · {first_line}', 'lines': buf})

    toc_tree: list[dict] = []
    raw_sections: dict[str, str] = {}
    stack: list[tuple[int, dict]] = []

    for idx, sec in enumerate(sections, 1):
        level = sec['level']
        while stack and stack[-1][0] >= level:
            stack.pop()
        parent_id = stack[-1][1]['node_id'] if stack else None
        node_id = f's{idx}'
        locator = sec['title'][:64]
        body_text = '\n'.join(sec['lines']).strip()
        node, cleaned = _node_dict(node_id, parent_id, sec['title'], locator, body_text)
        raw_sections[node_id] = cleaned or node['title']
        if stack:
            stack[-1][1]['children'].append(node)
        else:
            toc_tree.append(node)
        stack.append((level, node))

    return toc_tree, raw_sections


def _extract_pdf_pages_pure_python(data: bytes) -> list[str]:
    """Best-effort lightweight pure-Python extractor for standard uncompressed/Flate text PDFs."""
    pages: list[str] = []
    streams = re.findall(rb'stream\r?\n(.*?)\r?\nendstream', data, flags=re.S)
    for raw_stream in streams:
        decoded = None
        for attempt in (raw_stream,):
            try:
                decoded = zlib.decompress(attempt)
                break
            except zlib.error:
                decoded = attempt
        if not decoded:
            continue
        text_chunks = []
        # Extract literal strings inside (...) before Tj / TJ operators.
        for match in re.finditer(rb'\(([^()\\]*(?:\\.[^()\\]*)*)\)\s*Tj', decoded):
            raw = match.group(1)
            raw = raw.replace(rb'\n', b'\n').replace(rb'\r', b' ').replace(rb'\t', b' ')
            raw = raw.replace(rb'\(', b'(').replace(rb'\)', b')').replace(rb'\\', b'\\')
            try:
                chunk = raw.decode('utf-8')
            except UnicodeDecodeError:
                chunk = raw.decode('latin-1', errors='ignore')
            if chunk.strip():
                text_chunks.append(chunk)
        for arr_match in re.finditer(rb'\[(.*?)\]\s*TJ', decoded, flags=re.S):
            parts = []
            for str_match in re.finditer(rb'\(([^()\\]*(?:\\.[^()\\]*)*)\)', arr_match.group(1)):
                raw = str_match.group(1).replace(rb'\(', b'(').replace(rb'\)', b')').replace(rb'\\', b'\\')
                try:
                    parts.append(raw.decode('utf-8'))
                except UnicodeDecodeError:
                    parts.append(raw.decode('latin-1', errors='ignore'))
            joined = ''.join(parts).strip()
            if joined:
                text_chunks.append(joined)
        if text_chunks:
            page_text = clean_resource_excerpt(' '.join(text_chunks), max_len=MAX_SECTION_CHARS)
            if len(page_text) >= 12:
                pages.append(page_text)
    return pages


def _extract_pdf_via_endpoint(data: bytes, filename: str, endpoint: str) -> tuple[list[dict], dict[str, str]] | None:
    """Optional pluggable MinerU/Docling HTTP parser via DOC_PARSER_ENDPOINT."""
    boundary = '----UniMindDocParserBoundary'
    safe_name = re.sub(r'[^A-Za-z0-9._-]+', '_', filename or 'document.pdf')
    body = (
        f'--{boundary}\r\n'
        f'Content-Disposition: form-data; name="file"; filename="{safe_name}"\r\n'
        f'Content-Type: application/pdf\r\n\r\n'
    ).encode('utf-8') + data + f'\r\n--{boundary}--\r\n'.encode('utf-8')
    req = urllib.request.Request(
        endpoint,
        data=body,
        headers={'Content-Type': f'multipart/form-data; boundary={boundary}'},
        method='POST',
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        payload = json.loads(resp.read().decode('utf-8'))
    markdown = payload.get('markdown') or payload.get('text') or ''
    if isinstance(markdown, str) and markdown.strip():
        return parse_markdown_or_text(markdown, title=filename, kind='markdown')
    return None


def parse_pdf_bytes(data: bytes, filename: str = '') -> tuple[list[dict], dict[str, str]]:
    """Parse PDF bytes via pluggable DOC_PARSER_ENDPOINT, pypdf/fitz if installed, or pure-Python fallback."""
    if not data or not data.startswith(b'%PDF'):
        raise ValidationError('上传的文件不是有效的 PDF 文档。')

    endpoint = (os.getenv('DOC_PARSER_ENDPOINT') or '').strip()
    if endpoint:
        try:
            parsed = _extract_pdf_via_endpoint(data, filename, endpoint)
            if parsed:
                return parsed
        except Exception as exc:
            logger.warning('DOC_PARSER_ENDPOINT failed, falling back to local PDF parser: %s', exc)

    pages: list[str] = []
    # Try optional lightweight libraries when present in the environment.
    try:
        import io
        from pypdf import PdfReader  # type: ignore
        reader = PdfReader(io.BytesIO(data))
        for page in reader.pages[:MAX_TOC_NODES]:
            pages.append((page.extract_text() or '').strip())
    except ImportError:
        try:
            import fitz  # type: ignore
            doc = fitz.open(stream=data, filetype='pdf')
            for idx in range(min(len(doc), MAX_TOC_NODES)):
                pages.append((doc[idx].get_text('text') or '').strip())
        except ImportError:
            pages = _extract_pdf_pages_pure_python(data)

    non_empty = [(idx + 1, text) for idx, text in enumerate(pages) if text and text.strip()]
    if not non_empty:
        raise ValidationError(
            '未能从该 PDF 提取到可选中文本（可能是扫描图片版 PDF）。建议粘贴 Markdown/纯文本讲义，或配置 DOC_PARSER_ENDPOINT（MinerU/Docling）解析。'
        )

    # Group pages into a clean TOC tree (1 node per page or grouped 3-page ranges if very long).
    toc_tree: list[dict] = []
    raw_sections: dict[str, str] = {}
    group_size = 1 if len(non_empty) <= 60 else max(2, (len(non_empty) + 59) // 60)

    for g_idx in range(0, len(non_empty), group_size):
        chunk = non_empty[g_idx:g_idx + group_size]
        p_start, p_end = chunk[0][0], chunk[-1][0]
        locator = f'P{p_start}' if p_start == p_end else f'P{p_start}-{p_end}'
        combined = '\n'.join(text for _, text in chunk)
        first_line = next((line.strip() for line in combined.splitlines() if len(line.strip()) >= 4), '')
        sec_title = f'{locator} · {first_line[:48]}' if first_line else f'第 {locator} 页'
        node_id = f'p{p_start}' if p_start == p_end else f'p{p_start}_{p_end}'
        node, cleaned = _node_dict(node_id, None, sec_title, locator, combined)
        toc_tree.append(node)
        raw_sections[node_id] = cleaned or sec_title

    return toc_tree, raw_sections


def parse_bilibili_series(
    url: str,
    title: str = '',
    outline_text: str = '',
    html_fetcher=None,
) -> tuple[str, str, list[dict], dict[str, str]]:
    """Parse a Bilibili multi-part series URL and/or custom episode outline into a TOC tree."""
    url = (url or '').strip()
    if not url.startswith('https://'):
        raise ValidationError('请提供 B 站公开 HTTPS 链接。')
    if public_asset_resolvers.detect_source_kind(url) != 'bilibili':
        raise ValidationError('请输入有效的 B 站视频或合集链接（bilibili.com）。')

    segments = []
    resolved_title = (title or '').strip()
    resolved_url = url
    description = ''

    if outline_text and outline_text.strip():
        segments = public_asset_resolvers.parse_custom_outline_segments(url, outline_text)
    if not segments:
        try:
            resolved = public_asset_resolvers.resolve_public_asset_url(url, html_fetcher=html_fetcher)
            resolved_title = resolved_title or resolved.get('title', '')
            resolved_url = resolved.get('url', url)
            description = resolved.get('description', '')
            segments = resolved.get('segments') or []
            if not segments:
                segments = [{
                    'index': 1,
                    'title': resolved_title or '主视频',
                    'url': resolved_url,
                    'locator': resolved.get('locator') or 'P1',
                    'summary': description or resolved_title,
                }]
        except Exception as exc:
            if not outline_text.strip():
                raise ValidationError(f'B 站合集解析失败，可粘贴自定义分 P 目录重试：{exc}') from exc

    resolved_title = resolved_title or 'B 站系列合集'
    toc_tree: list[dict] = []
    raw_sections: dict[str, str] = {}
    for idx, seg in enumerate(segments[:MAX_TOC_NODES], 1):
        node_id = f'ep{idx}'
        seg_title = str(seg.get('title') or f'第 {idx} 讲').strip()
        locator = str(seg.get('locator') or f'P{seg.get("index", idx)}').strip()
        seg_url = str(seg.get('url') or resolved_url).strip()
        seg_summary = str(seg.get('summary') or f'{resolved_title} · {locator} · {seg_title}').strip()
        node, cleaned = _node_dict(node_id, None, seg_title, locator, seg_summary, url=seg_url)
        toc_tree.append(node)
        raw_sections[node_id] = cleaned or seg_title

    return resolved_title, resolved_url, toc_tree, raw_sections


def parse_web_repo(
    url: str,
    title: str = '',
    outline_text: str = '',
    html_fetcher=None,
) -> tuple[str, str, list[dict], dict[str, str]]:
    """Parse an open-source web repo / wiki / doc site into a TOC tree."""
    url = (url or '').strip()
    if not url.startswith('https://'):
        raise ValidationError('请提供公开 HTTPS 链接。')
    if not public_asset_resolvers.is_asset_url_allowed(url, 'intl'):
        raise ValidationError('不支持该站点，请使用专业开源讲义、Wiki 或公开教材链接。')

    segments = public_asset_resolvers.parse_custom_outline_segments(url, outline_text) if outline_text.strip() else []
    resolved_title = (title or '').strip()
    resolved_url = url
    description = ''
    if not segments:
        try:
            resolved = public_asset_resolvers.resolve_public_asset_url(url, html_fetcher=html_fetcher)
            resolved_title = resolved_title or resolved.get('title', '')
            resolved_url = resolved.get('url', url)
            description = resolved.get('description', '')
            segments = resolved.get('segments') or []
        except Exception as exc:
            raise ValidationError(f'公开讲义解析失败：{exc}') from exc

    if not segments:
        segments = [{
            'index': 1,
            'title': resolved_title or '主页面',
            'url': resolved_url,
            'locator': public_asset_resolvers.extract_locator_from_url(resolved_url) or '主文档',
            'summary': description or resolved_title,
        }]

    resolved_title = resolved_title or '开源讲义资料'
    toc_tree: list[dict] = []
    raw_sections: dict[str, str] = {}
    for idx, seg in enumerate(segments[:MAX_TOC_NODES], 1):
        node_id = f'w{idx}'
        seg_title = str(seg.get('title') or f'章节 {idx}').strip()
        locator = str(seg.get('locator') or f'第 {idx} 节').strip()
        seg_url = str(seg.get('url') or resolved_url).strip()
        seg_summary = str(seg.get('summary') or seg_title).strip()
        node, cleaned = _node_dict(node_id, None, seg_title, locator, seg_summary, url=seg_url)
        toc_tree.append(node)
        raw_sections[node_id] = cleaned or seg_title

    return resolved_title, resolved_url, toc_tree, raw_sections


def parse_course_album(album_id: int, user) -> tuple[str, str, list[dict], dict[str, str]]:
    """Build a TOC tree from an in-platform Course Album visible to the user."""
    from types import SimpleNamespace
    from courses.access import visible_courses
    from courses.models import Album

    album = Album.objects.filter(pk=album_id).first()
    if album is None:
        raise ValidationError('所选站内课程专辑不存在。')
    courses = list(
        visible_courses(SimpleNamespace(user=user, query_params={}))
        .filter(album=album)
        .select_related('knowledge_point')
        .order_by('order', 'pk')[:MAX_TOC_NODES]
    )
    if not courses:
        raise ValidationError('当前空间下该专辑暂无可见课程。')

    toc_tree: list[dict] = []
    raw_sections: dict[str, str] = {}
    for idx, course in enumerate(courses, 1):
        node_id = f'c{course.pk}'
        locator = f'站内第{idx}讲'
        parts = [course.title]
        if course.knowledge_point:
            parts.append(f'关联知识点：{course.knowledge_point.name}')
        if course.description:
            parts.append(course.description)
        outline = getattr(course, 'ai_outline', None) or getattr(course, 'outline', None)
        if isinstance(outline, list):
            for seg in outline[:12]:
                if isinstance(seg, dict):
                    seg_label = seg.get('title') or seg.get('summary') or ''
                    if seg_label:
                        parts.append(str(seg_label))
        elif isinstance(outline, str) and outline.strip():
            parts.append(outline[:1200])
        transcript = getattr(course, 'transcript', None) or ''
        if isinstance(transcript, str) and transcript.strip():
            parts.append(transcript[:1500])
        body = '\n'.join(p for p in parts if p)
        node, cleaned = _node_dict(node_id, None, course.title, locator, body, url=f'/course/{course.pk}')
        toc_tree.append(node)
        raw_sections[node_id] = cleaned or course.title

    return album.name, '/courses', toc_tree, raw_sections
