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
globalThis.localStorage = { getItem: () => 'zh-CN' };
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
  const { FlashcardDeckView } = await server.ssrLoadModule('/src/components/workbench/FlashcardDeckView.tsx');
  const { StudioQuizView } = await server.ssrLoadModule('/src/components/workbench/StudioQuizView.tsx');
  const { flashcardStep, studioQuizAnswers } = await server.ssrLoadModule('/src/components/workbench/studioPractice.ts');
  const { companionProjectId, companionReturnHref, companionSeconds } = await server.ssrLoadModule('/src/lib/companionVideo.ts');
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
    const href = playbackHref(video.companion_url, video.start_seconds, 'chat + id');
    assert.equal(href, '/course/3?project=8&t=860.9&conversation=chat+%2B+id');
    const { searchParams } = new URL(href, 'http://localhost');
    assert.equal(companionProjectId(searchParams), 8);
    assert.equal(companionSeconds(searchParams), 860.9);
    assert.equal(companionReturnHref(8, searchParams.get('conversation')), '/xiaoyu?project=8&conversation=chat+%2B+id');
    assert.equal(companionReturnHref(8), '/xiaoyu?project=8');
    assert.equal(companionSeconds(new URLSearchParams('t=0')), 0);
    for (const input of ['', 't=', 't=-1', 't=Infinity']) assert.equal(companionSeconds(new URLSearchParams(input)), null);
    for (const input of ['', 'project=0', 'project=8.1', 'project=0x8']) assert.equal(companionProjectId(new URLSearchParams(input)), null);
    assert.equal(playbackHref('https://www.bilibili.com/video/BV1?p=3', 65.8), 'https://www.bilibili.com/video/BV1?p=3&t=65');
    assert.equal(playbackHref('https://www.youtube.com/watch?v=xyz', 65.8), 'https://www.youtube.com/watch?v=xyz&t=65s');
  });

  await test('闪卡默认显示题面，进度与掌握状态和卡组一致，键盘前后切换有边界', () => {
    const cards = [
      { id: 'fc_1', front: '何为准备金率？', back: '法定准备金占存款的比例。', hint: '看第十二页', cite_key: pdf.cite_key, mastery: 'unseen' },
      { id: 'fc_2', front: '第二张', back: '第二张答案', hint: '', cite_key: pdf.cite_key, mastery: 'mastered' },
    ];
    let body;
    function Deck() {
      body = FlashcardDeckView({ cards, citations: [pdf], conversationId: 'chat', onSelect() {}, onRate() {}, saving: false });
      return body;
    }
    const html = renderToStaticMarkup(React.createElement(Deck));
    assert.match(html, /第 1 张，共 2 张/);
    assert.match(html, /已掌握 1 张/);
    assert.match(html, /<progress[^>]+value="1"[^>]+max="2"/);
    assert.match(html, /um-wb-card-back" aria-hidden="true" inert=""/);
    assert.match(html, /何为准备金率/);
    assert.match(html, /金融讲义/);
    assert.equal(flashcardStep(0, 'ArrowLeft', cards.length), 0);
    assert.equal(flashcardStep(0, 'ArrowRight', cards.length), 1);
    assert.equal(flashcardStep(1, 'ArrowRight', cards.length), 1);
    let prevented = false;
    body.props.onKeyDown({ key: 'ArrowLeft', preventDefault: () => { prevented = true; } });
    assert.equal(prevented, true);
  });

  await test('自测支持选项 0 与主观答案，提交前隐藏答案，批改后显示得分和来源', () => {
    const questions = [
      { id: 'q_1', type: 'single_choice', prompt: '准备金率衡量什么？', options: ['比例', '绝对金额'], cite_key: pdf.cite_key },
      { id: 'q_2', type: 'subjective', prompt: '解释第三讲的案例。', cite_key: video.cite_key },
    ];
    assert.deepEqual(studioQuizAnswers(questions, { q_1: 0, q_2: ' 先然后。 ', outside: 1 }),
      [{ question_id: 'q_1', answer: 0 }, { question_id: 'q_2', answer: '先然后。' }]);
    assert.deepEqual(studioQuizAnswers(questions, { q_2: '   ' }), []);
    const props = { questions, submitting: false, conversationId: 'chat', onSelect() {}, onSubmit() {}, onGenerate() {} };
    const initial = renderToStaticMarkup(React.createElement(StudioQuizView, props));
    assert.match(initial, /type="radio"/);
    assert.match(initial, /<textarea/);
    assert.match(initial, /disabled="">提交批改/);
    assert.doesNotMatch(initial, /参考答案|金融讲义/);
    const attempt = { score: 1.5, max_score: 2, results: [
      { question_id: 'q_1', answer: 0, correct_answer: 0, score: 1, max_score: 1, explanation: '比例的含义', feedback: '', citation: pdf },
      { question_id: 'q_2', answer: '作答内容', correct_answer: '参考推导', score: .5, max_score: 1, explanation: '过程解析', feedback: '补充末步', citation: video },
    ] };
    const graded = renderToStaticMarkup(React.createElement(StudioQuizView, { ...props, attempt }));
    assert.match(graded, /1.5 \/ 2/);
    assert.match(graded, /参考答案.*比例/);
    assert.match(graded, /补充末步/);
    assert.match(graded, /金融讲义/);
    assert.match(graded, /14:20/);
    assert.match(graded, /重新作答/);
    assert.match(graded, /生成新自测/);
    assert.doesNotMatch(graded, /提交批改/);
  });
} finally {
  await server.close();
}
