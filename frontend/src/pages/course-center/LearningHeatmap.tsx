import { memo, useCallback, useEffect, useId, useMemo, useRef, useState, type KeyboardEvent, type CSSProperties } from 'react';
import type { LearningDay } from './types';
import { dateOffset, learningDuration } from './learningDates';

interface DayActivity { seconds: number; completions: number; }
interface DayView { day: string; week: string; level: number; }

const weekday = (date: string) => (new Date(`${date}T12:00:00Z`).getUTCDay() + 6) % 7;
const activityLevel = (value?: DayActivity) => !value || (!value.seconds && !value.completions) ? 0 : value.seconds >= 3600 ? 4 : value.seconds >= 1800 ? 3 : value.seconds >= 600 ? 2 : 1;

const ActivityCell = memo(function ActivityCell({ date, index, label, level, selected, tabbable, detailId, onSelect, onMove }: {
  date: string; index: number; label: string; level: number; selected: boolean; tabbable: boolean; detailId: string;
  onSelect: (date: string) => void; onMove: (event: KeyboardEvent<HTMLButtonElement>, index: number) => void;
}) {
  return <button type="button" data-day-index={index} data-level={level} title={label} aria-label={label} aria-pressed={selected} aria-describedby={detailId} tabIndex={tabbable ? 0 : -1} onPointerEnter={() => onSelect(date)} onClick={() => onSelect(date)} onFocus={() => onSelect(date)} onKeyDown={event => onMove(event, index)} />;
});

export const LearningHeatmap = memo(function LearningHeatmap({ today, days }: { today: string; days: LearningDay[] }) {
  const [mode, setMode] = useState<'day' | 'week'>('day');
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
  }, [today]);
  const model = useMemo(() => {
    const byDate = new Map<string, DayActivity>();
    days.forEach(day => {
      const previous = byDate.get(day.date) || { seconds: 0, completions: 0 };
      byDate.set(day.date, { seconds: previous.seconds + day.watched_seconds, completions: previous.completions + day.completions });
    });
    const yearStart = dateOffset(today, -364);
    const start = dateOffset(yearStart, -weekday(yearStart));
    const weeks = Math.ceil((weekday(yearStart) + 365) / 7);
    const dates = Array.from({ length: weeks * 7 }, (_, index) => dateOffset(start, index));
    const summaries = new Map<string, DayView>();
    let activeDays = 0;
    // Aggregate each week once; pointer movement only selects a cached summary.
    for (let index = 0; index < weeks; index++) {
      const weekDates = dates.slice(index * 7, index * 7 + 7).filter(date => date >= yearStart && date <= today);
      const total = weekDates.reduce((sum, date) => {
        const value = byDate.get(date);
        return { seconds: sum.seconds + (value?.seconds || 0), completions: sum.completions + (value?.completions || 0) };
      }, { seconds: 0, completions: 0 });
      const week = `${weekDates[0]} 至 ${weekDates[weekDates.length - 1]} · ${learningDuration(total.seconds)} · 完成 ${total.completions} 门`;
      weekDates.forEach(date => {
        const value = byDate.get(date);
        const level = activityLevel(value);
        if (level) activeDays++;
        summaries.set(date, { day: `${date} · ${learningDuration(value?.seconds || 0)} · 完成 ${value?.completions || 0} 门`, week, level });
      });
    }
    return { dates, weeks, yearStart, summaries, activeDays };
  }, [today, days]);
  const { dates, weeks, yearStart, summaries, activeDays } = model;
  const selectedDate = summaries.has(selected) ? selected : today;
  const selectedIndex = dates.indexOf(selectedDate);
  const selectedWeek = Math.floor(selectedIndex / 7);
  const first = mode === 'day' ? selectedIndex : Math.max(selectedWeek * 7, dates.indexOf(yearStart));
  const last = mode === 'day' ? selectedIndex : Math.min(selectedWeek * 7 + 6, dates.indexOf(today));
  const move = useCallback((event: KeyboardEvent<HTMLButtonElement>, index: number) => {
    const delta = { ArrowLeft: -7, ArrowRight: 7, ArrowUp: -1, ArrowDown: 1 }[event.key];
    if (delta === undefined) return;
    event.preventDefault();
    const next = index + delta;
    if (next < 0 || next >= dates.length || dates[next] < yearStart || dates[next] > today) return;
    setSelected(dates[next]);
    event.currentTarget.parentElement?.querySelector<HTMLButtonElement>(`[data-day-index="${next}"]`)?.focus();
  }, [dates, today, yearStart]);
  return <section className="um-portal-card um-activity-card" aria-label="学习活动">
    <div className="um-course-section-heading"><div><h2>学习活动</h2><p>近一年 · {activeDays} 天有听课记录</p></div><div className="um-segmented" role="group" aria-label="学习活动统计范围"><button type="button" aria-pressed={mode === 'day'} onClick={() => setMode('day')}>按天</button><button type="button" aria-pressed={mode === 'week'} onClick={() => setMode('week')}>按周</button></div></div>
    <p className="sr-only">每个方格代表一天，共 365 天。颜色表示当天听课时长。按周统计周一至周日的记录，边界周只统计图中日期。可以悬停、点击或用方向键查看。</p>
    <div className="um-heatmap-scroll" ref={scrollElement}>
      <div className="um-heatmap-layout" style={{ '--heat-weeks': weeks } as CSSProperties}>
        <div className="um-heatmap-weekdays" aria-hidden="true"><span>一</span><span>二</span><span>三</span><span>四</span><span>五</span><span>六</span><span>日</span></div>
        <div className="um-heatmap-months" aria-hidden="true">{Array.from({ length: weeks }, (_, index) => { const date = dates[index * 7]; return <span key={date}>{index === 0 || date.slice(5, 7) !== dates[(index - 1) * 7].slice(5, 7) ? `${Number(date.slice(5, 7))}月` : ''}</span>; })}</div>
        <div className="um-heatmap-grid" role="group" aria-label="全年每日学习热力图">{dates.map((date, index) => {
          const value = summaries.get(date);
          if (!value) return <span key={date} aria-hidden="true" />;
          const isSelected = mode === 'week' ? Math.floor(index / 7) === selectedWeek : date === selectedDate;
          return <ActivityCell key={date} date={date} index={index} label={value[mode]} level={value.level} selected={isSelected} tabbable={date === selectedDate} detailId={`${chartId}-detail`} onSelect={setSelected} onMove={move} />;
        })}<span className="um-heatmap-selection" aria-hidden="true" style={{ transform: `translate3d(${selectedWeek * 18}px, ${(first % 7) * 18}px, 0)`, height: `${(last - first + 1) * 18 - 4}px` }} /></div>
      </div>
    </div>
    <div className="um-heatmap-footer"><p id={`${chartId}-detail`} aria-live="polite">{summaries.get(selectedDate)?.[mode]}</p><div className="um-heatmap-legend" aria-label="颜色越深代表当天观看时间越长"><span>少</span>{[0, 1, 2, 3, 4].map(value => <i key={value} data-level={value} aria-hidden="true" />)}<span>多</span></div></div>
  </section>;
});
