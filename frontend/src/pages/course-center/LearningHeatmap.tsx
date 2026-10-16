import { memo, useCallback, useEffect, useId, useMemo, useRef, useState, type CSSProperties, type KeyboardEvent } from 'react';
import { CaretRight } from '@phosphor-icons/react';
import { Collapse } from '@/components/ui/collapse';
import { courseGroups, type Course, type LearningDay } from './types';
import { dateOffset, learningDuration } from './learningDates';

const activityLevel = (seconds: number) => seconds <= 0 ? 0 : seconds >= 3600 ? 4 : seconds >= 1800 ? 3 : seconds >= 600 ? 2 : 1;

function ActivityLegend() {
  return <div className="um-activity-legend" aria-label="灰色代表无观看时长，绿色越深代表时长越长"><span>少</span>{[0, 1, 2, 3, 4].map(level => <i key={level} data-level={level} aria-hidden="true" />)}<span>多</span></div>;
}

interface DayActivity { seconds: number; completions: number; }
interface DayView { day: string; week: string; level: number; }

const weekday = (date: string) => (new Date(`${date}T12:00:00Z`).getUTCDay() + 6) % 7;

const ActivityCell = memo(function ActivityCell({ date, index, label, level, selected, tabbable, detailId, onSelect, onMove }: {
  date: string; index: number; label: string; level: number; selected: boolean; tabbable: boolean; detailId: string;
  onSelect: (date: string) => void; onMove: (event: KeyboardEvent<HTMLButtonElement>, index: number) => void;
}) {
  return <button type="button" data-day-index={index} data-level={level} title={label} aria-label={label} aria-pressed={selected} aria-describedby={detailId} tabIndex={tabbable ? 0 : -1} onPointerEnter={() => onSelect(date)} onClick={() => onSelect(date)} onFocus={() => onSelect(date)} onKeyDown={event => onMove(event, index)} />;
});

const CalendarHeatmap = memo(function CalendarHeatmap({ today, days }: { today: string; days: LearningDay[] }) {
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
        const level = activityLevel(value?.seconds || 0);
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
  const move = useCallback((event: KeyboardEvent<HTMLButtonElement>, index: number) => {
    const delta = { ArrowLeft: -7, ArrowRight: 7, ArrowUp: -1, ArrowDown: 1 }[event.key];
    if (delta === undefined) return;
    event.preventDefault();
    const next = index + delta;
    if (next < 0 || next >= dates.length || dates[next] < yearStart || dates[next] > today) return;
    setSelected(dates[next]);
    event.currentTarget.parentElement?.querySelector<HTMLButtonElement>(`[data-day-index="${next}"]`)?.focus();
  }, [dates, today, yearStart]);
  return <div className="um-activity-overall" style={{ '--heat-weeks': weeks } as CSSProperties}>
    <div className="um-course-section-heading"><div><h2>学习活动</h2><p>近一年 · {activeDays} 天有听课记录</p></div><div className="um-segmented" role="group" aria-label="学习活动统计范围"><button type="button" aria-pressed={mode === 'day'} onClick={() => setMode('day')}>按天</button><button type="button" aria-pressed={mode === 'week'} onClick={() => setMode('week')}>按周</button></div></div>
    <p className="sr-only">每个方格代表一天，共 365 天。颜色表示当天听课时长。按周统计周一至周日的记录，边界周只统计图中日期。可以悬停、点击或用方向键查看。</p>
    <div className="um-heatmap-scroll" ref={scrollElement}>
      <div className="um-heatmap-layout">
        <div className="um-heatmap-weekdays" aria-hidden="true"><span>一</span><span>二</span><span>三</span><span>四</span><span>五</span><span>六</span><span>日</span></div>
        <div className="um-heatmap-months" aria-hidden="true">{Array.from({ length: weeks }, (_, index) => { const date = dates[index * 7]; return <span key={date}>{index === 0 || date.slice(5, 7) !== dates[(index - 1) * 7].slice(5, 7) ? `${Number(date.slice(5, 7))}月` : ''}</span>; })}</div>
        <div className="um-heatmap-grid" role="group" aria-label="全年每日学习热力图">{dates.map((date, index) => {
          const value = summaries.get(date);
          if (!value) return <span key={date} aria-hidden="true" />;
          const isSelected = mode === 'week' ? Math.floor(index / 7) === selectedWeek : date === selectedDate;
          return <ActivityCell key={date} date={date} index={index} label={value[mode]} level={value.level} selected={isSelected} tabbable={date === selectedDate} detailId={`${chartId}-detail`} onSelect={setSelected} onMove={move} />;
        })}</div>
      </div>
    </div>
    <div className="um-heatmap-footer"><p id={`${chartId}-detail`} aria-live="polite">{summaries.get(selectedDate)?.[mode]}</p><ActivityLegend /></div>
  </div>;
});

interface ActivityRow {
  subject: string;
  name: string;
  values: { date: string; seconds: number }[];
  seconds: number;
  activeDays: number;
}

function moveDay(event: KeyboardEvent<HTMLButtonElement>, index: number, count: number) {
  const next = event.key === 'ArrowLeft' ? index - 1 : event.key === 'ArrowRight' ? index + 1 : event.key === 'Home' ? 0 : event.key === 'End' ? count - 1 : -1;
  if (next < 0 || next >= count) return;
  event.preventDefault();
  event.currentTarget.parentElement?.querySelector<HTMLButtonElement>(`[data-day-index="${next}"]`)?.focus();
}

const ActivityStrip = memo(function ActivityStrip({ row, selectedDate, detailId, onSelect }: {
  row: ActivityRow; selectedDate: string | null; detailId: string;
  onSelect: (subject: string, date: string) => void;
}) {
  return <div className="um-activity-strip" role="group" aria-label={`${row.name}每日观看时长`}>
    {row.values.map(({ date, seconds }, index) => <button
      type="button" key={date} data-day-index={index} data-level={activityLevel(seconds)}
      aria-label={`${row.name} · ${date} · ${learningDuration(seconds)}`}
      title={`${date} · ${learningDuration(seconds)}`} aria-describedby={detailId}
      aria-pressed={date === selectedDate} tabIndex={date === (selectedDate || row.values[row.values.length - 1].date) ? 0 : -1}
      onPointerEnter={() => onSelect(row.subject, date)} onFocus={() => onSelect(row.subject, date)}
      onClick={() => onSelect(row.subject, date)} onKeyDown={event => moveDay(event, index, row.values.length)}
    />)}
  </div>;
});

export const LearningHeatmap = memo(function LearningHeatmap({ today, days, courses }: { today: string; days: LearningDay[]; courses: Course[] }) {
  const [expanded, setExpanded] = useState(false);
  const [selected, setSelected] = useState({ subject: '', date: today });
  const chartId = useId();
  const select = useCallback((subject: string, date: string) => setSelected(previous => previous.subject === subject && previous.date === date ? previous : { subject, date }), []);
  const model = useMemo(() => {
    // Clamp the same day three calendar months ago before taking the inclusive range.
    const end = new Date(`${today}T12:00:00Z`);
    const startMonth = new Date(Date.UTC(end.getUTCFullYear(), end.getUTCMonth() - 3, 1, 12));
    const monthEnd = new Date(Date.UTC(startMonth.getUTCFullYear(), startMonth.getUTCMonth() + 1, 0, 12)).getUTCDate();
    startMonth.setUTCDate(Math.min(end.getUTCDate(), monthEnd));
    const start = dateOffset(startMonth.toISOString().slice(0, 10), 1);
    const count = Math.round((end.getTime() - new Date(`${start}T12:00:00Z`).getTime()) / 86400000) + 1;
    const dates = Array.from({ length: count }, (_, index) => dateOffset(start, index));
    const subjects = new Map(courses.map(course => [course.id, courseGroups(course, 'subject')[0]]));
    const totals = new Map<string, number>();
    const bySubject = new Map<string, Map<string, number>>();
    subjects.forEach(subject => { if (!bySubject.has(subject)) bySubject.set(subject, new Map()); });
    days.forEach(day => {
      const subject = subjects.get(day.course);
      if (!subject || day.date < start || day.date > today) return;
      const values = bySubject.get(subject)!;
      values.set(day.date, (values.get(day.date) || 0) + day.watched_seconds);
      totals.set(day.date, (totals.get(day.date) || 0) + day.watched_seconds);
    });
    const row = (subject: string, name: string, values: Map<string, number>): ActivityRow => ({
      subject, name, values: dates.map(date => ({ date, seconds: values.get(date) || 0 })),
      seconds: [...values.values()].reduce((sum, seconds) => sum + seconds, 0),
      activeDays: [...values.values()].filter(seconds => seconds > 0).length,
    });
    return {
      start, count, heatWeeks: Math.ceil((weekday(dateOffset(today, -364)) + 365) / 7), total: row('', '全部学科', totals),
      subjects: [...bySubject].sort(([a], [b]) => a === '待归类学科' ? 1 : b === '待归类学科' ? -1 : a.localeCompare(b, 'zh-CN')).map(([name, values]) => row(name, name, values)),
    };
  }, [today, days, courses]);
  const rows = model.subjects;
  const selectedRow = rows.find(row => row.subject === selected.subject) || rows[0] || model.total;
  const selectedValue = selectedRow.values.find(value => value.date === selected.date) || selectedRow.values[model.count - 1];
  return <section className="um-portal-card um-activity-card" aria-label="学习活动" style={{ '--heat-weeks': model.heatWeeks } as CSSProperties}>
    <CalendarHeatmap today={today} days={days} />
    <button type="button" className="um-activity-expand" aria-expanded={expanded} aria-controls={`${chartId}-subjects`} onClick={() => setExpanded(value => !value)}><CaretRight size={14} className="um-disclosure-chevron" /><span>{expanded ? '收起分学科学习情况' : '查看分学科学习情况'}</span></button>
    <Collapse open={expanded} id={`${chartId}-subjects`}>
    <div className="um-activity-subjects" style={{ '--activity-days': model.count } as CSSProperties}>
    <div className="um-activity-rows">
      {rows.map(row => <div className="um-activity-row" key={row.subject}>
        <div className="um-activity-row-heading">
          <span className="um-activity-subject">{row.name}</span>
          <span className="um-activity-summary">{row.activeDays} 天 · {learningDuration(row.seconds)}</span>
        </div>
        <ActivityStrip row={row} selectedDate={row === selectedRow ? selectedValue.date : null} detailId={`${chartId}-detail`} onSelect={select} />
      </div>)}
      <div className="um-activity-dates" aria-label="统计日期范围"><time dateTime={model.start}>{model.start}</time><time dateTime={today}>{today}</time></div>
    </div>
    <div className="um-heatmap-footer"><p id={`${chartId}-detail`} aria-live="polite">{selectedRow.name} · {selectedValue.date} · {learningDuration(selectedValue.seconds)}</p><ActivityLegend /></div>
    </div>
    </Collapse>
  </section>;
});
