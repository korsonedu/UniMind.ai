import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Dialog, DialogContent } from '@/components/ui/dialog';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Award, BrainCircuit, Calendar, Download, TrendingUp } from 'lucide-react';
import { toPng } from 'html-to-image';
import api from '@/lib/api';
import { useAuthStore } from '@/store/useAuthStore';

type TrendMetricKey = 'accuracy' | 'question_count' | 'focus_minutes' | 'lesson_minutes';

interface DailySeriesPoint {
  date: string;
  label: string;
  weekday: string;
  accuracy: number;
  question_count: number;
  focus_minutes: number;
  lesson_minutes: number;
}

interface WeeklyReportData {
  user_nickname: string;
  conversion_rate: number;
  permanent_count: number;
  elo_percentile: number;
  week_reviews: number;
  current_elo: number;
  report_date: string;
  week_label: string;
  weekly_accuracy: number;
  weekly_question_count: number;
  weekly_focus_minutes: number;
  weekly_lesson_minutes: number;
  daily_series: DailySeriesPoint[];
}

const TREND_METRICS: Array<{
  key: TrendMetricKey;
  label: string;
  unit: string;
  color: string;
  description: string;
}> = [
  {
    key: 'accuracy',
    label: '正确率',
    unit: '%',
    color: '#4f46e5',
    description: '按天统计的答题正确率（%）',
  },
  {
    key: 'question_count',
    label: '做题数',
    unit: '题',
    color: '#0284c7',
    description: '按天统计的做题数量（题）',
  },
  {
    key: 'focus_minutes',
    label: '专注时长',
    unit: '分钟',
    color: '#059669',
    description: '按天统计的专注时长（分钟）',
  },
  {
    key: 'lesson_minutes',
    label: '听课时长',
    unit: '分钟',
    color: '#d97706',
    description: '按天统计的听课时长（分钟）',
  },
];

const toNumber = (value: unknown) => {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
};

const formatMetricValue = (key: TrendMetricKey, value: number) => {
  if (key === 'accuracy') return `${value.toFixed(1)}%`;
  if (key === 'question_count') return `${value.toFixed(0)} 题`;
  return `${value % 1 === 0 ? value.toFixed(0) : value.toFixed(1)} 分钟`;
};

const toDailyLabel = (day: string) => {
  const normalized = day.toLowerCase();
  if (normalized.startsWith('mon')) return '周一';
  if (normalized.startsWith('tue')) return '周二';
  if (normalized.startsWith('wed')) return '周三';
  if (normalized.startsWith('thu')) return '周四';
  if (normalized.startsWith('fri')) return '周五';
  if (normalized.startsWith('sat')) return '周六';
  if (normalized.startsWith('sun')) return '周日';
  return day;
};

export const WeeklyReportDialog: React.FC = () => {
  const { user } = useAuthStore();
  const reportCaptureRef = useRef<HTMLDivElement | null>(null);
  const [report, setReport] = useState<WeeklyReportData | null>(null);
  const [isOpen, setIsOpen] = useState(false);
  const [activeMetric, setActiveMetric] = useState<TrendMetricKey>('accuracy');

  useEffect(() => {
    if (!user?.is_member) return;

    const handleManualOpen = () => {
      void fetchReport(true);
    };

    window.addEventListener('open-weekly-report', handleManualOpen);
    return () => {
      window.removeEventListener('open-weekly-report', handleManualOpen);
    };
  }, [user]);

  const fetchReport = async (manual = false) => {
    try {
      const res = await api.get('/users/me/weekly-report/');
      const nextReport = res.data as WeeklyReportData;
      const hasProgress =
        nextReport.week_reviews > 0 ||
        nextReport.permanent_count > 0 ||
        nextReport.weekly_question_count > 0 ||
        nextReport.weekly_focus_minutes > 0 ||
        nextReport.weekly_lesson_minutes > 0;

      if (manual || hasProgress) {
        setReport(nextReport);
        setIsOpen(true);
      }
    } catch {
      // Silent fail to avoid interrupting app usage.
    }
  };

  const handleClose = () => {
    setIsOpen(false);
  };

  const safeDailySeries = useMemo(() => {
    if (!report?.daily_series || report.daily_series.length === 0) {
      return [] as DailySeriesPoint[];
    }
    return report.daily_series.map((item) => ({
      ...item,
      accuracy: toNumber(item.accuracy),
      question_count: toNumber(item.question_count),
      focus_minutes: toNumber(item.focus_minutes),
      lesson_minutes: toNumber(item.lesson_minutes),
    }));
  }, [report]);

  const activeMetricConfig = useMemo(
    () => TREND_METRICS.find((item) => item.key === activeMetric) || TREND_METRICS[0],
    [activeMetric]
  );

  const metricSeries = useMemo(() => {
    return safeDailySeries.map((item) => toNumber(item[activeMetric]));
  }, [safeDailySeries, activeMetric]);

  const chart = useMemo(() => {
    const len = metricSeries.length;
    const graphHeight = 248;
    const top = 20;
    const right = 36;
    const bottom = 66;
    const left = 44;
    const graphWidth = 820;
    const innerWidth = graphWidth - left - right;
    const innerHeight = graphHeight - top - bottom;
    const maxPoint = Math.max(...metricSeries, 0);
    const maxY = Math.max(1, Math.ceil(maxPoint * 1.2));

    const pointAt = (index: number, value: number) => {
      const x = len <= 1 ? left + innerWidth / 2 : left + (index / (len - 1)) * innerWidth;
      const y = top + (1 - value / Math.max(maxY, 1)) * innerHeight;
      return { x, y };
    };

    const points = metricSeries.map((value, index) => pointAt(index, value));
    const linePath = points
      .map((p, index) => `${index === 0 ? 'M' : 'L'} ${p.x} ${p.y}`)
      .join(' ');
    const areaPath =
      points.length > 0
        ? `${linePath} L ${points[points.length - 1].x} ${graphHeight - bottom + 8} L ${points[0].x} ${graphHeight - bottom + 8} Z`
        : '';

    return {
      graphWidth,
      graphHeight,
      top,
      bottom,
      left,
      right,
      innerHeight,
      points,
      linePath,
      areaPath,
      maxY,
    };
  }, [metricSeries, activeMetric]);

  const latestMetricValue = metricSeries.length > 0 ? metricSeries[metricSeries.length - 1] : 0;
  const previousMetricValue = metricSeries.length > 1 ? metricSeries[metricSeries.length - 2] : 0;
  const metricDelta = latestMetricValue - previousMetricValue;

  const handleSaveImage = async () => {
    if (!reportCaptureRef.current || !report) return;
    try {
      const target = reportCaptureRef.current;
      const pngDataUrl = await toPng(target, {
        cacheBust: true,
        backgroundColor: '#ffffff',
        pixelRatio: 2,
      });
      const a = document.createElement('a');
      const fileSafeNickname = (report.user_nickname || 'user').replace(/[^\w\u4e00-\u9fa5-]/g, '_');
      a.href = pngDataUrl;
      a.download = `unimind_weekly_report_${fileSafeNickname}_${report.week_label}.png`;
      document.body.appendChild(a);
      a.click();
      a.remove();
    } catch (error) {
      console.error('save weekly report image failed:', error);
      window.alert('保存图片失败，请重试（可查看控制台错误）。');
    }
  };

  if (!report) return null;

  return (
    <Dialog
      open={isOpen}
      onOpenChange={(open) => {
        if (!open) handleClose();
      }}
    >
      <DialogContent className="h-[90vh] w-[96vw] sm:h-[88vh] sm:w-[94vw] max-w-[1140px] rounded-[1.8rem] border-none bg-white p-0 shadow-2xl overflow-hidden">
        <div ref={reportCaptureRef} className="flex h-full min-h-0 flex-col lg:grid lg:grid-cols-[320px_1fr]">
          <aside className="relative overflow-y-auto overflow-x-hidden border-b border-slate-200 bg-slate-950 p-6 text-white lg:border-b-0 lg:border-r lg:border-slate-800 lg:p-7">
            <div className="pointer-events-none absolute -right-16 -top-16 h-52 w-52 rounded-full bg-indigo-500/30 blur-3xl" />
            <div className="relative z-10 flex h-full flex-col justify-between gap-5">
              <div className="space-y-3">
                <div className="flex items-center gap-2">
                  <Badge className="border-none bg-indigo-500 px-2.5 py-1 text-[10px] font-black uppercase tracking-wider text-white">
                    Cognitive Assets
                  </Badge>
                  <span className="text-[10px] font-bold uppercase tracking-[0.18em] text-slate-300">
                    {report.week_label}
                  </span>
                </div>
                <h2 className="text-2xl font-black leading-tight tracking-tight">
                  {report.user_nickname} 的认知资产周报
                </h2>
                <p className="text-xs font-semibold text-slate-300">统计周期：{report.report_date}</p>
              </div>

              <div className="rounded-2xl border border-white/15 bg-white/10 p-4 backdrop-blur-sm">
                <div className="flex items-center gap-2 text-xs font-bold text-slate-200">
                  <Calendar className="h-3.5 w-3.5" />
                  一周总结
                </div>
                <p className="mt-2 text-[14px] leading-relaxed text-slate-100">
                  上周你将 <span className="font-black text-indigo-300">{report.permanent_count}</span> 道题从短期记忆转化为长期资产，
                  复习表现超过 <span className="font-black text-emerald-300">{report.elo_percentile}%</span> 学员。
                </p>
                <div className="mt-3 grid grid-cols-2 gap-2.5">
                  <div className="rounded-xl bg-white/10 px-2.5 py-2">
                    <p className="text-[10px] font-black uppercase tracking-widest text-slate-300">Current ELO</p>
                    <p className="mt-0.5 text-base font-black tabular-nums">{report.current_elo}</p>
                  </div>
                  <div className="rounded-xl bg-white/10 px-2.5 py-2">
                    <p className="text-[10px] font-black uppercase tracking-widest text-slate-300">复习次数</p>
                    <p className="mt-0.5 text-base font-black tabular-nums">{report.week_reviews}</p>
                  </div>
                </div>
              </div>
            </div>
          </aside>

          <section className="relative min-h-0 flex-1 overflow-y-auto bg-slate-50 px-4 py-4 sm:px-5 sm:py-5 lg:px-6 lg:py-6">
            <div className="flex min-h-full flex-col gap-4">
              <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm sm:p-5">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <p className="text-[10px] font-black uppercase tracking-[0.2em] text-slate-400">Daily Trend</p>
                    <h3 className="mt-1 text-lg font-black tracking-tight text-slate-900">学习变化曲线（按天）</h3>
                    <p className="mt-1 text-xs text-slate-500">{activeMetricConfig.description}</p>
                  </div>
                  <div className="flex items-center gap-2">
                    <Badge variant="outline" className="rounded-full border-slate-200 text-[10px] font-black text-slate-500">
                      {safeDailySeries.length || 0} 天数据
                    </Badge>
                    <Button
                      type="button"
                      variant="outline"
                      onClick={handleSaveImage}
                      className="h-8 rounded-full border-slate-300 px-3 text-[11px] font-black text-slate-700 hover:bg-slate-100"
                    >
                      <Download className="mr-1.5 h-3.5 w-3.5" />
                      保存为图片
                    </Button>
                  </div>
                </div>

                <div className="mt-3 flex flex-wrap gap-2">
                  {TREND_METRICS.map((metric) => (
                    <button
                      key={metric.key}
                      type="button"
                      onClick={() => setActiveMetric(metric.key)}
                      className={
                        activeMetric === metric.key
                          ? 'h-8 rounded-full px-3 text-[11px] font-black text-white shadow-sm'
                          : 'h-8 rounded-full bg-slate-100 px-3 text-[11px] font-black text-slate-500 transition-colors hover:bg-slate-200'
                      }
                      style={activeMetric === metric.key ? { backgroundColor: metric.color } : {}}
                    >
                      {metric.label}
                    </button>
                  ))}
                </div>

                <div className="mt-4 rounded-2xl border border-slate-200 bg-gradient-to-b from-slate-50 to-white p-3">
                  <div className="pb-1">
                    <svg
                      viewBox={`0 0 ${chart.graphWidth} ${chart.graphHeight}`}
                      className="h-[248px] w-full"
                    >
                      <defs>
                        <linearGradient id="weekly-report-area" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="0%" stopColor={activeMetricConfig.color} stopOpacity="0.24" />
                          <stop offset="100%" stopColor={activeMetricConfig.color} stopOpacity="0.02" />
                        </linearGradient>
                      </defs>

                      {[0, 0.25, 0.5, 0.75, 1].map((ratio) => {
                        const y = chart.top + chart.innerHeight * ratio;
                        return (
                          <line
                            key={ratio}
                            x1={chart.left}
                            x2={chart.graphWidth - chart.right}
                            y1={y}
                            y2={y}
                            stroke="#dbe3ef"
                            strokeDasharray="4 6"
                            strokeWidth="1"
                          />
                        );
                      })}

                      {chart.areaPath ? <path d={chart.areaPath} fill="url(#weekly-report-area)" /> : null}
                      {chart.linePath ? (
                        <path
                          d={chart.linePath}
                          fill="none"
                          stroke={activeMetricConfig.color}
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          strokeWidth="3"
                        />
                      ) : null}

                      {chart.points.map((point, idx) => (
                        <g key={`${safeDailySeries[idx]?.date || idx}`}>
                          <circle cx={point.x} cy={point.y} r="4.5" fill={activeMetricConfig.color} />
                          <circle cx={point.x} cy={point.y} r="8" fill={activeMetricConfig.color} opacity="0.16" />
                          <text
                            x={point.x}
                            y={chart.graphHeight - chart.bottom + 23}
                            textAnchor="middle"
                            className="fill-slate-500 text-[11px] font-semibold"
                          >
                            {safeDailySeries[idx]?.label || '--'}
                          </text>
                          <text
                            x={point.x}
                            y={chart.graphHeight - chart.bottom + 39}
                            textAnchor="middle"
                            className="fill-slate-400 text-[10px]"
                          >
                            {toDailyLabel(safeDailySeries[idx]?.weekday || '')}
                          </text>
                        </g>
                      ))}

                      <text
                        x={chart.left}
                        y={18}
                        textAnchor="start"
                        className="fill-slate-400 text-[10px] font-semibold"
                      >
                        上限 {chart.maxY} {activeMetricConfig.unit}
                      </text>
                    </svg>
                  </div>
                </div>

                <div className="mt-3 flex flex-wrap items-center justify-between gap-2 text-xs">
                  <div className="flex items-center gap-2 text-slate-500">
                    <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: activeMetricConfig.color }} />
                    当前曲线：{activeMetricConfig.label}
                  </div>
                  <p className={`font-bold ${metricDelta >= 0 ? 'text-emerald-600' : 'text-rose-600'}`}>
                    较前一天 {metricDelta >= 0 ? '+' : ''}{formatMetricValue(activeMetric, Math.abs(metricDelta))}
                  </p>
                </div>
              </div>

              <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
                <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
                  <div className="flex h-8 w-8 items-center justify-center rounded-xl bg-indigo-50 text-indigo-600">
                    <TrendingUp className="h-4 w-4" />
                  </div>
                  <p className="mt-2 text-[10px] font-black uppercase tracking-widest text-slate-400">正确率</p>
                  <p className="mt-1 text-xl font-black tabular-nums text-slate-900">{report.weekly_accuracy.toFixed(1)}%</p>
                </div>

                <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
                  <div className="flex h-8 w-8 items-center justify-center rounded-xl bg-sky-50 text-sky-600">
                    <BrainCircuit className="h-4 w-4" />
                  </div>
                  <p className="mt-2 text-[10px] font-black uppercase tracking-widest text-slate-400">做题数</p>
                  <p className="mt-1 text-xl font-black tabular-nums text-slate-900">{report.weekly_question_count}</p>
                </div>

                <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
                  <div className="flex h-8 w-8 items-center justify-center rounded-xl bg-emerald-50 text-emerald-600">
                    <Calendar className="h-4 w-4" />
                  </div>
                  <p className="mt-2 text-[10px] font-black uppercase tracking-widest text-slate-400">专注时长</p>
                  <p className="mt-1 text-xl font-black tabular-nums text-slate-900">
                    {formatMetricValue('focus_minutes', report.weekly_focus_minutes)}
                  </p>
                </div>

                <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
                  <div className="flex h-8 w-8 items-center justify-center rounded-xl bg-amber-50 text-amber-600">
                    <Award className="h-4 w-4" />
                  </div>
                  <p className="mt-2 text-[10px] font-black uppercase tracking-widest text-slate-400">听课时长</p>
                  <p className="mt-1 text-xl font-black tabular-nums text-slate-900">
                    {formatMetricValue('lesson_minutes', report.weekly_lesson_minutes)}
                  </p>
                </div>
              </div>

            </div>
          </section>
        </div>
      </DialogContent>
    </Dialog>
  );
};
