import assert from 'node:assert/strict';
import test from 'node:test';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { createServer } from 'vite';

const values = new Map();
globalThis.sessionStorage = {
  getItem: key => values.get(key) ?? null,
  setItem: (key, value) => values.set(key, value),
  removeItem: key => values.delete(key),
};
globalThis.document = {
  compatMode: 'CSS1Compat', querySelectorAll: () => [], querySelector: () => null, documentElement: {},
  head: { appendChild() {} }, createElement: () => ({ appendChild() {} }), createTextNode() {},
};
globalThis.location = new URL('http://localhost/');
globalThis.window = { location, addEventListener() {} };

const server = await createServer({ server: { middlewareMode: true, hmr: false }, optimizeDeps: { noDiscovery: true } });
try {
  const { isPersonalWorkspace, personalWorkbenchProjectId } = await server.ssrLoadModule('/src/lib/workbenchMode.ts');
  const { setActiveWorkspace } = await server.ssrLoadModule('/src/lib/activeWorkspace.ts');
  const { MarkdownContent } = await server.ssrLoadModule('/src/components/MarkdownContent.tsx');
  const { CitationPill } = await server.ssrLoadModule('/src/components/workbench/CitationPill.tsx');
  const { splitCitationMarkers, stripStreamingCitations, workbenchCitationMarkdown } = await server.ssrLoadModule('/src/components/workbench/workbenchCitations.tsx');
  const { findAnchoredChunk, playbackHref } = await server.ssrLoadModule('/src/components/workbench/workbenchSourcePresentation.ts');

  const pdf = {
    cite_key: 'S1#C3', index: 1, source_id: 'pdf-id', source_title: '金融讲义', source_type: 'pdf',
    chunk_id: 42, chunk_index: 3, anchor_type: 'page', locator_label: 'P.12', heading: '', quote: '准备金率',
    page_number: 12, slide_number: null, start_seconds: null, end_seconds: null, companion_url: null,
  };
  const video = {
    cite_key: 'S2#C0', index: 2, source_id: 'video-id', source_title: '第三讲', source_type: 'course',
    chunk_id: 78, chunk_index: 0, anchor_type: 'timestamp', locator_label: '14:20', heading: '', quote: '课程案例',
    page_number: null, slide_number: null, start_seconds: 860.9, end_seconds: 880, companion_url: '/course/3?project=8&t=860',
  };

  await test('个人项目进入三栏，个人自由对话和机构会话保留原布局', () => {
    assert.equal(isPersonalWorkspace(), true);
    assert.equal(personalWorkbenchProjectId(8), 8);
    assert.equal(personalWorkbenchProjectId(null), null);
    setActiveWorkspace(42);
    assert.equal(isPersonalWorkspace(), false);
    assert.equal(personalWorkbenchProjectId(8), null);
    assert.equal(personalWorkbenchProjectId(null), null);
    setActiveWorkspace(null);
  });

  await test('多来源引用在 Markdown 中各自显示，保留普通链接、代码与公式', () => {
    assert.deepEqual(splitCitationMarkers('见[S1#C3, S2#C0]和[S1#C3]'), [
      '见', { keys: ['S1#C3', 'S2#C0'] }, '和', { keys: ['S1#C3'] },
    ]);
    assert.equal(stripStreamingCitations('结论[S1#C3]。补充[S1#C3, S2#'), '结论。补充');
    assert.equal(stripStreamingCitations('引用[S1#C3，S2#C0] 与 [普通链接]'), '引用 与 [普通链接]');
    const markdown = workbenchCitationMarkdown([pdf, video], { conversationId: 'chat', onSelect() {} });
    const html = renderToStaticMarkup(React.createElement(MarkdownContent, {
      ...markdown,
      content: '见[S1#C3, S2#C0]。[S9#C0] [链接](https://example.com) `[S1#C3]` $x^2$',
    }));
    assert.equal((html.match(/class="um-wb-citation"/g) ?? []).length, 2);
    assert.match(html, /金融讲义/);
    assert.match(html, /14:20/);
    assert.match(html, /href="https:\/\/example.com"/);
    assert.match(html, /<code>\[S1#C3\]<\/code>/);
    assert.match(html, /katex/);
    assert.doesNotMatch(html, /S9#C0/);
  });

  await test('点击引用派发完整锚点，按片段而非同页的第一段定位', () => {
    let anchor;
    let click;
    function CaptureButton() {
      const card = CitationPill({ citation: pdf, conversationId: 'chat', onSelect: value => { anchor = value; } });
      click = card.props.children[0].props.children.props.onClick;
      return card;
    }
    renderToStaticMarkup(React.createElement(CaptureButton));
    click();
    assert.deepEqual(anchor, {
      sourceId: 'pdf-id', chunkId: 42, chunkIndex: 3, pageNumber: 12, slideNumber: null,
      startSeconds: null, quote: '准备金率',
    });
    const first = { ...pdf, id: 41, chunk_index: 2 };
    const exact = { ...pdf, id: 42 };
    assert.equal(findAnchoredChunk([first, exact], anchor), exact);
    assert.equal(findAnchoredChunk([first, exact], { sourceId: 'pdf-id', chunkIndex: 3 }), exact);
  });

  await test('伴学链接保留项目和对话，外部平台使用对应的时间参数', () => {
    assert.equal(playbackHref(video.companion_url, video.start_seconds, 'chat'), '/course/3?project=8&t=860&conversation=chat');
    assert.equal(playbackHref('https://www.bilibili.com/video/BV1?p=3', 65.8), 'https://www.bilibili.com/video/BV1?p=3&t=65');
    assert.equal(playbackHref('https://www.youtube.com/watch?v=xyz', 65.8), 'https://www.youtube.com/watch?v=xyz&t=65s');
  });
} finally {
  await server.close();
}
