import { t, useLocale } from '@/i18n';
import { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { CheckCircle, CircleNotch, WarningCircle, XCircle } from '@phosphor-icons/react';

import {
  isActiveExamStatus,
  useExamActivityStore,
  type ExamActivity,
} from '@/store/useExamActivityStore';
import '@/styles/exam-activity.css';

const copyFor = (activity: ExamActivity) => {
  if (isActiveExamStatus(activity.status)) {
    const progress = activity.total ? t('已批 {0}/{1} 题', { 0: activity.graded, 1: activity.total }) : t('正在批改');
    return { title: t('正在批改'), meta: progress };
  }
  if (activity.status === 'completed') {
    const score = activity.maxScore ? t('得分 {0}/{1}', { 0: activity.totalScore ?? 0, 1: activity.maxScore }) : '';
    return { title: t('评估完成，查看复盘'), meta: score };
  }
  if (activity.status === 'partial') {
    return { title: t('部分完成，查看复盘'), meta: t('{0} 题待重试', { 0: activity.failed }) };
  }
  return { title: t('批改未完成，查看'), meta: t('可进入结果页重试') };
};

const iconFor = (activity: ExamActivity) => {
  if (isActiveExamStatus(activity.status)) {
    return <CircleNotch size={18} weight="bold" className="exam-activity-spinner" aria-hidden="true" />;
  }
  if (activity.status === 'completed') return <CheckCircle size={18} weight="fill" aria-hidden="true" />;
  if (activity.status === 'partial') return <WarningCircle size={18} weight="fill" aria-hidden="true" />;
  return <XCircle size={18} weight="fill" aria-hidden="true" />;
};

export const ExamActivityBar = () => {
  useLocale();
  const navigate = useNavigate();
  const activities = useExamActivityStore(state => state.activities);
  const pruneExpired = useExamActivityStore(state => state.pruneExpired);

  useEffect(() => {
    if (!activities.length) return;
    const timer = window.setInterval(pruneExpired, 1000);
    return () => window.clearInterval(timer);
  }, [activities.length, pruneExpired]);

  if (!activities.length) return null;

  const visible = activities.slice(0, 3);
  const hidden = activities.length - visible.length;
  const open = (activity: ExamActivity) => {
    useExamActivityStore.getState().dismiss(activity.examId);
    navigate(activity.href);
  };

  return (
    <section className="exam-activity-bar" aria-label={t('练习批改状态')} aria-live="polite" role="status">
      {visible.map((activity) => {
        const copy = copyFor(activity);
        const progress = activity.total
          ? Math.min(100, Math.round((activity.graded / activity.total) * 100))
          : 0;
        return (
          <button
            type="button"
            key={activity.examId}
            className={`exam-activity-item is-${activity.status}`}
            onClick={() => open(activity)}
            aria-label={`${copy.title}，${copy.meta}`}
          >
            <span className="exam-activity-icon">{iconFor(activity)}</span>
            <span className="exam-activity-copy">
              <span className="exam-activity-title">{copy.title}</span>
              {copy.meta && <span className="exam-activity-meta">{copy.meta}</span>}
              {isActiveExamStatus(activity.status) && activity.total > 0 && (
                <span className="exam-activity-progress" aria-hidden="true">
                  <span style={{ width: `${progress}%` }} />
                </span>
              )}
            </span>
            <span className="exam-activity-arrow" aria-hidden="true">↗</span>
          </button>
        );
      })}
      {hidden > 0 && <span className="exam-activity-more">{t('还有 {0} 条练习状态', { 0: hidden })}</span>}
    </section>
  );
};
