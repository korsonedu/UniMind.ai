import { Link, useNavigate } from 'react-router-dom';
import { MemoryRetentionTrend } from './MemoryRetentionTrend';

export interface DashData {
  stats: {
    streak_days: number; weekly_activity: number; accuracy: number; total_attempted: number;
    attempted_questions?: number; total_attempts?: number;
    last_accuracy?: number | null; lifetime_accuracy?: number | null; has_attempts?: boolean;
    heatmap_days: { date: string; count: number }[]; is_new_user: boolean;
    today_checked_in: boolean; checkin_streak: number;
    checkin_history: { date: string; checked_in: boolean }[];
    unlocked_achievement_count: number;
    next_achievements: { key: string; name: string; description: string; icon: string; category: string }[];
  };
  reviews: { due_count: number };
  exams: { id: number; total_score: number; max_score: number; percentage: number; elo_change: number; created_at: string }[];
}

export function LearningOverview({ data, error, onRetry }: {
  data: DashData | null; error: boolean; onRetry: () => void;
}) {
  const navigate = useNavigate();
  const stats = data?.stats;
  const exam = data?.exams[0];
  return <>
    {error ? <section className="um-agent-panel"><p role="alert">学习数据加载失败</p><button className="um-course-button" onClick={onRetry}>重试</button></section> : !stats ? <p role="status">正在读取学习数据…</p> : <>
      {stats.is_new_user && <section className="um-agent-panel um-agent-summary um-agent-diagnostic"><div><h2>开始你的第一次诊断测试</h2><p>了解当前学习水平，定位薄弱知识点，确定接下来的练习方向。</p></div><button className="um-course-button um-course-button-primary" onClick={() => navigate('/diagnostic')}>开始诊断</button></section>}
      <section className="um-agent-panel um-agent-summary" aria-label="练习表现">
        <header><h2>练习表现</h2><Link to="/report-card">成绩报告</Link></header>
        <dl className="um-agent-metrics">
          <div><dt>连续练习</dt><dd>{stats.streak_days}<small> 天</small></dd></div>
          <div>
            <dt>最近正确率</dt>
            <dd>{stats.has_attempts === false ? '—' : (stats.last_accuracy ?? stats.accuracy)}<small>{stats.has_attempts === false ? '' : ' %'}</small></dd>
            <p>
              已练 {stats.attempted_questions ?? stats.total_attempted} 题
              {stats.lifetime_accuracy != null && ` · 累计正确率 ${stats.lifetime_accuracy}%`}
            </p>
          </div>
          <div><dt>本周练习</dt><dd>{stats.weekly_activity}<small> 题</small></dd></div>
          <div><dt>待复习</dt><dd>{data?.reviews.due_count ?? 0}<small> 题</small></dd><Link to="/tests">开始练习</Link></div>
        </dl>
      </section>
      <MemoryRetentionTrend />
        <section className="um-agent-panel um-agent-achievements"><header><h2>下一个成就 · 已解锁 {stats.unlocked_achievement_count} 个</h2><Link to="/achievements">全部成就</Link></header><ul>{stats.next_achievements.map(item => <li key={item.key}>{item.icon && <span className="um-agent-achievement-icon" aria-hidden="true">{item.icon}</span>}<div><span>{item.name}</span><p>{item.description}</p></div></li>)}</ul>{!stats.next_achievements.length && <p className="um-agent-activity-detail">暂无待解锁成就</p>}</section>
      {exam && <section className="um-agent-panel um-agent-exam"><h2>最近考试</h2><span>{exam.total_score} / {exam.max_score}</span><span>{exam.percentage}%</span><span className="um-agent-gain">{exam.elo_change >= 0 ? '+' : ''}{exam.elo_change} ELO</span><Link className="um-course-button" to="/report-card">成绩报告</Link></section>}
    </>}
  </>;
}
