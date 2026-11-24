// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { PracticeQuizCard, type PracticePayload } from '../src/components/PracticeQuizCard';
import { createApiClient } from '../src/lib/api';

const payload: PracticePayload = {
  practice_id: 'f46e9f45-35dc-4c83-82c1-ee7a36b12c06',
  title: '现金流随堂练习',
  questions: [
    { id: 11, text: '现值由哪个因素决定？', q_type: 'objective', options: ['折现率', '字号'] },
    { id: 22, text: '请解释折现率变高时会怎样。', q_type: 'subjective', options: [] },
  ],
};

const api = createApiClient({
  serverOrigin: 'http://localhost:8000', token: 'test-token',
});

function json(data: unknown, status = 200) {
  return new Response(JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json' } });
}

beforeEach(() => {
  localStorage.clear();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe('随堂练习', () => {
  it('选择客观答案、保存主观草稿，并按主站协议提交和显示分数及解析', async () => {
    const requests: { path: string; request?: RequestInit }[] = [];
    const fetch = vi.fn(async (input: string | URL | Request, request?: RequestInit) => {
      const path = new URL(typeof input === 'string' ? input : input instanceof URL ? input.href : input.url).pathname;
      requests.push({ path, request });
      if (path.includes('/submissions/')) return json({ detail: 'Not found' }, 404);
      if (path.endsWith('/submit-exam/')) return json({ exam_id: 9 }, 201);
      return json({
        status: 'completed', total_score: 2, max_score: 2, graded_count: 2, total_questions: 2, correct_count: 2,
        results: [
          { position: 1, status: 'graded', score: 1, max_score: 1, is_correct: true, correct_answer: '折现率', analysis: '根据现值公式计算。' },
          { position: 2, status: 'graded', score: 1, max_score: 1, is_correct: true, correct_answer: '现值降低', analysis: '折现率越高，现值越低。' },
        ],
      });
    });
    vi.stubGlobal('fetch', fetch);

    const first = render(<PracticeQuizCard payload={payload} api={api} storageScope="test-account" />);
    const option = await screen.findByRole('button', { name: /折现率/ });
    await waitFor(() => expect((option as HTMLButtonElement).disabled).toBe(false));
    fireEvent.click(option);
    fireEvent.click(screen.getByRole('button', { name: /下一题/ }));
    fireEvent.change(screen.getByRole('textbox', { name: '本题答案' }), { target: { value: '未来现金流现值降低' } });
    first.unmount();

    render(<PracticeQuizCard payload={payload} api={api} storageScope="test-account" />);
    const answer = await screen.findByRole('textbox', { name: '本题答案' });
    expect((answer as HTMLTextAreaElement).value).toBe('未来现金流现值降低');
    const submit = screen.getByRole('button', { name: /提交批改/ });
    await waitFor(() => expect((submit as HTMLButtonElement).disabled).toBe(false));
    fireEvent.click(submit);

    expect(await screen.findByText('折现率越高，现值越低。')).toBeTruthy();
    expect(await screen.findByText(/2\s*\/\s*2/, { selector: 'p' })).toBeTruthy();
    expect(requests.some(({ path }) => path === '/api/quizzes/exams/9/')).toBe(true);
    const sent = requests.find(({ path }) => path === '/api/quizzes/submit-exam/')?.request;
    expect(JSON.parse(String(sent?.body))).toEqual({
      submission_id: payload.practice_id,
      answers: [{ question_id: 11, answer: '折现率' }, { question_id: 22, answer: '未来现金流现值降低' }],
    });
    expect(sent?.credentials).toBe('omit');
    expect(new Headers(sent?.headers).get('Authorization')).toBe('Token test-token');
  });

  it('恢复已存在的服务端提交，并从批改中轮询到最终结果', async () => {
    let polls = 0;
    const fetch = vi.fn(async (input: string | URL | Request) => {
      const path = new URL(typeof input === 'string' ? input : input instanceof URL ? input.href : input.url).pathname;
      if (path.includes('/submissions/')) return json({ exam_id: 19, answers: [{ position: 1, answer: '折现率' }] });
      if (path !== '/api/quizzes/exams/19/') return json({ detail: 'Unexpected request' }, 404);
      polls++;
      const graded = polls > 1;
      return json({
        status: graded ? 'completed' : 'grading', total_score: graded ? 1 : 0,
        max_score: 2, graded_count: graded ? 2 : 0, total_questions: 2, correct_count: graded ? 1 : 0,
        results: graded ? [{ position: 1, status: 'graded', score: 1, max_score: 1,
          is_correct: true, correct_answer: '折现率', analysis: '服务端已批改完成。' }] : [],
      });
    });
    vi.stubGlobal('fetch', fetch);
    render(<PracticeQuizCard payload={payload} api={api} storageScope="recovered-account" />);
    expect(await screen.findByText(/批改中/)).toBeTruthy();
    expect(screen.queryByRole('button', { name: '提交批改' })).toBeNull();
    expect(screen.getByRole('button', { name: /折现率/ }).getAttribute('aria-pressed')).toBe('true');
    expect(await screen.findByText('服务端已批改完成。', {}, { timeout: 4000 })).toBeTruthy();
    expect(polls).toBe(2);
  });
});
