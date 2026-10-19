import { useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { ArrowLeft, ArrowsClockwise, CircleNotch, CheckCircle } from '@phosphor-icons/react';
import { toast } from 'sonner';

import api from '@/lib/api';
import { formatApiErrorToast } from '@/lib/apiError';
import { queryKeys } from '@/lib/queryKeys';
import { processMathContent } from '@/lib/utils';
import { PageWrapper } from '@/components/PageWrapper';
import { MarkdownContent } from '@/components/MarkdownContent';
import { EmptyState } from '@/components/EmptyState';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { useExamActivityStore } from '@/store/useExamActivityStore';
import '@/styles/exam-result.css';

type ExamStatus = 'pending' | 'grading' | 'completed' | 'partial' | 'failed';
type ItemStatus = 'pending' | 'graded' | 'failed';

interface ExamResultItem {
  question_id: number | null;
  position: number;
  status: ItemStatus;
  question_text: string;
  q_type: string;
  subjective_type: string;
  options: string[];
  user_answer: string;
  correct_answer: string;
  analysis: string;
  feedback: string;
  error_type: string;
  error_metadata: { reasoning?: string; suggested_focus?: string; error?: string };
  score: number;
  max_score: number;
  is_correct: boolean;
  kp_id: number | null;
  kp_name: string;
  kp_code: string;
}

interface ExamResultData {
  id: number;
  status: ExamStatus;
  created_at: string;
  completed_at: string | null;
  total_questions: number;
  graded_count: number;
  failed_count: number;
  pending_count: number;
  total_score: number;
  max_score: number;
  correct_rate: number;
  correct_count: number;
  summary_text: string;
  kp_breakdown: Array<{ kp_id: number; kp_name: string; correct_rate: number }>;
  results: ExamResultItem[];
}

const statusText: Record<ExamStatus, string> = {
  pending: '待批改',
  grading: '批改中',
  completed: '已完成',
  partial: '部分完成',
  failed: '批改失败',
};

const isActive = (status: ExamStatus) => status === 'pending' || status === 'grading';

export const ExamResultPage = () => {
  const { examId: rawExamId } = useParams<{ examId: string }>();
  const examId = Number(rawExamId);
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [filter, setFilter] = useState<'all' | 'wrong' | 'pending'>('all');
  const [expanded, setExpanded] = useState<Record<number, boolean>>({});
  const [mastered, setMastered] = useState<Set<number>>(new Set());
  const [retrying, setRetrying] = useState(false);

  const detail = useQuery({
    queryKey: queryKeys.exams.detail(examId),
    queryFn: async () => {
      const response = await api.get<ExamResultData>(`/quizzes/exams/${examId}/`);
      return response.data;
    },
    enabled: Number.isFinite(examId),
    staleTime: 0,
    retry: 1,
    refetchInterval: (query: { state: { data?: ExamResultData } }) => {
      const data = query.state.data;
      return data && isActive(data.status) ? 2500 : false;
    },
  });

  const data = detail.data;
  const counts = useMemo(() => {
    const results = data?.results ?? [];
    return {
      wrong: results.filter(item => item.status === 'graded' && !item.is_correct).length,
      pending: results.filter(item => item.status !== 'graded').length,
    };
  }, [data]);

  const visibleResults = useMemo(() => {
    const results = data?.results ?? [];
    if (filter === 'wrong') return results.filter(item => item.status === 'graded' && !item.is_correct);
    if (filter === 'pending') return results.filter(item => item.status !== 'graded');
    return results;
  }, [data, filter]);

  if (!Number.isFinite(examId)) {
    return <PageWrapper title="练习结果"><EmptyState title="练习不存在" description="链接缺少有效的练习编号。" /></PageWrapper>;
  }

  if (detail.isLoading) {
    return (
      <PageWrapper title="练习结果">
        <div className="um-exam-result-state" role="status">
          <CircleNotch size={22} className="um-exam-result-spin" />
          正在读取练习结果…
        </div>
      </PageWrapper>
    );
  }

  if (detail.isError || !data) {
    return (
      <PageWrapper title="练习结果">
        <EmptyState
          title="结果暂时无法打开"
          description="请返回习题训练，稍后从最近练习重新进入。"
        />
        <div className="um-exam-result-state-actions">
          <Button onClick={() => navigate('/tests')}>返回习题训练</Button>
        </div>
      </PageWrapper>
    );
  }

  const active = isActive(data.status);
  const canRetry = data.status === 'partial' || data.status === 'failed';

  const retry = async () => {
    setRetrying(true);
    try {
      await api.post(`/quizzes/exams/${examId}/retry/`);
      useExamActivityStore.getState().start({
        examId,
        total: data.total_questions,
        status: 'pending',
        graded: data.graded_count,
        failed: 0,
      });
      await queryClient.invalidateQueries({ queryKey: queryKeys.exams.detail(examId) });
      toast.success('已提交重试');
    } catch (error) {
      toast.error(formatApiErrorToast(error, '提交重试失败'));
    } finally {
      setRetrying(false);
    }
  };

  const toggleMastered = async (item: ExamResultItem) => {
    if (!item.question_id) return;
    try {
      const response = await api.post('/quizzes/mastered/toggle/', { question_id: item.question_id });
      setMastered(prev => {
        const next = new Set(prev);
        if (response.data?.is_mastered) next.add(item.question_id as number);
        else next.delete(item.question_id as number);
        return next;
      });
      toast.success(response.data?.is_mastered ? '已标记掌握' : '已取消掌握');
    } catch (error) {
      toast.error(formatApiErrorToast(error, '操作失败'));
    }
  };

  return (
    <PageWrapper title="练习结果">
      <div className="um-exam-result">
        <header className="um-exam-result-header">
          <button type="button" className="um-exam-result-back" onClick={() => navigate('/tests')}>
            <ArrowLeft size={16} /> 返回习题训练
          </button>
          <div className="um-exam-result-heading">
            <div>
              <p className="um-exam-result-kicker">练习结果</p>
              <h1>这次练得怎么样</h1>
            </div>
            <Badge variant={data.status === 'completed' ? 'apple-green' : data.status === 'failed' ? 'destructive' : 'secondary'}>
              {statusText[data.status]}
            </Badge>
          </div>
          <p className="um-exam-result-time">
            {data.created_at ? new Date(data.created_at).toLocaleString('zh-CN', { hour12: false }) : ''}
          </p>
        </header>

        {active && (
          <section className="um-exam-result-banner" role="status">
            <CircleNotch size={18} className="um-exam-result-spin" />
            <div>
              <strong>正在批改，已完成 {data.graded_count}/{data.total_questions} 题</strong>
              <span>可以先看已经完成的部分，其余题目会自动补上。</span>
            </div>
          </section>
        )}

        {(data.status === 'partial' || data.status === 'failed') && (
          <section className="um-exam-result-banner is-warning" role="status">
            <div>
              <strong>{data.failed_count} 题还没有完成批改</strong>
              <span>重试后只批改未完成的题，已完成的结果不会重复计算。</span>
            </div>
            {canRetry && (
              <Button size="sm" variant="outline" onClick={retry} disabled={retrying}>
                <ArrowsClockwise size={14} /> {retrying ? '提交中…' : '重试未完成题'}
              </Button>
            )}
          </section>
        )}

        <section className="um-exam-result-summary" aria-label="本轮总结">
          <div className="um-exam-result-metrics">
            <div><span>得分</span><strong>{data.max_score ? `${data.total_score} / ${data.max_score}` : '—'}</strong></div>
            <div><span>正确率</span><strong>{data.max_score ? `${data.correct_rate}%` : '—'}</strong></div>
            <div><span>已批改</span><strong>{data.graded_count} / {data.total_questions}</strong></div>
            <div><span>未完成</span><strong>{data.failed_count + (data.pending_count ?? 0)}</strong></div>
          </div>
          <div className="um-exam-result-progress" aria-hidden="true">
            <span style={{ width: `${data.total_questions ? Math.min(100, (data.graded_count / data.total_questions) * 100) : 0}%` }} />
          </div>
          <p className="um-exam-result-summary-text">{data.summary_text || '完成批改后，这里会显示本轮总结。'}</p>
          {data.kp_breakdown.length > 0 && (
            <div className="um-exam-result-kps">
              <h2>知识点掌握</h2>
              {data.kp_breakdown.map(item => (
                <div className="um-exam-result-kp" key={item.kp_id}>
                  <span>{item.kp_name || '未命名知识点'}</span>
                  <span className="um-exam-result-kp-track" aria-hidden="true">
                    <i style={{ width: `${Math.max(0, Math.min(100, item.correct_rate))}%` }} />
                  </span>
                  <small>{item.correct_rate}%</small>
                </div>
              ))}
            </div>
          )}
        </section>

        <section className="um-exam-result-review" aria-label="逐题复盘">
          <div className="um-exam-result-toolbar">
            <div className="um-exam-result-filters" role="group" aria-label="筛选题目">
              <button type="button" aria-pressed={filter === 'all'} onClick={() => setFilter('all')}>全部 {data.results.length}</button>
              <button type="button" aria-pressed={filter === 'wrong'} onClick={() => setFilter('wrong')}>只看错题 {counts.wrong}</button>
              <button type="button" aria-pressed={filter === 'pending'} onClick={() => setFilter('pending')}>未完成 {counts.pending}</button>
            </div>
            <span className="um-exam-result-count">本轮共 {data.total_questions} 题</span>
          </div>

          {visibleResults.length === 0 ? (
            <EmptyState
              title={filter === 'wrong' ? '本轮没有错题' : filter === 'pending' ? '所有题目都已批改' : '还没有逐题结果'}
              description={filter === 'pending' ? '完成批改后，这里会显示每一题的解析。' : undefined}
            />
          ) : (
            <div className="um-exam-result-list">
              {visibleResults.map(item => {
                const isOpen = !!expanded[item.position];
                const itemStatus = item.status === 'graded'
                  ? item.is_correct ? '正确' : '错误'
                  : item.status === 'failed' ? '批改失败' : '批改中';
                return (
                  <article
                    className={`um-exam-result-item is-${item.status}${item.status === 'graded' && !item.is_correct ? ' is-wrong' : ''}`}
                    key={`${item.position}-${item.question_id ?? 'none'}`}
                  >
                    <button
                      type="button"
                      className="um-exam-result-item-head"
                      aria-expanded={isOpen}
                      onClick={() => setExpanded(prev => ({ ...prev, [item.position]: !prev[item.position] }))}
                    >
                      <span className="um-exam-result-item-index">{String(item.position).padStart(2, '0')}</span>
                      <span className="um-exam-result-item-title">
                        <strong>{item.kp_name || '题目'}</strong>
                        <span>{item.q_type === 'objective' ? '客观题' : (item.subjective_type || '主观题')}</span>
                      </span>
                      <span className={`um-exam-result-item-status is-${item.status}`}>
                        {item.status === 'graded' && item.is_correct && <CheckCircle size={14} weight="fill" />}
                        {itemStatus}
                      </span>
                      <span className="um-exam-result-item-score">
                        {item.status === 'graded' ? `${item.score}/${item.max_score}` : '—'}
                      </span>
                      <span className="um-exam-result-item-chevron" aria-hidden="true">{isOpen ? '−' : '+'}</span>
                    </button>

                    {isOpen && (
                      <div className="um-exam-result-item-body">
                        <div className="um-exam-result-question">
                          <MarkdownContent content={processMathContent(item.question_text)} />
                        </div>
                        {item.options.length > 0 && (
                          <ol className="um-exam-result-options">
                            {item.options.map((option, index) => (
                              <li key={`${item.position}-option-${index}`}>
                                <span className="um-exam-result-option-key">{String.fromCharCode(65 + index)}</span>
                                {option}
                              </li>
                            ))}
                          </ol>
                        )}
                        {item.status === 'graded' && (
                          <>
                            <div className="um-exam-result-answer">
                              <span>你的答案</span>
                              <MarkdownContent content={processMathContent(item.user_answer || '（未作答）')} />
                            </div>
                            <div className="um-exam-result-answer is-reference">
                              <span>参考答案</span>
                              <MarkdownContent content={processMathContent(item.correct_answer || '暂无')} />
                            </div>
                            {item.feedback && (
                              <div className="um-exam-result-answer">
                                <span>批改反馈</span>
                                <MarkdownContent content={processMathContent(item.feedback)} />
                              </div>
                            )}
                            {item.analysis && (
                              <div className="um-exam-result-answer is-analysis">
                                <span>解析</span>
                                <MarkdownContent content={processMathContent(item.analysis)} />
                              </div>
                            )}
                            {(item.error_metadata?.reasoning || item.error_metadata?.suggested_focus) && (
                              <div className="um-exam-result-error">
                                {item.error_metadata.reasoning && <p><strong>错因：</strong>{item.error_metadata.reasoning}</p>}
                                {item.error_metadata.suggested_focus && <p><strong>建议复习：</strong>{item.error_metadata.suggested_focus}</p>}
                              </div>
                            )}
                            {item.question_id && (
                              <Button
                                size="sm"
                                variant="outline"
                                onClick={() => toggleMastered(item)}
                              >
                                {mastered.has(item.question_id) ? '已标记掌握' : '标记掌握'}
                              </Button>
                            )}
                          </>
                        )}
                        {item.status === 'pending' && <p className="um-exam-result-pending">这题还在批改中，完成后会自动显示。</p>}
                        {item.status === 'failed' && (
                          <p className="um-exam-result-pending">
                            {item.error_metadata?.error || '这题批改未完成，可以回到上方重试。'}
                          </p>
                        )}
                      </div>
                    )}
                  </article>
                );
              })}
            </div>
          )}
        </section>
      </div>
    </PageWrapper>
  );
};
