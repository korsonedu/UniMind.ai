import { getLocale, t, useLocale } from '@/i18n';
import { useNavigate, Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { ArrowLeft, ArrowRight, CircleNotch } from '@phosphor-icons/react';

import api from '@/lib/api';
import { queryKeys } from '@/lib/queryKeys';
import { PageWrapper } from '@/components/PageWrapper';
import { EmptyState } from '@/components/EmptyState';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import '@/styles/exam-result.css';

type ExamStatus = 'pending' | 'grading' | 'completed' | 'partial' | 'failed';

interface HistoryItem {
  kind: 'exam';
  id: number;
  title: string;
  status: ExamStatus;
  created_at: string;
  completed_at: string | null;
  total_questions: number;
  graded_count: number;
  failed_count: number;
  total_score: number;
  max_score: number;
  correct_rate: number;
  summary_text: string;
  href: string;
}

const statusText: Record<ExamStatus, string> = {
  pending: '待批改',
  grading: '批改中',
  completed: '已完成',
  partial: '部分完成',
  failed: '批改失败',
};

const isActive = (status: ExamStatus) => status === 'pending' || status === 'grading';

export const ExamHistoryPage = () => {
  useLocale();
  const navigate = useNavigate();
  const history = useQuery({
    queryKey: queryKeys.exams.history,
    queryFn: async () => {
      const response = await api.get<{ items: HistoryItem[] }>('/quizzes/exams/?limit=50');
      return response.data.items;
    },
    staleTime: 0,
    refetchInterval: (query: { state: { data?: HistoryItem[] } }) => {
      const items = query.state.data;
      return items?.some(item => isActive(item.status)) ? 4000 : false;
    },
  });

  const items = history.data ?? [];

  return (
    <PageWrapper title={t('最近练习')}>
      <div className="um-exam-history">
        <header className="um-exam-history-header">
          <button type="button" className="um-exam-result-back" onClick={() => navigate('/tests')}>
            <ArrowLeft size={16} /> {t('返回习题训练')}
          </button>
          <div className="um-exam-history-heading">
            <div>
              <p className="um-exam-result-kicker">{t('练习记录')}</p>
              <h1>{t('最近练习')}</h1>
            </div>
            <Button variant="outline" onClick={() => navigate('/tests')}>{t('开始新练习')}</Button>
          </div>
          <p className="um-exam-history-lead">{t('每次提交后的批改进度、得分和逐题复盘都在这里。')}</p>
        </header>

        {history.isLoading ? (
          <div className="um-exam-result-state" role="status">
            <CircleNotch size={22} className="um-exam-result-spin" />
            {t('正在读取练习记录…')}
          </div>
        ) : history.isError ? (
          <div className="um-exam-result-state" role="alert">
            {t('练习记录加载失败，请刷新重试。')}
          </div>
        ) : items.length === 0 ? (
          <EmptyState
            title={t('还没有练习记录')}
            description={t('完成一次练习后，结果会出现在这里。')}
          />
        ) : (
          <div className="um-exam-history-list">
            {items.map(item => {
              const active = isActive(item.status);
              const progress = item.total_questions
                ? Math.min(100, (item.graded_count / item.total_questions) * 100)
                : 0;
              const score = item.max_score ? `${item.total_score}/${item.max_score}` : '—';
              return (
                <Link className="um-exam-history-item" key={item.id} to={item.href}>
                  <span className="um-exam-history-date">
                    {item.created_at
                      ? new Date(item.created_at).toLocaleString(getLocale(), { hour12: false, month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
                      : '—'}
                  </span>
                  <span className="um-exam-history-main">
                    <span className="um-exam-history-title">
                      <strong>{item.title}</strong>
                      <Badge variant={item.status === 'completed' ? 'apple-green' : item.status === 'failed' ? 'destructive' : 'secondary'}>
                        {t(statusText[item.status])}
                      </Badge>
                    </span>
                    <span className="um-exam-history-meta">
                      {item.total_questions} {t('题 ·')} {active ? t('已批 {0}/{1}', { 0: item.graded_count, 1: item.total_questions }) : t('得分 {0}', { 0: score })}
                      {item.status === 'partial' && item.failed_count > 0 ? t(' · {0} 题待重试', { 0: item.failed_count }) : ''}
                    </span>
                    {active && (
                      <span className="um-exam-result-progress" aria-hidden="true">
                        <span style={{ width: `${progress}%` }} />
                      </span>
                    )}
                  </span>
                  <span className="um-exam-history-arrow" aria-hidden="true"><ArrowRight size={16} /></span>
                </Link>
              );
            })}
          </div>
        )}
      </div>
    </PageWrapper>
  );
};
