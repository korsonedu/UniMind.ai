import React, { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { toast } from 'sonner';
import api from '@/lib/api';
import { formatApiErrorToast } from '@/lib/apiError';
import type { SubmissionItem } from './types';

interface SubmissionPanelProps {
  examId: number;
}

export const SubmissionPanel: React.FC<SubmissionPanelProps> = ({ examId }) => {
  const [subs, setSubs] = useState<SubmissionItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [scores, setScores] = useState<Record<number, string>>({});
  const [feedbacks, setFeedbacks] = useState<Record<number, string>>({});
  const [gradedFiles, setGradedFiles] = useState<Record<number, File | null>>({});
  const [savingIds, setSavingIds] = useState<Set<number>>(new Set());
  const [gradingId, setGradingId] = useState<number | null>(null);
  const { t, i18n } = useTranslation('pdfMockExam');

  useEffect(() => {
    setLoading(true);
    api.get(`/quizzes/teacher-exams/${examId}/submissions/`)
      .then((res) => {
        const list = (res.data?.results || []) as SubmissionItem[];
        setSubs(list);
        const sm: Record<number, string> = {};
        const fm: Record<number, string> = {};
        for (const s of list) {
          sm[s.id] = s.score !== null ? String(s.score) : '';
          fm[s.id] = s.feedback || '';
        }
        setScores(sm);
        setFeedbacks(fm);
      })
      .catch(() => toast.error(t('toast.loadSubmissionsFailed')))
      .finally(() => setLoading(false));
  }, [examId]);

  const saveGrade = async (subId: number) => {
    setSavingIds((prev) => new Set(prev).add(subId));
    try {
      const fd = new FormData();
      fd.append('score', scores[subId] || '');
      fd.append('feedback', feedbacks[subId] || '');
      const file = gradedFiles[subId];
      if (file) fd.append('graded_pdf', file);
      await api.post(`/quizzes/teacher-exams/submissions/${subId}/grade/`, fd);
      toast.success(t('toast.scoreSaved'));
      setGradingId(null);
      const res = await api.get(`/quizzes/teacher-exams/${examId}/submissions/`);
      setSubs((res.data?.results || []) as SubmissionItem[]);
    } catch (e) {
      toast.error(formatApiErrorToast(e, t('toast.saveFailed')));
    } finally {
      setSavingIds((prev) => {
        const next = new Set(prev);
        next.delete(subId);
        return next;
      });
    }
  };

  if (loading) {
    return <p className="text-sm text-muted-foreground text-center py-4">{t('submissionsDialog.loading')}</p>;
  }

  if (subs.length === 0) {
    return <p className="text-sm text-muted-foreground text-center py-4">{t('submissionsDialog.noSubmissions')}</p>;
  }

  return (
    <div className="space-y-2 mt-3">
      <p className="text-xs font-bold uppercase tracking-widest text-muted-foreground">
        {t('submissionsDialog.title')} ({subs.length})
      </p>
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-border text-left">
              <th className="font-medium text-muted-foreground py-2 pr-2">{t('submissionsDialog.studentName')}</th>
              <th className="font-medium text-muted-foreground py-2 pr-2">{t('submissionsDialog.submittedOn')}</th>
              <th className="font-medium text-muted-foreground py-2 pr-2">{t('submissionsDialog.status')}</th>
              <th className="font-medium text-muted-foreground py-2 pr-2">{t('submissionsDialog.score')}</th>
              <th className="font-medium text-muted-foreground py-2">{t('submissionsDialog.actions')}</th>
            </tr>
          </thead>
          <tbody>
            {subs.map((s) => {
              const status: 'not_submitted' | 'submitted' | 'graded' =
                s.graded_pdf_url || s.score != null ? 'graded' : s.answer_pdf_url ? 'submitted' : 'not_submitted';

              return (
                <React.Fragment key={s.id}>
                  <tr className="border-b border-border/50">
                    <td className="py-2 pr-2">
                      <p className="font-medium">{s.student_name}</p>
                      <p className="text-[10px] text-muted-foreground/60">{s.student_email}</p>
                    </td>
                    <td className="py-2 pr-2 text-muted-foreground">
                      {new Date(s.created_at).toLocaleString(i18n.language?.startsWith('zh') ? 'zh-CN' : 'en-US')}
                    </td>
                    <td className="py-2 pr-2">
                      <Badge variant="secondary" className={`rounded text-[10px] ${
                        status === 'graded' ? 'bg-green-50 text-green-700 border-green-200' :
                        status === 'submitted' ? 'bg-amber-50 text-amber-700 border-amber-200' :
                        'bg-gray-50 text-gray-500 border-gray-200'
                      }`}>
                        {status === 'graded' ? t('submissionsDialog.graded') :
                         status === 'submitted' ? t('submissionsDialog.submitted') :
                         t('submissionsDialog.notSubmitted')}
                      </Badge>
                    </td>
                    <td className="py-2 pr-2 font-mono font-bold">
                      {s.score != null ? s.score : '—'}
                    </td>
                    <td className="py-2">
                      <div className="flex items-center gap-1">
                        {s.answer_pdf_url && (
                          <Button size="sm" variant="outline" className="h-7 text-[10px] rounded" onClick={() => window.open(s.answer_pdf_url, '_blank', 'noopener,noreferrer')}>
                            {t('submissionsDialog.studentAnswer')}
                          </Button>
                        )}
                        {s.graded_pdf_url && (
                          <Button size="sm" variant="outline" className="h-7 text-[10px] rounded text-green-700 border-green-300" onClick={() => window.open(s.graded_pdf_url, '_blank', 'noopener,noreferrer')}>
                            {t('submissionsDialog.gradedPdf')}
                          </Button>
                        )}
                        {status !== 'graded' && (
                          <Button size="sm" variant="ghost" className="h-7 text-[10px] rounded" onClick={() => setGradingId(gradingId === s.id ? null : s.id)}>
                            {t('submissionsDialog.pendingGrading')}
                          </Button>
                        )}
                      </div>
                    </td>
                  </tr>
                  {gradingId === s.id && (
                    <tr key={`grade-${s.id}`}>
                      <td colSpan={5} className="py-3 pl-4 border-b border-border/50 bg-muted/30">
                        <div className="flex items-end gap-3 flex-wrap">
                          <div className="space-y-1">
                            <label className="text-[10px] font-medium text-muted-foreground">{t('submissionsDialog.score')}</label>
                            <Input
                              type="number"
                              className="h-8 w-20 text-sm rounded"
                              placeholder={t('submissionsDialog.scorePlaceholder')}
                              value={scores[s.id] ?? ''}
                              onChange={(e) => setScores((prev) => ({ ...prev, [s.id]: e.target.value }))}
                            />
                          </div>
                          <div className="flex-1 min-w-[140px] space-y-1">
                            <label className="text-[10px] font-medium text-muted-foreground">{t('submissionsDialog.feedback')}</label>
                            <Input
                              className="h-8 text-sm rounded"
                              placeholder={t('submissionsDialog.feedbackPlaceholder')}
                              value={feedbacks[s.id] ?? ''}
                              onChange={(e) => setFeedbacks((prev) => ({ ...prev, [s.id]: e.target.value }))}
                            />
                          </div>
                          <div className="space-y-1">
                            <label className="text-[10px] font-medium text-muted-foreground">{t('submissionsDialog.uploadHint')}</label>
                            <Input
                              type="file"
                              accept=".pdf"
                              className="h-8 text-[10px] rounded w-[180px]"
                              onChange={(e) => setGradedFiles((prev) => ({ ...prev, [s.id]: e.target.files?.[0] || null }))}
                            />
                          </div>
                          <Button
                            size="sm"
                            className="h-8 text-[10px] rounded"
                            disabled={savingIds.has(s.id)}
                            onClick={() => saveGrade(s.id)}
                          >
                            {savingIds.has(s.id) ? t('submissionsDialog.saving') : t('submissionsDialog.saveScore')}
                          </Button>
                        </div>
                      </td>
                    </tr>
                  )}
                </React.Fragment>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
};
