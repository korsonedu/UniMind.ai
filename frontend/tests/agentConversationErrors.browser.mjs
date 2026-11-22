import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { after, before, beforeEach, test } from 'node:test';
import { createServer } from 'vite';

// Run: PLAYWRIGHT_MODULE=/path/to/playwright node --test tests/agentConversationErrors.browser.mjs
// Isolated hook tests: real React, stream reader and recovery storage; no backend/model calls.
const { chromium } = createRequire(import.meta.url)(process.env.PLAYWRIGHT_MODULE || 'playwright');
const entry = `
import React from 'react';
import { createRoot } from 'react-dom/client';
import { toast } from 'sonner';
import { useAgentConversation } from '/src/hooks/useAgentConversation.ts';
import { useAuthStore } from '/src/store/useAuthStore.ts';
import { readRecovery, recoveryScope } from '/src/lib/conversationRecovery.ts';
import api from '/src/lib/api.ts';
const findBot = bots => bots[0];
api.get = async () => ({data: []});
api.post = async () => ({data: {}});
useAuthStore.setState({user: {id: 1}});
window.errors = [];
window.requests = [];
window.settled = [];
window.doneCalls = 0;
window.saved = () => readRecovery(recoveryScope(1, 1));
toast.error = message => window.errors.push(message);
window.fetch = async (_url, init) => {
  if (window.httpError) return Response.json(window.httpError.body, {status: window.httpError.status});
  if (window.networkError) throw new TypeError('Failed to fetch');
  let controller;
  const body = new ReadableStream({start(c) { controller = c; }});
  init.signal.addEventListener('abort', () => controller.error(new DOMException('Stopped', 'AbortError')));
  window.requests.push({init, controller});
  return new Response(body);
};
function Harness() {
  window.chat = useAgentConversation({
    findBot,
    onDone: () => ++window.doneCalls,
    onRunSettled: (id, outcome) => window.settled.push({id, outcome}),
  });
  return null;
}
window.root = createRoot(document.getElementById('root'));
window.root.render(React.createElement(Harness));
`;
let server, browser, context, page;
before(async () => {
  server = await createServer({
    server: {host: '127.0.0.1', port: 0},
    plugins: [{
      name: 'conversation-errors-test',
      configureServer(server) {
        server.middlewares.use('/__chat-errors', (_req, res) => {
          res.setHeader('Content-Type', 'text/html');
          res.end('<div id="root"></div><script type="module" src="/@vite/client"></script><script type="module" src="/__error-harness.js"></script>');
        });
      },
      resolveId(id) { if (id === '/__error-harness.js') return id; },
      load(id) { if (id === '/__error-harness.js') return entry; },
    }],
  });
  await server.listen();
  browser = await chromium.launch({headless: true, channel: process.env.BROWSER_CHANNEL || 'chrome'});
});
after(async () => {
  await context?.close();
  await browser?.close();
  await server?.close();
});
beforeEach(async () => {
  await context?.close();
  context = await browser.newContext({locale: 'zh-CN'});
  page = await context.newPage();
  page.on('pageerror', error => console.error(error));
  page.setDefaultTimeout(5000);
  await page.goto(`${server.resolvedUrls.local[0]}__chat-errors`);
  await page.waitForFunction(() => !!window.chat);
  await page.evaluate(() => {
    window.chat.setBot({id: 1, name: '小宇', bot_type: 'planner'});
    window.chat.setInitialized(true);
  });
  await page.waitForFunction(() => !!window.saved().lastConversationId);
});
async function send() {
  await page.evaluate(() => {
    window.chat.setInput('原问题');
    window.sendPromise = window.chat.doSend('原问题');
  });
}
async function emit(payload) {
  await page.evaluate(payload => window.requests[0].controller.enqueue(
    new TextEncoder().encode('data: ' + JSON.stringify(payload) + '\n\n'),
  ), payload);
}
async function finish() {
  await page.evaluate(() => window.sendPromise);
  await page.waitForFunction(() => !window.chat.loading);
}
async function state() {
  return page.evaluate(() => ({
    errors: window.errors, messages: window.chat.messages, draft: window.chat.input,
    sessions: window.chat.sessions, activeSessionId: window.chat.activeSessionId,
    outcome: window.settled.map(row => row.outcome), doneCalls: window.doneCalls,
    saved: window.saved().conversations[window.chat.conversationId],
  }));
}
test('SSE error displays once, removes the failed empty session and restores the saved draft', async () => {
  await send();
  await page.waitForFunction(() => window.requests.length === 1 && window.chat.sessions.length === 1);
  await emit({type: 'text_delta', delta: '临时回复'});
  await emit({done: true, is_error: true, full_content: '内容访问范围尚未配置，请联系管理员。'});
  await finish();
  const result = await state();
  assert.deepEqual(result.errors, ['内容访问范围尚未配置，请联系管理员。']);
  assert.deepEqual(result.messages, []);
  assert.deepEqual(result.sessions, []);
  assert.equal(result.activeSessionId, null);
  assert.equal(result.draft, '原问题');
  assert.equal(result.saved.draft, '原问题');
  assert.equal(result.saved.pending, undefined);
  assert.deepEqual(result.outcome, ['error']);
  assert.equal(result.doneCalls, 0);
});
test('SSE error without text uses the localized fallback', async () => {
  await send();
  await page.waitForFunction(() => window.requests.length === 1);
  await emit({done: true, is_error: true});
  await finish();
  assert.deepEqual((await state()).errors, ['请求失败，请稍后重试。']);
});
test('premature EOF displays the stream error', async () => {
  await send();
  await page.waitForFunction(() => window.requests.length === 1);
  await page.evaluate(() => window.requests[0].controller.close());
  await finish();
  assert.deepEqual((await state()).errors, ['回复流已中断。']);
  assert.equal((await state()).draft, '原问题');
});
for (const status of [403, 503]) {
  test(`HTTP ${status} displays the response detail`, async () => {
    await page.evaluate(status => { window.httpError = {status, body: {detail: '请求未完成，请重试。'}}; }, status);
    await send();
    await finish();
    assert.deepEqual((await state()).errors, ['请求未完成，请重试。']);
    assert.equal((await state()).draft, '原问题');
  });
}
test('network failure displays the error once', async () => {
  await page.evaluate(() => { window.networkError = true; });
  await send();
  await finish();
  assert.deepEqual((await state()).errors, ['Failed to fetch']);
});
test('AbortError does not display an error', async () => {
  await send();
  await page.waitForFunction(() => window.requests.length === 1);
  await page.evaluate(() => window.requests[0].controller.error(new DOMException('Stopped', 'AbortError')));
  await finish();
  assert.deepEqual((await state()).errors, []);
});
test('cancelled request on unmount does not display an error', async () => {
  await send();
  await page.waitForFunction(() => window.requests.length === 1);
  await page.evaluate(() => window.root.unmount());
  await page.evaluate(() => window.sendPromise);
  assert.equal(await page.evaluate(() => window.requests[0].init.signal.aborted), true);
  assert.deepEqual(await page.evaluate(() => window.errors), []);
});
test('error in a background conversation does not flash a toast in the new conversation', async () => {
  await send();
  await page.waitForFunction(() => window.requests.length === 1);
  await page.evaluate(() => window.chat.handleReset(false));
  await emit({done: true, is_error: true, full_content: '旧会话错误'});
  await finish();
  assert.deepEqual((await state()).errors, []);
  assert.deepEqual((await state()).outcome, ['error']);
});
test('failure rolls back to existing history and keeps a newly typed draft', async () => {
  await page.evaluate(() => window.chat.handleLoadSession(window.chat.groupIntoSessions([
    {role: 'assistant', content: '已有回复', conversation_id: 'existing'},
  ])[0]));
  await send();
  await page.waitForFunction(() => window.requests.length === 1);
  await page.evaluate(() => window.chat.setInput('下一条草稿'));
  await emit({done: true, is_error: true, full_content: '请求失败'});
  await finish();
  const result = await state();
  assert.deepEqual(result.messages.map(row => row.content), ['已有回复']);
  assert.equal(result.sessions.length, 1);
  assert.equal(result.activeSessionId, result.sessions[0].id);
  assert.equal(result.sessions[0].conversationId, 'existing');
  assert.equal(result.draft, '下一条草稿');
  assert.equal(result.saved.draft, '下一条草稿');
  assert.deepEqual(result.errors, ['请求失败']);
});
test('successful stream completes without an error and keeps the response', async () => {
  await send();
  await page.waitForFunction(() => window.requests.length === 1);
  await emit({done: true, full_content: '完整回答', message_id: 42});
  await finish();
  const result = await state();
  assert.deepEqual(result.errors, []);
  assert.deepEqual(result.messages.map(row => row.content), ['原问题', '完整回答']);
  assert.equal(result.draft, '');
  assert.equal(result.saved.pending, undefined);
  assert.deepEqual(result.outcome, ['completed']);
  assert.equal(result.doneCalls, 1);
});
