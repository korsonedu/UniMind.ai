import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { ArrowLeft, ArrowRight, Check, Spinner, CaretLeft, Target, Clock } from '@phosphor-icons/react';
import api from '@/lib/api';
import ReactMarkdown from 'react-markdown';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import 'katex/dist/katex.min.css';

interface QuestionItem {
  id: number;
  text: string;
  q_type: string;
  subjective_type?: string;
  options?: string[];
  difficulty_level: string;
  kp_name: string;
  kp_code: string;
  is_review: boolean;
}

interface AnswerEntry {
  question_id: number;
  answer: string;
}

interface PracticeResult {
  question_id: number;
  is_correct: boolean;
  score: number;
  max_score: number;
  feedback: string;
  error_analysis?: {
    type: string;
    reasoning: string;
    suggested_focus: string;
  } | null;
  kp_name: string;
}

interface SubmitResponse {
  total_score: number;
  max_score: number;
  correct_rate: number;
  correct_count: number;
  total_questions: number;
  results: PracticeResult[];
  kp_breakdown: { kp_id: number; kp_name: string; correct_rate: number }[];
  summary_text: string;
}

type Phase = 'loading' | 'answering' | 'submitting' | 'results';

function processMathContent(text: string): string {
  if (!text) return '';
  return text
    .replace(/(?<!\\)\\(?!\()/g, '\\\\')
    .replace(/\\\\(?!\()/g, '\\');
}

const PracticeSession: React.FC = () => {
  const { sessionId } = useParams<{ sessionId: string }>();
  const navigate = useNavigate();

  const [phase, setPhase] = useState<Phase>('loading');
  const [questions, setQuestions] = useState<QuestionItem[]>([]);
  const [currentIdx, setCurrentIdx] = useState(0);
  const [answers, setAnswers] = useState<Record<number, string>>({});
  const [error, setError] = useState('');
  const [submitResult, setSubmitResult] = useState<SubmitResponse | null>(null);
  const [startTime] = useState(Date.now());
  const [isMobile, setIsMobile] = useState(false);

  // ── Mobile detection ─────────────────────────────────
  useEffect(() => {
    const mq = window.matchMedia('(max-width: 767px)');
    setIsMobile(mq.matches);
    const handler = (e: MediaQueryListEvent) => setIsMobile(e.matches);
    mq.addEventListener('change', handler);
    return () => mq.removeEventListener('change', handler);
  }, []);

  // ── Fetch questions ──────────────────────────────────
  useEffect(() => {
    if (!sessionId) {
      setError('缺少会话 ID');
      return;
    }
    api.post('/ai/practice/start/', { count: 5 })
      .then((res) => {
        if (res.data.questions?.length) {
          setQuestions(res.data.questions);
          setPhase('answering');
        } else {
          setError('没有找到匹配的题目');
        }
      })
      .catch((err) => {
        setError(err?.response?.data?.error || '加载题目失败');
      });
  }, [sessionId]);

  // ── Keyboard navigation ──────────────────────────────
  const handleKeyDown = useCallback((e: KeyboardEvent) => {
    if (phase !== 'answering') return;
    if (e.key === 'ArrowLeft' && currentIdx > 0) {
      setCurrentIdx(currentIdx - 1);
    }
    if (e.key === 'ArrowRight' && currentIdx < questions.length - 1) {
      setCurrentIdx(currentIdx + 1);
    }
  }, [phase, currentIdx, questions.length]);

  useEffect(() => {
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [handleKeyDown]);

  // ── Restore answers from localStorage on mount ───────
  useEffect(() => {
    if (!sessionId) return;
    const saved = localStorage.getItem(`practice:${sessionId}:answers`);
    if (saved) {
      try { setAnswers(JSON.parse(saved)); } catch {}
    }
  }, [sessionId]);

  // ── Pre-grade on question change ─────────────────────
  const prevIdxRef = React.useRef(currentIdx);
  useEffect(() => {
    const prevIdx = prevIdxRef.current;
    prevIdxRef.current = currentIdx;

    // 离开上一题时，如果已作答，发送异步预批改
    if (prevIdx !== currentIdx && questions[prevIdx]) {
      const qid = questions[prevIdx].id;
      const ans = answers[qid]?.trim();
      if (ans && sessionId) {
        api.post('/ai/practice/pre-grade/', {
          session_id: sessionId,
          question_id: qid,
          answer: ans,
        }).catch(() => {}); // 静默失败，submit 时 fallback
      }
    }
  }, [currentIdx]); // eslint-disable-line react-hooks/exhaustive-deps

  // ── Persist answers to localStorage ──────────────────
  const persistAnswers = (updated: Record<number, string>) => {
    if (!sessionId) return;
    localStorage.setItem(`practice:${sessionId}:answers`, JSON.stringify(updated));
  };

  // ── Answer handlers ──────────────────────────────────
  const selectOption = (qid: number, option: string) => {
    const updated = { ...answers, [qid]: option };
    setAnswers(updated);
    persistAnswers(updated);
  };

  const setTextAnswer = (qid: number, text: string) => {
    const updated = { ...answers, [qid]: text };
    setAnswers(updated);
    persistAnswers(updated);
  };

  // ── Submit ───────────────────────────────────────────
  const handleSubmit = async () => {
    setPhase('submitting');
    const answerList: AnswerEntry[] = questions.map((q) => ({
      question_id: q.id,
      answer: answers[q.id] || '',
    }));

    try {
      const res = await api.post('/ai/practice/submit/', {
        session_id: sessionId,
        answers: answerList,
      });
      setSubmitResult(res.data);
      setPhase('results');
      // Clean up localStorage
      localStorage.removeItem(`practice:${sessionId}:answers`);
    } catch (err: any) {
      setError(err?.response?.data?.error || '提交失败');
      setPhase('answering');
    }
  };

  const timeSpent = Math.floor((Date.now() - startTime) / 1000);
  const timeStr = `${Math.floor(timeSpent / 60)}分${timeSpent % 60}秒`;

  // ── Touch swipe ──────────────────────────────────────
  const touchStartRef = React.useRef(0);
  const onTouchStart = (e: React.TouchEvent) => {
    touchStartRef.current = e.touches[0].clientX;
  };
  const onTouchEnd = (e: React.TouchEvent) => {
    if (phase !== 'answering') return;
    const diff = touchStartRef.current - e.changedTouches[0].clientX;
    if (diff > 50 && currentIdx < questions.length - 1) setCurrentIdx(currentIdx + 1);
    if (diff < -50 && currentIdx > 0) setCurrentIdx(currentIdx - 1);
  };

  // ── Loading / Error ──────────────────────────────────
  if (phase === 'loading') {
    return (
      <div className="h-full min-h-0 bg-white flex items-center justify-center">
        {error ? (
          <div className="text-center">
            <p className="text-red-500 mb-4">{error}</p>
            <button onClick={() => navigate('/xiaoyu')} className="text-stone-500 underline">
              返回小宇对话
            </button>
          </div>
        ) : (
          <Spinner className="w-8 h-8 animate-spin text-stone-400" />
        )}
      </div>
    );
  }

  // ── Results Phase ────────────────────────────────────
  if (phase === 'results' && submitResult) {
    const { correct_rate, correct_count, total_questions, kp_breakdown, summary_text } = submitResult;
    return (
      <div className="h-full min-h-0 bg-white flex flex-col overflow-auto">
        <div className="flex-1 flex flex-col items-center justify-center px-6 py-10 max-w-md mx-auto w-full">
          {/* Hero */}
          <div className="text-6xl mb-4">🎯</div>
          <h2 className="text-xl font-bold text-stone-800 mb-2">练习完成</h2>
          <div className="text-5xl font-extrabold text-stone-900 mb-1">
            {correct_rate}%
          </div>
          <p className="text-stone-500 mb-2">
            正确率（{correct_count}/{total_questions}）
          </p>
          <div className="flex items-center gap-2 text-stone-400 text-sm mb-6">
            <Clock className="w-4 h-4" />
            <span>用时 {timeStr}</span>
          </div>

          {/* KP breakdown */}
          {kp_breakdown.length > 0 && (
            <div className="w-full bg-stone-50 rounded-xl p-4 mb-6">
              <h3 className="text-sm font-semibold text-stone-700 mb-3">知识点掌握度</h3>
              {kp_breakdown.map((kp) => (
                <div key={kp.kp_id} className="flex items-center justify-between py-1.5 text-sm">
                  <span className="text-stone-600 truncate flex-1 mr-2">{kp.kp_name}</span>
                  <div className="flex items-center gap-2">
                    <div className="w-20 h-1.5 bg-stone-200 rounded-full overflow-hidden">
                      <div
                        className={`h-full rounded-full transition-all ${
                          kp.correct_rate >= 80 ? 'bg-emerald-500' :
                          kp.correct_rate >= 60 ? 'bg-amber-400' : 'bg-red-400'
                        }`}
                        style={{ width: `${Math.max(kp.correct_rate, 5)}%` }}
                      />
                    </div>
                    <span className="text-xs text-stone-500 w-10 text-right">{kp.correct_rate}%</span>
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* Summary */}
          <p className="text-sm text-stone-500 text-center mb-8">{summary_text}</p>

          {/* View analysis button */}
          <button
            onClick={() => navigate('/xiaoyu?practiceDone=1')}
            className="w-full py-3 bg-stone-900 text-white rounded-xl font-medium hover:bg-stone-800 transition-colors flex items-center justify-center gap-2"
          >
            <Target className="w-4 h-4" />
            查看小宇分析 →
          </button>
        </div>
      </div>
    );
  }

  // ── Submitting Phase ─────────────────────────────────
  if (phase === 'submitting') {
    return (
      <div className="h-full min-h-0 bg-white flex items-center justify-center">
        <div className="text-center">
          <Spinner className="w-10 h-10 animate-spin text-stone-400 mx-auto mb-4" />
          <p className="text-stone-500">正在批改...</p>
        </div>
      </div>
    );
  }

  // ── Answering Phase ──────────────────────────────────
  const current = questions[currentIdx];
  const isLast = currentIdx === questions.length - 1;
  const hasCurrentAnswer = answers[current?.id]?.trim()?.length > 0;
  const allAnswered = questions.every((q) => answers[q.id]?.trim()?.length > 0);

  return (
    <div className="h-full min-h-0 bg-white flex flex-col overflow-hidden">
      {/* Top bar */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-stone-100 shrink-0">
        <button
          onClick={() => navigate('/xiaoyu')}
          className="flex items-center gap-1 text-stone-400 hover:text-stone-600 text-sm"
        >
          <CaretLeft className="w-4 h-4" />
          {!isMobile && <span>退出</span>}
        </button>
        <span className="text-sm font-medium text-stone-600">
          第 {currentIdx + 1} 题 / 共 {questions.length} 题
        </span>
        <div className="w-12" /> {/* spacer */}
      </div>

      {/* Progress bar */}
      <div className="h-1 bg-stone-100 shrink-0">
        <div
          className="h-full bg-stone-800 transition-all duration-300"
          style={{ width: `${((currentIdx + 1) / questions.length) * 100}%` }}
        />
      </div>

      {/* Question area */}
      <div
        className="flex-1 overflow-y-auto px-4 py-6"
        onTouchStart={onTouchStart}
        onTouchEnd={onTouchEnd}
      >
        <div className="max-w-lg mx-auto">
          {/* KP tag */}
          {current.kp_name && (
            <div className="inline-block bg-stone-100 text-stone-500 text-xs px-2.5 py-1 rounded-full mb-4">
              {current.kp_name}
              {current.is_review && <span className="ml-1 text-amber-500">· 复习</span>}
            </div>
          )}

          {/* Question text */}
          <div className="text-stone-800 text-lg leading-relaxed mb-6 prose prose-stone max-w-none">
            <ReactMarkdown
              remarkPlugins={[remarkMath]}
              rehypePlugins={[rehypeKatex]}
            >
              {processMathContent(current.text)}
            </ReactMarkdown>
          </div>

          {/* Answer area */}
          {current.q_type === 'objective' && current.options?.length ? (
            <div className="space-y-3">
              {current.options.map((opt, i) => {
                const isSelected = answers[current.id] === opt;
                return (
                  <button
                    key={i}
                    onClick={() => selectOption(current.id, opt)}
                    className={`w-full text-left px-4 py-3 rounded-xl border transition-all ${
                      isSelected
                        ? 'border-stone-800 bg-stone-50 text-stone-900 font-medium'
                        : 'border-stone-200 text-stone-600 hover:border-stone-300'
                    }`}
                  >
                    <span className="inline-block w-6 h-6 rounded-full border-2 border-current text-center leading-5 text-xs mr-3">
                      {String.fromCharCode(65 + i)}
                    </span>
                    {opt}
                  </button>
                );
              })}
            </div>
          ) : (
            <textarea
              value={answers[current.id] || ''}
              onChange={(e) => setTextAnswer(current.id, e.target.value)}
              placeholder="输入你的答案..."
              rows={5}
              className="w-full border border-stone-200 rounded-xl px-4 py-3 text-stone-800 placeholder-stone-300 focus:outline-none focus:border-stone-400 resize-none"
            />
          )}
        </div>
      </div>

      {/* Bottom nav */}
      <div className="border-t border-stone-100 px-4 py-3 shrink-0">
        <div className="max-w-lg mx-auto flex items-center justify-between">
          <button
            onClick={() => setCurrentIdx(currentIdx - 1)}
            disabled={currentIdx === 0}
            className="flex items-center gap-1.5 px-3 py-2 text-sm text-stone-500 disabled:text-stone-300 disabled:cursor-not-allowed hover:text-stone-700"
          >
            <ArrowLeft className="w-4 h-4" />
            {!isMobile && '上一题'}
          </button>

          <div className="flex gap-1">
            {questions.map((_, i) => (
              <button
                key={i}
                onClick={() => setCurrentIdx(i)}
                className={`w-2 h-2 rounded-full transition-all ${
                  i === currentIdx
                    ? 'bg-stone-800 w-4'
                    : answers[questions[i].id]?.trim()
                      ? 'bg-emerald-400'
                      : 'bg-stone-200'
                }`}
              />
            ))}
          </div>

          {isLast ? (
            <button
              onClick={handleSubmit}
              disabled={!allAnswered}
              className="flex items-center gap-1.5 px-4 py-2 text-sm font-medium bg-stone-900 text-white rounded-lg disabled:bg-stone-300 disabled:cursor-not-allowed hover:bg-stone-800 transition-colors"
            >
              <Check className="w-4 h-4" />
              提交
            </button>
          ) : (
            <button
              onClick={() => setCurrentIdx(currentIdx + 1)}
              className="flex items-center gap-1.5 px-3 py-2 text-sm text-stone-500 hover:text-stone-700"
            >
              {!isMobile && '下一题'}
              <ArrowRight className="w-4 h-4" />
            </button>
          )}
        </div>
      </div>
    </div>
  );
};

export default PracticeSession;
