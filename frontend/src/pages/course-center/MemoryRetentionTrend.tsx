import { useEffect, useId, useState } from 'react';
import { Link } from 'react-router-dom';
import api from '@/lib/api';

type CurvePoint = { date: string; predicted: number; actual: number; count: number };
type MemoryCurve = {
  window_days: number;
  time_series: CurvePoint[];
  metrics: { review_count: number; rmse: number | null; mae: number | null; avg_predicted: number | null; avg_actual: number | null };
  profile: { last_optimized_at: string | null; total_reviews_used: number };
};
type Optimization = { id: number; improvement_ratio: number; reviews_used: number; accepted: boolean; created_at: string };

const percent = (value: number | null | undefined) => value == null ? '—' : `${Math.round(value * 100)}%`;
const shortDate = (value: string) => `${Number(value.slice(5, 7))}/${Number(value.slice(8, 10))}`;

export function MemoryRetentionTrend() {
  const titleId = useId();
  const descriptionId = useId();
  const [curve, setCurve] = useState<MemoryCurve | null>(null);
  const [history, setHistory] = useState<Optimization[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [historyError, setHistoryError] = useState(false);
  const [version, setVersion] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    api.get<MemoryCurve>('/quizzes/memorix/curve/', { params: { window_days: 90 }, signal: controller.signal })
      .then(response => { setCurve(response.data); setError(false); })
      .catch(() => { if (!controller.signal.aborted) setError(true); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    api.get<{ results: Optimization[] }>('/quizzes/memorix/optimization-history/', { signal: controller.signal })
      .then(response => { setHistory(response.data.results); setHistoryError(false); })
      .catch(() => { if (!controller.signal.aborted) setHistoryError(true); });
    return () => controller.abort();
  }, [version]);

  const series = curve?.time_series || [];
  const first = series[0];
  const last = series[series.length - 1];
  const start = first ? Date.parse(first.date) : 0;
  const end = last ? Date.parse(last.date) : 0;
  const x = (point: CurvePoint) => end === start ? 398 : 44 + (Date.parse(point.date) - start) / (end - start) * 708;
  const y = (value: number) => 16 + (1 - Math.max(0, Math.min(1, value))) * 160;
  const path = (key: 'predicted' | 'actual') => series.map((point, index) => `${index ? 'L' : 'M'} ${x(point)} ${y(point[key])}`).join(' ');

  return <section className="um-memory-trend um-portal-card" aria-label="记忆保持趋势">
    <header className="um-course-section-heading"><div><h2>记忆保持趋势</h2><p>Memorix-Field · 近 {curve?.window_days || 90} 天的复习记录</p></div><button type="button" className="um-course-text-button" disabled={loading} onClick={() => setVersion(value => value + 1)}>{loading ? '读取中…' : '刷新'}</button></header>
    {loading ? <p role="status" className="um-memory-empty">正在读取记忆趋势…</p> : error ? <p role="alert" className="um-memory-empty">记忆趋势加载失败，请刷新重试。</p> : !series.length ? <div className="um-memory-empty"><p>完成几轮复习后，你可以在这里看到记忆保持的变化。</p><Link to="/tests">开始练习</Link></div> : <>
      <dl className="um-memory-metrics"><div><dt>预计记住的程度</dt><dd>{percent(curve?.metrics.avg_predicted)}</dd></div><div><dt>实际回忆表现</dt><dd>{percent(curve?.metrics.avg_actual)}</dd></div><div><dt>复习记录</dt><dd>{curve?.metrics.review_count}<small> 次</small></dd></div></dl>
      <p className="um-memory-explainer">上方为期间平均值。实线是系统预测的记忆保持程度，虚线是复习时成功回忆的比例，只统计有复习记录的日期。</p>
      <div className="um-memory-chart"><svg viewBox="0 0 768 212" role="img" aria-labelledby={`${titleId} ${descriptionId}`}>
        <title id={titleId}>记忆保持趋势</title><desc id={descriptionId}>{`${first.date} 至 ${last.date}，预计记住的程度平均 ${percent(curve?.metrics.avg_predicted)}，实际回忆表现平均 ${percent(curve?.metrics.avg_actual)}。详细日期和数值可在下方详情查看。`}</desc>
        {[1, .5, 0].map(value => <g key={value}><line x1="44" x2="752" y1={y(value)} y2={y(value)} className="um-memory-gridline" /><text x="32" y={y(value) + 4} textAnchor="end">{value * 100}%</text></g>)}
        <path d={path('predicted')} fill="none" className="um-memory-predicted" strokeWidth="2.5" /><path d={path('actual')} fill="none" className="um-memory-actual" strokeWidth="2.5" strokeDasharray="5 4" />
        {series.map(point => <g key={point.date}><title>{`${point.date}，预计 ${percent(point.predicted)}，实际 ${percent(point.actual)}，复习 ${point.count} 次`}</title><circle cx={x(point)} cy={y(point.predicted)} r="3" className="um-memory-predicted-dot" /><circle cx={x(point)} cy={y(point.actual)} r="3" className="um-memory-actual-dot" /></g>)}
        <text x={x(first)} y="203" textAnchor={series.length === 1 ? 'middle' : 'start'}>{shortDate(first.date)}</text>{series.length > 1 && <text x={x(last)} y="203" textAnchor="end">{shortDate(last.date)}</text>}
      </svg></div>
      <div className="um-memory-legend"><span><i />预计记住的程度</span><span><i />实际回忆表现</span></div>
      <details className="um-memory-details"><summary>查看数据与算法更新</summary>
        <p>最近更新：{curve?.profile.last_optimized_at ? new Date(curve.profile.last_optimized_at).toLocaleString('zh-CN') : '尚未更新'}。算法根据你的复习记录调整预测，更新改善率表示预测误差的变化。</p>
        <dl><div><dt>预测误差（RMSE）</dt><dd>{curve?.metrics.rmse ?? '—'}</dd></div><div><dt>平均绝对误差（MAE）</dt><dd>{curve?.metrics.mae ?? '—'}</dd></div></dl>
        <div className="um-memory-table"><table><caption>每日复习数据</caption><thead><tr><th scope="col">日期</th><th scope="col">预计</th><th scope="col">实际</th><th scope="col">次数</th></tr></thead><tbody>{series.map(point => <tr key={point.date}><th scope="row">{point.date}</th><td>{percent(point.predicted)}</td><td>{percent(point.actual)}</td><td>{point.count}</td></tr>)}</tbody></table></div>
        <h3>最近算法更新</h3>{historyError ? <p role="alert">更新记录加载失败，请刷新重试。</p> : !history.length ? <p>暂无更新记录</p> : <ul>{history.slice(0, 3).map(item => <li key={item.id}><span>{item.accepted ? '已采用' : '未采用'} · 预测误差改善 {(item.improvement_ratio * 100).toFixed(2)}%</span><span>{item.reviews_used} 次复习 · {new Date(item.created_at).toLocaleString('zh-CN')}</span></li>)}</ul>}
      </details>
    </>}
  </section>;
}
