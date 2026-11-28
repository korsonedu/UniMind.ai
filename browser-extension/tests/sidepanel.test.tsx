// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { App } from '../src/entrypoints/sidepanel/App';
import type { ActiveVideoDescriptor, CaptureContextResult } from '../src/shared/types';

const video: ActiveVideoDescriptor = {
  platform: 'bilibili', video_key: 'bilibili:BVfixture:p2', external_id: 'BVfixture',
  part: 2, title: '折现课第二节', url: 'https://www.bilibili.com/video/BVfixture?p=2',
};
const restoredId = '00000000-0000-4000-8000-000000000033';
const origin = 'http://localhost:8000';
const event = { addListener: vi.fn(), removeListener: vi.fn() };

afterEach(() => {
  cleanup();
  localStorage.clear();
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

function stubLoggedOutBrowser() {
  const values: Record<string, unknown> = {};
  vi.stubGlobal('chrome', {
    runtime: { sendMessage: vi.fn().mockResolvedValue({ token: null }) },
    storage: {
      onChanged: { addListener: vi.fn(), removeListener: vi.fn() },
      local: {
        get: async (key: string) => ({ [key]: values[key] }),
        set: async (data: object) => { Object.assign(values, data); },
      },
    },
  });
  return values;
}

it('默认使用验证码登录，60 秒后允许重发，并保存验证码登录结果', async () => {
  const values = stubLoggedOutBrowser();
  const fetch = vi.fn(async (input: string) => new Response(JSON.stringify(
    new URL(input).pathname.endsWith('/login-by-code/')
      ? { token: 'code-token', user: { id: 72, email: 'learner@example.com' } }
      : { message: '验证码已发送' },
  ), { status: 200 }));
  vi.stubGlobal('fetch', fetch);
  render(<App />);
  const codeTab = await screen.findByRole('tab', { name: '验证码登录' });
  expect(codeTab.getAttribute('aria-selected')).toBe('true');
  expect(screen.getByRole('heading', { name: '欢迎回来' })).toBeTruthy();
  expect(screen.getByRole('link', { name: /打开 UniMind 主站登录/ }).getAttribute('href'))
    .toBe('https://unimind-ai.com/login');
  expect(screen.getByRole('button', { name: '同步浏览器登录态' })).toBeTruthy();
  fireEvent.change(screen.getByRole('textbox', { name: '邮箱' }), { target: { value: 'learner@example.com' } });
  vi.useFakeTimers({ toFake: ['Date', 'setInterval', 'clearInterval'] });
  fireEvent.click(screen.getByRole('button', { name: '发送验证码' }));
  const countdown = await screen.findByRole('button', { name: '60 秒后重发' });
  expect((countdown as HTMLButtonElement).disabled).toBe(true);
  await act(() => vi.advanceTimersByTimeAsync(59000));
  expect((screen.getByRole('button', { name: '1 秒后重发' }) as HTMLButtonElement).disabled).toBe(true);
  await act(() => vi.advanceTimersByTimeAsync(1000));
  expect((screen.getByRole('button', { name: '发送验证码' }) as HTMLButtonElement).disabled).toBe(false);
  fireEvent.click(screen.getByRole('button', { name: '发送验证码' }));
  await screen.findByRole('button', { name: '60 秒后重发' });
  expect(fetch).toHaveBeenCalledTimes(2);
  fireEvent.change(screen.getByRole('textbox', { name: '验证码' }), { target: { value: '123456' } });
  fireEvent.click(screen.getByRole('button', { name: '登录' }));
  await waitFor(() => expect(values['unimind:auth:https://unimind-ai.com']).toMatchObject({
    token: 'code-token', tokenSource: 'inline', user: { id: 72 },
  }));
  expect(fetch.mock.calls.at(-1)?.[0]).toBe('https://unimind-ai.com/api/users/login-by-code/');
});

it('通过键盘切换到密码登录，并用用户名提交主站登录接口', async () => {
  const values = stubLoggedOutBrowser();
  const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({ token: 'password-token', user: { id: 73 } }), { status: 200 }));
  vi.stubGlobal('fetch', fetch);
  render(<App />);
  const codeTab = await screen.findByRole('tab', { name: '验证码登录' });
  fireEvent.keyDown(codeTab, { key: 'ArrowRight' });
  const passwordTab = screen.getByRole('tab', { name: '密码登录' });
  expect(passwordTab.getAttribute('aria-selected')).toBe('true');
  expect(document.activeElement).toBe(passwordTab);
  fireEvent.change(screen.getByRole('textbox', { name: '邮箱 / 用户名' }), { target: { value: 'learner' } });
  fireEvent.change(screen.getByLabelText('密码', { exact: true }), { target: { value: 'secret-password' } });
  fireEvent.click(screen.getByRole('button', { name: '登录' }));
  await waitFor(() => expect(values['unimind:auth:https://unimind-ai.com']).toMatchObject({ token: 'password-token' }));
  expect(fetch.mock.calls[0]?.[0]).toBe('https://unimind-ai.com/api/users/login/');
  expect(JSON.parse(String(fetch.mock.calls[0]?.[1]?.body))).toEqual({ username: 'learner', password: 'secret-password' });
});

it('按视频恢复最近会话和练习，改绑项目，并让新会话首轮带上项目和视频上下文', async () => {
  const capture: CaptureContextResult = {
    ok: true, descriptor: video, warnings: [],
    context: {
      platform: video.platform, external_id: video.external_id, part: video.part, title: video.title, url: video.url,
      video_seconds: 320, transcript_source: 'platform_cc',
      segments: [{ start_time: 318, end_time: 323, text: '讲到折现率' }],
      integration_hooks: { knowledge_tree_id: null, knowledge_node_id: null, memory_event_target: null },
    },
  };
  const localValues: Record<string, unknown> = {
    'unimind:settings': { serverOrigin: origin },
    [`unimind:auth:${origin}`]: { token: 'fixture-token', tokenSource: 'inline', user: { id: 42 } },
  };
  vi.stubGlobal('chrome', {
    tabs: { query: async () => [{ id: 21, windowId: 1 }], sendMessage: async () => video, onActivated: event, onUpdated: event },
    runtime: {
      onMessage: event,
      sendMessage: async (request: { type: string }) => {
        if (request.type === 'UNIMIND_CAPTURE_CONTEXT_FOR_ASK') return capture;
        if (request.type === 'UNIMIND_CAPTURE_SOURCE_FOR_WORKBENCH') return { source: {
          kind: 'external_video', platform: 'bilibili', external_id: video.external_id, part: video.part,
          title: video.title, url: video.url, duration_seconds: 3600, segments: capture.context?.segments,
        } };
        return { token: 'fixture-token' };
      },
    },
    storage: {
      onChanged: event,
      local: { get: async (key: string) => ({ [key]: localValues[key] }), set: async (data: object) => { Object.assign(localValues, data); } },
    },
  });
  const requests: { url: URL; method?: string; payload: unknown }[] = [];
  vi.stubGlobal('fetch', vi.fn(async (input: string, request?: RequestInit) => {
    const url = new URL(input);
    requests.push({ url, method: request?.method, payload: request?.body ? JSON.parse(String(request.body)) : null });
    const json = (data: unknown, status = 200) => new Response(JSON.stringify(data), { status });
    switch (url.pathname) {
      case '/api/ai/bots/': return json([{ id: 7, bot_type: 'planner' }]);
      case '/api/ai/projects/': return json([{ id: 1, name: '金额换算' }, { id: 2, name: '折现专题' }]);
      case '/api/ai/projects/2/sources/import/': return json({ status: 'ready', unit_count: 1 }, 201);
      case '/api/ai/conversations/': return json([{ conversation_id: restoredId, project_id: 1 }]);
      case `/api/ai/conversations/${restoredId}/`: return json({ project_id: 2 });
      case '/api/ai/history/': return json([{
        id: 5, role: 'assistant', content: '欢迎继续学习折现。',
        metadata: { dsh_cards: [{ type: 'practice_quiz', payload: {
          practice_id: 'fixture-practice', title: '历史随堂练习',
          questions: [{ id: 7, text: '什么是贴现率？', q_type: 'subjective', options: [] }],
        } }] },
      }]);
      case '/api/ai/chat/stream/':
        return new Response('data: {"type":"text_delta","delta":"先算"}\n\ndata: {"done":true,"full_content":"这是新会话的最终回答。"}\n\n',
          { headers: { 'Content-Type': 'text/event-stream' } });
      default: return json({ detail: '尚未提交' }, 404);
    }
  }));

  render(<App />);
  expect(await screen.findByText('欢迎继续学习折现。')).toBeTruthy();
  expect(await screen.findByRole('region', { name: '历史随堂练习' })).toBeTruthy();
  expect(requests.some(({ url }) => url.searchParams.get('external_video_key') === video.video_key)).toBe(true);
  expect(requests.some(({ url }) => url.searchParams.get('conversation_id') === restoredId)).toBe(true);
  const projectSelect = () => screen.getByRole('combobox', { name: '当前对话所属项目' }) as HTMLSelectElement;
  expect(projectSelect().value).toBe('1');
  await screen.findByRole('option', { name: '折现专题' });
  await waitFor(() => expect(projectSelect().disabled).toBe(false));
  fireEvent.change(projectSelect(), { target: { value: '2' } });
  await waitFor(() => expect(projectSelect().value).toBe('2'));
  expect(requests.find(action => action.method === 'PATCH')?.payload).toEqual({ project_id: 2 });
  fireEvent.click(screen.getByRole('button', { name: '收入工作台 · 视频讲稿' }));
  await screen.findByText('已收入「折现专题」工作台（共 1 段内容）');
  expect(requests.find(({ url }) => url.pathname.endsWith('/sources/import/'))?.payload).toMatchObject({
    kind: 'external_video', platform: 'bilibili', part: 2, duration_seconds: 3600, segments: capture.context?.segments,
  });

  fireEvent.click(screen.getByRole('button', { name: '新对话' }));
  await screen.findByRole('option', { name: '折现专题' });
  await waitFor(() => expect(projectSelect().disabled).toBe(false));
  fireEvent.change(projectSelect(), { target: { value: '2' } });
  fireEvent.change(screen.getByRole('textbox', { name: '向小宇提问' }), { target: { value: '为什么？' } });
  fireEvent.click(screen.getByRole('button', { name: '发送消息' }));
  expect(await screen.findByText('这是新会话的最终回答。')).toBeTruthy();
  const payload = requests.find(({ url }) => url.pathname === '/api/ai/chat/stream/')?.payload;
  expect(payload).toMatchObject({ bot_id: 7, project_id: 2, message: '为什么？', external_video_context: capture.context });
  expect(payload).not.toMatchObject({ conversation_id: restoredId });
});

it('从网页侧栏新建项目、剪藏正文并更新同一来源，导入失败时显示原因', async () => {
  const source = { kind: 'text', title: '折现文档', source_url: 'https://example.org/discount', content: '## 折现\n\n现值怎么算？' };
  const sendMessage = vi.fn(async ({ type }: { type: string }) =>
    type === 'UNIMIND_CAPTURE_SOURCE_FOR_WORKBENCH' ? { source } : { token: 'fixture-token' });
  const browserValues: Record<string, unknown> = {
    'unimind:settings': { serverOrigin: origin },
    [`unimind:auth:${origin}`]: { token: 'fixture-token', tokenSource: 'inline', user: { id: 42 } },
  };
  vi.stubGlobal('chrome', {
    tabs: { query: async () => [{ id: 21, windowId: 1 }], sendMessage: async () => null, onActivated: event, onUpdated: event },
    runtime: { onMessage: event, sendMessage },
    storage: { onChanged: event, local: {
      get: async (key: string) => ({ [key]: browserValues[key] }),
      set: async (data: object) => { Object.assign(browserValues, data); },
    } },
  });
  const writes: { path: string; body: unknown }[] = [];
  const importStatuses = [201, 200, 403];
  vi.stubGlobal('fetch', vi.fn(async (input: string, request: RequestInit) => {
    const path = new URL(input).pathname;
    const json = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status });
    if (request.method === 'POST') {
      expect(new Headers(request.headers).get('Authorization')).toBe('Token fixture-token');
      expect(request.credentials).toBe('omit');
      writes.push({ path, body: JSON.parse(String(request.body)) });
    }
    if (path === '/api/ai/bots/') return json([{ id: 7, bot_type: 'planner' }]);
    if (path === '/api/ai/projects/' && request.method === 'POST') return json({ id: 14, name: '折现专题' }, 201);
    if (path === '/api/ai/projects/14/sources/import/') {
      const status = importStatuses.shift();
      return json(status === 403 ? { detail: '请在本人个人空间中处理项目来源。' } : { status: 'ready', unit_count: 2 }, status);
    }
    return json([]);
  }));
  render(<App />);
  await screen.findByRole('textbox', { name: '向小宇提问' });
  const clip = () => screen.getByRole('button', { name: '收入工作台 · 当前网页' });
  await waitFor(() => expect((clip() as HTMLButtonElement).disabled).toBe(false));
  fireEvent.click(clip());
  expect(screen.getByText('请先选择项目，或新建项目。')).toBeTruthy();
  expect(writes).toEqual([]);
  const name = screen.getByRole('textbox', { name: '新项目名称' });
  fireEvent.change(name, { target: { value: '折现专题' } });
  fireEvent.click(screen.getByRole('button', { name: '创建' }));
  await waitFor(() => expect((clip() as HTMLButtonElement).disabled).toBe(false));
  fireEvent.click(clip());
  await screen.findByText('已收入「折现专题」工作台（共 2 段内容）');
  expect(screen.getByRole('link', { name: '打开工作台' }).getAttribute('href')).toBe(`${origin}/xiaoyu?project=14`);
  expect(sendMessage).toHaveBeenCalledWith({ type: 'UNIMIND_CAPTURE_SOURCE_FOR_WORKBENCH', payload: { windowId: 1 } });
  expect(writes).toEqual([
    { path: '/api/ai/projects/', body: { name: '折现专题' } },
    { path: '/api/ai/projects/14/sources/import/', body: source },
  ]);
  fireEvent.click(clip());
  await screen.findByText('已更新工作台中的资料（共 2 段内容）');
  fireEvent.click(clip());
  await screen.findByText('请在本人个人空间中处理项目来源。');
  expect(screen.queryByRole('link', { name: '打开工作台' })).toBeNull();
});
