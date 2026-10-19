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
    const progress = activity.total ? `已批 ${activity.graded}/${activity.total} 题` : '正在批改';
    return { title: '正在批改', meta: progress };
  }
  if (activity.status === 'completed') {
    const score = activity.maxScore ? `得分 ${activity.totalScore ?? 0}/${activity.maxScore}` : '';
    return { title: '评估完成，查看复盘', meta: score };
  }
  if (activity.status === 'partial') {
    return { title: '部分完成，查看复盘', meta: `${activity.failed} 题待重试` };
  }
  return { title: '批改未完成，查看', meta: '可进入结果页重试' };
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
    <section className="exam-activity-bar" aria-label="练习批改状态" aria-live="polite" role="status">
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
      {hidden > 0 && <span className="exam-activity-more">还有 {hidden} 个任务在批改</span>}
    </section>
  );
};
