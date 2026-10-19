import { Link } from 'react-router-dom';

interface PracticeResultPayload {
  exam_id: number;
  status: 'pending' | 'grading' | 'completed' | 'partial' | 'failed';
  status_text: string;
  total_score: number;
  max_score: number;
  correct_rate: number;
  total_questions: number;
  graded_count: number;
  failed_count: number;
  weak_points: string[];
  href: string;
  summary_text: string;
}

const isActive = (status: PracticeResultPayload['status']) =>
  status === 'pending' || status === 'grading';

export function PracticeResultCard({ payload }: { payload: PracticeResultPayload }) {
  const active = isActive(payload.status);
  const score = payload.max_score
    ? `${payload.total_score}/${payload.max_score}`
    : '—';

  return (
    <div className="space-y-4 rounded-2xl border border-border bg-card p-5">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-[10px] uppercase tracking-widest text-muted-foreground">Practice result</p>
          <h3 className="text-sm font-bold">最近一次练习</h3>
        </div>
        <span className="rounded-full bg-muted px-2.5 py-1 text-[11px] font-semibold text-muted-foreground">
          {payload.status_text || '练习结果'}
        </span>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div className="rounded-xl bg-muted/50 p-3">
          <p className="text-[10px] text-muted-foreground">得分</p>
          <p className="mt-1 text-xl font-bold tabular-nums">{active ? '—' : score}</p>
        </div>
        <div className="rounded-xl bg-muted/50 p-3">
          <p className="text-[10px] text-muted-foreground">{active ? '批改进度' : '正确率'}</p>
          <p className="mt-1 text-xl font-bold tabular-nums">
            {active ? `${payload.graded_count}/${payload.total_questions}` : `${payload.correct_rate}%`}
          </p>
        </div>
      </div>

      {active && (
        <div className="space-y-1.5">
          <div className="h-1.5 overflow-hidden rounded-full bg-muted">
            <div
              className="h-full rounded-full bg-primary transition-all"
              style={{ width: `${payload.total_questions ? Math.min(100, (payload.graded_count / payload.total_questions) * 100) : 0}%` }}
            />
          </div>
          <p className="text-xs text-muted-foreground">批改完成后会自动更新，先继续做别的事也可以。</p>
        </div>
      )}

      {payload.summary_text && !active && (
        <p className="text-xs leading-relaxed text-muted-foreground">{payload.summary_text}</p>
      )}

      {payload.weak_points.length > 0 && (
        <div className="space-y-2">
          <p className="text-[10px] text-muted-foreground">薄弱知识点</p>
          <div className="flex flex-wrap gap-1.5">
            {payload.weak_points.map(point => (
              <span key={point} className="rounded-full bg-amber-50 px-2.5 py-1 text-[11px] font-medium text-amber-700">
                {point}
              </span>
            ))}
          </div>
        </div>
      )}

      <Link
        to={payload.href}
        className="inline-flex items-center gap-1 text-xs font-semibold text-primary hover:underline"
      >
        {active ? '查看批改进度' : '查看逐题复盘'} <span aria-hidden="true">↗</span>
      </Link>
    </div>
  );
}
