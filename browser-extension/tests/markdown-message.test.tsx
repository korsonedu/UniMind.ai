// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { MarkdownMessage } from '../src/components/MarkdownMessage';

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

it('跳播 Markdown 锚点与裸时间戳，同时保留 GFM、KaTeX 和代码文字', async () => {
  const sendMessage = vi.fn().mockResolvedValue({ ok: true });
  vi.stubGlobal('chrome', {
    tabs: { query: vi.fn().mockResolvedValue([{ id: 91 }]), sendMessage },
  });
  const content = '[讲稿 05:20](#seek:320.5) 和 [01:02:03]；代码 `[05:20]`。\n\n'
    + '| 记号 | 含义 |\n| --- | --- |\n| $x^2$ | 平方 |';
  const view = render(<MarkdownMessage content={content} />);
  expect(screen.getByRole('table')).toBeTruthy();
  expect(view.container.querySelector('.katex')).toBeTruthy();
  expect(view.container.querySelector('code')?.textContent).toBe('[05:20]');
  fireEvent.click(screen.getByRole('button', { name: '跳播到 05:20' }));
  fireEvent.click(screen.getByRole('button', { name: '跳播到 1:02:03' }));
  await waitFor(() => expect(sendMessage.mock.calls).toEqual([
    [91, { type: 'UNIMIND_SEEK_VIDEO', payload: { seconds: 320.5 } }],
    [91, { type: 'UNIMIND_SEEK_VIDEO', payload: { seconds: 3723 } }],
  ]));
});
