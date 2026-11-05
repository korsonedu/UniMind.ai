import assert from 'node:assert/strict';
import { createServer } from 'vite';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';

const server = await createServer({
  server: { middlewareMode: true },
  // This test only loads SSR modules; no client dependency discovery is needed.
  optimizeDeps: { noDiscovery: true },
});
try {
  const { courseCitationComponents } = await server.ssrLoadModule('/src/components/course/courseCitations.tsx');
  const { MarkdownContent } = await server.ssrLoadModule('/src/components/MarkdownContent.tsx');
  let position;
  const components = courseCitationComponents({ course_id: 7, segments: [{ id: 42, start_time: 90.5, end_time: 110, text: '真实讲稿' }] }, 7, seconds => { position = seconds; });
  const renderLink = href => components.a({ href, children: '引用' });
  const valid = renderLink('/course/7?t=90.5#segment-42');
  assert.equal(valid.type, 'button');
  valid.props.onClick();
  assert.equal(position, 90.5);
  for (const href of ['/course/8?t=90.5#segment-42', '/course/7?t=91#segment-42', '/course/7?t=90.5#segment-99']) {
    assert.equal(renderLink(href).type, 'span');
  }
  assert.equal(renderLink('https://example.com').props.href, 'https://example.com');
  assert.equal(renderLink('https://example.com/#segment-42').type, 'a');
  assert.equal(courseCitationComponents(undefined, 7, () => {}).a({ href: '/course/7?t=90.5#segment-42', children: '旧消息' }).type, 'span');
  const visualComponents = courseCitationComponents({ course_id: 7, segments: [],
    visual: { current: { video_seconds: 120 }, previous: { video_seconds: 112 } } }, 7, seconds => { position = seconds; });
  for (const seconds of [112, 120]) {
    const link = visualComponents.a({ href: `/course/7?t=${seconds}`, children: '画面' });
    assert.equal(link.type, 'button');
    link.props.onClick();
    assert.equal(position, seconds);
  }
  for (const href of ['/course/8?t=120', '/course/7?t=113', '/course/7?t=120#other']) {
    assert.equal(visualComponents.a({ href, children: '错误画面' }).type, 'span');
  }
  const html = renderToStaticMarkup(React.createElement(MarkdownContent, {
    content: '正文 123 [讲稿](/course/7?t=90.5#segment-42) [普通链接](https://example.com)\n\n$$x^2$$', components,
  }));
  assert.match(html, /<button/);
  assert.match(html, /href="https:\/\/example.com"/);
  assert.match(html, /katex/);
  assert.match(html, /正文 123/);
  console.log('课程片段点击、拒绝伪造与跨课引用、普通链接、公式渲染检查通过');
} finally {
  await server.close();
}
