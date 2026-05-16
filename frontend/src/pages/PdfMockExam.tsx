import React, { useEffect, useRef, useState } from 'react';
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
import { isAdminUser } from '@/lib/authz';
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

  const submit = async () => {
    const file = fileRef.current?.files?.[0];
    if (!file || !title.trim()) {
      toast.error('请填写标题并选择 PDF 文件');
      return;
    }
    setSaving(true);
    try {
      const fd = new FormData();
      fd.append('title', title.trim());
      fd.append('description', desc.trim());
      fd.append('exam_pdf', file);
      await api.post('/quizzes/teacher-exams/create/', fd);
      toast.success('试卷已发布');
      setTitle('');
      setDesc('');
      if (fileRef.current) fileRef.current.value = '';
      onOpenChange(false);
      onPublished();
    } catch (e) {
      toast.error(formatApiErrorToast(e, '发布失败'));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>发布新试卷</DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          <Input
            placeholder="试卷标题（如：2025 模拟卷 A）"
            className="h-9 text-sm"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
          />
          <textarea
            placeholder="试卷说明（可选）"
            className="flex w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
            rows={2}
            value={desc}
            onChange={(e) => setDesc(e.target.value)}
          />
          <Input ref={fileRef} type="file" accept=".pdf" className="h-9 text-xs" />
        </div>
        <DialogFooter>
          <Button variant="outline" size="sm" onClick={() => onOpenChange(false)}>取消</Button>
          <Button size="sm" onClick={submit} disabled={saving}>
            {saving ? '发布中...' : '发布试卷'}
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
      .catch(() => toast.error('加载提交列表失败'))
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
      toast.success('评分已保存');
      onGraded();
    } catch (e) {
      toast.error(formatApiErrorToast(e, '保存失败'));
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
          <DialogTitle>学生提交列表</DialogTitle>
        </DialogHeader>
        {loading ? (
          <p className="text-sm text-muted-foreground text-center py-8">加载中...</p>
        ) : subs.length === 0 ? (
          <p className="text-sm text-muted-foreground text-center py-8">暂无学生提交</p>
        ) : (
          <div className="space-y-4">
            {subs.map((s) => (
              <div key={s.id} className="p-4 rounded-xl border border-border/60 space-y-3">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-sm font-bold">{s.student_name}</p>
                    <p className="text-xs text-muted-foreground">{s.student_email}</p>
                    <p className="text-xs text-muted-foreground/60">
                      提交于 {new Date(s.created_at).toLocaleString('zh-CN')}
                    </p>
                  </div>
                  <div className="flex items-center gap-2">
                    {s.answer_pdf_url && (
                      <Button
                        size="sm"
                        variant="outline"
                        className="h-8 text-xs"
                        onClick={() => window.open(s.answer_pdf_url, '_blank')}
                      >
                        学生解答
                      </Button>
                    )}
                    {s.graded_pdf_url && (
                      <Button
                        size="sm"
                        variant="outline"
                        className="h-8 text-xs text-green-700 border-green-300"
                        onClick={() => window.open(s.graded_pdf_url, '_blank')}
                      >
                        批改件
                      </Button>
                    )}
                  </div>
                </div>
                <div className="space-y-2">
                  <div className="flex items-end gap-3">
                    <div className="flex-1 space-y-1">
                      <label className="text-xs font-bold text-muted-foreground">分数</label>
                      <Input
                        type="number"
                        className="h-9 text-sm"
                        placeholder="输入分数"
                        value={scores[s.id] ?? ''}
                        onChange={(e) => setScores((prev) => ({ ...prev, [s.id]: e.target.value }))}
                      />
                    </div>
                    <div className="flex-[2] space-y-1">
                      <label className="text-xs font-bold text-muted-foreground">评语</label>
                      <Input
                        className="h-9 text-sm"
                        placeholder="输入评语"
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
                      {savingIds.has(s.id) ? '保存中...' : '保存评分'}
                    </Button>
                  </div>
                  <div className="flex items-center gap-2">
                    <Input
                      type="file"
                      accept=".pdf"
                      className="h-8 text-xs flex-1"
                      onChange={(e) => setGradedFiles((prev) => ({ ...prev, [s.id]: e.target.files?.[0] || null }))}
                    />
                    <span className="text-[10px] text-muted-foreground shrink-0">上传批改后带笔迹的PDF</span>
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
  const user = useAuthStore((s) => s.user);
  const isAdmin = isAdminUser(user);

  const loadData = async () => {
    setLoading(true);
    setFailed('');
    try {
      const res = await api.get('/quizzes/personalized-mock-exams/');
      setItems((res.data?.results || []) as MockExamItem[]);
      const tRes = await api.get('/quizzes/teacher-exams/');
      setTeacherItems((tRes.data?.results || []) as TeacherExamItem[]);
    } catch (e) {
      setFailed(formatApiErrorToast(e, '加载数据失败'));
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
      toast.success('已提交 AI 组卷任务，请稍候刷新查看');
      await loadData();
    } catch (e) {
      toast.error(formatApiErrorToast(e, '生成失败'));
    } finally {
      setCreating(false);
    }
  };

  const deleteExam = async (examId: number) => {
    try {
      await api.delete(`/quizzes/personalized-mock-exams/?id=${examId}`);
      toast.success('已删除');
      await loadData();
    } catch (e) {
      toast.error(formatApiErrorToast(e, '删除失败'));
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
      toast.success('解答上传成功，等待老师批改');
      await loadData();
    } catch (err) {
      toast.error(formatApiErrorToast(err, '上传失败'));
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
      toast.success('试卷已删除');
      await loadData();
    } catch (e) {
      toast.error(formatApiErrorToast(e, '删除失败'));
    } finally {
      setDeletingId(null);
    }
  };

  return (
    <PageWrapper title="PDF 模考" subtitle="根据薄弱点自动组卷，或下载名师精选密卷。">
      <div className="max-w-4xl mx-auto space-y-4 pb-16">
        <div className="flex items-center gap-4 border-b border-border pb-3">
          <button onClick={() => setActiveTab('ai')} className={`text-sm font-bold pb-2 border-b-2 ${activeTab === 'ai' ? 'border-indigo-600' : 'border-transparent text-muted-foreground'}`}>AI 个性化组卷</button>
          <button onClick={() => setActiveTab('teacher')} className={`text-sm font-bold pb-2 border-b-2 ${activeTab === 'teacher' ? 'border-indigo-600' : 'border-transparent text-muted-foreground'}`}>名师精选密卷</button>
        </div>

        {activeTab === 'ai' ? (
          <>
            <Card className="p-5 rounded-2xl border border-border/60 flex items-center justify-between">
              <div>
                <p className="text-sm font-black">个性化纸质模考</p>
                <p className="text-xs text-muted-foreground mt-1">根据你的 FSRS 数据和错题本，自动生成 PDF 试卷与解析。</p>
              </div>
              <Button className="rounded-xl text-xs font-bold bg-black text-white" onClick={createExam} disabled={creating}>
                {creating ? '生成中...' : '生成本周专属模考'}
              </Button>
            </Card>

            {loading ? (
              <Card className="p-10 rounded-2xl border border-border/60 text-center text-sm font-bold text-muted-foreground">加载中...</Card>
            ) : failed ? (
              <Card className="p-10 rounded-2xl border border-red-200 bg-red-50/70 text-center text-sm font-bold text-red-700">{failed}</Card>
            ) : items.length === 0 ? (
              <Card className="p-6 rounded-2xl border border-border/60"><EmptyState title="暂无历史模考记录" className="py-4" /></Card>
            ) : (
              items.map((item) => (
                <Card key={item.id} className={`p-4 rounded-2xl border ${item.status === 'processing' ? 'border-amber-200 bg-amber-50/40' : 'border-border/60'}`}>
                  <div className="flex items-center justify-between gap-3">
                    <div>
                      <p className="text-sm font-black">
                        AI 自动组卷 #{item.id}
                        {item.status === 'processing' && <span className="ml-2 text-amber-600 text-xs font-bold animate-pulse">生成中...</span>}
                        {item.status === 'ready' && <span className="ml-2 text-green-600 text-xs">可下载</span>}
                        {item.status === 'failed' && <span className="ml-2 text-red-600 text-xs">失败</span>}
                      </p>
                      {item.status !== 'processing' && (
                        <p className="text-xs text-muted-foreground mt-1">
                          题量 {item.question_count} · 薄弱点命中 {item.weak_coverage} · {new Date(item.created_at).toLocaleString('zh-CN')}
                        </p>
                      )}
                      {item.error_message ? <p className="text-xs text-red-600 mt-1">{item.error_message}</p> : null}
                    </div>
                    <div className="flex gap-2 shrink-0">
                      {item.status === 'ready' && (
                        <>
                          <Button size="sm" variant="outline" className="h-8 text-[11px]" onClick={() => window.open(item.exam_pdf_url, '_blank')}>
                            下载试卷版
                          </Button>
                          <Button size="sm" variant="outline" className="h-8 text-[11px]" onClick={() => window.open(item.answer_pdf_url, '_blank')}>
                            下载解析版
                          </Button>
                        </>
                      )}
                      <Button size="sm" variant="ghost" className="h-8 text-[11px] text-red-500 hover:text-red-700" onClick={() => deleteExam(item.id)}>
                        删除
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
                  发布新试卷
                </Button>
              </div>
            )}

            <PublishExamDialog
              open={publishOpen}
              onOpenChange={setPublishOpen}
              onPublished={loadData}
            />

            {loading ? (
              <Card className="p-10 rounded-2xl border border-border/60 text-center text-sm font-bold text-muted-foreground">加载中...</Card>
            ) : failed ? (
              <Card className="p-10 rounded-2xl border border-red-200 bg-red-50/70 text-center text-sm font-bold text-red-700">{failed}</Card>
            ) : teacherItems.length === 0 && !isAdmin ? (
              <Card className="p-6 rounded-2xl border border-border/60"><EmptyState title="老师暂未发布试卷" className="py-4" /></Card>
            ) : teacherItems.length === 0 ? (
              <Card className="p-6 rounded-2xl border border-border/60"><EmptyState title="暂无已发布试卷" className="py-4" /></Card>
            ) : (
              teacherItems.map((item) => (
                <Card key={item.id} className="p-5 rounded-2xl border border-border/60 space-y-4">
                  <div className="flex items-center justify-between gap-3">
                    <div>
                      <p className="text-base font-black">{item.title}</p>
                      <p className="text-sm text-muted-foreground mt-1">{item.description || '无详细说明'}</p>
                      <p className="text-xs text-muted-foreground/60 mt-1">发布于 {new Date(item.created_at).toLocaleString('zh-CN')}</p>
                    </div>
                    <div className="flex items-center gap-2 shrink-0">
                      <Button size="sm" variant="default" className="h-9 text-xs" disabled={!item.exam_pdf_url} onClick={() => window.open(item.exam_pdf_url, '_blank')}>
                        下载题目 PDF
                      </Button>
                      {isAdmin && (
                        <>
                          <Button
                            size="sm"
                            variant="outline"
                            className="h-9 text-xs"
                            onClick={() => { setSubmissionsExamId(item.id); setSubmissionsOpen(true); }}
                          >
                            查看提交
                          </Button>
                          <Button
                            size="sm"
                            variant="destructive"
                            className="h-9 text-xs"
                            disabled={deletingId === item.id}
                            onClick={() => deleteTeacherExam(item.id)}
                          >
                            {deletingId === item.id ? '删除中...' : '删除'}
                          </Button>
                        </>
                      )}
                    </div>
                  </div>
                  {!isAdmin && (
                    <div className="p-4 bg-muted/40 rounded-xl border border-border/50">
                      <p className="text-xs font-black tracking-widest text-muted-foreground uppercase mb-3">我的作答与成绩</p>
                      {item.submission ? (
                        <div className="space-y-2">
                          <div className="flex items-center gap-3">
                             <span className="text-sm font-bold">
                               {item.submission.score !== null ? `成绩: ${item.submission.score} 分` : '老师批改中...'}
                               {item.submission.graded_pdf_url && (
                                 <span className="ml-2 text-green-600 text-xs bg-green-50 px-2 py-0.5 rounded-full">已批改</span>
                               )}
                             </span>
                             <Button size="sm" variant="link" className="h-6 px-0 text-xs" onClick={() => window.open(item.submission!.answer_pdf_url, '_blank')}>查看我的解答</Button>
                             {item.submission.graded_pdf_url && (
                               <Button size="sm" variant="default" className="h-7 text-xs" onClick={() => window.open(item.submission!.graded_pdf_url, '_blank')}>下载批改后试卷</Button>
                             )}
                          </div>
                          {item.submission.feedback && (
                             <div className="text-sm text-indigo-900 bg-indigo-50 p-3 rounded-lg border border-indigo-100">
                               老师评语: {item.submission.feedback}
                             </div>
                          )}
                        </div>
                      ) : (
                        <div className="flex items-center gap-3">
                          <Input type="file" accept=".pdf,.jpg,.png" className="w-[260px] h-9 text-xs" onChange={(e) => uploadSubmission(item.id, e)} />
                          {uploadingExamId === item.id && <span className="text-xs text-muted-foreground">上传中...</span>}
                          <span className="text-xs text-muted-foreground">做完后拍照转成PDF上传给老师批改</span>
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
