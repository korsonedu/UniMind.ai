// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { QuickActionsBar, QUIZ_PROMPT, SUMMARY_PROMPT } from '../src/components/QuickActionsBar';
import { createApiClient } from '../src/lib/api';

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

it('发送约定的快捷提示词并保存带原链接和时间戳的个人笔记', async () => {
  const onAsk = vi.fn();
  const fetch = vi.fn<(url: string, init?: RequestInit) => Promise<Response>>()
    .mockResolvedValue(new Response('{"id":3}', { status: 201 }));
  vi.stubGlobal('fetch', fetch);
  const api = createApiClient({ serverOrigin: 'http://localhost:8000', token: 'fixture-token' });
  render(<QuickActionsBar api={api} onAsk={onAsk}
    latestAnswer="复习一遍 [05:20] 所讲的折现率" videoSeconds={312}
    video={{ platform: 'bilibili', video_key: 'bilibili:BVfixture:p2', external_id: 'BVfixture',
      title: '现金流', part: 2, url: 'https://www.bilibili.com/video/BVfixture?p=2' }} />);
  fireEvent.click(screen.getByRole('button', { name: '考我 2 题' }));
  fireEvent.click(screen.getByRole('button', { name: '梳理本段' }));
  await waitFor(() => expect(onAsk.mock.calls).toEqual([[QUIZ_PROMPT], [SUMMARY_PROMPT]]));
  fireEvent.click(screen.getByRole('button', { name: '存为笔记' }));
  expect(await screen.findByText('已存为个人笔记')).toBeTruthy();

  expect(fetch.mock.calls[0]?.[0]).toBe('http://localhost:8000/api/notes/');
  const request = fetch.mock.calls[0]?.[1];
  expect(request?.method).toBe('POST');
  const payload = JSON.parse(String(request?.body)) as { title: string; content: string };
  expect(payload.title).toContain('现金流');
  expect(payload.content).toContain('复习一遍 [05:20] 所讲的折现率');
  expect(payload.content).toContain('https://www.bilibili.com/video/BVfixture?p=2');
  expect(payload.content).toContain('[05:20](https://www.bilibili.com/video/BVfixture?p=2&t=320)');
  expect(payload.content).toContain('[05:12](https://www.bilibili.com/video/BVfixture?p=2&t=312)');
});
