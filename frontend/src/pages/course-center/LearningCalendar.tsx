import { useState } from 'react';
import { CaretLeft as ChevronLeft, CaretRight as ChevronRight } from '@phosphor-icons/react';
import type { LearningDay } from './types';
import { dateOffset, learningDuration } from './learningDates';
import { LearningHeatmap } from './LearningHeatmap';

export function LearningCalendar({ today, days }: { today: string; days: LearningDay[] }) {
  const [mode, setMode] = useState('week');
  const [month, setMonth] = useState(today.slice(0, 7));
  const [selected, setSelected] = useState(today);
  const activity = new Map<string, { seconds: number; completions: number }>();
  days.forEach(day => { const previous = activity.get(day.date) || { seconds: 0, completions: 0 }; activity.set(day.date, { seconds: previous.seconds + day.watched_seconds, completions: previous.completions + day.completions }); });
  const selectedActivity = activity.get(selected);
  const weekStart = dateOffset(today, -(new Date(`${today}T12:00:00Z`).getUTCDay() + 6) % 7);
  const week = Array.from({ length: 7 }, (_, index) => dateOffset(weekStart, index));
  const maxSeconds = Math.max(600, ...week.map(date => activity.get(date)?.seconds || 0));
  const monthStart = `${month}-01`;
  const firstDay = (new Date(`${monthStart}T12:00:00Z`).getUTCDay() + 6) % 7;
  const count = new Date(Date.UTC(Number(month.slice(0, 4)), Number(month.slice(5)), 0)).getUTCDate();
  const changeMonth = (offset: number) => {
    const value = new Date(`${monthStart}T12:00:00Z`);
    value.setUTCMonth(value.getUTCMonth() + offset);
    setMonth(value.toISOString().slice(0, 7));
  };
  const level = (seconds: number, completions = 0) => !seconds && !completions ? 0 : seconds >= 3600 ? 4 : seconds >= 1800 ? 3 : seconds >= 600 ? 2 : 1;
  return <section className="um-portal-card um-calendar-card" aria-label="学习活动"><div className="um-course-section-heading"><h2>学习活动</h2><div className="um-segmented" role="group" aria-label="学习活动视图"><button type="button" aria-pressed={mode === 'week'} onClick={() => setMode('week')}>周</button><button type="button" aria-pressed={mode === 'month'} onClick={() => setMode('month')}>月</button><button type="button" aria-pressed={mode === 'heat'} onClick={() => setMode('heat')}>热力</button></div></div>
    {mode === 'heat' ? <LearningHeatmap today={today} days={days} trackingStarted={null} embedded /> : mode === 'week' ? <div className="um-week-chart" aria-label="本周学习时长">{week.map((date, index) => { const seconds = activity.get(date)?.seconds || 0; const completions = activity.get(date)?.completions || 0; return <button type="button" key={date} disabled={date > today} aria-pressed={selected === date} aria-label={`${date}：${learningDuration(seconds)}，完成 ${completions} 门`} onClick={() => setSelected(date)}><span className="um-week-chart-date">{Number(date.slice(8))}</span><span className="um-week-chart-track"><i style={{ height: `${seconds > 0 ? Math.max(5, seconds / maxSeconds * 100) : 0}%` }} /></span><span>{['一', '二', '三', '四', '五', '六', '日'][index]}</span></button>; })}</div> : <><div className="um-calendar-month-toolbar"><button type="button" className="um-portal-icon-button" aria-label="上个月" onClick={() => changeMonth(-1)}><ChevronLeft size={14} /></button><span>{month.replace('-', ' 年 ')} 月</span><button type="button" className="um-portal-icon-button" aria-label="下个月" disabled={month >= today.slice(0, 7)} onClick={() => changeMonth(1)}><ChevronRight size={14} /></button></div><div className="um-month-calendar" aria-label={`${month}学习日历`}>{['一', '二', '三', '四', '五', '六', '日'].map(day => <span className="um-calendar-weekday" key={day}>{day}</span>)}{Array.from({ length: firstDay }, (_, index) => <span key={`empty-${index}`} />)}{Array.from({ length: count }, (_, index) => { const date = dateOffset(monthStart, index); const value = activity.get(date); return <button type="button" key={date} data-level={level(value?.seconds || 0, value?.completions)} disabled={date > today} aria-pressed={selected === date} aria-label={`${date}：${learningDuration(value?.seconds || 0)}，完成 ${value?.completions || 0} 门`} onClick={() => setSelected(date)}>{index + 1}</button>; })}</div></>}
    {mode !== 'heat' && <p className="um-calendar-selected" aria-live="polite">{selected.slice(5).replace('-', '/')} · {learningDuration(selectedActivity?.seconds || 0)} · {selectedActivity?.completions || 0} 门</p>}
  </section>;
}
