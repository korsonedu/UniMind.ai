# PdfMockExam 重构 + 全局移动端响应式 — 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 重构密卷页面的组件架构和教师批改工作流，同时对全部 21 个前端页面进行统一的移动端响应式适配。

**Architecture:** PdfMockExam 从 558 行单文件拆分为 1 个主页面 + 4 个子组件。移动端采用统一断点策略（<768px 底栏 + 全宽），逐页审查和修复布局/溢出/触控/安全区问题。

**Tech Stack:** React 19 + TypeScript + Tailwind CSS 4 + shadcn/ui + react-i18next + lucide-react

---

## Phase 1: 密卷页面组件拆分

### Task 1: 创建共享类型和 AiExamTab

**Files:**
- Create: `frontend/src/components/exam/types.ts`
- Create: `frontend/src/components/exam/AiExamTab.tsx`

- [ ] **Step 1: 创建 types.ts**

```typescript
export type SubmissionStatus = 'not_submitted' | 'submitted' | 'graded';

export type MockExamItem = {
  id: number;
  status: 'processing' | 'ready' | 'failed';
  question_count: number;
  weak_coverage: number;
  error_message: string;
  created_at: string;
  exam_pdf_url: string;
  answer_pdf_url: string;
};

export type TeacherExamItem = {
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

export type SubmissionItem = {
  id: number;
  student_name: string;
  student_email: string;
  answer_pdf_url: string;
  graded_pdf_url: string;
  score: number | null;
  feedback: string;
  created_at: string;
};
```

- [ ] **Step 2: 创建 AiExamTab.tsx**

从 PdfMockExam.tsx 提取 AI Tab 内容（当前 activeTab === 'ai' 分支，第 395-448 行），作为独立组件：

```typescript
import React from 'react';
import { useTranslation } from 'react-i18next';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { EmptyState } from '@/components/EmptyState';
import type { MockExamItem } from './types';

interface AiExamTabProps {
  loading: boolean;
  creating: boolean;
  failed: string;
  items: MockExamItem[];
  onCreate: () => void;
  onDelete: (id: number) => void;
}

export const AiExamTab: React.FC<AiExamTabProps> = ({
  loading, creating, failed, items, onCreate, onDelete,
}) => {
  const { t, i18n } = useTranslation('pdfMockExam');

  return (
    <>
      <Card className="p-5 rounded-lg border border-border flex items-center justify-between">
        <div>
          <p className="text-sm font-bold">{t('aiSection.title')}</p>
          <p className="text-xs text-muted-foreground mt-1">{t('aiSection.description')}</p>
        </div>
        <Button className="rounded-lg text-xs font-medium" onClick={onCreate} disabled={creating}>
          {creating ? t('aiSection.generating') : t('aiSection.generate')}
        </Button>
      </Card>

      {loading ? (
        <Card className="p-10 rounded-lg border border-border text-center text-sm font-medium text-muted-foreground">{t('aiSection.loading')}</Card>
      ) : failed ? (
        <Card className="p-10 rounded-lg border border-red-200 bg-red-50/70 text-center text-sm font-medium text-red-700">{failed}</Card>
      ) : items.length === 0 ? (
        <Card className="p-6 rounded-lg border border-border"><EmptyState title={t('aiSection.noHistory')} className="py-4" /></Card>
      ) : (
        items.map((item) => (
          <Card key={item.id} className={`p-4 rounded-lg border ${item.status === 'processing' ? 'border-amber-200 bg-amber-50/40' : 'border-border'}`}>
            <div className="flex items-center justify-between gap-3">
              <div>
                <p className="text-sm font-bold">
                  {t('aiSection.aiLabel', { id: item.id })}
                  {item.status === 'processing' && <span className="ml-2 text-amber-600 text-xs font-medium animate-pulse">{t('aiSection.statusProcessing')}</span>}
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
                <Button size="sm" variant="ghost" className="h-8 text-[11px] text-red-500 hover:text-red-700" onClick={() => onDelete(item.id)}>
                  {t('aiSection.delete')}
                </Button>
              </div>
            </div>
          </Card>
        ))
      )}
    </>
  );
};
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/exam/types.ts frontend/src/components/exam/AiExamTab.tsx
git commit -m "feat: extract AiExamTab and shared types from PdfMockExam"
```

---

### Task 2: 创建 PublishExamForm（发布试卷内联表单）

**Files:**
- Create: `frontend/src/components/exam/PublishExamForm.tsx`

- [ ] **Step 1: 创建 PublishExamForm.tsx**（替代 PublishExamDialog 弹窗）

```typescript
import React, { useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { toast } from 'sonner';
import api from '@/lib/api';
import { formatApiErrorToast } from '@/lib/apiError';

interface PublishExamFormProps {
  onPublished: () => void;
}

export const PublishExamForm: React.FC<PublishExamFormProps> = ({ onPublished }) => {
  const [title, setTitle] = useState('');
  const [desc, setDesc] = useState('');
  const [saving, setSaving] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);
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
      setExpanded(false);
      onPublished();
    } catch (e) {
      toast.error(formatApiErrorToast(e, t('toast.publishFailed')));
    } finally {
      setSaving(false);
    }
  };

  if (!expanded) {
    return (
      <div className="flex justify-end">
        <Button size="sm" variant="apple" onClick={() => setExpanded(true)}>
          {t('aiSection.publishNew')}
        </Button>
      </div>
    );
  }

  return (
    <div className="p-4 rounded-lg border border-primary/30 bg-primary/5 space-y-3">
      <p className="text-sm font-bold">{t('publishDialog.title')}</p>
      <Input
        placeholder={t('publishDialog.titlePlaceholder')}
        className="h-10 rounded-lg"
        value={title}
        onChange={(e) => setTitle(e.target.value)}
        autoComplete="off"
      />
      <textarea
        placeholder={t('publishDialog.descriptionPlaceholder')}
        className="flex w-full rounded-lg border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
        rows={2}
        value={desc}
        onChange={(e) => setDesc(e.target.value)}
      />
      <Input ref={fileRef} type="file" accept=".pdf" className="h-10 text-xs rounded-lg" />
      <div className="flex gap-2">
        <Button variant="outline" size="sm" onClick={() => setExpanded(false)}>{t('publishDialog.cancel')}</Button>
        <Button size="sm" onClick={submit} disabled={saving}>
          {saving ? t('publishDialog.saving') : t('publishDialog.submit')}
        </Button>
      </div>
    </div>
  );
};
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/exam/PublishExamForm.tsx
git commit -m "feat: add PublishExamForm inline component to replace dialog"
```

---

### Task 3: 创建 SubmissionPanel（提交批改内联面板）

**Files:**
- Create: `frontend/src/components/exam/SubmissionPanel.tsx`

- [ ] **Step 1: 创建 SubmissionPanel.tsx**（替代 SubmissionsDialog 弹窗）

设计为在试卷卡片内部展开的内联面板，包含提交概览表和逐行批改表单：

```typescript
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
      // 刷新以获取最新状态
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
                          <Button size="sm" variant="outline" className="h-7 text-[10px] rounded" onClick={() => window.open(s.answer_pdf_url, '_blank')}>
                            {t('submissionsDialog.studentAnswer')}
                          </Button>
                        )}
                        {s.graded_pdf_url && (
                          <Button size="sm" variant="outline" className="h-7 text-[10px] rounded text-green-700 border-green-300" onClick={() => window.open(s.graded_pdf_url, '_blank')}>
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
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/exam/SubmissionPanel.tsx
git commit -m "feat: add SubmissionPanel with inline grading table"
```

---

### Task 4: 创建 TeacherExamTab

**Files:**
- Create: `frontend/src/components/exam/TeacherExamTab.tsx`

- [ ] **Step 1: 创建 TeacherExamTab.tsx**

整合教师/学生双视角的试卷列表 + 内联发布表单 + 提交批改面板：

```typescript
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
            {/* 试卷头部 */}
            <div className="flex items-center justify-between gap-3">
              <div>
                <p className="text-base font-bold">{item.title}</p>
                <p className="text-sm text-muted-foreground mt-1">{item.description || t('teacherSection.noDescription')}</p>
                <p className="text-xs text-muted-foreground/60 mt-1">
                  {t('teacherSection.publishedOn', { date: new Date(item.created_at).toLocaleString(i18n.language?.startsWith('zh') ? 'zh-CN' : 'en-US') })}
                </p>
              </div>
              <div className="flex items-center gap-2 shrink-0">
                <Button size="sm" variant="default" className="h-9 text-xs" disabled={!item.exam_pdf_url} onClick={() => window.open(item.exam_pdf_url, '_blank')}>
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

            {/* 学生提交/批改区域 */}
            {isAdmin && expandedSubmissions.has(item.id) && (
              <div className="border-t border-border pt-3">
                <SubmissionPanel examId={item.id} />
              </div>
            )}

            {/* 学生作答区域 */}
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
                      <Button size="sm" variant="link" className="h-6 px-0 text-xs" onClick={() => window.open(item.submission!.answer_pdf_url, '_blank')}>
                        {t('teacherSection.viewMyAnswer')}
                      </Button>
                      {item.submission.graded_pdf_url && (
                        <Button size="sm" variant="default" className="h-7 text-xs" onClick={() => window.open(item.submission!.graded_pdf_url, '_blank')}>
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
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/exam/TeacherExamTab.tsx
git commit -m "feat: add TeacherExamTab with submission status flow and inline grading"
```

---

### Task 5: 精简 PdfMockExam.tsx 主页面

**Files:**
- Modify: `frontend/src/pages/PdfMockExam.tsx`

- [ ] **Step 1: 重写 PdfMockExam.tsx**

将当前 558 行精简为 ~80 行，仅保留 Tab 切换、数据加载、轮询逻辑，渲染子组件：

```typescript
import React, { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { PageWrapper } from '@/components/PageWrapper';
import api from '@/lib/api';
import { formatApiErrorToast } from '@/lib/apiError';
import { toast } from 'sonner';
import { useAuthStore } from '@/store/useAuthStore';
import { AiExamTab } from '@/components/exam/AiExamTab';
import { TeacherExamTab } from '@/components/exam/TeacherExamTab';
import type { MockExamItem, TeacherExamItem } from '@/components/exam/types';

export const PdfMockExam: React.FC = () => {
  const [activeTab, setActiveTab] = useState<'ai' | 'teacher'>('ai');
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [items, setItems] = useState<MockExamItem[]>([]);
  const [teacherItems, setTeacherItems] = useState<TeacherExamItem[]>([]);
  const [failed, setFailed] = useState('');
  const { t } = useTranslation('pdfMockExam');
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

  useEffect(() => { loadData(); }, []);

  // 自动轮询：有 processing 状态记录时每 5s 刷新
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

  return (
    <PageWrapper title={t('pageTitle')} subtitle={t('pageSubtitle')}>
      <div className="max-w-4xl mx-auto space-y-4 pb-16 px-4 md:px-0">
        {/* Tab 切换 */}
        <div className="flex items-center gap-4 border-b border-border">
          <button
            onClick={() => setActiveTab('ai')}
            className={`text-sm font-bold pb-2 border-b-2 transition-colors ${
              activeTab === 'ai' ? 'border-foreground text-foreground' : 'border-transparent text-muted-foreground'
            }`}
          >
            {t('tabAI')}
          </button>
          <button
            onClick={() => setActiveTab('teacher')}
            className={`text-sm font-bold pb-2 border-b-2 transition-colors ${
              activeTab === 'teacher' ? 'border-foreground text-foreground' : 'border-transparent text-muted-foreground'
            }`}
          >
            {t('tabTeacher')}
          </button>
        </div>

        {activeTab === 'ai' ? (
          <AiExamTab
            loading={loading}
            creating={creating}
            failed={failed}
            items={items}
            onCreate={createExam}
            onDelete={deleteExam}
          />
        ) : (
          <TeacherExamTab
            loading={loading}
            failed={failed}
            items={teacherItems}
            isAdmin={isAdmin}
            onRefresh={loadData}
          />
        )}
      </div>
    </PageWrapper>
  );
};
```

- [ ] **Step 2: 移除 PdfMockExam.tsx 中的内联组件定义**

删除文件中原来的 `PublishExamDialog`、`SubmissionsDialog` 函数组件和相关的 `MockExamItem`、`TeacherExamItem`、`SubmissionItem` 类型定义。确保所有 import 清理干净。

- [ ] **Step 3: 验证构建**

```bash
cd frontend && npm run build 2>&1 | tail -5
```
期望: `✓ built in X.XXs`

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/PdfMockExam.tsx
git commit -m "refactor: slim PdfMockExam to tab shell, extract child components"
```

---

## Phase 2: 移动端 — MainLayout 底部导航

### Task 6: 底部导航栏打磨

**Files:**
- Modify: `frontend/src/layouts/MainLayout.tsx`

- [ ] **Step 1: 更新底部导航栏 active 态样式**

找到底栏渲染位置（约 line 503 附近），将 active 检测和样式改为：

```tsx
const isBottomNavActive = (path: string) => {
  if (path === '/courses') return location.pathname.startsWith('/courses') || location.pathname.startsWith('/course');
  if (path === '/tests') return location.pathname.startsWith('/tests') || location.pathname.startsWith('/test');
  if (path === '/knowledge-map') return location.pathname.startsWith('/knowledge-map');
  if (path === '/study') return location.pathname.startsWith('/study');
  if (path === '/profile') return location.pathname.startsWith('/profile');
  return false;
};
```

每个底栏按钮结构：
```tsx
<Link to={path} className={cn(
  'flex flex-col items-center justify-center gap-0.5 py-1 px-3 rounded-lg transition-colors min-h-[44px] min-w-[44px]',
  isBottomNavActive(path)
    ? 'text-primary'
    : 'text-muted-foreground hover:text-foreground'
)}>
  <Icon className="h-5 w-5" />
  <span className="text-[10px] font-bold">{label}</span>
  {isBottomNavActive(path) && <span className="absolute top-0 inset-x-3 h-0.5 bg-primary rounded-full" />}
</Link>
```

- [ ] **Step 2: 确保沉浸式页面底栏隐藏逻辑正确**

检查 `hideMobileBottomNav` 变量已经覆盖：`/tests/session`、`/course/`、`/study` 三个路径。

```tsx
const hideMobileBottomNav = isMobile && (
  location.pathname.startsWith('/tests/session') ||
  location.pathname.startsWith('/course/') ||
  location.pathname === '/study'
);
```

- [ ] **Step 3: 内容区移动端 padding**

确保主内容区在移动端有底部留白给底栏：
```tsx
<main className={cn(
  'flex-1 min-h-0',
  isMobile && !hideMobileBottomNav && 'pb-16',
)}>
```

- [ ] **Step 4: 验证构建**

```bash
cd frontend && npm run build 2>&1 | tail -5
```
期望: `✓ built in X.XXs`

- [ ] **Step 5: Commit**

```bash
git add frontend/src/layouts/MainLayout.tsx
git commit -m "feat: polish mobile bottom nav active states and safe area"
```

---

## Phase 3: 移动端 — P0/P1 页面适配

### Task 7: P0 + P1 页面移动端响应式

**Files:**
- Modify: `frontend/src/pages/PdfMockExam.tsx`
- Modify: `frontend/src/pages/TestSessionPage.tsx`
- Modify: `frontend/src/pages/CourseDetails.tsx`
- Modify: `frontend/src/pages/KnowledgeMap.tsx`
- Modify: `frontend/src/pages/InstitutionDashboard.tsx`
- Modify: `frontend/src/pages/InstitutionStudents.tsx`

- [ ] **Step 1: PdfMockExam 移动端**

Tabs 切换在移动端使用 `overflow-x-auto` 防止溢出：
```tsx
<div className="flex items-center gap-4 border-b border-border overflow-x-auto -mx-4 px-4">
```
卡片内操作按钮在 md 以下纵向堆叠：给卡片里的 `flex items-center justify-between` 加上 `max-md:flex-col max-md:items-start max-md:gap-2`。

- [ ] **Step 2: TestSessionPage 移动端**

页面已经是全屏沉浸式设计，主要通过 `isMobile` 判断。检查：
- 选择题选项网格 `grid grid-cols-1`（已有，确认）
- textarea 高度 `min-h-[170px]` 在移动端合理
- 底部 footer padding 包含 `safe-area-inset-bottom`（已有，确认）

- [ ] **Step 3: CourseDetails 移动端**

在 `max-w-[1600px]` 容器外添加 `px-0 lg:px-6`。视频下方内容 grid `lg:grid-cols-12` 在移动端自动单列。课程卡片 `grid-cols-1 md:grid-cols-2`（已有，确认）。

- [ ] **Step 4: KnowledgeMap 移动端**

知识图谱画布已有 `w-full h-full`，通过 transform 控制缩放。确认 TreePanel（左侧栏）在移动端的行为：移动端应默认隐藏，通过按钮触发 overlay 显示。

- [ ] **Step 5: InstitutionDashboard + InstitutionStudents 移动端**

统计卡片区：
```tsx
<div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
```
表格使用：
```tsx
<div className="overflow-x-auto -mx-4 px-4">
  <table className="min-w-[600px] w-full ...">
</div>
```

- [ ] **Step 6: 验证构建**

```bash
cd frontend && npm run build 2>&1 | tail -5
```
期望: `✓ built in X.XXs`

- [ ] **Step 7: Commit**

```bash
git add frontend/src/pages/PdfMockExam.tsx frontend/src/pages/TestSessionPage.tsx frontend/src/pages/CourseDetails.tsx frontend/src/pages/KnowledgeMap.tsx frontend/src/pages/InstitutionDashboard.tsx frontend/src/pages/InstitutionStudents.tsx
git commit -m "feat: add mobile responsive layouts for P0/P1 pages"
```

---

## Phase 4: 移动端 — P2/P3 页面适配

### Task 8: P2 页面移动端响应式

**Files:**
- Modify: `frontend/src/pages/ArticleDetail.tsx`
- Modify: `frontend/src/pages/StudyRoom.tsx`
- Modify: `frontend/src/pages/WrongQuestionReviewPage.tsx`
- Modify: `frontend/src/pages/QASystem.tsx`
- Modify: `frontend/src/pages/KnowledgeNodeDetail.tsx`

- [ ] **Step 1: ArticleDetail**

文章内容区 `max-w-3xl mx-auto`，移动端 `px-4`。页面头部的返回按钮和元信息在移动端纵向排列。

- [ ] **Step 2: StudyRoom**

已为全屏沉浸式（`isFullPage` 判断），确认。

- [ ] **Step 3: WrongQuestionReviewPage**

统计卡片 `grid-cols-1 md:grid-cols-3` 已有。Drill 卡片 `grid-cols-1 md:grid-cols-2` 已有。底部分解面板 `grid-cols-1 md:grid-cols-2` 已有。主要确认移动端没有溢出。

- [ ] **Step 4: QASystem**

检查左侧问题列表 + 右侧对话区的分栏在移动端的行为。移动端应默认显示对话区，通过返回按钮切回列表。

- [ ] **Step 5: KnowledgeNodeDetail**

类似 ArticleDetail，内容居中 `max-w-3xl mx-auto px-4`。

- [ ] **Step 6: 验证构建 + Commit**

```bash
cd frontend && npm run build 2>&1 | tail -5
git add frontend/src/pages/ArticleDetail.tsx frontend/src/pages/StudyRoom.tsx frontend/src/pages/WrongQuestionReviewPage.tsx frontend/src/pages/QASystem.tsx frontend/src/pages/KnowledgeNodeDetail.tsx
git commit -m "feat: add mobile responsive layouts for P2 pages"
```

---

### Task 9: P3 页面 + 弹窗/Sheet 移动端

**Files:**
- Modify: `frontend/src/pages/maintenance/AuditPanel.tsx`
- Modify: `frontend/src/pages/maintenance/KnowledgeSystemPanel.tsx`
- Modify: `frontend/src/pages/maintenance/MaintenanceComponents.tsx`
- Modify: `frontend/src/pages/maintenance/MembershipPanel.tsx`
- Modify: `frontend/src/pages/maintenance/QuestionBankPanel.tsx`
- Modify: `frontend/src/components/ui/dialog.tsx`
- Modify: `frontend/src/components/ui/sheet.tsx`
- Modify: `frontend/src/components/ui/alert-dialog.tsx`

- [ ] **Step 1: Maintenance 面板**

所有面板使用统一的管理后台布局。表格区加 `overflow-x-auto`，操作按钮确保在移动端不掉出视口。

- [ ] **Step 2: Dialog 移动端适配**

在 `DialogContent` 添加移动端样式：
```tsx
className={cn(
  'fixed left-[50%] top-[50%] z-50 grid w-full max-w-lg translate-x-[-50%] translate-y-[-50%] gap-4 border bg-background p-6 shadow-lg duration-200 sm:rounded-xl',
  'max-sm:max-w-[calc(100vw-2rem)] max-sm:p-4',
  className
)}
```

- [ ] **Step 3: Sheet 移动端适配**

Sheet 在移动端应占满宽度：
```tsx
className={cn(
  'max-sm:w-[calc(100vw-1rem)]',
  className
)}
```

- [ ] **Step 4: AlertDialog 移动端适配**

同 Dialog 模式，加 `max-sm:max-w-[calc(100vw-2rem)]`。

- [ ] **Step 5: 验证构建 + Commit**

```bash
cd frontend && npm run build 2>&1 | tail -5
git add frontend/src/pages/maintenance/ frontend/src/components/ui/dialog.tsx frontend/src/components/ui/sheet.tsx frontend/src/components/ui/alert-dialog.tsx
git commit -m "feat: mobile responsive for maintenance panels and dialog/sheet"
```

---

## Phase 5: 最终验证

### Task 10: 全量构建 + 视觉审查

- [ ] **Step 1: 全量构建**

```bash
cd frontend && npm run build 2>&1
```
期望: 0 TypeScript 错误，构建成功

- [ ] **Step 2: 移动端关键路径检查清单**

在 Chrome DevTools 中切换到 375px 宽度，逐页检查：
- [ ] /tests (刷题首页) — 无水平溢出，卡片全宽
- [ ] /tests/session (答题页) — 全屏沉浸，底栏隐藏
- [ ] /courses (课程中心) — 课程卡片适配
- [ ] /course/:id (视频播放) — 全屏播放，底栏隐藏
- [ ] /knowledge-map (知识图谱) — 画布可触摸缩放
- [ ] /exams (密卷页面) — 双 Tab 可用，教师工作流完整
- [ ] /profile (个人页) — 内容区正常
- [ ] 管理后台 — 表格横向滚动

- [ ] **Step 3: 修复检查中发现的问题**

- [ ] **Step 4: Final commit**

```bash
git add -A  # 仅前端文件
git commit -m "chore: final mobile responsive verification and fixes"
```
