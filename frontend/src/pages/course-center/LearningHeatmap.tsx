import { useEffect, useId, useRef, useState, type KeyboardEvent, type CSSProperties } from 'react';
import { Portal as TooltipPortal } from '@radix-ui/react-tooltip';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';
import type { LearningDay } from './types';
import { dateOffset, learningDuration } from './learningDates';

interface DayActivity { seconds: number; completions: number; }

export function LearningHeatmap({ today, days }: { today: string; days: LearningDay[] }) {
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
  const byDate = new Map<string, DayActivity>();
  days.forEach(day => {
    const previous = byDate.get(day.date) || { seconds: 0, completions: 0 };
    byDate.set(day.date, { seconds: previous.seconds + day.watched_seconds, completions: previous.completions + day.completions });
  });
  const yearStart = dateOffset(today, -364);
  const weekday = (date: string) => (new Date(`${date}T12:00:00Z`).getUTCDay() + 6) % 7;
  const start = dateOffset(yearStart, -weekday(yearStart));
  const weeks = Math.ceil((weekday(yearStart) + 365) / 7);
  const dates = Array.from({ length: weeks * 7 }, (_, index) => dateOffset(start, index));
  const activeDays = dates.filter(date => date >= yearStart && date <= today && ((byDate.get(date)?.seconds || 0) > 0 || (byDate.get(date)?.completions || 0) > 0)).length;
  const summary = (date: string) => {
    const weekStart = dateOffset(date, -weekday(date));
    const from = mode === 'day' ? date : weekStart < yearStart ? yearStart : weekStart;
    const weekEnd = dateOffset(weekStart, 6);
    const to = mode === 'day' ? date : weekEnd > today ? today : weekEnd;
    let seconds = 0;
    let completions = 0;
    for (const [day, value] of byDate) {
      if (day >= from && day <= to) { seconds += value.seconds; completions += value.completions; }
    }
    return `${from}${to !== from ? ` 至 ${to}` : ''} · ${learningDuration(seconds)} · 完成 ${completions} 门`;
  };
  const level = (value?: DayActivity) => !value || (!value.seconds && !value.completions) ? 0 : value.seconds >= 3600 ? 4 : value.seconds >= 1800 ? 3 : value.seconds >= 600 ? 2 : 1;
  const move = (event: KeyboardEvent<HTMLButtonElement>, index: number) => {
    const delta = { ArrowLeft: -7, ArrowRight: 7, ArrowUp: -1, ArrowDown: 1 }[event.key];
    if (delta === undefined) return;
    event.preventDefault();
    const next = index + delta;
    if (next < 0 || next >= dates.length || dates[next] < yearStart || dates[next] > today) return;
    setSelected(dates[next]);
    event.currentTarget.parentElement?.querySelector<HTMLButtonElement>(`[data-day-index="${next}"]`)?.focus();
  };
  return <section className="um-portal-card um-activity-card" aria-label="学习活动">
    <div className="um-course-section-heading"><div><h2>学习活动</h2><p>近一年 · {activeDays} 天有听课记录</p></div><div className="um-segmented" role="group" aria-label="学习时长统计方式"><button type="button" aria-pressed={mode === 'day'} onClick={() => setMode('day')}>按天</button><button type="button" aria-pressed={mode === 'week'} onClick={() => setMode('week')}>按周</button></div></div>
    <p className="sr-only">每个方格代表一天，共 365 天。颜色表示当天听课时长。按周统计周一至周日的记录，边界周只统计图中日期。可以悬停、点击或用方向键查看。</p>
    <div className="um-heatmap-scroll" ref={scrollElement}>
      <div className="um-heatmap-layout" style={{ '--heat-weeks': weeks } as CSSProperties}>
        <div className="um-heatmap-weekdays" aria-hidden="true"><span>一</span><span>二</span><span>三</span><span>四</span><span>五</span><span>六</span><span>日</span></div>
        <div className="um-heatmap-months" aria-hidden="true">{Array.from({ length: weeks }, (_, index) => { const date = dates[index * 7]; return <span key={date}>{index === 0 || date.slice(5, 7) !== dates[(index - 1) * 7].slice(5, 7) ? `${Number(date.slice(5, 7))}月` : ''}</span>; })}</div>
        <TooltipProvider delayDuration={120}><div className="um-heatmap-grid" role="group" aria-label="全年每日学习热力图">{dates.map((date, index) => {
          if (date < yearStart || date > today) return <span key={date} aria-hidden="true" />;
          const label = summary(date);
          return <Tooltip key={date}><TooltipTrigger asChild><button type="button" data-day-index={index} data-level={level(byDate.get(date))} aria-label={label} aria-pressed={date === selected} aria-describedby={`${chartId}-detail`} tabIndex={date === selected ? 0 : -1} onPointerEnter={() => setSelected(date)} onClick={() => setSelected(date)} onFocus={() => setSelected(date)} onKeyDown={event => move(event, index)} /></TooltipTrigger><TooltipPortal><TooltipContent className="um-heatmap-tooltip">{label}</TooltipContent></TooltipPortal></Tooltip>;
        })}</div></TooltipProvider>
      </div>
    </div>
    <div className="um-heatmap-footer"><p id={`${chartId}-detail`} aria-live="polite">{summary(selected)}</p><div className="um-heatmap-legend" aria-label="颜色越深代表当天观看时间越长"><span>少</span>{[0, 1, 2, 3, 4].map(value => <i key={value} data-level={value} aria-hidden="true" />)}<span>多</span></div></div>
  </section>;
}
