import { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuthStore } from '@/store/useAuthStore';

export interface DashData {
  stats: {
    streak_days: number; weekly_activity: number; accuracy: number; total_attempted: number;
    heatmap_days: { date: string; count: number }[]; is_new_user: boolean;
    today_checked_in: boolean; checkin_streak: number;
    checkin_history: { date: string; checked_in: boolean }[];
    unlocked_achievement_count: number;
    next_achievements: { key: string; name: string; description: string; icon: string; category: string }[];
  };
  reviews: { due_count: number };
  exams: { id: number; total_score: number; max_score: number; percentage: number; elo_change: number; created_at: string }[];
}

export function LearningOverview({ data, error, onRetry, checkingIn, onCheckIn }: {
  data: DashData | null; error: boolean; onRetry: () => void; checkingIn: boolean; onCheckIn: () => void;
}) {
  const user = useAuthStore(state => state.user);
  const navigate = useNavigate();
  const [now, setNow] = useState(() => new Date());
  const [selectedDay, setSelectedDay] = useState('');
  useEffect(() => { const timer = window.setInterval(() => setNow(new Date()), 1000); return () => window.clearInterval(timer); }, []);
  const hour = Number(new Intl.DateTimeFormat('en-GB', { timeZone: 'Asia/Shanghai', hour: 'numeric', hourCycle: 'h23' }).format(now));
  const greeting = hour < 12 ? '早上好' : hour < 18 ? '下午好' : '晚上好';
  const stats = data?.stats;
  const exam = data?.exams[0];
  const eloChange = data?.exams.reduce((sum, item) => sum + item.elo_change, 0) ?? 0;
  const day = stats?.heatmap_days.find(item => item.date === selectedDay);
  return <>
    <header className="um-agent-welcome"><h2>{greeting}，{user?.nickname || user?.username || '同学'}</h2><time dateTime={now.toISOString()} title={now.toLocaleDateString('zh-CN', { timeZone: 'Asia/Shanghai' })}>{new Intl.DateTimeFormat('zh-CN', { timeZone: 'Asia/Shanghai', hour: '2-digit', minute: '2-digit', hourCycle: 'h23' }).format(now)}</time></header>
    {error ? <section className="um-agent-panel"><p role="alert">学习数据加载失败</p><button className="um-agent-button" onClick={onRetry}>重试</button></section> : !stats ? <p role="status">正在读取学习数据…</p> : <>
      {stats.is_new_user && <section className="um-agent-panel um-agent-summary"><h2>诊断测试</h2><button className="um-agent-button um-agent-button-primary" onClick={() => navigate('/diagnostic')}>开始诊断</button></section>}
      <section className="um-agent-panel um-agent-summary" aria-label="学习概览">
        <header><h2>学习概览</h2><button className="um-agent-button" onClick={onCheckIn} disabled={checkingIn || stats.today_checked_in}>{checkingIn ? '打卡中…' : stats.today_checked_in ? '已打卡' : '今日打卡'}</button></header>
        <dl className="um-agent-metrics">
          <div><dt>连续学习</dt><dd>{stats.streak_days}<small> 天</small></dd><p>打卡 {stats.checkin_streak} 天</p></div>
          <div><dt>正确率</dt><dd>{stats.accuracy}<small> %</small></dd><p>累计 {stats.total_attempted} 题</p></div>
          <div><dt>本周练习</dt><dd>{stats.weekly_activity}<small> 题</small></dd><p>待复习 {data?.reviews.due_count ?? 0} 题</p></div>
          <div><dt>ELO</dt><dd>{user?.elo_score ?? '—'}</dd><p><span className="um-agent-gain">{eloChange >= 0 ? '+' : ''}{eloChange}</span> · 近期考试</p></div>
        </dl>
      </section>
      <div className="um-agent-dashboard-grid">
        <section className="um-agent-panel"><h2>28 天学习活动</h2><div className="um-agent-activity-grid" role="group" aria-label="每日练习次数">
          {stats.heatmap_days.map(item => <button key={item.date} data-level={item.count === 0 ? 0 : item.count <= 3 ? 1 : item.count <= 8 ? 2 : item.count <= 15 ? 3 : 4} title={`${item.date} · ${item.count} 题`} aria-label={`${item.date} · ${item.count} 题`} aria-pressed={selectedDay === item.date} onClick={() => setSelectedDay(item.date)} />)}
        </div><p className="um-agent-activity-detail" aria-live="polite">{day ? `${day.date} · ${day.count} 题` : stats.heatmap_days.length ? '近 28 天' : '暂无学习活动'}</p></section>
        <section className="um-agent-panel um-agent-achievements"><h2>成就 · {stats.unlocked_achievement_count} 已解锁</h2><ul>{stats.next_achievements.map(item => <li key={item.key}><details><summary>{item.name}</summary><p>{item.description}</p></details></li>)}</ul><Link to="/achievements">全部成就</Link></section>
      </div>
      {exam && <section className="um-agent-panel um-agent-exam"><h2>最近考试</h2><span>{exam.total_score} / {exam.max_score}</span><span>{exam.percentage}%</span><span className="um-agent-gain">{exam.elo_change >= 0 ? '+' : ''}{exam.elo_change} ELO</span><Link className="um-agent-button" to="/report-card">成绩报告</Link></section>}
    </>}
  </>;
}
