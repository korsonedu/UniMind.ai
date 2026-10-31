import { ArrowRight, Clock, CheckCircle, WarningCircle } from '@phosphor-icons/react';
import { Link } from 'react-router-dom';

export interface PracticeResultPayload {
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

const isActive = (status: PracticeResultPayload['status']) => status === 'pending' || status === 'grading';

export function PracticeResultCard({ payload, snapshot = false }: { payload: PracticeResultPayload; snapshot?: boolean }) {
  const active = isActive(payload.status);
  const score = payload.max_score ? `${payload.total_score}/${payload.max_score}` : '—';
  const StatusIcon = active ? Clock : payload.status === 'completed' ? CheckCircle : WarningCircle;
  return <div className="um-visual-practice-result">
    <header className="um-visual-result-heading"><h3>最近一次练习</h3><span><StatusIcon size={15} />{payload.status_text || '练习结果'}</span></header>
    <dl className="um-visual-result-metrics">
      <div><dt>得分</dt><dd>{active ? '—' : score}</dd></div>
      <div><dt>{active ? '批改进度' : '正确率'}</dt><dd>{active ? `${payload.graded_count}/${payload.total_questions}` : `${payload.correct_rate}%`}</dd></div>
    </dl>
    {active && <div>
      <progress className="um-visual-result-progress" aria-label="批改进度" max={payload.total_questions || 1} value={payload.graded_count} />
      <p className="um-visual-note">{snapshot ? '这是查询时的批改进度，打开详情查看最新状态。' : '批改完成后会自动更新，先继续做别的事也可以。'}</p>
    </div>}
    {payload.summary_text && !active && <p className="um-visual-note">{payload.summary_text}</p>}
    {payload.weak_points.length > 0 && <div className="um-visual-weak-points"><p>薄弱知识点</p><ul>{payload.weak_points.map(point => <li key={point}>{point}</li>)}</ul></div>}
    <Link to={payload.href} className="um-visual-link">{active ? '查看批改进度' : '查看逐题复盘'}<ArrowRight size={14} /></Link>
  </div>;
}
