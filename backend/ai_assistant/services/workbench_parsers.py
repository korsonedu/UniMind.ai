"""Deterministic text extraction with locators suitable for citations."""

import http.client
import re
from html.parser import HTMLParser
from io import BytesIO

from docx import Document
from docx.text.paragraph import Paragraph
from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE_TYPE
from pypdf import PdfReader
from pypdf.errors import PyPdfError
from rest_framework.exceptions import ValidationError

from . import learning_resources


class WorkbenchParseError(ValueError):
    """An extraction failure with a message suitable for the source owner."""


PDF_NO_TEXT = '该 PDF 未检测到可提取文本层（可能为纯扫描件或受密码保护）'
MARKDOWN_HEADING = re.compile(r'^ {0,3}#{1,3}[ \t]+(.+?)(?:[ \t]+#+)?[ \t]*$')
MARKDOWN_FENCE = re.compile(r'^ {0,3}(`{3,}|~{3,})(.*)$')


def _split_text(text, limit, next_limit=None):
    text = text.strip()
    while len(text) > limit:
        floor = limit // 2
        cut = max(text.rfind(mark, floor, limit) for mark in '\n。！？；.!?; ')
        cut = cut + 1 if cut >= floor else limit
        yield text[:cut].strip()
        text = text[cut:].lstrip()
        limit = next_limit or limit
    if text:
        yield text


def _chunk(anchor_type, locator_label, content, heading='', **anchor):
    return {
        'anchor_type': anchor_type, 'locator_label': locator_label,
        'heading': heading[:240], 'content': content, **anchor,
    }


def parse_pdf_bytes(data):
    return parse_pdf_file(BytesIO(data))


def parse_pdf_file(file):
    return parse_pdf_document(file)[0]


def parse_pdf_document(file):
    """Return readable chunks and the page count, including blank pages."""
    try:
        reader = PdfReader(file)
        if reader.is_encrypted:
            raise WorkbenchParseError(PDF_NO_TEXT)

        chunks = []
        for page_number, page in enumerate(reader.pages, 1):
            content = (page.extract_text() or '').strip()
            if not content:
                continue
            first_line = content.splitlines()[0].strip()
            heading = first_line if len(first_line) <= 100 else ''
            for part, piece in enumerate(_split_text(content, 1800), 1):
                label = f'P.{page_number}' if part == 1 else f'P.{page_number} ({part})'
                chunks.append(_chunk('page', label, piece, heading, page_number=page_number))
    except PyPdfError as exc:
        raise WorkbenchParseError('无法读取该 PDF，请检查文件是否完整后重新上传。') from exc

    if not chunks:
        raise WorkbenchParseError(PDF_NO_TEXT)
    return chunks, len(reader.pages)


def _slide_text(shapes):
    for shape in shapes:
        if shape.shape_type == MSO_SHAPE_TYPE.GROUP:
            yield from _slide_text(shape.shapes)
        if shape.has_text_frame:
            yield shape.text
        if shape.has_table:
            for row in shape.table.rows:
                yield ' | '.join(cell.text.strip() for cell in row.cells).strip(' |')


def parse_pptx_file(file):
    return parse_pptx_document(file)[0]


def parse_pptx_document(file):
    """Return readable chunks and the original deck's slide count."""
    chunks = []
    slides = Presentation(file).slides
    for index, slide in enumerate(slides, 1):
        title = slide.shapes.title
        blocks = [text.strip() for text in _slide_text(slide.shapes) if text.strip()]
        if slide.has_notes_slide:
            frame = slide.notes_slide.notes_text_frame
            if frame is not None and frame.text.strip():
                blocks.append(f'[讲者备注] {frame.text.strip()}')
        if blocks:
            chunks.append(_chunk('slide', f'Slide {index}', '\n'.join(blocks),
                                 title.text.strip() if title is not None else '', slide_number=index))
    if not chunks:
        raise WorkbenchParseError('该演示文稿没有可提取的幻灯片文本。')
    return chunks, len(slides)


def _section_chunks(blocks):
    """Group consecutive paragraphs under their heading with a 1,400-character cap."""
    chunks = []
    heading = ''
    paragraphs = []
    length = 0

    def flush():
        nonlocal length
        if not paragraphs:
            return
        index = len(chunks) + 1
        label = f'§{index} {heading[:24]}' if heading else f'第 {index} 节'
        chunks.append(_chunk('section', label, '\n\n'.join(paragraphs), heading))
        paragraphs.clear()
        length = 0

    for is_heading, text in blocks:
        text = text.strip()
        if not text:
            continue
        if is_heading:
            flush()
            heading = text
        separator = 2 if paragraphs else 0
        if length >= 600 and length + separator + len(text) > 1400:
            flush()
            separator = 0
        for part, piece in enumerate(_split_text(text, 1400 - length - separator, next_limit=1400)):
            if part:
                flush()
                separator = 0
            paragraphs.append(piece)
            length += separator + len(piece)
    flush()
    if not chunks:
        raise WorkbenchParseError('来源没有可提取的正文，请检查内容后重试。')
    return chunks


def _document_blocks(document):
    for item in document.iter_inner_content():
        if isinstance(item, Paragraph):
            is_heading = item.style.style_id in {'Title', 'Heading1', 'Heading2', 'Heading3'}
            yield is_heading, item.text
        else:
            for row in item.rows:
                yield False, ' | '.join(cell.text.strip() for cell in row.cells).strip(' |')


def parse_docx_file(file):
    return _section_chunks(_document_blocks(Document(file)))


def _markdown_blocks(content):
    paragraph = []
    fence = ''
    for line in content.splitlines():
        marker = MARKDOWN_FENCE.match(line)
        if fence:
            paragraph.append(line)
            if marker and marker[1].startswith(fence) and not marker[2].strip():
                fence = ''
            continue
        if marker:
            fence = marker[1]
            paragraph.append(line)
            continue
        heading = MARKDOWN_HEADING.match(line)
        if heading or not line.strip():
            if paragraph:
                yield False, '\n'.join(paragraph)
                paragraph.clear()
            if heading:
                yield True, heading[1]
        else:
            paragraph.append(line)
    if paragraph:
        yield False, '\n'.join(paragraph)


def parse_text_content(content):
    return _section_chunks(_markdown_blocks(content.lstrip('\ufeff')))


class _StructuredPage(HTMLParser):
    headings = {'h1', 'h2', 'h3'}
    block_tags = headings | {'p', 'li'}
    hidden_tags = {'script', 'style', 'nav', 'noscript', 'footer', 'template'}

    def __init__(self):
        super().__init__()
        self.hidden = 0
        self.in_title = False
        self.title = []
        self.blocks = []
        self.open_blocks = []
        self.parts = []
        self.unstructured = []

    def _flush(self):
        text = ' '.join(''.join(self.parts).split())
        if text:
            self.blocks.append((self.open_blocks[-1] in self.headings, text))
        self.parts.clear()

    def handle_starttag(self, tag, attrs):
        if tag in self.hidden_tags:
            self.hidden += 1
        if self.hidden:
            return
        if tag == 'title':
            self.in_title = True
        elif tag in self.block_tags:
            self._flush()
            self.open_blocks.append(tag)
        elif tag == 'br' and self.open_blocks:
            self.parts.append(' ')

    def handle_endtag(self, tag):
        if tag in self.hidden_tags:
            self.hidden = max(0, self.hidden - 1)
        if tag == 'title':
            self.in_title = False
        elif not self.hidden and tag in self.open_blocks:
            self._flush()
            while self.open_blocks.pop() != tag:
                pass

    def handle_data(self, data):
        if self.hidden:
            return
        if self.in_title:
            self.title.append(data)
        elif self.open_blocks:
            self.parts.append(data)
        elif data.strip():
            self.unstructured.append(data.strip())

    def close(self):
        super().close()
        self._flush()


def parse_web_url(url):
    """Return citation chunks, the fetched URL after redirects, and the page title."""
    try:
        resolved_url, html = learning_resources.public_text(url)
    except ValidationError as exc:
        raise WorkbenchParseError(str(exc.detail[0])) from exc
    except (OSError, http.client.HTTPException, ValueError) as exc:
        raise WorkbenchParseError('暂时无法读取网页，请检查公开 HTTPS 链接后重试。') from exc

    page = _StructuredPage()
    page.feed(html)
    page.close()
    title = ' '.join(''.join(page.title).split())
    if not title:
        title = next((text for is_heading, text in page.blocks if is_heading), resolved_url)
    chunks = _section_chunks(page.blocks) if page.blocks else parse_text_content('\n'.join(page.unstructured))
    return chunks, resolved_url, title[:240]
