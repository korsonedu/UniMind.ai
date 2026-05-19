import React, { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Card } from '@/components/ui/card';
import { EmptyState } from '@/components/EmptyState';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { Checkbox } from '@/components/ui/checkbox';
import { Switch } from '@/components/ui/switch';
import { ScrollArea } from '@/components/ui/scroll-area';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from '@/components/ui/dialog';
import { Loader2, RefreshCw, RotateCcw, Sparkles, Swords, CheckCircle2, XCircle, Trash2 } from 'lucide-react';
import api from '@/lib/api';
import { formatApiErrorToast } from '@/lib/apiError';
import { useDebouncedValue } from '@/lib/useDebouncedValue';
import { cn } from '@/lib/utils';
import { toast } from 'sonner';

type TaskStatus = 'draft' | 'pending' | 'running' | 'review' | 'completed' | 'failed' | 'cancelled';
type TaskType = 'ai_parse' | 'ai_generate' | 'bulk_import' | 'course_publish' | 'article_publish' | 'other';

type PipelineTask = {
  id: number;
  task_type: TaskType;
  task_type_display: string;
  status: TaskStatus;
  status_display: string;
  title: string;
  description: string;
  progress: number;
  payload: Record<string, unknown>;
  result: Record<string, unknown>;
  error_message: string;
  created_by_username: string;
  created_at: string;
  updated_at: string;
  started_at?: string | null;
  finished_at?: string | null;
};

type PipelineMetrics = {
  window_days: number;
  overview: {
    total: number; completed: number; failed: number; running: number;
    review: number; pending: number; cancelled: number; draft: number;
    completion_rate: number; fail_rate: number;
  };
  pipeline_quality: {
    tasks_with_pipeline: number; schema_ok_rate: number;
    review_reject_rate: number; avg_author_windows: number;
    avg_author_candidates: number; avg_review_passed: number;
  };
  top_errors: Array<{ error: string; count: number }>;
  daily: Array<{ date: string; total: number; completed: number; failed: number }>;
};

type KnowledgePoint = { id: number; name: string; level: string; parent_name?: string };

const STATUS_OPTIONS: Array<{ value: TaskStatus | 'all' }> = [
  { value: 'all' }, { value: 'pending' }, { value: 'running' },
  { value: 'review' }, { value: 'completed' }, { value: 'failed' },
  { value: 'cancelled' }, { value: 'draft' },
];

const TYPE_OPTIONS: Array<{ value: TaskType | 'all' }> = [
  { value: 'all' }, { value: 'ai_parse' }, { value: 'ai_generate' },
  { value: 'bulk_import' }, { value: 'other' },
];

const statusBadgeClass = (status: TaskStatus) => {
  if (status === 'completed') return 'bg-emerald-50 text-emerald-700 border-emerald-200';
  if (status === 'failed') return 'bg-red-50 text-red-700 border-red-200';
  if (status === 'running') return 'bg-indigo-50 text-indigo-700 border-indigo-200';
  if (status === 'review') return 'bg-amber-50 text-amber-700 border-amber-200';
  if (status === 'cancelled') return 'bg-slate-100 text-slate-700 border-slate-200';
  return 'bg-slate-50 text-slate-700 border-slate-200';
};

const formatDate = (value?: string | null) => {
  if (!value) return '--';
  try {
    const d = new Date(value);
    const pad = (n: number) => String(n).padStart(2, '0');
    return `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
  } catch { return value; }
};

const toPercentText = (value: number) => `${Number(value || 0).toFixed(1)}%`;

export const PipelinePanel: React.FC = () => {
  const { t } = useTranslation('maintenance');
  const [tasks, setTasks] = useState<PipelineTask[]>([]);
  const [metrics, setMetrics] = useState<PipelineMetrics | null>(null);
  const [reviewTasks, setReviewTasks] = useState<PipelineTask[]>([]);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [statusFilter, setStatusFilter] = useState<TaskStatus | 'all'>('all');
  const [typeFilter, setTypeFilter] = useState<TaskType | 'all'>('all');
  const [search, setSearch] = useState('');
  const [updatingMap, setUpdatingMap] = useState<Record<number, boolean>>({});

  // Smart generate state
  const [smartDialogOpen, setSmartDialogOpen] = useState(false);
  const [adversarialMode, setAdversarialMode] = useState(false);
  const [smartKpIds, setSmartKpIds] = useState<number[]>([]);
  const [smartCount, setSmartCount] = useState(2);
  const [smartDifficulty, setSmartDifficulty] = useState('normal');
  const [smartTypes, setSmartTypes] = useState<string[]>(['objective', 'subjective:noun', 'subjective:short']);
  const [smartTaskName, setSmartTaskName] = useState('');
  const [knowledgePoints, setKnowledgePoints] = useState<KnowledgePoint[]>([]);
  const [loadingKps, setLoadingKps] = useState(false);
  const [smartSubmitting, setSmartSubmitting] = useState(false);
  const [previewQuestions, setPreviewQuestions] = useState<any[] | null>(null);
  const [selectedPreviewIds, setSelectedPreviewIds] = useState<Set<number>>(new Set());

  // Review action state
  const [reviewingMap, setReviewingMap] = useState<Record<number, boolean>>({});
  const [previewTask, setPreviewTask] = useState<PipelineTask | null>(null);

  const debouncedSearch = useDebouncedValue(search.trim(), 400);

  // ── Label helpers ──

  const statusLabel = (s: string): string => {
    const map: Record<string, string> = {
      all: t('pipeline.statusAll'), pending: t('pipeline.statusPending'), running: t('pipeline.statusRunning'),
      review: t('pipeline.statusReview'), completed: t('pipeline.statusCompleted'), failed: t('pipeline.statusFailed'),
      cancelled: t('pipeline.statusCancelled'), draft: t('pipeline.statusDraft'),
    };
    return map[s] || s;
  };

  const typeLabel = (s: string): string => {
    const map: Record<string, string> = {
      all: t('pipeline.typeAll'), ai_parse: t('pipeline.typeAiParse'), ai_generate: t('pipeline.typeAiGenerate'),
      bulk_import: t('pipeline.typeBulkImport'), other: t('pipeline.typeOther'),
    };
    return map[s] || s;
  };

  const getTypeLabel = (q: any): string => {
    const Q_TYPE_MAP: Record<string, string> = {
      objective: t('pipeline.qTypeObjective'),
      subjective: t('pipeline.qTypeSubjective'),
      noun: t('pipeline.qTypeNoun'),
      short: t('pipeline.qTypeShort'),
      essay: t('pipeline.qTypeEssay'),
      calculate: t('pipeline.qTypeCalculate'),
      'subjective:noun': t('pipeline.qTypeNoun'),
      'subjective:short': t('pipeline.qTypeShort'),
      'subjective:essay': t('pipeline.qTypeEssay'),
      'subjective:calculate': t('pipeline.qTypeCalculate'),
    };
    const sub = Q_TYPE_MAP[q.subjective_type];
    if (sub && q.q_type !== 'objective') return sub;
    const cqt = Q_TYPE_MAP[q.question_type];
    if (cqt) return cqt;
    const qt = Q_TYPE_MAP[q.q_type] || Q_TYPE_MAP[q.type];
    if (qt) return qt;
    return q.subjective_type || q.question_type || q.q_type || q.type || '?';
  };

  const diffLabel = (s?: string): string => {
    if (!s) return '?';
    const map: Record<string, string> = {
      entry: t('pipeline.difficultyEntry'), easy: t('pipeline.difficultyEasy'),
      normal: t('pipeline.difficultyNormal'), hard: t('pipeline.difficultyHard'),
      extreme: t('pipeline.difficultyExtreme'), mixed: t('pipeline.difficultyMixed'),
    };
    return map[s] || s;
  };

  const qTypeBadgeLabel = (type: string): string => {
    const map: Record<string, string> = {
      objective: t('pipeline.qTypeObjective'),
      'subjective:noun': t('pipeline.qTypeNoun'),
      'subjective:short': t('pipeline.qTypeShort'),
      'subjective:essay': t('pipeline.qTypeEssay'),
      'subjective:calculate': t('pipeline.qTypeCalculate'),
    };
    return map[type] || type;
  };

  const fetchTasks = useCallback(async (targetPage: number) => {
    setLoading(true);
    try {
      const [res, metricsRes, reviewRes] = await Promise.all([
        api.get('/quizzes/admin/pipeline-tasks/', {
          params: { page: targetPage, page_size: 20, status: statusFilter, task_type: typeFilter, search: debouncedSearch },
        }),
        api.get('/quizzes/admin/pipeline-metrics/', { params: { days: 14 } }),
        api.get('/quizzes/admin/pipeline-review/'),
      ]);
      setTasks((res.data?.results || []) as PipelineTask[]);
      setMetrics((metricsRes.data || null) as PipelineMetrics | null);
      setReviewTasks((reviewRes.data?.results || []) as PipelineTask[]);
      setPage(res.data?.page || targetPage);
      setTotalPages(res.data?.total_pages || 1);
    } catch (e) {
      toast.error(formatApiErrorToast(e, t('pipeline.loadFailed')));
    } finally {
      setLoading(false);
    }
  }, [debouncedSearch, statusFilter, typeFilter, t]);

  // 过滤器/搜索词变化时回到第 1 页重新加载
  useEffect(() => { fetchTasks(1); }, [debouncedSearch, statusFilter, typeFilter]);

  const handleRetryTask = async (taskId: number) => {
    setUpdatingMap((prev) => ({ ...prev, [taskId]: true }));
    try {
      await api.post(`/quizzes/admin/pipeline-tasks/${taskId}/retry/`);
      toast.success(t('pipeline.retryCreated'));
      fetchTasks(1);
    } catch (e) {
      toast.error(formatApiErrorToast(e, t('pipeline.retryFailed')));
    } finally {
      setUpdatingMap((prev) => ({ ...prev, [taskId]: false }));
    }
  };

  const handleDeleteTask = async (taskId: number) => {
    if (!confirm(t('pipeline.deleteConfirm'))) return;
    setUpdatingMap((prev) => ({ ...prev, [taskId]: true }));
    try {
      await api.delete(`/quizzes/admin/pipeline-tasks/${taskId}/`);
      toast.success(t('pipeline.taskDeleted'));
      fetchTasks(1);
    } catch (e) {
      toast.error(formatApiErrorToast(e, t('pipeline.deleteFailed')));
    } finally {
      setUpdatingMap((prev) => ({ ...prev, [taskId]: false }));
    }
  };

  // ── Smart Generate ──────────────────────────────────────────

  const fetchKnowledgePoints = useCallback(async () => {
    setLoadingKps(true);
    try {
      const res = await api.get('/quizzes/knowledge-points/');
      const raw = res.data?.results || res.data || [];
      const items = Array.isArray(raw) ? raw : [];

      const flat: KnowledgePoint[] = [];
      const walk = (nodes: any[], parentName?: string) => {
        for (const it of nodes) {
          flat.push({ id: Number(it.id), name: it.name, level: it.level, parent_name: parentName });
          if (it.children?.length) walk(it.children, it.name);
        }
      };
      // 如果数据是嵌套树结构则递归展开，否则直接按 level 过滤
      if (items.length > 0 && items[0].children !== undefined) {
        walk(items);
      } else {
        items.forEach((it: any) => flat.push({ id: Number(it.id), name: it.name, level: it.level }));
      }
      // 仅保留 level='kp' 的叶子考点
      setKnowledgePoints(flat.filter((kp) => kp.level === 'kp'));
    } catch (e) {
      toast.error(formatApiErrorToast(e, t('pipeline.loadKpFailed')));
    } finally { setLoadingKps(false); }
  }, [t]);

  const handleOpenGenerateDialog = () => {
    setPreviewQuestions(null);
    setSelectedPreviewIds(new Set());
    setSmartTaskName('');
    setSmartDialogOpen(true);
    fetchKnowledgePoints();
  };

  const handleSubmitSmartGenerate = async () => {
    if (smartKpIds.length === 0) return toast.error(t('pipeline.pleaseSelectKp'));
    setSmartSubmitting(true);
    toast.info(t('pipeline.aiGenerating'));
    try {
      const res = await api.post('/quizzes/ai-smart-generate-preview/', {
        kp_ids: smartKpIds, count: smartCount,
        difficulty_level: smartDifficulty, types: smartTypes,
      }, { timeout: 180000 });
      const data = res.data;
      const questions = data.questions || [];
      const passed = data.pipeline?.review_passed || 0;
      const rejected = data.pipeline?.review_rejected || 0;
      if (questions.length > 0) {
        setPreviewQuestions(questions);
        setSelectedPreviewIds(new Set(questions.map((_: any, i: number) => i)));
        toast.success(t('pipeline.generatedResult', { total: questions.length, passed, rejected }));
      } else {
        toast.error(t('pipeline.aiNoValidQuestions'));
      }
      fetchTasks(1);
    } catch (e) {
      toast.error(formatApiErrorToast(e, t('pipeline.aiGenerateFailed')));
    } finally {
      setSmartSubmitting(false);
    }
  };

  const handleSubmitAdversarial = async () => {
    if (smartKpIds.length === 0) return toast.error(t('pipeline.pleaseSelectKp'));
    setSmartSubmitting(true);
    try {
      const res = await api.post('/quizzes/admin/adversarial-pipeline/', {
        kp_ids: smartKpIds,
        questions_per_kp: smartCount,
        title: smartTaskName.trim() || '',
        types: smartTypes,
      });
      toast.success(t('pipeline.adversarialSubmitted', { taskId: res.data.task_id }));
      setSmartDialogOpen(false);
      setSmartKpIds([]);
      fetchTasks(1);
    } catch (e) {
      toast.error(formatApiErrorToast(e, t('pipeline.adversarialStartFailed')));
    } finally {
      setSmartSubmitting(false);
    }
  };

  // ── Review Actions ──────────────────────────────────────────

  const handleReviewAction = async (taskId: number, action: 'approve' | 'reject') => {
    setReviewingMap((prev) => ({ ...prev, [taskId]: true }));
    try {
      const res = await api.post(`/quizzes/admin/pipeline-review/${taskId}/`, { action });
      toast.success(action === 'approve'
        ? t('pipeline.approvedImported', { count: (res.data as any).questions_created || 0 })
        : t('pipeline.rejectedDone'));
      fetchTasks(1);
    } catch (e) {
      toast.error(formatApiErrorToast(e, t('pipeline.actionFailed')));
    } finally {
      setReviewingMap((prev) => ({ ...prev, [taskId]: false }));
    }
  };

  return (
    <div className="space-y-6 text-left">
      <div className="flex items-center gap-3 mb-2">
        <Sparkles className="h-5 w-5 text-indigo-600" />
        <h2 className="text-xl font-black tracking-tight">{t('pipeline.title')}</h2>
      </div>

      {/* ── Metrics ── */}
      <Card className="p-6 rounded-3xl border-none shadow-sm bg-gradient-to-br from-white to-slate-50 space-y-4">
        <div className="flex items-center justify-between">
          <p className="text-[11px] font-bold uppercase tracking-widest text-black/40">{t('pipeline.qualityOverview')}</p>
          <Badge className="bg-slate-100 text-slate-700 border-none text-[10px] font-black rounded-lg">
            Author → Reviewer → Classifier
          </Badge>
        </div>
        <div className="grid grid-cols-2 lg:grid-cols-6 gap-3">
          {[
            { label: t('pipeline.totalTasks'), value: metrics?.overview?.total ?? 0, color: 'bg-white border-black/[0.04]', textColor: 'text-slate-900', subColor: 'text-black/40' },
            { label: t('pipeline.completionRate'), value: toPercentText(metrics?.overview?.completion_rate ?? 0), color: 'bg-emerald-50 border-emerald-100', textColor: 'text-emerald-700', subColor: 'text-emerald-700/70' },
            { label: t('pipeline.failRate'), value: toPercentText(metrics?.overview?.fail_rate ?? 0), color: 'bg-red-50 border-red-100', textColor: 'text-red-700', subColor: 'text-red-700/70' },
            { label: t('pipeline.schemaOkRate'), value: toPercentText(metrics?.pipeline_quality?.schema_ok_rate ?? 0), color: 'bg-indigo-50 border-indigo-100', textColor: 'text-indigo-700', subColor: 'text-indigo-700/70' },
            { label: t('pipeline.reviewRejectRate'), value: toPercentText(metrics?.pipeline_quality?.review_reject_rate ?? 0), color: 'bg-amber-50 border-amber-100', textColor: 'text-amber-700', subColor: 'text-amber-700/70' },
            { label: t('pipeline.pendingReview'), value: metrics?.overview?.review ?? 0, color: 'bg-slate-100 border-slate-200', textColor: 'text-slate-800', subColor: 'text-slate-600' },
          ].map((m) => (
            <div key={m.label} className={`rounded-2xl ${m.color} border p-3`}>
              <p className={`text-[10px] font-bold uppercase ${m.subColor}`}>{m.label}</p>
              <p className={`text-xl font-black ${m.textColor} mt-1`}>{m.value}</p>
            </div>
          ))}
        </div>
      </Card>

      {/* ── Pipeline Trigger ── */}
      <Card className="p-6 rounded-3xl border border-indigo-200 shadow-sm bg-gradient-to-br from-indigo-50 to-white">
        <div className="flex flex-col lg:flex-row items-start lg:items-center justify-between gap-4">
          <div className="max-w-xl">
            <p className="text-sm font-bold">{t('pipeline.aiSmartGenerate')}</p>
            <p className="text-[11px] text-muted-foreground mt-1">
              {t('pipeline.smartGenerateDesc')}
              <b className="text-indigo-600">{t('pipeline.quickMode')}</b>
              {t('pipeline.quickModeDesc')}
              <b className="text-rose-600">{t('pipeline.adversarialMode')}</b>
              {t('pipeline.adversarialModeDesc')}
            </p>
          </div>
          <Button onClick={handleOpenGenerateDialog} className="rounded-xl bg-indigo-600 hover:bg-indigo-700 text-white h-11 px-6 text-xs font-bold shrink-0">
            <Sparkles className="h-4 w-4 mr-2" />{t('pipeline.aiGenerateBtn')}
          </Button>
        </div>
      </Card>

      {/* ── Review Queue ── */}
      {reviewTasks.length > 0 && (
        <Card className="p-6 rounded-3xl border border-amber-200 shadow-sm bg-gradient-to-br from-amber-50 to-white space-y-4">
          <div className="flex items-center gap-2">
            <Badge className="bg-amber-100 text-amber-700 border-none text-[10px] font-black rounded-lg">{t('pipeline.itemsPendingReview', { count: reviewTasks.length })}</Badge>
            <p className="text-sm font-bold">{t('pipeline.reviewQueue')}</p>
          </div>
          <ScrollArea className="h-64">
            <div className="space-y-2">
              {reviewTasks.map((task) => {
                const questions = (task.result as any)?.questions || [];
                const summary = (task.result as any)?.summary || {};
                const stages = (task.result as any)?.stages || [];
                return (
                  <div key={task.id} className="p-4 bg-white rounded-2xl border border-amber-100 space-y-2">
                    <div className="flex items-center justify-between gap-4">
                      <div onClick={() => setPreviewTask(task)} className="min-w-0 text-left hover:text-indigo-600 transition-colors cursor-pointer">
                        <p className="text-xs font-bold truncate">{task.title}</p>
                        <p className="text-[10px] text-muted-foreground mt-1">
                          {t('pipeline.questionSummary', {
                            count: questions.length,
                            score: typeof summary.avg_quality_score === 'number' ? summary.avg_quality_score.toFixed(3) : '--',
                            date: formatDate(task.created_at),
                          })}
                        </p>
                      </div>
                      <div className="flex gap-2 shrink-0">
                        <Button onClick={() => setPreviewTask(task)} variant="outline" className="h-8 rounded-lg text-[10px] font-bold px-2">{t('pipeline.preview')}</Button>
                        <Button
                          onClick={() => handleReviewAction(task.id, 'approve')}
                          disabled={reviewingMap[task.id]}
                          className="h-8 rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white text-[10px] font-bold px-3"
                        >
                          {reviewingMap[task.id] ? <Loader2 className="h-3 w-3 animate-spin" /> : <CheckCircle2 className="h-3 w-3 mr-1" />}
                          {t('pipeline.approveImport')}
                      </Button>
                      <Button
                        onClick={() => handleReviewAction(task.id, 'reject')}
                        disabled={reviewingMap[task.id]}
                        variant="outline"
                        className="h-8 rounded-lg border-red-200 text-red-700 hover:bg-red-50 text-[10px] font-bold px-3"
                      >
                        <XCircle className="h-3 w-3 mr-1" />{t('pipeline.reject')}
                      </Button>
                    </div>
                  </div>
                  </div>
                );
              })}
            </div>
          </ScrollArea>
        </Card>
      )}

      {/* ── Task List ── */}
      <Card className="p-6 rounded-3xl border-none shadow-sm bg-white space-y-4">
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-3 items-end">
          <div className="lg:col-span-3">
            <Label className="text-[11px] font-bold uppercase opacity-40">{t('pipeline.statusFilter')}</Label>
            <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value as TaskStatus | 'all')}
              className="w-full bg-apple-gray-50 border-none h-10 rounded-xl px-3 text-xs font-bold mt-1">
              {STATUS_OPTIONS.map((item) => (<option key={item.value} value={item.value}>{statusLabel(item.value)}</option>))}
            </select>
          </div>
          <div className="lg:col-span-3">
            <Label className="text-[11px] font-bold uppercase opacity-40">{t('pipeline.typeFilter')}</Label>
            <select value={typeFilter} onChange={(e) => setTypeFilter(e.target.value as TaskType | 'all')}
              className="w-full bg-apple-gray-50 border-none h-10 rounded-xl px-3 text-xs font-bold mt-1">
              {TYPE_OPTIONS.map((item) => (<option key={item.value} value={item.value}>{typeLabel(item.value)}</option>))}
            </select>
          </div>
          <div className="lg:col-span-4">
            <Label className="text-[11px] font-bold uppercase opacity-40">{t('pipeline.keyword')}</Label>
            <Input value={search} onChange={(e) => setSearch(e.target.value)}
              className="bg-apple-gray-50 border-none h-10 rounded-xl font-bold text-xs mt-1" placeholder={t('pipeline.searchPlaceholder')} />
          </div>
          <div className="lg:col-span-2">
            <Button onClick={() => fetchTasks(1)} variant="outline" className="h-10 rounded-xl text-xs font-bold w-full">
              <RefreshCw className={loading ? 'h-3.5 w-3.5 animate-spin mr-1' : 'h-3.5 w-3.5 mr-1'} />{t('pipeline.refresh')}
            </Button>
          </div>
        </div>

        {loading ? (
          <div className="py-14 flex justify-center"><Loader2 className="h-7 w-7 animate-spin text-muted-foreground/40" /></div>
        ) : tasks.length === 0 ? (
          <EmptyState title={t('pipeline.noTasks')} className="py-6" />
        ) : (
          <div className="space-y-2">
            {tasks.map((task) => {
              const pipeline = (task.result?.pipeline || null) as Record<string, any> | null;
              return (
                <div key={task.id} className="p-4 bg-apple-gray-50/50 rounded-2xl border border-black/[0.03] space-y-2">
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <p className="text-sm font-bold truncate">{task.title}</p>
                      <p className="text-[11px] text-muted-foreground mt-1">
                        #{task.id} · {task.task_type_display} · {task.created_by_username} · {formatDate(task.created_at)}
                      </p>
                    </div>
                    <Badge variant="outline" className={statusBadgeClass(task.status)}>{task.status_display}</Badge>
                  </div>
                  {pipeline ? (
                    <div className="flex flex-wrap gap-1.5">
                      <Badge className="bg-indigo-100 text-indigo-700 border-none text-[10px] font-black rounded-lg">{t('pipeline.windowLabel', { count: Number(pipeline.author_windows || 0) })}</Badge>
                      <Badge className="bg-sky-100 text-sky-700 border-none text-[10px] font-black rounded-lg">{t('pipeline.candidateLabel', { count: Number(pipeline.author_candidates || 0) })}</Badge>
                      <Badge className="bg-emerald-100 text-emerald-700 border-none text-[10px] font-black rounded-lg">{t('pipeline.passedLabel', { count: Number(pipeline.review_passed || 0) })}</Badge>
                      <Badge className="bg-amber-100 text-amber-700 border-none text-[10px] font-black rounded-lg">{t('pipeline.rejectedLabel', { count: Number(pipeline.review_rejected || 0) })}</Badge>
                    </div>
                  ) : null}
                  <div className="flex justify-end gap-2">
                    {(task.status === 'failed' || task.status === 'cancelled') && (
                      <Button onClick={() => handleRetryTask(task.id)} disabled={updatingMap[task.id]}
                        variant="outline" size="sm" className="h-7 rounded-lg text-[10px] font-bold">
                        {updatingMap[task.id] ? <Loader2 className="h-3 w-3 animate-spin mr-1" /> : <RotateCcw className="h-3 w-3 mr-1" />}{t('pipeline.retry')}
                      </Button>
                    )}
                    <Button onClick={() => handleDeleteTask(task.id)} disabled={updatingMap[task.id]}
                      variant="outline" size="sm" className="h-7 rounded-lg text-[10px] font-bold text-red-500 hover:text-red-700 hover:bg-red-50 border-red-200">
                      {updatingMap[task.id] ? <Loader2 className="h-3 w-3 animate-spin mr-1" /> : <Trash2 className="h-3 w-3 mr-1" />}{t('pipeline.delete')}
                    </Button>
                  </div>
                </div>
              );
            })}
          </div>
        )}

        <div className="flex items-center justify-between pt-2">
          <p className="text-[11px] text-muted-foreground">{t('pipeline.pageInfo', { page, total: Math.max(totalPages, 1) })}</p>
          <div className="flex gap-2">
            <Button variant="outline" disabled={page <= 1 || loading} onClick={() => fetchTasks(page - 1)} className="h-8 rounded-lg text-[11px] font-bold">{t('pipeline.prevPage')}</Button>
            <Button variant="outline" disabled={page >= totalPages || loading} onClick={() => fetchTasks(page + 1)} className="h-8 rounded-lg text-[11px] font-bold">{t('pipeline.nextPage')}</Button>
          </div>
        </div>
      </Card>

      {/* ── Generate Dialog ── */}
      <Dialog open={smartDialogOpen} onOpenChange={(o) => { if (!o) { setSmartDialogOpen(false); setPreviewQuestions(null); setSelectedPreviewIds(new Set()); } }}>
        <DialogContent className={previewQuestions ? 'max-w-3xl max-h-[85vh] overflow-y-auto' : 'max-w-2xl'}>
          <DialogHeader>
            <DialogTitle>{adversarialMode ? t('pipeline.deepAdversarialTitle') : t('pipeline.quickGenerateTitle')}</DialogTitle>
            <DialogDescription>
              {adversarialMode
                ? t('pipeline.deepAdversarialDesc')
                : t('pipeline.quickGenerateDesc')}
            </DialogDescription>
          </DialogHeader>

          {previewQuestions ? (
            <div className="space-y-4 py-2">
              <div className="flex items-center justify-between">
                <p className="text-xs font-bold text-emerald-600">{t('pipeline.candidateSummary', { total: previewQuestions.length, selected: selectedPreviewIds.size })}</p>
                <div className="flex gap-2">
                  <Button variant="ghost" size="sm" onClick={() => setSelectedPreviewIds(new Set(previewQuestions.map((_: any, i: number) => i)))}
                    className="h-7 rounded-lg text-[10px] font-bold">{t('pipeline.selectAll')}</Button>
                  <Button variant="ghost" size="sm" onClick={() => setSelectedPreviewIds(new Set())}
                    className="h-7 rounded-lg text-[10px] font-bold">{t('pipeline.clearAll')}</Button>
                </div>
              </div>
              <ScrollArea className="h-[420px] rounded-xl border bg-slate-50 p-4">
                <div className="space-y-3">
                  {previewQuestions.map((q: any, i: number) => {
                    const typeLabel = getTypeLabel(q);
                    return (
                    <Card key={i} className={cn('p-4 rounded-2xl border-none shadow-sm space-y-2 transition-all', selectedPreviewIds.has(i) ? 'bg-white ring-2 ring-emerald-200' : 'bg-white/60 opacity-70')}>
                      <div className="flex items-center gap-2">
                        <Checkbox checked={selectedPreviewIds.has(i)}
                          onCheckedChange={(c) => setSelectedPreviewIds(prev => { const next = new Set(prev); c ? next.add(i) : next.delete(i); return next; })} />
                        <Badge className="text-[9px] font-bold rounded-lg">{i + 1}</Badge>
                        <Badge className="bg-slate-100 text-slate-700 border-none text-[9px] font-bold rounded-lg">{typeLabel}</Badge>
                        {q.difficulty_level && <Badge className="bg-indigo-100 text-indigo-700 border-none text-[9px] font-bold rounded-lg">{diffLabel(q.difficulty_level)}</Badge>}
                        {q.kp_name && <span className="text-[9px] text-muted-foreground ml-auto">{q.kp_name}</span>}
                      </div>
                      <p className="text-xs font-bold">{q.question || q.text}</p>
                      {q.options && typeof q.options === 'object' && Object.keys(q.options).length > 0 && (
                        <div className="grid grid-cols-2 gap-1">
                          {Object.entries(q.options as Record<string, string>).map(([k, v]) => (
                            <span key={k} className="text-[10px] text-slate-500"><b>{k}.</b> {v as string}</span>
                          ))}
                        </div>
                      )}
                      <div className="flex gap-3 text-[10px]">
                        {q.answer && <span className="text-emerald-600 font-bold">{t('pipeline.answer')}: {q.answer}</span>}
                        {q.correct_answer && <span className="text-emerald-600 font-bold">{t('pipeline.answer')}: {q.correct_answer}</span>}
                      </div>
                    </Card>
                  );})}
                </div>
              </ScrollArea>
              <DialogFooter>
                <Button variant="outline" onClick={() => { setPreviewQuestions(null); setSelectedPreviewIds(new Set()); setSmartKpIds([]); setSmartDialogOpen(false); }}
                  className="rounded-xl h-11 px-6 text-xs font-bold border-red-200 text-red-600 hover:bg-red-50">
                  <XCircle className="h-4 w-4 mr-2" />{t('pipeline.discardAll')}
                </Button>
                <Button onClick={async () => {
                  const selected = previewQuestions.filter((_: any, i: number) => selectedPreviewIds.has(i));
                  if (selected.length === 0) return toast.error(t('pipeline.pleaseSelectOne'));
                  try {
                    await api.post('/quizzes/ai-bulk-import/', { questions: selected, kp_id: smartKpIds[0] || null });
                    toast.success(t('pipeline.importedSuccess', { count: selected.length }));
                    setPreviewQuestions(null); setSelectedPreviewIds(new Set()); setSmartKpIds([]); setSmartDialogOpen(false); fetchTasks(1);
                  } catch (e) { toast.error(formatApiErrorToast(e, t('pipeline.importFailed'))); }
                }} disabled={selectedPreviewIds.size === 0}
                  className="rounded-xl bg-emerald-600 hover:bg-emerald-700 text-white h-11 px-6 text-xs font-bold">
                  <CheckCircle2 className="h-4 w-4 mr-2" />{t('pipeline.importSelected', { count: selectedPreviewIds.size })}
                </Button>
              </DialogFooter>
            </div>
          ) : (
            <div className="space-y-4 py-2">
              {/* ── 任务名 ── */}
              <div className="space-y-1.5">
                <Label className="text-[11px] font-bold uppercase opacity-40">{t('pipeline.taskNameLabel')}</Label>
                <Input value={smartTaskName} onChange={(e) => setSmartTaskName(e.target.value)}
                  placeholder={t('pipeline.taskNamePlaceholder')}
                  className="bg-apple-gray-50 border-none h-10 rounded-xl font-bold text-xs" />
              </div>

              {/* ── 质量模式开关 ── */}
              <div className="flex items-center justify-between p-4 rounded-2xl border border-border bg-muted/30">
                <div>
                  <p className="text-sm font-bold">{adversarialMode ? t('pipeline.deepAdversarialReview') : t('pipeline.quickGenerate')}</p>
                  <p className="text-[10px] text-muted-foreground mt-0.5">
                    {adversarialMode
                      ? t('pipeline.adversarialSwitchDesc')
                      : t('pipeline.quickSwitchDesc')}
                  </p>
                </div>
                <Switch checked={adversarialMode} onCheckedChange={setAdversarialMode} />
              </div>

              <div className={adversarialMode ? 'grid grid-cols-2 gap-3' : 'grid grid-cols-3 gap-3'}>
                <div className="space-y-1.5">
                  <Label className="text-[11px] font-bold uppercase opacity-40">{t('pipeline.countPerKp')}</Label>
                  <Input type="number" min={1} max={adversarialMode ? 10 : 5} value={smartCount}
                    onChange={(e) => setSmartCount(Math.max(1, parseInt(e.target.value) || 1))}
                    className="bg-apple-gray-50 border-none h-10 rounded-xl font-bold text-xs" />
                </div>
                {!adversarialMode && (
                  <div className="space-y-1.5">
                    <Label className="text-[11px] font-bold uppercase opacity-40">{t('pipeline.targetDifficulty')}</Label>
                    <select value={smartDifficulty} onChange={(e) => setSmartDifficulty(e.target.value)}
                      className="w-full bg-apple-gray-50 border-none h-10 rounded-xl px-3 text-xs font-bold">
                      <option value="entry">{t('pipeline.difficultyEntry')}</option><option value="easy">{t('pipeline.difficultyEasy')}</option>
                      <option value="normal">{t('pipeline.difficultyNormal')}</option><option value="hard">{t('pipeline.difficultyHard')}</option>
                      <option value="mixed">{t('pipeline.difficultyMixed')}</option>
                    </select>
                  </div>
                )}
                <div className="space-y-1.5">
                  <Label className="text-[11px] font-bold uppercase opacity-40">{t('pipeline.questionType')}</Label>
                  <div className="flex flex-wrap gap-1">
                    {['objective', 'subjective:noun', 'subjective:short', 'subjective:essay', 'subjective:calculate'].map((type) => (
                      <Badge key={type} onClick={() => setSmartTypes((prev) => prev.includes(type) ? prev.filter((x) => x !== type) : [...prev, type])}
                        className={`cursor-pointer text-[10px] font-bold rounded-lg border ${smartTypes.includes(type) ? 'bg-indigo-100 text-indigo-700 border-indigo-200' : 'bg-slate-100 text-slate-500 border-slate-200'}`}>
                        {qTypeBadgeLabel(type)}
                      </Badge>
                    ))}
                  </div>
                </div>
              </div>
              <div className="space-y-1.5">
                <Label className="text-[11px] font-bold uppercase opacity-40">{t('pipeline.selectKp')}</Label>
                {loadingKps ? (
                  <div className="py-8 flex justify-center"><Loader2 className="h-5 w-5 animate-spin text-muted-foreground/40" /></div>
                ) : (
                  <ScrollArea className="h-64 rounded-xl border bg-apple-gray-50 p-2">
                    {knowledgePoints.map((kp) => (
                      <label key={kp.id} className="flex items-center gap-3 p-2 rounded-lg hover:bg-white cursor-pointer">
                        <Checkbox checked={smartKpIds.includes(kp.id)}
                          onCheckedChange={(c) => setSmartKpIds((prev) => c ? [...prev, kp.id] : prev.filter((id) => id !== kp.id))} />
                        <span className="text-xs font-bold">{kp.name}</span>
                        {kp.parent_name && <span className="text-[9px] text-muted-foreground ml-auto truncate max-w-[120px]">{kp.parent_name}</span>}
                      </label>
                    ))}
                    {knowledgePoints.length === 0 && !loadingKps && (
                      <div className="py-8 text-center text-[11px] font-bold text-muted-foreground">{t('pipeline.noLeafKp')}</div>
                    )}
                  </ScrollArea>
                )}
                <p className="text-[10px] text-muted-foreground mt-1">{t('pipeline.selectedKps', { count: smartKpIds.length })}</p>
              </div>
              <DialogFooter>
                <Button variant="outline" onClick={() => setSmartDialogOpen(false)} className="rounded-xl h-11 px-6 text-xs font-bold">{t('commonActions.cancel')}</Button>
                <Button
                  onClick={adversarialMode ? handleSubmitAdversarial : handleSubmitSmartGenerate}
                  disabled={smartKpIds.length === 0 || smartSubmitting}
                  className={adversarialMode
                    ? 'rounded-xl bg-rose-600 hover:bg-rose-700 text-white h-11 px-6 text-xs font-bold'
                    : 'rounded-xl bg-indigo-600 hover:bg-indigo-700 text-white h-11 px-6 text-xs font-bold'}
                >
                  {smartSubmitting ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : adversarialMode ? <Swords className="h-4 w-4 mr-2" /> : <Sparkles className="h-4 w-4 mr-2" />}
                  {smartSubmitting ? t('pipeline.submitting') : adversarialMode ? t('pipeline.submitToQueue') : t('pipeline.generateAndPreview')}
                </Button>
              </DialogFooter>
            </div>
          )}
        </DialogContent>
      </Dialog>

      {/* ── 题目预览 Dialog ── */}
      <Dialog open={!!previewTask} onOpenChange={(o) => !o && setPreviewTask(null)}>
        <DialogContent className="max-w-3xl max-h-[85vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>{previewTask?.title || t('pipeline.questionPreview')}</DialogTitle>
            <DialogDescription>
              {(() => {
                const qs = (previewTask?.result as any)?.questions || [];
                const sm = (previewTask?.result as any)?.summary || {};
                const st = (previewTask?.result as any)?.stages || [];
                return t('pipeline.reviewTaskSummary', {
                  count: qs.length,
                  score: typeof sm.avg_quality_score === 'number' ? sm.avg_quality_score.toFixed(3) : '--',
                  stages: st.length,
                });
              })()}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-2">
            {/* ── ARC 管线流程 ── */}
            {(() => {
              const stages = (previewTask?.result as any)?.stages || [];
              const summary = (previewTask?.result as any)?.summary || {};
              if (stages.length === 0 && !summary.avg_quality_score) return null;
              return (
                <div className="p-4 bg-slate-50 rounded-2xl space-y-3">
                  <p className="text-[10px] font-bold uppercase tracking-widest text-slate-500">{t('pipeline.pipelineFlowArc')}</p>
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                    {/* A - Author */}
                    <div className="p-3 bg-white rounded-xl border border-slate-200 space-y-1">
                      <p className="text-[11px] font-black text-indigo-600">{t('pipeline.authorStage')}</p>
                      <p className="text-[10px] text-slate-500">
                        {t('pipeline.authorGenerated', { count: summary.total_generated || stages.find((s: any) => s.stage === 'author_generated')?.count || '?' })}
                      </p>
                    </div>
                    {/* R - Reviewer */}
                    <div className="p-3 bg-white rounded-xl border border-slate-200 space-y-1">
                      <p className="text-[11px] font-black text-rose-600">{t('pipeline.reviewerStage')}</p>
                      <p className="text-[10px] text-slate-500">
                        {t('pipeline.reviewerScore', { score: typeof summary.avg_quality_score === 'number' ? (summary.avg_quality_score * 100).toFixed(0) : '--' })}
                        {summary.iteration_distribution ? t('pipeline.reviewerIteration', { iteration: JSON.stringify(summary.iteration_distribution) }) : ''}
                      </p>
                    </div>
                    {/* C - Classifier */}
                    <div className="p-3 bg-white rounded-xl border border-slate-200 space-y-1">
                      <p className="text-[11px] font-black text-emerald-600">{t('pipeline.classifierStage')}</p>
                      <p className="text-[10px] text-slate-500">
                        {t('pipeline.classifierDesc')}
                      </p>
                    </div>
                  </div>
                </div>
              );
            })()}

            {/* ── 题目列表 ── */}
            {((previewTask?.result as any)?.questions || []).map((q: any, i: number) => (
              <div key={i} className="p-4 bg-white rounded-2xl border space-y-3">
                {/* 题头 */}
                <div className="flex items-center gap-2">
                  <Badge className="text-[9px] font-bold rounded-lg">{i + 1}</Badge>
                  <Badge className="bg-slate-100 text-slate-700 border-none text-[9px] font-bold rounded-lg">{getTypeLabel(q)}</Badge>
                  <Badge className={cn(
                    'text-[9px] font-bold rounded-lg border-none',
                    q.difficulty_level === 'entry' ? 'bg-emerald-100 text-emerald-700' :
                    q.difficulty_level === 'easy' ? 'bg-sky-100 text-sky-700' :
                    q.difficulty_level === 'normal' ? 'bg-indigo-100 text-indigo-700' :
                    q.difficulty_level === 'hard' ? 'bg-amber-100 text-amber-700' :
                    'bg-red-100 text-red-700'
                  )}>{diffLabel(q.difficulty_level) || '?'}</Badge>
                  {q.review_score != null && (
                    <Badge className={cn('text-[9px] font-bold rounded-lg border-none', q.review_score >= 0.7 ? 'bg-emerald-100 text-emerald-700' : 'bg-red-100 text-red-700')}>
                      {t('pipeline.scoreLabel', { score: Number(q.review_score * 100).toFixed(0) })}
                    </Badge>
                  )}
                  {q.quality_warning && <Badge className="bg-rose-100 text-rose-700 text-[9px] font-bold rounded-lg">{t('pipeline.lowQualityWarning')}</Badge>}
                </div>

                {/* A: Author 出题内容 */}
                <div className="pl-2 border-l-2 border-indigo-200 space-y-1.5">
                  <p className="text-[9px] font-bold uppercase text-indigo-500">{t('pipeline.authorLabel')}</p>
                  <p className="text-xs font-bold">{q.question}</p>
                  {q.options && typeof q.options === 'object' && Object.keys(q.options).length > 0 && (
                    <div className="grid grid-cols-2 gap-1">
                      {Object.entries(q.options as Record<string, string>).map(([k, v]) => (
                        <span key={k} className="text-[10px] text-slate-500"><b>{k}.</b> {v as string}</span>
                      ))}
                    </div>
                  )}
                  <div className="flex gap-3 text-[10px]">
                    {q.answer && <span className="text-emerald-600 font-bold">{t('pipeline.answer')}: {q.answer}</span>}
                    {q.kp_name && <span className="text-slate-400">{t('pipeline.knowledgePoint')}: {q.kp_name}</span>}
                  </div>
                </div>

                {/* R: Reviewer 审查结果 */}
                {(q.review_feedback || q.review_dimensions || q.iteration) && (
                  <div className="pl-2 border-l-2 border-rose-200 space-y-1.5">
                    <div className="flex items-center gap-2">
                      <p className="text-[9px] font-bold uppercase text-rose-500">{t('pipeline.reviewerLabel')}</p>
                      {q.iteration && <span className="text-[9px] text-rose-400">{t('pipeline.iterationPassed', { iteration: q.iteration })}</span>}
                    </div>
                    {q.review_dimensions && (
                      <div className="flex flex-wrap gap-1.5">
                        {Object.entries(q.review_dimensions as Record<string, number>).map(([k, v]) => (
                          <span key={k} className="text-[9px] px-1.5 py-0.5 rounded bg-rose-50 text-rose-700 font-medium">
                            {k}: {typeof v === 'number' ? (v * 100).toFixed(0) : v}%
                          </span>
                        ))}
                      </div>
                    )}
                    {q.review_feedback && <p className="text-[10px] text-slate-500 leading-relaxed">{q.review_feedback}</p>}
                  </div>
                )}

                {/* C: Classifier 分类 */}
                {(q.knowledge_tags?.length > 0 || q.question_type) && (
                  <div className="pl-2 border-l-2 border-emerald-200 space-y-1.5">
                    <p className="text-[9px] font-bold uppercase text-emerald-500">{t('pipeline.classifierLabel')}</p>
                    <div className="flex flex-wrap gap-1.5">
                      {q.question_type && <span className="text-[9px] px-1.5 py-0.5 rounded bg-emerald-50 text-emerald-700 font-medium">{getTypeLabel(q)}</span>}
                      {(q.knowledge_tags || []).map((tag: string) => (
                        <span key={tag} className="text-[9px] px-1.5 py-0.5 rounded bg-slate-100 text-slate-600 font-medium">{tag}</span>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setPreviewTask(null)} className="rounded-xl text-xs font-bold">{t('pipeline.close')}</Button>
            <Button onClick={() => { handleReviewAction(previewTask!.id, 'reject'); setPreviewTask(null); }} disabled={!previewTask || reviewingMap[previewTask.id]} variant="outline" className="rounded-xl border-red-200 text-red-700 text-xs font-bold">
              <XCircle className="h-3.5 w-3.5 mr-1" />{t('pipeline.rejectAll')}
            </Button>
            <Button onClick={() => { handleReviewAction(previewTask!.id, 'approve'); setPreviewTask(null); }} disabled={!previewTask || reviewingMap[previewTask.id]} className="rounded-xl bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-bold">
              <CheckCircle2 className="h-3.5 w-3.5 mr-1" />{t('pipeline.approveImport')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};
