import { t, useLocale } from '@/i18n';
import React from 'react';
import { Button } from '@/components/ui/button';
import { toast } from 'sonner';

interface ReportStats {
  total_attempted?: number;
  total_distinct?: number;
  correct_count?: number;
  wrong_count?: number;
  mastered_count?: number;
  accuracy?: number;
  last_accuracy?: number | null;
  lifetime_accuracy?: number | null;
  attempted_questions?: number;
  has_attempts?: boolean;
  diagnostic_mastered_count?: number;
  diagnostic_kp_count?: number;
  study_streak?: number;
  checkin_streak?: number;
}

interface RadarEntry {
  subject: string;
  avg_mastery?: number;
  avg_score?: number;
  kp_count: number;
}

interface ExamRecord {
  id: number;
  total_score: number;
  max_score: number;
  percentage: number;
  created_at: string;
}

export function StudentReportPreview({ payload }: { payload: Record<string, unknown> }) {
  useLocale();
  const stats = (payload.stats || {}) as ReportStats;
  const radar = (payload.radar || []) as RadarEntry[];
  const exams = (payload.exams || []) as ExamRecord[];
  const studentName = (payload.student_name as string) || '';
  const dateFrom = (payload.date_from as string) || '';
  const dateTo = (payload.date_to as string) || '';

  const handleExportPdf = () => {
    toast.info(t('PDF 导出即将上线'));
  };

  const handleSendToStudent = () => {
    toast.info(t('发送给学生功能即将上线'));
  };

  // Backend accuracy is already 0-100 scale
  const accuracyValue = stats.has_attempts === false
    ? null
    : (stats.last_accuracy ?? stats.accuracy);
  const accuracyPct = accuracyValue != null ? `${Number(accuracyValue).toFixed(1)}%` : '-';
  // Backend avg_mastery is 0-100 scale; avg_score fallback is 0-1
  const masteryValue = (entry: RadarEntry) => (
    entry.avg_mastery ?? (entry.avg_score != null ? entry.avg_score * 100 : 0)
  );

  return (
    <div className="um-visual-report space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-sm font-bold">{t('{0} 的学习报告', { 0: studentName })}</h3>
          {dateFrom && (
            <p className="text-[10px] text-muted-foreground">
              {dateFrom.slice(0, 10)} ~ {dateTo.slice(0, 10)}
            </p>
          )}
        </div>
      </div>

      <div className="grid grid-cols-3 gap-2">
        <StatItem label={t('累计作答')} value={String(stats.total_attempted || 0)} />
        <StatItem label={t('最近正确率')} value={accuracyPct} />
        <StatItem label={t('连续天数')} value={String(stats.study_streak || 0)} />
        <StatItem label={t('最近答对')} value={String(stats.correct_count || 0)} />
        <StatItem label={t('曾答错')} value={String(stats.wrong_count || 0)} />
        <StatItem
          label={t('诊断掌握知识点')}
          value={`${stats.diagnostic_mastered_count ?? 0}/${stats.diagnostic_kp_count ?? 0}`}
        />
      </div>

      {radar.length > 0 && (
        <div className="space-y-1">
          <h4 className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">{t('科目掌握度')}</h4>
          <div className="space-y-1">
            {radar.slice(0, 5).map((r) => (
              <div key={r.subject} className="flex items-center justify-between text-xs">
                <span>{r.subject}</span>
                <div className="flex items-center gap-2">
                  <div className="w-24 h-1.5 bg-muted rounded-full overflow-hidden">
                    <div
                      className="h-full bg-primary rounded-full transition-all"
                      style={{ width: `${masteryValue(r).toFixed(0)}%` }}
                    />
                  </div>
                  <span className="text-muted-foreground w-8 text-right">{masteryValue(r).toFixed(0)}%</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {exams.length > 0 && (
        <div className="space-y-1">
          <h4 className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">{t('最近考试')}</h4>
          <div className="space-y-0.5">
            {exams.slice(0, 5).map((e) => (
              <div key={e.id} className="flex items-center justify-between text-[11px]">
                <span className="truncate max-w-[140px]">{t('考试 #')}{e.id}</span>
                <span className="text-muted-foreground">{e.percentage?.toFixed(0)}%</span>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="flex items-center gap-2 pt-2">
        <Button size="sm" variant="outline" className="rounded-xl text-xs" onClick={handleExportPdf}>
          {t('导出 PDF')}</Button>
        <Button size="sm" className="rounded-xl text-xs" onClick={handleSendToStudent}>
          {t('发送给学生')}</Button>
      </div>
    </div>
  );
}

function StatItem({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-border/50 bg-muted/30 p-2 text-center">
      <p className="text-[10px] text-muted-foreground">{label}</p>
      <p className="text-sm font-bold tabular-nums">{value}</p>
    </div>
  );
}
