import React from 'react';
import { Button } from '@/components/ui/button';
import { toast } from 'sonner';
import { useTranslation } from 'react-i18next';

interface ReportStats {
  total_attempted?: number;
  total_distinct?: number;
  correct_count?: number;
  wrong_count?: number;
  mastered_count?: number;
  accuracy?: number;
  study_streak?: number;
  checkin_streak?: number;
}

interface RadarEntry {
  subject: string;
  avg_score: number;
  kp_count: number;
}

interface Achievement {
  name: string;
  description: string;
  unlocked_at?: string;
}

interface ExamRecord {
  id: number;
  total_score: number;
  max_score: number;
  percentage: number;
  elo_change?: number;
  created_at: string;
}

export function StudentReportPreview({ payload }: { payload: Record<string, unknown> }) {
  const { t } = useTranslation('workbench');
  const stats = (payload.stats || {}) as ReportStats;
  const radar = (payload.radar || []) as RadarEntry[];
  const achievements = (payload.achievements || []) as Achievement[];
  const exams = (payload.exams || []) as ExamRecord[];
  const studentName = (payload.student_name as string) || '';
  const dateFrom = (payload.date_from as string) || '';
  const dateTo = (payload.date_to as string) || '';

  const handleExportPdf = () => {
    toast.info(t('pdfExportComingSoon'));
  };

  const handleSendToStudent = () => {
    toast.info(t('sendToStudentComingSoon'));
  };

  // Backend accuracy is already 0-100 scale
  const accuracyPct = stats.accuracy != null ? `${Number(stats.accuracy).toFixed(1)}%` : '-';
  // avg_score is 0-1 mastery score
  const masteryPct = (score: number) => `${(score * 100).toFixed(0)}%`;

  return (
    <div className="space-y-4 rounded-2xl border border-border bg-card p-5">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-sm font-bold">{studentName} {t('learningReport')}</h3>
          {dateFrom && (
            <p className="text-[10px] text-muted-foreground">
              {dateFrom.slice(0, 10)} ~ {dateTo.slice(0, 10)}
            </p>
          )}
        </div>
      </div>

      <div className="grid grid-cols-3 gap-2">
        <StatItem label={t('totalAttempts')} value={String(stats.total_attempted || 0)} />
        <StatItem label={t('accuracy')} value={accuracyPct} />
        <StatItem label={t('streakDays')} value={String(stats.study_streak || 0)} />
        <StatItem label={t('correct')} value={String(stats.correct_count || 0)} />
        <StatItem label={t('wrong')} value={String(stats.wrong_count || 0)} />
        <StatItem label={t('masteredKP')} value={String(stats.mastered_count || 0)} />
      </div>

      {radar.length > 0 && (
        <div className="space-y-1">
          <h4 className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">{t('subjectMastery')}</h4>
          <div className="space-y-1">
            {radar.slice(0, 5).map((r) => (
              <div key={r.subject} className="flex items-center justify-between text-xs">
                <span>{r.subject}</span>
                <div className="flex items-center gap-2">
                  <div className="w-24 h-1.5 bg-muted rounded-full overflow-hidden">
                    <div
                      className="h-full bg-primary rounded-full transition-all"
                      style={{ width: masteryPct(r.avg_score) }}
                    />
                  </div>
                  <span className="text-muted-foreground w-8 text-right">{masteryPct(r.avg_score)}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {achievements.length > 0 && (
        <div className="space-y-1">
          <h4 className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">{t('achievements')}</h4>
          <div className="flex flex-wrap gap-1">
            {achievements.map((a) => (
              <span key={a.name} className="text-[10px] bg-primary/10 text-primary px-2 py-0.5 rounded-full">
                {a.name}
              </span>
            ))}
          </div>
        </div>
      )}

      {exams.length > 0 && (
        <div className="space-y-1">
          <h4 className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">{t('recentExams')}</h4>
          <div className="space-y-0.5">
            {exams.slice(0, 5).map((e) => (
              <div key={e.id} className="flex items-center justify-between text-[11px]">
                <span className="truncate max-w-[140px]">{t('exam')} #{e.id}</span>
                <span className="text-muted-foreground">{e.percentage?.toFixed(0)}%</span>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="flex items-center gap-2 pt-2">
        <Button size="sm" variant="outline" className="rounded-xl text-xs" onClick={handleExportPdf}>
          {t('exportPdf')}
        </Button>
        <Button size="sm" className="rounded-xl text-xs" onClick={handleSendToStudent}>
          {t('sendToStudent')}
        </Button>
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
