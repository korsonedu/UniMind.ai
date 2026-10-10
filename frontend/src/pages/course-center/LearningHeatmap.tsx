import { useEffect, useId, useRef, useState, type KeyboardEvent, type CSSProperties } from 'react';
import type { LearningDay } from './types';
import { dateOffset, learningDuration } from './learningDates';

interface DayActivity { seconds: number; completions: number; }

export function LearningHeatmap({ today, days, embedded = false }: { today: string; days: LearningDay[]; trackingStarted: string | null; embedded?: boolean }) {
  const [weeks, setWeeks] = useState(26);
  const [selected, setSelected] = useState(today);
  const chartId = useId();
  const scrollElement = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const element = scrollElement.current;
    if (!element) return;
    const showRecent = () => { element.scrollLeft = element.scrollWidth; };
    showRecent();
    const observer = new ResizeObserver(showRecent);
    observer.observe(element);
    return () => observer.disconnect();
  }, [weeks]);
  const byDate = new Map<string, DayActivity>();
  days.forEach(day => {
    const previous = byDate.get(day.date) || { seconds: 0, completions: 0 };
    byDate.set(day.date, { seconds: previous.seconds + day.watched_seconds, completions: previous.completions + day.completions });
  });
  const start = dateOffset(today, -(weeks - 1) * 7 - new Date(`${today}T12:00:00Z`).getUTCDay());
  const dates = Array.from({ length: weeks * 7 }, (_, index) => dateOffset(start, index));
  const selectedActivity = byDate.get(selected) || { seconds: 0, completions: 0 };
  const activeDays = dates.filter(date => date <= today && ((byDate.get(date)?.seconds || 0) > 0 || (byDate.get(date)?.completions || 0) > 0)).length;
  const level = (value?: DayActivity) => !value || (!value.seconds && !value.completions) ? 0 : value.seconds >= 3600 ? 4 : value.seconds >= 1800 ? 3 : value.seconds >= 600 ? 2 : 1;
  const move = (event: KeyboardEvent<HTMLButtonElement>, index: number) => {
    const delta = { ArrowLeft: -7, ArrowRight: 7, ArrowUp: -1, ArrowDown: 1 }[event.key];
    if (delta === undefined) return;
    event.preventDefault();
    const next = index + delta;
    if (next < 0 || next >= dates.length || dates[next] > today) return;
    setSelected(dates[next]);
    event.currentTarget.parentElement?.querySelector<HTMLButtonElement>(`[data-day-index="${next}"]`)?.focus();
  };
  return <section className={embedded ? 'um-heatmap-embedded' : 'um-portal-card um-activity-card'} aria-label="学习热力图">
    <div className="um-course-section-heading"><span>{activeDays} 天</span><div className="um-segmented um-segmented-small" role="group" aria-label="热力图时间范围"><button type="button" aria-pressed={weeks === 26} onClick={() => setWeeks(26)}>半年</button><button type="button" aria-pressed={weeks === 52} onClick={() => setWeeks(52)}>一年</button></div></div>
    <p className="sr-only">每个方格代表一天，可用方向键移动，查看当天学习时长和完成课程。</p>
    <div className="um-heatmap-scroll" ref={scrollElement}>
      <div className="um-heatmap-layout" style={{ '--heat-weeks': weeks } as CSSProperties}>
        <div className="um-heatmap-weekdays" aria-hidden="true"><span>日</span><span>一</span><span>二</span><span>三</span><span>四</span><span>五</span><span>六</span></div>
        <div className="um-heatmap-months" aria-hidden="true">{Array.from({ length: weeks }, (_, index) => { const date = dates[index * 7]; return <span key={date}>{index === 0 || date.slice(5, 7) !== dates[(index - 1) * 7].slice(5, 7) ? `${Number(date.slice(5, 7))}月` : ''}</span>; })}</div>
        <div className="um-heatmap-grid" role="group" aria-label="每日学习热力图">{dates.map((date, index) => {
          const value = byDate.get(date);
          const label = `${date}：${learningDuration(value?.seconds || 0)}，完成 ${value?.completions || 0} 门课程`;
          return <button type="button" key={date} data-day-index={index} data-level={level(value)} disabled={date > today} aria-label={label} aria-pressed={date === selected} aria-describedby={`${chartId}-detail`} tabIndex={date === selected || (!dates.includes(selected) && date === today) ? 0 : -1} title={label} onClick={() => setSelected(date)} onFocus={() => setSelected(date)} onKeyDown={event => move(event, index)} />;
        })}</div>
      </div>
    </div>
    <div className="um-heatmap-footer"><p id={`${chartId}-detail`} aria-live="polite"><span>{selected}</span> · {learningDuration(selectedActivity.seconds)} · 完成 {selectedActivity.completions} 门</p><div className="um-heatmap-legend" aria-label="颜色越深代表观看时间越长"><span>少</span>{[0, 1, 2, 3, 4].map(value => <i key={value} data-level={value} aria-hidden="true" />)}<span>多</span></div></div>
  </section>;
}
