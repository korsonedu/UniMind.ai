import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { createServer } from 'vite';

// Run: PLAYWRIGHT_MODULE=/path/to/playwright node tests/agentConversation.browser.mjs
const require = createRequire(import.meta.url);
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const entry = `
import React from 'react';
import { createRoot } from 'react-dom/client';
import { useAgentConversation } from '/src/hooks/useAgentConversation.ts';
import { useChatUnreadStore } from '/src/store/useChatUnreadStore.ts';
import api from '/src/lib/api.ts';
const findBot = bots => bots[0];
api.get = async () => ({data: window.historyFixture || []});
api.post = async () => ({data: {}});
window.requests = [];
window.runSettled = [];
window.unreadStore = useChatUnreadStore;
window.fetch = async (url, init) => {
  let controller;
  const body = new ReadableStream({start(c) { controller = c; }});
  // Deliberately allow late chunks after abort to exercise the request identity guard.
  window.requests.push({init, controller});
  return new Response(body);
};
function Harness() {
  window.chat = useAgentConversation({
    findBot,
    enableProjects: true,
    onRunSettled: (id, outcome) => { window.runSettled.push({id, outcome}); },
  });
  return null;
}
createRoot(document.getElementById('root')).render(React.createElement(Harness));
`;
const server = await createServer({
  server: { host: '127.0.0.1', port: 0 },
  plugins: [{
    name: 'conversation-regression-harness',
    configureServer(server) {
      server.middlewares.use('/__chat-test', (_req, res) => {
        res.setHeader('Content-Type', 'text/html');
        res.end('<div id="root"></div><script type="module" src="/@vite/client"></script><script type="module" src="/__chat-harness.js"></script>');
      });
    },
    resolveId(id) { if (id === '/__chat-harness.js') return id; },
    load(id) { if (id === '/__chat-harness.js') return entry; },
  }],
});
await server.listen();
const browser = await chromium.launch({ headless: true, channel: process.env.BROWSER_CHANNEL || 'chrome' });
const page = await browser.newPage();
page.setDefaultTimeout(5000);
page.on('pageerror', error => console.error(error.message));
const failures = [];
async function check(name, run) {
  try { await run(); console.log('PASS', name); }
  catch (error) { failures.push(name); console.error('FAIL', name, error.message); }
}
async function fresh() {
  await page.goto(`${server.resolvedUrls.local[0]}__chat-test`);
  await page.waitForFunction(() => !!window.chat);
  await page.evaluate(() => window.chat.setBot({id: 1, name: '小宇', bot_type: 'planner'}));
  await page.waitForFunction(() => !!window.chat.bot);
}
async function emit(index, payload) {
  await page.evaluate(({index, payload}) => {
    window.requests[index].controller.enqueue(new TextEncoder().encode('data: ' + JSON.stringify(payload) + '\n\n'));
  }, { index, payload });
  await page.waitForTimeout(30);
}
try {
  await check('首次发送立即进入侧栏，标题和消息持续同步', async () => {
    await fresh();
    await page.evaluate(() => { void window.chat.doSend('复习利率'); });
    await page.waitForFunction(() => window.requests.length === 1);
    assert.equal(await page.evaluate(() => window.chat.sessions.length), 1);
    await emit(0, {done: true, full_content: '开始复习', conversation_title: '利率复习', message_id: 42});
    await page.evaluate(() => window.requests[0].controller.close());
    await page.waitForFunction(() => !window.chat.loading);
    assert.equal(await page.evaluate(() => window.chat.sessions[0].title), '利率复习');
    assert.equal(await page.evaluate(() => window.chat.sessions[0].messages.length), 2);
    assert.equal(await page.evaluate(() => window.chat.activeSessionId === window.chat.sessions[0].id), true);
  });
  await check('按 conversation_id 归组，交错消息和长时间续聊均不拆分', async () => {
    await fresh();
    const grouped = await page.evaluate(() => window.chat.groupIntoSessions([
      {id: 1, role: 'user', content: 'A', conversation_id: 'a', timestamp: '2026-10-16T01:00:00Z'},
      {id: 2, role: 'user', content: 'B', conversation_id: 'b', timestamp: '2026-10-16T01:01:00Z'},
      {id: 3, role: 'assistant', content: 'A回复', conversation_id: 'a', timestamp: '2026-10-16T03:00:00Z'},
    ]));
    assert.equal(grouped.length, 2);
    assert.equal(grouped.find(s => s.conversationId === 'a').messages.length, 2);
  });
  await check('切换会话不取消旧请求，迟到回复写入原会话并上报停住', async () => {
    await fresh();
    const aCid = await page.evaluate(() => window.chat.conversationId);
    await page.evaluate(() => { void window.chat.doSend('A'); });
    await page.waitForFunction(() => window.requests.length === 1);
    await page.evaluate(() => window.chat.handleLoadSession({id: 7, label: 'B', conversationId: 'b', messages: [{role: 'user', content: 'B', conversation_id: 'b'}], lastTime: ''}));
    assert.equal(await page.evaluate(() => window.requests[0].init.signal.aborted), false);
    await emit(0, {done: true, full_content: 'A迟到回复', message_id: 43});
    await page.evaluate(() => window.requests[0].controller.close());
    await page.waitForFunction(cid => {
      const session = window.chat.sessions.find(item => item.conversationId === cid);
      return session && session.messages.length === 2;
    }, aCid);
    assert.deepEqual(await page.evaluate(() => window.chat.messages.map(m => m.content)), ['B']);
    assert.deepEqual(await page.evaluate(cid => window.chat.sessions.find(item => item.conversationId === cid).messages.map(m => m.content), aCid), ['A', 'A迟到回复']);
    assert.deepEqual(await page.evaluate(cid => window.runSettled.filter(item => item.id === cid), aCid), [{id: aCid, outcome: 'completed'}]);
    assert.equal(await page.evaluate(() => window.chat.loading), false);
  });
  await check('新建对话立即解除等待，旧请求结束不干扰新请求', async () => {
    await fresh();
    await page.evaluate(() => { void window.chat.doSend('旧问题'); });
    await page.waitForFunction(() => window.requests.length === 1);
    await page.evaluate(() => window.chat.handleReset(false));
    assert.equal(await page.evaluate(() => window.chat.loading), false);
    await page.evaluate(() => { void window.chat.doSend('新问题'); });
    await page.waitForFunction(() => window.requests.length === 2);
    await page.evaluate(() => window.requests[0].controller.close());
    await page.waitForTimeout(30);
    assert.equal(await page.evaluate(() => window.chat.loading), true);
    assert.deepEqual(await page.evaluate(() => window.chat.messages.map(m => m.content)), ['新问题']);
  });
  await check('历史刷新为空时清空列表，会话 ID 不随删除和排序改变', async () => {
    await fresh();
    const stable = await page.evaluate(() => {
      const a = {id: 1, role: 'user', content: 'A', conversation_id: 'a'};
      const b = {id: 2, role: 'user', content: 'B', conversation_id: 'b'};
      return [window.chat.groupIntoSessions([a, b]).find(s => s.conversationId === 'b').id, window.chat.groupIntoSessions([b])[0].id];
    });
    assert.equal(stable[0], stable[1]);
    await page.evaluate(() => window.chat.setSessions([{id: 9, messages: [], lastTime: '', label: '旧对话'}]));
    await page.evaluate(() => window.chat.handleRefreshSessions());
    assert.equal(await page.evaluate(() => window.chat.sessions.length), 0);
  });
  await check('切换后立即发送使用目标会话，侧栏保留两个独立快照', async () => {
    await fresh();
    await page.evaluate(() => { void window.chat.doSend('A问题'); });
    await page.waitForFunction(() => window.chat.sessions.length === 1);
    await emit(0, {done: true, full_content: 'A回答'});
    await page.evaluate(() => window.requests[0].controller.close());
    await page.waitForFunction(() => !window.chat.loading);
    await page.evaluate(() => {
      window.savedA = window.chat.sessions[0];
      window.chat.handleReset(false);
    });
    await page.evaluate(() => { void window.chat.doSend('B问题'); });
    await page.waitForFunction(() => window.chat.sessions.length === 2);
    await page.evaluate(() => {
      window.chat.handleLoadSession(window.savedA);
      void window.chat.doSend('A追问');
    });
    await page.waitForFunction(() => window.requests.length === 3);
    assert.equal(await page.evaluate(() => JSON.parse(window.requests[2].init.body).conversation_id === window.savedA.conversationId), true);
    const snapshots = await page.evaluate(() => window.chat.sessions.map(s => s.messages.map(m => m.content)));
    assert.deepEqual(snapshots, [['B问题'], ['A问题', 'A回答', 'A追问']]);
  });
  await check('历史刷新慢响应不会覆盖刚发出的新对话', async () => {
    await fresh();
    await page.evaluate(async () => {
      const api = (await import('/src/lib/api.ts')).default;
      api.get = () => new Promise(resolve => { window.resolveHistory = resolve; });
      void window.chat.handleRefreshSessions();
    });
    await page.evaluate(() => { void window.chat.doSend('新对话'); });
    await page.waitForFunction(() => window.chat.sessions.length === 1);
    await page.evaluate(() => window.resolveHistory({data: []}));
    await page.waitForTimeout(30);
    assert.equal(await page.evaluate(() => window.chat.sessions.length), 1);
  });
  await check('未读只在非当前会话停住时标记，查看、离开和删除会清除', async () => {
    await fresh();
    const states = await page.evaluate(() => {
      const store = window.unreadStore;
      const read = () => ({...store.getState().unread});
      store.getState().reset();
      store.getState().view('a');
      store.getState().markSettled('a', 'completed');
      const viewed = read();
      store.getState().leave('a');
      store.getState().markSettled('a', 'error');
      const background = read();
      store.getState().view('a');
      const opened = read();
      store.getState().markSettled('a', 'error');
      const viewedAgain = read();
      store.getState().remove('a');
      const removed = read();
      return { viewed, background, opened, viewedAgain, removed };
    });
    assert.deepEqual(states.viewed, {});
    assert.deepEqual(states.background, {a: true});
    assert.deepEqual(states.opened, {});
    assert.deepEqual(states.viewedAgain, {});
    assert.deepEqual(states.removed, {});
  });
} finally {
  await browser.close();
  await server.close();
}
if (failures.length) process.exitCode = 1;
