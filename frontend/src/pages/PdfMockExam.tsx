import React, { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { PageWrapper } from '@/components/PageWrapper';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog';

import api from '@/lib/api';
import { formatApiErrorToast } from '@/lib/apiError';
import { EmptyState } from '@/components/EmptyState';
import { useAuthStore } from '@/store/useAuthStore';
import { toast } from 'sonner';

type MockExamItem = {
  id: number;
  status: 'processing' | 'ready' | 'failed';
  question_count: number;
  weak_coverage: number;
  error_message: string;
  created_at: string;
  exam_pdf_url: string;
  answer_pdf_url: string;
};

type TeacherExamItem = {
  id: number;
  title: string;
  description: string;
  exam_pdf_url: string;
  created_at: string;
  submission: {
    id: number;
    answer_pdf_url: string;
    graded_pdf_url: string;
    score: number | null;
    feedback: string;
  } | null;
};

type SubmissionItem = {
  id: number;
  student_name: string;
  student_email: string;
  answer_pdf_url: string;
  graded_pdf_url: string;
  score: number | null;
  feedback: string;
  created_at: string;
};

function PublishExamDialog({
  open,
  onOpenChange,
  onPublished,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  onPublished: () => void;
}) {
  const [title, setTitle] = useState('');
  const [desc, setDesc] = useState('');
  const fileRef = useRef<HTMLInputElement>(null);
  const [saving, setSaving] = useState(false);
  const { t } = useTranslation('pdfMockExam');

  const submit = async () => {
    const file = fileRef.current?.files?.[0];
    if (!file || !title.trim()) {
      toast.error(t('toast.fillTitle'));
      return;
    }
    setSaving(true);
    try {
      const fd = new FormData();
      fd.append('title', title.trim());
      fd.append('description', desc.trim());
      fd.append('exam_pdf', file);
      await api.post('/quizzes/teacher-exams/create/', fd);
      toast.success(t('toast.examPublished'));
      setTitle('');
      setDesc('');
      if (fileRef.current) fileRef.current.value = '';
      onOpenChange(false);
      onPublished();
    } catch (e) {
      toast.error(formatApiErrorToast(e, t('toast.publishFailed')));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>{t('publishDialog.title')}</DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          <Input
            placeholder={t('publishDialog.titlePlaceholder')}
            className="h-9 text-sm"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
          />
          <textarea
            placeholder={t('publishDialog.descriptionPlaceholder')}
            className="flex w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
            rows={2}
            value={desc}
            onChange={(e) => setDesc(e.target.value)}
          />
          <Input ref={fileRef} type="file" accept=".pdf" className="h-9 text-xs" />
        </div>
        <DialogFooter>
          <Button variant="outline" size="sm" onClick={() => onOpenChange(false)}>{t('publishDialog.cancel')}</Button>
          <Button size="sm" onClick={submit} disabled={saving}>
            {saving ? t('publishDialog.saving') : t('publishDialog.submit')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function SubmissionsDialog({
  open,
  onOpenChange,
  examId,
  onGraded,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  examId: number | null;
  onGraded: () => void;
}) {
  const [subs, setSubs] = useState<SubmissionItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [scores, setScores] = useState<Record<number, string>>({});
  const [feedbacks, setFeedbacks] = useState<Record<number, string>>({});
  const [gradedFiles, setGradedFiles] = useState<Record<number, File | null>>({});
  const [savingIds, setSavingIds] = useState<Set<number>>(new Set());
  const { t, i18n } = useTranslation('pdfMockExam');

  useEffect(() => {
    if (!open || !examId) return;
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
  }, [open, examId]);

  const saveGrade = async (subId: number) => {
    setSavingIds((prev) => new Set(prev).add(subId));
    try {
      const fd = new FormData();
      fd.append('score', scores[subId] || '');
      fd.append('feedback', feedbacks[subId] || '');
      const file = gradedFiles[subId];
      if (file) {
        fd.append('graded_pdf', file);
      }
      await api.post(`/quizzes/teacher-exams/submissions/${subId}/grade/`, fd);
      toast.success(t('toast.scoreSaved'));
      onGraded();
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

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[80vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{t('submissionsDialog.title')}</DialogTitle>
        </DialogHeader>
        {loading ? (
          <p className="text-sm text-muted-foreground text-center py-8">{t('submissionsDialog.loading')}</p>
        ) : subs.length === 0 ? (
          <p className="text-sm text-muted-foreground text-center py-8">{t('submissionsDialog.noSubmissions')}</p>
        ) : (
          <div className="space-y-4">
            {subs.map((s) => (
              <div key={s.id} className="p-4 rounded-xl border border-border/60 space-y-3">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-sm font-bold">{s.student_name}</p>
                    <p className="text-xs text-muted-foreground">{s.student_email}</p>
                    <p className="text-xs text-muted-foreground/60">
                      {t('submissionsDialog.submittedOn', { date: new Date(s.created_at).toLocaleString(i18n.language?.startsWith('zh') ? 'zh-CN' : 'en-US') })}                    </p>
                  </div>
                  <div className="flex items-center gap-2">
                    {s.answer_pdf_url && (
                      <Button
                        size="sm"
                        variant="outline"
                        className="h-8 text-xs"
                        onClick={() => window.open(s.answer_pdf_url, '_blank')}
                      >
                        {t('submissionsDialog.studentAnswer')}
                      </Button>
                    )}
                    {s.graded_pdf_url && (
                      <Button
                        size="sm"
                        variant="outline"
                        className="h-8 text-xs text-green-700 border-green-300"
                        onClick={() => window.open(s.graded_pdf_url, '_blank')}
                      >
                        {t('submissionsDialog.gradedPdf')}
                      </Button>
                    )}
                  </div>
                </div>
                <div className="space-y-2">
                  <div className="flex items-end gap-3">
                    <div className="flex-1 space-y-1">
                      <label className="text-xs font-bold text-muted-foreground">{t('submissionsDialog.score')}</label>
                      <Input
                        type="number"
                        className="h-9 text-sm"
                        placeholder={t('submissionsDialog.scorePlaceholder')}
                        value={scores[s.id] ?? ''}
                        onChange={(e) => setScores((prev) => ({ ...prev, [s.id]: e.target.value }))}
                      />
                    </div>
                    <div className="flex-[2] space-y-1">
                      <label className="text-xs font-bold text-muted-foreground">{t('submissionsDialog.feedback')}</label>
                      <Input
                        className="h-9 text-sm"
                        placeholder={t('submissionsDialog.feedbackPlaceholder')}
                        value={feedbacks[s.id] ?? ''}
                        onChange={(e) => setFeedbacks((prev) => ({ ...prev, [s.id]: e.target.value }))}
                      />
                    </div>
                    <Button
                      size="sm"
                      className="h-9 text-xs shrink-0"
                      disabled={savingIds.has(s.id)}
                      onClick={() => saveGrade(s.id)}
                    >
                      {savingIds.has(s.id) ? t('submissionsDialog.saving') : t('submissionsDialog.saveScore')}
                    </Button>
                  </div>
                  <div className="flex items-center gap-2">
                    <Input
                      type="file"
                      accept=".pdf"
                      className="h-8 text-xs flex-1"
                      onChange={(e) => setGradedFiles((prev) => ({ ...prev, [s.id]: e.target.files?.[0] || null }))}
                    />
                    <span className="text-[10px] text-muted-foreground shrink-0">{t('submissionsDialog.uploadHint')}</span>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}

export const PdfMockExam: React.FC = () => {
  const [activeTab, setActiveTab] = useState<'ai' | 'teacher'>('ai');
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [items, setItems] = useState<MockExamItem[]>([]);
  const [teacherItems, setTeacherItems] = useState<TeacherExamItem[]>([]);
  const [failed, setFailed] = useState('');
  const [uploadingExamId, setUploadingExamId] = useState<number | null>(null);
  const { t, i18n } = useTranslation('pdfMockExam');
  const user = useAuthStore((s) => s.user);
  const isAdmin = user?.is_admin || user?.is_institution_admin || user?.role === 'admin';

  const loadData = async () => {
    setLoading(true);
    setFailed('');
    try {
      const res = await api.get('/quizzes/personalized-mock-exams/');
      setItems((res.data?.results || []) as MockExamItem[]);
      const tRes = await api.get('/quizzes/teacher-exams/');
      setTeacherItems((tRes.data?.results || []) as TeacherExamItem[]);
    } catch (e) {
      setFailed(formatApiErrorToast(e, t('toast.loadDataFailed')));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  // 自动轮询：如果有 processing 状态的记录，每 5 秒刷新一次
  useEffect(() => {
    const hasProcessing = items.some((i) => i.status === 'processing');
    if (!hasProcessing) return;
    const timer = setInterval(() => loadData(), 5000);
    return () => clearInterval(timer);
  }, [items]);

  const createExam = async () => {
    setCreating(true);
    try {
      await api.post('/quizzes/personalized-mock-exams/', {});
      toast.success(t('toast.aiTaskSubmitted'));
      await loadData();
    } catch (e) {
      toast.error(formatApiErrorToast(e, t('toast.generateFailed')));
    } finally {
      setCreating(false);
    }
  };

  const deleteExam = async (examId: number) => {
    try {
      await api.delete(`/quizzes/personalized-mock-exams/?id=${examId}`);
      toast.success(t('toast.deleted'));
      await loadData();
    } catch (e) {
      toast.error(formatApiErrorToast(e, t('toast.deleteFailed')));
    }
  };

  const uploadSubmission = async (examId: number, e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploadingExamId(examId);
    try {
      const fd = new FormData();
      fd.append('file', file);
      await api.post(`/quizzes/teacher-exams/${examId}/submit/`, fd);
      toast.success(t('toast.answerUploaded'));
      await loadData();
    } catch (err) {
      toast.error(formatApiErrorToast(err, t('toast.uploadFailed')));
    } finally {
      setUploadingExamId(null);
    }
  };

  // --- 教师发布试卷 ---
  const [publishOpen, setPublishOpen] = useState(false);
  const [submissionsOpen, setSubmissionsOpen] = useState(false);
  const [submissionsExamId, setSubmissionsExamId] = useState<number | null>(null);
  const [deletingId, setDeletingId] = useState<number | null>(null);

  const deleteTeacherExam = async (examId: number) => {
    setDeletingId(examId);
    try {
      await api.delete(`/quizzes/teacher-exams/${examId}/delete/`);
      toast.success(t('toast.examDeleted'));
      await loadData();
    } catch (e) {
      toast.error(formatApiErrorToast(e, t('toast.deleteFailed')));
    } finally {
      setDeletingId(null);
    }
  };

  return (
    <PageWrapper title={t('pageTitle')} subtitle={t('pageSubtitle')}>
      <div className="max-w-4xl mx-auto space-y-4 pb-16">
        <div className="flex items-center gap-4 border-b border-border pb-3">
          <button onClick={() => setActiveTab('ai')} className={`text-sm font-bold pb-2 border-b-2 ${activeTab === 'ai' ? 'border-indigo-600' : 'border-transparent text-muted-foreground'}`}>{t('tabAI')}</button>
          <button onClick={() => setActiveTab('teacher')} className={`text-sm font-bold pb-2 border-b-2 ${activeTab === 'teacher' ? 'border-indigo-600' : 'border-transparent text-muted-foreground'}`}>{t('tabTeacher')}</button>
        </div>

        {activeTab === 'ai' ? (
          <>
            <Card className="p-5 rounded-2xl border border-border/60 flex items-center justify-between">
              <div>
                <p className="text-sm font-black">{t('aiSection.title')}</p>
                <p className="text-xs text-muted-foreground mt-1">{t('aiSection.description')}</p>
              </div>
              <Button className="rounded-xl text-xs font-bold bg-black text-white" onClick={createExam} disabled={creating}>
                {creating ? t('aiSection.generating') : t('aiSection.generate')}
              </Button>
            </Card>

            {loading ? (
              <Card className="p-10 rounded-2xl border border-border/60 text-center text-sm font-bold text-muted-foreground">{t('aiSection.loading')}</Card>
            ) : failed ? (
              <Card className="p-10 rounded-2xl border border-red-200 bg-red-50/70 text-center text-sm font-bold text-red-700">{failed}</Card>
            ) : items.length === 0 ? (
              <Card className="p-6 rounded-2xl border border-border/60"><EmptyState title={t('aiSection.noHistory')} className="py-4" /></Card>
            ) : (
              items.map((item) => (
                <Card key={item.id} className={`p-4 rounded-2xl border ${item.status === 'processing' ? 'border-amber-200 bg-amber-50/40' : 'border-border/60'}`}>
                  <div className="flex items-center justify-between gap-3">
                    <div>
                      <p className="text-sm font-black">
                        {t('aiSection.aiLabel', { id: item.id })}
                        {item.status === 'processing' && <span className="ml-2 text-amber-600 text-xs font-bold animate-pulse">{t('aiSection.statusProcessing')}</span>}
                        {item.status === 'ready' && <span className="ml-2 text-green-600 text-xs">{t('aiSection.statusReady')}</span>}
                        {item.status === 'failed' && <span className="ml-2 text-red-600 text-xs">{t('aiSection.statusFailed')}</span>}
                      </p>
                      {item.status !== 'processing' && (
                        <p className="text-xs text-muted-foreground mt-1">
                          {t('aiSection.questionInfo', { count: item.question_count, coverage: item.weak_coverage })} · {new Date(item.created_at).toLocaleString(i18n.language?.startsWith('zh') ? 'zh-CN' : 'en-US')}
                        </p>
                      )}
                      {item.error_message ? <p className="text-xs text-red-600 mt-1">{item.error_message}</p> : null}
                    </div>
                    <div className="flex gap-2 shrink-0">
                      {item.status === 'ready' && (
                        <>
                          <Button size="sm" variant="outline" className="h-8 text-[11px]" onClick={() => window.open(item.exam_pdf_url, '_blank')}>
                            {t('aiSection.downloadExam')}
                          </Button>
                          <Button size="sm" variant="outline" className="h-8 text-[11px]" onClick={() => window.open(item.answer_pdf_url, '_blank')}>
                            {t('aiSection.downloadAnswer')}
                          </Button>
                        </>
                      )}
                      <Button size="sm" variant="ghost" className="h-8 text-[11px] text-red-500 hover:text-red-700" onClick={() => deleteExam(item.id)}>
                        {t('aiSection.delete')}
                      </Button>
                    </div>
                  </div>
                </Card>
              ))
            )}
          </>
        ) : (
          <>
            {isAdmin && (
              <div className="flex justify-end">
                <Button size="sm" variant="apple" onClick={() => setPublishOpen(true)}>
                  {t('aiSection.publishNew')}
                </Button>
              </div>
            )}

            <PublishExamDialog
              open={publishOpen}
              onOpenChange={setPublishOpen}
              onPublished={loadData}
            />

            {loading ? (
              <Card className="p-10 rounded-2xl border border-border/60 text-center text-sm font-bold text-muted-foreground">{t('teacherSection.loading')}</Card>
            ) : failed ? (
              <Card className="p-10 rounded-2xl border border-red-200 bg-red-50/70 text-center text-sm font-bold text-red-700">{failed}</Card>
            ) : teacherItems.length === 0 && !isAdmin ? (
              <Card className="p-6 rounded-2xl border border-border/60"><EmptyState title={t('teacherSection.noExamsPublished')} className="py-4" /></Card>
            ) : teacherItems.length === 0 ? (
              <Card className="p-6 rounded-2xl border border-border/60"><EmptyState title={t('teacherSection.noExamsAvailable')} className="py-4" /></Card>
            ) : (
              teacherItems.map((item) => (
                <Card key={item.id} className="p-5 rounded-2xl border border-border/60 space-y-4">
                  <div className="flex items-center justify-between gap-3">
                    <div>
                      <p className="text-base font-black">{item.title}</p>
                      <p className="text-sm text-muted-foreground mt-1">{item.description || t('teacherSection.noDescription')}</p>
                      <p className="text-xs text-muted-foreground/60 mt-1">{t('teacherSection.publishedOn', { date: new Date(item.created_at).toLocaleString(i18n.language?.startsWith('zh') ? 'zh-CN' : 'en-US') })}</p>
                    </div>
                    <div className="flex items-center gap-2 shrink-0">
                      <Button size="sm" variant="default" className="h-9 text-xs" disabled={!item.exam_pdf_url} onClick={() => window.open(item.exam_pdf_url, '_blank')}>
                        {t('teacherSection.downloadPdf')}
                      </Button>
                      {isAdmin && (
                        <>
                          <Button
                            size="sm"
                            variant="outline"
                            className="h-9 text-xs"
                            onClick={() => { setSubmissionsExamId(item.id); setSubmissionsOpen(true); }}
                          >
                            {t('teacherSection.viewSubmissions')}
                          </Button>
                          <Button
                            size="sm"
                            variant="destructive"
                            className="h-9 text-xs"
                            disabled={deletingId === item.id}
                            onClick={() => deleteTeacherExam(item.id)}
                          >
                            {deletingId === item.id ? t('teacherSection.deleting') : t('teacherSection.delete')}
                          </Button>
                        </>
                      )}
                    </div>
                  </div>
                  {!isAdmin && (
                    <div className="p-4 bg-muted/40 rounded-xl border border-border/50">
                      <p className="text-xs font-black tracking-widest text-muted-foreground uppercase mb-3">{t('teacherSection.myAnswer')}</p>
                      {item.submission ? (
                        <div className="space-y-2">
                          <div className="flex items-center gap-3">
                             <span className="text-sm font-bold">
                               {item.submission.score !== null ? t('teacherSection.score', { score: item.submission.score }) : t('teacherSection.grading')}
                               {item.submission.graded_pdf_url && (
                                 <span className="ml-2 text-green-600 text-xs bg-green-50 px-2 py-0.5 rounded-full">{t('teacherSection.graded')}</span>
                               )}
                             </span>
                             <Button size="sm" variant="link" className="h-6 px-0 text-xs" onClick={() => window.open(item.submission!.answer_pdf_url, '_blank')}>{t('teacherSection.viewMyAnswer')}</Button>
                             {item.submission.graded_pdf_url && (
                               <Button size="sm" variant="default" className="h-7 text-xs" onClick={() => window.open(item.submission!.graded_pdf_url, '_blank')}>{t('teacherSection.downloadGraded')}</Button>
                             )}
                          </div>
                          {item.submission.feedback && (
                             <div className="text-sm text-indigo-900 bg-indigo-50 p-3 rounded-lg border border-indigo-100">
                               {t('teacherSection.teacherFeedback', { feedback: item.submission.feedback })}
                             </div>
                          )}
                        </div>
                      ) : (
                        <div className="flex items-center gap-3">
                          <Input type="file" accept=".pdf,.jpg,.png" className="w-[260px] h-9 text-xs" onChange={(e) => uploadSubmission(item.id, e)} />
                          {uploadingExamId === item.id && <span className="text-xs text-muted-foreground">{t('teacherSection.uploading')}</span>}
                          <span className="text-xs text-muted-foreground">{t('teacherSection.uploadHint')}</span>
                        </div>
                      )}
                    </div>
                  )}
                </Card>
              ))
            )}

            <SubmissionsDialog
              open={submissionsOpen}
              onOpenChange={setSubmissionsOpen}
              examId={submissionsExamId}
              onGraded={loadData}
            />
          </>
        )}
      </div>
    </PageWrapper>
  );
};
