import React, { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { EmptyState } from '@/components/EmptyState';
import { PublishExamForm } from './PublishExamForm';
import { SubmissionPanel } from './SubmissionPanel';
import { toast } from 'sonner';
import api from '@/lib/api';
import { formatApiErrorToast } from '@/lib/apiError';
import type { TeacherExamItem } from './types';

interface TeacherExamTabProps {
  loading: boolean;
  failed: string;
  items: TeacherExamItem[];
  isAdmin: boolean;
  onRefresh: () => void;
}

export const TeacherExamTab: React.FC<TeacherExamTabProps> = ({
  loading, failed, items, isAdmin, onRefresh,
}) => {
  const { t, i18n } = useTranslation('pdfMockExam');
  const [uploadingExamId, setUploadingExamId] = useState<number | null>(null);
  const [deletingId, setDeletingId] = useState<number | null>(null);
  const [expandedSubmissions, setExpandedSubmissions] = useState<Set<number>>(new Set());

  const uploadSubmission = async (examId: number, e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploadingExamId(examId);
    try {
      const fd = new FormData();
      fd.append('file', file);
      await api.post(`/quizzes/teacher-exams/${examId}/submit/`, fd);
      toast.success(t('toast.answerUploaded'));
      onRefresh();
    } catch (err) {
      toast.error(formatApiErrorToast(err, t('toast.uploadFailed')));
    } finally {
      setUploadingExamId(null);
    }
  };

  const deleteTeacherExam = async (examId: number) => {
    setDeletingId(examId);
    try {
      await api.delete(`/quizzes/teacher-exams/${examId}/delete/`);
      toast.success(t('toast.examDeleted'));
      onRefresh();
    } catch (e) {
      toast.error(formatApiErrorToast(e, t('toast.deleteFailed')));
    } finally {
      setDeletingId(null);
    }
  };

  const toggleSubmissions = (examId: number) => {
    setExpandedSubmissions((prev) => {
      const next = new Set(prev);
      next.has(examId) ? next.delete(examId) : next.add(examId);
      return next;
    });
  };

  if (loading) {
    return <Card className="p-10 rounded-lg border border-border text-center text-sm font-medium text-muted-foreground">{t('teacherSection.loading')}</Card>;
  }

  if (failed) {
    return <Card className="p-10 rounded-lg border border-red-200 bg-red-50/70 text-center text-sm font-medium text-red-700">{failed}</Card>;
  }

  if (items.length === 0) {
    return (
      <>
        {isAdmin && <PublishExamForm onPublished={onRefresh} />}
        <Card className="p-6 rounded-lg border border-border">
          <EmptyState title={isAdmin ? t('teacherSection.noExamsAvailable') : t('teacherSection.noExamsPublished')} className="py-4" />
        </Card>
      </>
    );
  }

  return (
    <>
      {isAdmin && <PublishExamForm onPublished={onRefresh} />}

      {items.map((item) => (
        <Card key={item.id} className="rounded-lg border border-border overflow-hidden">
          <div className="p-5 space-y-4">
            <div className="flex items-center justify-between gap-3 max-md:flex-col max-md:items-start">
              <div>
                <p className="text-base font-bold">{item.title}</p>
                <p className="text-sm text-muted-foreground mt-1">{item.description || t('teacherSection.noDescription')}</p>
                <p className="text-xs text-muted-foreground/60 mt-1">
                  {t('teacherSection.publishedOn', { date: new Date(item.created_at).toLocaleString(i18n.language?.startsWith('zh') ? 'zh-CN' : 'en-US') })}
                </p>
              </div>
              <div className="flex items-center gap-2 shrink-0 max-md:w-full max-md:justify-end">
                <Button size="sm" variant="default" className="h-9 text-xs" disabled={!item.exam_pdf_url} onClick={() => window.open(item.exam_pdf_url, '_blank', 'noopener,noreferrer')}>
                  {t('teacherSection.downloadPdf')}
                </Button>
                {isAdmin && (
                  <>
                    <Button size="sm" variant="outline" className="h-9 text-xs" onClick={() => toggleSubmissions(item.id)}>
                      {t('teacherSection.viewSubmissions')}
                    </Button>
                    <Button size="sm" variant="destructive" className="h-9 text-xs" disabled={deletingId === item.id} onClick={() => deleteTeacherExam(item.id)}>
                      {deletingId === item.id ? t('teacherSection.deleting') : t('teacherSection.delete')}
                    </Button>
                  </>
                )}
              </div>
            </div>

            {isAdmin && expandedSubmissions.has(item.id) && (
              <div className="border-t border-border pt-3">
                <SubmissionPanel examId={item.id} />
              </div>
            )}

            {!isAdmin && (
              <div className="p-4 bg-muted/40 rounded-lg border border-border/50">
                <p className="text-xs font-bold uppercase tracking-widest text-muted-foreground mb-3">{t('teacherSection.myAnswer')}</p>
                {item.submission ? (
                  <div className="space-y-2">
                    <div className="flex items-center gap-3 flex-wrap">
                      <span className="text-sm font-bold">
                        {item.submission.score !== null
                          ? t('teacherSection.score', { score: item.submission.score })
                          : t('teacherSection.grading')}
                      </span>
                      {item.submission.graded_pdf_url && (
                        <Badge variant="secondary" className="rounded text-[10px] bg-green-50 text-green-700 border-green-200">
                          {t('teacherSection.graded')}
                        </Badge>
                      )}
                      {!item.submission.graded_pdf_url && item.submission.score == null && (
                        <Badge variant="secondary" className="rounded text-[10px] bg-amber-50 text-amber-700 border-amber-200">
                          {t('teacherSection.submittedWaiting')}
                        </Badge>
                      )}
                      <Button size="sm" variant="link" className="h-6 px-0 text-xs" onClick={() => window.open(item.submission!.answer_pdf_url, '_blank', 'noopener,noreferrer')}>
                        {t('teacherSection.viewMyAnswer')}
                      </Button>
                      {item.submission.graded_pdf_url && (
                        <Button size="sm" variant="default" className="h-7 text-xs" onClick={() => window.open(item.submission!.graded_pdf_url, '_blank', 'noopener,noreferrer')}>
                          {t('teacherSection.downloadGraded')}
                        </Button>
                      )}
                    </div>
                    {item.submission.feedback && (
                      <div className="text-sm text-primary bg-primary/5 p-3 rounded-lg border border-primary/10">
                        {item.submission.feedback}
                      </div>
                    )}
                  </div>
                ) : (
                  <div className="flex items-center gap-3 flex-wrap">
                    <Input type="file" accept=".pdf,.jpg,.png" className="w-[220px] h-9 text-xs" onChange={(e) => uploadSubmission(item.id, e)} />
                    {uploadingExamId === item.id && <span className="text-xs text-muted-foreground">{t('teacherSection.uploading')}</span>}
                    <span className="text-xs text-muted-foreground">{t('teacherSection.uploadHint')}</span>
                  </div>
                )}
              </div>
            )}
          </div>
        </Card>
      ))}
    </>
  );
};
