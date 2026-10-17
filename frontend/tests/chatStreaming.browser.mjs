// Requires a running Vite server with preview fixtures and Playwright available.
// CHAT_TEST_URL and PLAYWRIGHT_EXECUTABLE_PATH can select the local runtime.
import assert from 'node:assert/strict';
import test from 'node:test';
import { createRequire } from 'node:module';

const { chromium } = createRequire(import.meta.url)('playwright');

async function openChat(t) {
  const browser = await chromium.launch({
    headless: true,
    ...(process.env.PLAYWRIGHT_EXECUTABLE_PATH
      ? { executablePath: process.env.PLAYWRIGHT_EXECUTABLE_PATH } : {}),
  });
  t.after(() => browser.close());
  const page = await browser.newPage();
  await page.goto(`${process.env.CHAT_TEST_URL || 'http://127.0.0.1:5174'}/xiaoyu?preview=1`);
  await page.waitForLoadState('networkidle');
  await page.getByRole('textbox', { name: '和小宇对话' }).waitFor();
  await page.evaluate(() => {
    const originalFetch = window.fetch;
    window.fetch = (input, init) => {
      if (!String(input).includes('/api/ai/chat/stream/')) return originalFetch(input, init);
      const body = new ReadableStream({
        start(controller) {
          const encoder = new TextEncoder();
          window.emitChatEvent = event => controller.enqueue(
            encoder.encode(`data: ${JSON.stringify(event)}\n\n`),
          );
          window.closeChatStream = () => controller.close();
        },
      });
      return Promise.resolve(new Response(body, { headers: { 'Content-Type': 'text/event-stream' } }));
    };
  });
  return page;
}

const emit = (page, event) => page.evaluate(value => window.emitChatEvent(value), event);

test('聊天在 done 前显示分片，多轮文本和最终消息不重复，卡片仍可见', async t => {
  const page = await openChat(t);
  await page.getByRole('textbox', { name: '和小宇对话' }).fill('测试真实分片显示');
  await page.getByRole('button', { name: '发送消息', exact: true }).click();
  await page.waitForFunction(() => typeof window.emitChatEvent === 'function');

  await emit(page, { type: 'text_delta', delta: '第一段增量文字。' });
  await page.getByText('第一段增量文字。', { exact: true }).waitFor({ timeout: 2000 });
  await emit(page, { type: 'text_delta', delta: '第二段增量文字。' });
  const intermediate = '第一段增量文字。第二段增量文字。';
  await page.getByText(intermediate, { exact: true }).waitFor({ timeout: 2000 });
  await emit(page, { type: 'message', content: intermediate });
  assert.equal(await page.getByText(intermediate, { exact: true }).count(), 1);

  const visual = { type: 'action_cards', payload: { cards: [{
    title: '每日三十分钟', description: '本地测试选项', icon: 'plan',
    action: { type: 'reply', url: '每天学习三十分钟', label: '选择', reply_mode: 'single' },
  }] } };
  await emit(page, { type: 'step', call_id: 'stream-card', run_id: 'stream-run', round: 1,
    name: 'render_visual', label: '选择学习时间', status: 'running' });
  await emit(page, { type: 'step', call_id: 'stream-card', run_id: 'stream-run', round: 1,
    name: 'render_visual', label: '选择学习时间', status: 'succeeded', visual });
  await emit(page, { type: 'text_delta', delta: '请选择每日学习时间。' });
  await page.getByText('请选择每日学习时间。', { exact: true }).waitFor({ timeout: 2000 });
  await emit(page, { done: true, run_id: 'stream-run', full_content: '请选择每日学习时间。',
    message_id: 999, metadata: { all_visuals: [visual] } });
  await page.evaluate(() => window.closeChatStream());
  await page.getByText('每日三十分钟', { exact: true }).waitFor();
  assert.equal(await page.getByText('请选择每日学习时间。', { exact: true }).count(), 1);
  assert.equal(await page.getByText(intermediate, { exact: true }).count(), 1);
});

test('全局小宇引擎同样实时累计分片，done 原位补齐消息信息', async t => {
  const page = await openChat(t);
  await page.evaluate(async () => {
    const storeUrl = performance.getEntriesByType('resource')
      .map(entry => entry.name).find(url => url.includes('/src/store/useXiaoYuStore.ts'));
    const { useXiaoYuStore } = await import(storeUrl);
    useXiaoYuStore.getState().setBotId(1);
    window.chatStore = useXiaoYuStore;
  });
  await page.waitForFunction(() => typeof window.chatStore.getState().sendMessage === 'function',
    null, { timeout: 2000 });
  await page.evaluate(() => window.chatStore.getState().sendMessage('测试全局引擎'));
  await page.waitForFunction(() => typeof window.emitChatEvent === 'function');
  await emit(page, { type: 'text_delta', delta: '全局第一段。' });
  await page.waitForFunction(() => window.chatStore.getState().messages.some(
    message => message.content === '全局第一段。' && message.visible,
  ), null, { timeout: 2000 });
  await emit(page, { type: 'text_delta', delta: '全局第二段。' });
  await emit(page, { done: true, full_content: '全局第一段。全局第二段。', message_id: 998 });
  await page.evaluate(() => window.closeChatStream());
  await page.waitForFunction(() => !window.chatStore.getState().loading);
  const replies = await page.evaluate(() => window.chatStore.getState().messages.filter(
    message => message.role === 'assistant' && !message.toolStep,
  ));
  assert.equal(replies.length, 1);
  assert.equal(replies[0].content, '全局第一段。全局第二段。');
  assert.equal(replies[0].id, 998);
});
