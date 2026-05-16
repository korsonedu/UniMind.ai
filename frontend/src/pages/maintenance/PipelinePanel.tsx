import React, { useCallback, useEffect, useState } from 'react';
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

const STATUS_OPTIONS: Array<{ value: TaskStatus | 'all'; label: string }> = [
  { value: 'all', label: '全部状态' },
  { value: 'pending', label: '待执行' }, { value: 'running', label: '执行中' },
  { value: 'review', label: '待审核' }, { value: 'completed', label: '已完成' },
  { value: 'failed', label: '失败' }, { value: 'cancelled', label: '已取消' },
  { value: 'draft', label: '草稿' },
];

const TYPE_OPTIONS: Array<{ value: TaskType | 'all'; label: string }> = [
  { value: 'all', label: '全部类型' },
  { value: 'ai_parse', label: 'AI 整理解析' },
  { value: 'ai_generate', label: 'AI 智能命题' },
  { value: 'bulk_import', label: '批量题库导入' },
  { value: 'other', label: '其他任务' },
];

const Q_TYPE_CN: Record<string, string> = {
  objective: '客观选择', subjective: '主观题',
  noun: '名词解释', short: '简答', essay: '论述', calculate: '计算',
  'subjective:noun': '名词解释', 'subjective:short': '简答',
  'subjective:essay': '论述', 'subjective:calculate': '计算',
};

function getTypeLabel(q: any): string {
  // subjective_type 直接映射
  const sub = Q_TYPE_CN[q.subjective_type];
  if (sub && q.q_type !== 'objective') return sub;
  // question_type (Classifier) 直接映射
  const cqt = Q_TYPE_CN[q.question_type];
  if (cqt) return cqt;
  // q_type 直接映射
  const qt = Q_TYPE_CN[q.q_type] || Q_TYPE_CN[q.type];
  if (qt) return qt;
  // fallback
  return q.subjective_type || q.question_type || q.q_type || q.type || '?';
}
const DIFF_CN: Record<string, string> = {
  entry: '入门', easy: '简单', normal: '适当', hard: '困难', extreme: '极限', mixed: '混合',
};

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
      toast.error(formatApiErrorToast(e, '任务中心加载失败'));
    } finally {
      setLoading(false);
    }
  }, [debouncedSearch, statusFilter, typeFilter]);

  // 过滤器/搜索词变化时回到第 1 页重新加载
  useEffect(() => { fetchTasks(1); }, [debouncedSearch, statusFilter, typeFilter]);

  const handleRetryTask = async (taskId: number) => {
    setUpdatingMap((prev) => ({ ...prev, [taskId]: true }));
    try {
      await api.post(`/quizzes/admin/pipeline-tasks/${taskId}/retry/`);
      toast.success('已创建重试任务');
      fetchTasks(1);
    } catch (e) {
      toast.error(formatApiErrorToast(e, '重试失败'));
    } finally {
      setUpdatingMap((prev) => ({ ...prev, [taskId]: false }));
    }
  };

  const handleDeleteTask = async (taskId: number) => {
    if (!confirm('确定删除此任务？此操作不可撤销。')) return;
    setUpdatingMap((prev) => ({ ...prev, [taskId]: true }));
    try {
      await api.delete(`/quizzes/admin/pipeline-tasks/${taskId}/`);
      toast.success('任务已删除');
      fetchTasks(1);
    } catch (e) {
      toast.error(formatApiErrorToast(e, '删除失败'));
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
      toast.error(formatApiErrorToast(e, '加载知识点失败'));
    } finally { setLoadingKps(false); }
  }, []);

  const handleOpenGenerateDialog = () => {
    setPreviewQuestions(null);
    setSelectedPreviewIds(new Set());
    setSmartTaskName('');
    setSmartDialogOpen(true);
    fetchKnowledgePoints();
  };

  const handleSubmitSmartGenerate = async () => {
    if (smartKpIds.length === 0) return toast.error('请选择知识点');
    setSmartSubmitting(true);
    toast.info('AI 正在生成题目，请耐心等待…');
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
        toast.success(`生成 ${questions.length} 道题，通过 ${passed} 题，驳回 ${rejected} 题`);
      } else {
        toast.error('AI 未生成有效题目，请尝试调整参数');
      }
      fetchTasks(1);
    } catch (e) {
      toast.error(formatApiErrorToast(e, 'AI 生成失败'));
    } finally {
      setSmartSubmitting(false);
    }
  };

  const handleSubmitAdversarial = async () => {
    if (smartKpIds.length === 0) return toast.error('请选择知识点');
    setSmartSubmitting(true);
    try {
      const res = await api.post('/quizzes/admin/adversarial-pipeline/', {
        kp_ids: smartKpIds,
        questions_per_kp: smartCount,
        title: smartTaskName.trim() || '',
        types: smartTypes,
      });
      toast.success(`对抗性出题已提交，任务 #${res.data.task_id}。完成后将进入审核队列`);
      setSmartDialogOpen(false);
      setSmartKpIds([]);
      fetchTasks(1);
    } catch (e) {
      toast.error(formatApiErrorToast(e, '对抗性出题启动失败'));
    } finally {
      setSmartSubmitting(false);
    }
  };

  // ── Review Actions ──────────────────────────────────────────

  const handleReviewAction = async (taskId: number, action: 'approve' | 'reject') => {
    setReviewingMap((prev) => ({ ...prev, [taskId]: true }));
    try {
      const res = await api.post(`/quizzes/admin/pipeline-review/${taskId}/`, { action });
      toast.success(action === 'approve' ? `已批准入库 ${(res.data as any).questions_created || 0} 题` : '已拒绝');
      fetchTasks(1);
    } catch (e) {
      toast.error(formatApiErrorToast(e, '操作失败'));
    } finally {
      setReviewingMap((prev) => ({ ...prev, [taskId]: false }));
    }
  };

  return (
    <div className="space-y-6 text-left">
      <div className="flex items-center gap-3 mb-2">
        <Sparkles className="h-5 w-5 text-indigo-600" />
        <h2 className="text-xl font-black tracking-tight">AI 智能出题中心</h2>
      </div>

      {/* ── Metrics ── */}
      <Card className="p-6 rounded-3xl border-none shadow-sm bg-gradient-to-br from-white to-slate-50 space-y-4">
        <div className="flex items-center justify-between">
          <p className="text-[11px] font-bold uppercase tracking-widest text-black/40">出题管线质量总览（14天）</p>
          <Badge className="bg-slate-100 text-slate-700 border-none text-[10px] font-black rounded-lg">
            Author → Reviewer → Classifier
          </Badge>
        </div>
        <div className="grid grid-cols-2 lg:grid-cols-6 gap-3">
          {[
            { label: '任务总数', value: metrics?.overview?.total ?? 0, color: 'bg-white border-black/[0.04]', textColor: 'text-slate-900', subColor: 'text-black/40' },
            { label: '完成率', value: toPercentText(metrics?.overview?.completion_rate ?? 0), color: 'bg-emerald-50 border-emerald-100', textColor: 'text-emerald-700', subColor: 'text-emerald-700/70' },
            { label: '失败率', value: toPercentText(metrics?.overview?.fail_rate ?? 0), color: 'bg-red-50 border-red-100', textColor: 'text-red-700', subColor: 'text-red-700/70' },
            { label: 'Schema通过率', value: toPercentText(metrics?.pipeline_quality?.schema_ok_rate ?? 0), color: 'bg-indigo-50 border-indigo-100', textColor: 'text-indigo-700', subColor: 'text-indigo-700/70' },
            { label: '审核拒绝率', value: toPercentText(metrics?.pipeline_quality?.review_reject_rate ?? 0), color: 'bg-amber-50 border-amber-100', textColor: 'text-amber-700', subColor: 'text-amber-700/70' },
            { label: '待审核', value: metrics?.overview?.review ?? 0, color: 'bg-slate-100 border-slate-200', textColor: 'text-slate-800', subColor: 'text-slate-600' },
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
            <p className="text-sm font-bold">AI 智能出题</p>
            <p className="text-[11px] text-muted-foreground mt-1">
              选择知识点 → AI 自动生成题目。支持< b className="text-indigo-600">快速模式</b>（实时预览、一键入库）和
              <b className="text-rose-600">深度对抗</b>（多轮 AI 互搏、审核后入库）两种质量等级。
            </p>
          </div>
          <Button onClick={handleOpenGenerateDialog} className="rounded-xl bg-indigo-600 hover:bg-indigo-700 text-white h-11 px-6 text-xs font-bold shrink-0">
            <Sparkles className="h-4 w-4 mr-2" />AI 智能出题
          </Button>
        </div>
      </Card>

      {/* ── Review Queue ── */}
      {reviewTasks.length > 0 && (
        <Card className="p-6 rounded-3xl border border-amber-200 shadow-sm bg-gradient-to-br from-amber-50 to-white space-y-4">
          <div className="flex items-center gap-2">
            <Badge className="bg-amber-100 text-amber-700 border-none text-[10px] font-black rounded-lg">{reviewTasks.length} 项待审核</Badge>
            <p className="text-sm font-bold">审核队列</p>
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
                          {questions.length} 道题 · 均分 {typeof summary.avg_quality_score === 'number' ? summary.avg_quality_score.toFixed(3) : '--'} · {formatDate(task.created_at)}
                        </p>
                      </div>
                      <div className="flex gap-2 shrink-0">
                        <Button onClick={() => setPreviewTask(task)} variant="outline" className="h-8 rounded-lg text-[10px] font-bold px-2">预览</Button>
                        <Button
                          onClick={() => handleReviewAction(task.id, 'approve')}
                          disabled={reviewingMap[task.id]}
                          className="h-8 rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white text-[10px] font-bold px-3"
                        >
                          {reviewingMap[task.id] ? <Loader2 className="h-3 w-3 animate-spin" /> : <CheckCircle2 className="h-3 w-3 mr-1" />}
                          批准入库
                      </Button>
                      <Button
                        onClick={() => handleReviewAction(task.id, 'reject')}
                        disabled={reviewingMap[task.id]}
                        variant="outline"
                        className="h-8 rounded-lg border-red-200 text-red-700 hover:bg-red-50 text-[10px] font-bold px-3"
                      >
                        <XCircle className="h-3 w-3 mr-1" />拒绝
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
            <Label className="text-[11px] font-bold uppercase opacity-40">状态过滤</Label>
            <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value as TaskStatus | 'all')}
              className="w-full bg-apple-gray-50 border-none h-10 rounded-xl px-3 text-xs font-bold mt-1">
              {STATUS_OPTIONS.map((item) => (<option key={item.value} value={item.value}>{item.label}</option>))}
            </select>
          </div>
          <div className="lg:col-span-3">
            <Label className="text-[11px] font-bold uppercase opacity-40">类型过滤</Label>
            <select value={typeFilter} onChange={(e) => setTypeFilter(e.target.value as TaskType | 'all')}
              className="w-full bg-apple-gray-50 border-none h-10 rounded-xl px-3 text-xs font-bold mt-1">
              {TYPE_OPTIONS.map((item) => (<option key={item.value} value={item.value}>{item.label}</option>))}
            </select>
          </div>
          <div className="lg:col-span-4">
            <Label className="text-[11px] font-bold uppercase opacity-40">关键词</Label>
            <Input value={search} onChange={(e) => setSearch(e.target.value)}
              className="bg-apple-gray-50 border-none h-10 rounded-xl font-bold text-xs mt-1" placeholder="搜索任务标题" />
          </div>
          <div className="lg:col-span-2">
            <Button onClick={() => fetchTasks(1)} variant="outline" className="h-10 rounded-xl text-xs font-bold w-full">
              <RefreshCw className={loading ? 'h-3.5 w-3.5 animate-spin mr-1' : 'h-3.5 w-3.5 mr-1'} />刷新
            </Button>
          </div>
        </div>

        {loading ? (
          <div className="py-14 flex justify-center"><Loader2 className="h-7 w-7 animate-spin text-muted-foreground/40" /></div>
        ) : tasks.length === 0 ? (
          <EmptyState title="暂无任务" className="py-6" />
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
                      <Badge className="bg-indigo-100 text-indigo-700 border-none text-[10px] font-black rounded-lg">窗口 {Number(pipeline.author_windows || 0)}</Badge>
                      <Badge className="bg-sky-100 text-sky-700 border-none text-[10px] font-black rounded-lg">候选 {Number(pipeline.author_candidates || 0)}</Badge>
                      <Badge className="bg-emerald-100 text-emerald-700 border-none text-[10px] font-black rounded-lg">通过 {Number(pipeline.review_passed || 0)}</Badge>
                      <Badge className="bg-amber-100 text-amber-700 border-none text-[10px] font-black rounded-lg">驳回 {Number(pipeline.review_rejected || 0)}</Badge>
                    </div>
                  ) : null}
                  <div className="flex justify-end gap-2">
                    {(task.status === 'failed' || task.status === 'cancelled') && (
                      <Button onClick={() => handleRetryTask(task.id)} disabled={updatingMap[task.id]}
                        variant="outline" size="sm" className="h-7 rounded-lg text-[10px] font-bold">
                        {updatingMap[task.id] ? <Loader2 className="h-3 w-3 animate-spin mr-1" /> : <RotateCcw className="h-3 w-3 mr-1" />}重试
                      </Button>
                    )}
                    <Button onClick={() => handleDeleteTask(task.id)} disabled={updatingMap[task.id]}
                      variant="outline" size="sm" className="h-7 rounded-lg text-[10px] font-bold text-red-500 hover:text-red-700 hover:bg-red-50 border-red-200">
                      {updatingMap[task.id] ? <Loader2 className="h-3 w-3 animate-spin mr-1" /> : <Trash2 className="h-3 w-3 mr-1" />}删除
                    </Button>
                  </div>
                </div>
              );
            })}
          </div>
        )}

        <div className="flex items-center justify-between pt-2">
          <p className="text-[11px] text-muted-foreground">第 {page}/{Math.max(totalPages, 1)} 页</p>
          <div className="flex gap-2">
            <Button variant="outline" disabled={page <= 1 || loading} onClick={() => fetchTasks(page - 1)} className="h-8 rounded-lg text-[11px] font-bold">上一页</Button>
            <Button variant="outline" disabled={page >= totalPages || loading} onClick={() => fetchTasks(page + 1)} className="h-8 rounded-lg text-[11px] font-bold">下一页</Button>
          </div>
        </div>
      </Card>

      {/* ── Generate Dialog ── */}
      <Dialog open={smartDialogOpen} onOpenChange={(o) => { if (!o) { setSmartDialogOpen(false); setPreviewQuestions(null); setSelectedPreviewIds(new Set()); } }}>
        <DialogContent className={previewQuestions ? 'max-w-3xl max-h-[85vh] overflow-y-auto' : 'max-w-2xl'}>
          <DialogHeader>
            <DialogTitle>{adversarialMode ? '深度对抗出题' : '快速出题'}</DialogTitle>
            <DialogDescription>
              {adversarialMode
                ? 'Author ↔ Reviewer 多轮迭代博弈（异步后台执行），完成后进入审核队列。'
                : 'AI 实时生成 + 内部审查，秒级返回题目预览。'}
            </DialogDescription>
          </DialogHeader>

          {previewQuestions ? (
            <div className="space-y-4 py-2">
              <div className="flex items-center justify-between">
                <p className="text-xs font-bold text-emerald-600">生成 {previewQuestions.length} 道候选，已选 {selectedPreviewIds.size} 道</p>
                <div className="flex gap-2">
                  <Button variant="ghost" size="sm" onClick={() => setSelectedPreviewIds(new Set(previewQuestions.map((_: any, i: number) => i)))}
                    className="h-7 rounded-lg text-[10px] font-bold">全选</Button>
                  <Button variant="ghost" size="sm" onClick={() => setSelectedPreviewIds(new Set())}
                    className="h-7 rounded-lg text-[10px] font-bold">清空</Button>
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
                        {q.difficulty_level && <Badge className="bg-indigo-100 text-indigo-700 border-none text-[9px] font-bold rounded-lg">{DIFF_CN[q.difficulty_level] || q.difficulty_level}</Badge>}
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
                        {q.answer && <span className="text-emerald-600 font-bold">答案: {q.answer}</span>}
                        {q.correct_answer && <span className="text-emerald-600 font-bold">答案: {q.correct_answer}</span>}
                      </div>
                    </Card>
                  );})}
                </div>
              </ScrollArea>
              <DialogFooter>
                <Button variant="outline" onClick={() => { setPreviewQuestions(null); setSelectedPreviewIds(new Set()); setSmartKpIds([]); setSmartDialogOpen(false); }}
                  className="rounded-xl h-11 px-6 text-xs font-bold border-red-200 text-red-600 hover:bg-red-50">
                  <XCircle className="h-4 w-4 mr-2" />放弃全部
                </Button>
                <Button onClick={async () => {
                  const selected = previewQuestions.filter((_: any, i: number) => selectedPreviewIds.has(i));
                  if (selected.length === 0) return toast.error('请至少选择一道题目');
                  try {
                    await api.post('/quizzes/ai-bulk-import/', { questions: selected, kp_id: smartKpIds[0] || null });
                    toast.success(`成功导入 ${selected.length} 道题目`);
                    setPreviewQuestions(null); setSelectedPreviewIds(new Set()); setSmartKpIds([]); setSmartDialogOpen(false); fetchTasks(1);
                  } catch (e) { toast.error(formatApiErrorToast(e, '导入失败')); }
                }} disabled={selectedPreviewIds.size === 0}
                  className="rounded-xl bg-emerald-600 hover:bg-emerald-700 text-white h-11 px-6 text-xs font-bold">
                  <CheckCircle2 className="h-4 w-4 mr-2" />导入已选 ({selectedPreviewIds.size})
                </Button>
              </DialogFooter>
            </div>
          ) : (
            <div className="space-y-4 py-2">
              {/* ── 任务名 ── */}
              <div className="space-y-1.5">
                <Label className="text-[11px] font-bold uppercase opacity-40">任务名称（选填）</Label>
                <Input value={smartTaskName} onChange={(e) => setSmartTaskName(e.target.value)}
                  placeholder={'留空则使用默认名称'}
                  className="bg-apple-gray-50 border-none h-10 rounded-xl font-bold text-xs" />
              </div>

              {/* ── 质量模式开关 ── */}
              <div className="flex items-center justify-between p-4 rounded-2xl border border-border bg-muted/30">
                <div>
                  <p className="text-sm font-bold">{adversarialMode ? '深度对抗审查' : '快速生成'}</p>
                  <p className="text-[10px] text-muted-foreground mt-0.5">
                    {adversarialMode
                      ? 'Author ↔ Reviewer 多轮迭代博弈，后台异步执行，完成后进入审核队列'
                      : 'AI 实时生成 + 内部审查，秒级返回题目预览，确认后直接入库'}
                  </p>
                </div>
                <Switch checked={adversarialMode} onCheckedChange={setAdversarialMode} />
              </div>

              <div className={adversarialMode ? 'grid grid-cols-2 gap-3' : 'grid grid-cols-3 gap-3'}>
                <div className="space-y-1.5">
                  <Label className="text-[11px] font-bold uppercase opacity-40">每知识点题数</Label>
                  <Input type="number" min={1} max={adversarialMode ? 10 : 5} value={smartCount}
                    onChange={(e) => setSmartCount(Math.max(1, parseInt(e.target.value) || 1))}
                    className="bg-apple-gray-50 border-none h-10 rounded-xl font-bold text-xs" />
                </div>
                {!adversarialMode && (
                  <div className="space-y-1.5">
                    <Label className="text-[11px] font-bold uppercase opacity-40">目标难度</Label>
                    <select value={smartDifficulty} onChange={(e) => setSmartDifficulty(e.target.value)}
                      className="w-full bg-apple-gray-50 border-none h-10 rounded-xl px-3 text-xs font-bold">
                      <option value="entry">入门</option><option value="easy">简单</option>
                      <option value="normal">适当</option><option value="hard">困难</option>
                      <option value="mixed">混合</option>
                    </select>
                  </div>
                )}
                <div className="space-y-1.5">
                  <Label className="text-[11px] font-bold uppercase opacity-40">题型</Label>
                  <div className="flex flex-wrap gap-1">
                    {['objective', 'subjective:noun', 'subjective:short', 'subjective:essay', 'subjective:calculate'].map((t) => (
                      <Badge key={t} onClick={() => setSmartTypes((prev) => prev.includes(t) ? prev.filter((x) => x !== t) : [...prev, t])}
                        className={`cursor-pointer text-[10px] font-bold rounded-lg border ${smartTypes.includes(t) ? 'bg-indigo-100 text-indigo-700 border-indigo-200' : 'bg-slate-100 text-slate-500 border-slate-200'}`}>
                        {Q_TYPE_CN[t] || t}
                      </Badge>
                    ))}
                  </div>
                </div>
              </div>
              <div className="space-y-1.5">
                <Label className="text-[11px] font-bold uppercase opacity-40">选择知识点</Label>
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
                      <div className="py-8 text-center text-[11px] font-bold text-muted-foreground">未找到叶子考点，请先在知识体系中创建 level=kp 的节点</div>
                    )}
                  </ScrollArea>
                )}
                <p className="text-[10px] text-muted-foreground mt-1">已选 {smartKpIds.length} 个知识点</p>
              </div>
              <DialogFooter>
                <Button variant="outline" onClick={() => setSmartDialogOpen(false)} className="rounded-xl h-11 px-6 text-xs font-bold">取消</Button>
                <Button
                  onClick={adversarialMode ? handleSubmitAdversarial : handleSubmitSmartGenerate}
                  disabled={smartKpIds.length === 0 || smartSubmitting}
                  className={adversarialMode
                    ? 'rounded-xl bg-rose-600 hover:bg-rose-700 text-white h-11 px-6 text-xs font-bold'
                    : 'rounded-xl bg-indigo-600 hover:bg-indigo-700 text-white h-11 px-6 text-xs font-bold'}
                >
                  {smartSubmitting ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : adversarialMode ? <Swords className="h-4 w-4 mr-2" /> : <Sparkles className="h-4 w-4 mr-2" />}
                  {smartSubmitting ? '提交中...' : adversarialMode ? '提交至审核队列' : '生成并预览'}
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
            <DialogTitle>{previewTask?.title || '题目预览'}</DialogTitle>
            <DialogDescription>
              {(() => {
                const qs = (previewTask?.result as any)?.questions || [];
                const sm = (previewTask?.result as any)?.summary || {};
                const st = (previewTask?.result as any)?.stages || [];
                return `${qs.length} 道题 · 均分 ${typeof sm.avg_quality_score === 'number' ? sm.avg_quality_score.toFixed(3) : '--'} · ${st.length} 个管线阶段`;
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
                  <p className="text-[10px] font-bold uppercase tracking-widest text-slate-500">管线流程 (ARC)</p>
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                    {/* A - Author */}
                    <div className="p-3 bg-white rounded-xl border border-slate-200 space-y-1">
                      <p className="text-[11px] font-black text-indigo-600">A · Author（出题）</p>
                      <p className="text-[10px] text-slate-500">
                        生成 {summary.total_generated || stages.find((s: any) => s.stage === 'author_generated')?.count || '?'} 道候选
                      </p>
                    </div>
                    {/* R - Reviewer */}
                    <div className="p-3 bg-white rounded-xl border border-slate-200 space-y-1">
                      <p className="text-[11px] font-black text-rose-600">R · Reviewer（审查）</p>
                      <p className="text-[10px] text-slate-500">
                        均分 {typeof summary.avg_quality_score === 'number' ? (summary.avg_quality_score * 100).toFixed(0) : '--'} 分
                        {summary.iteration_distribution ? ` · 迭代 ${JSON.stringify(summary.iteration_distribution)}` : ''}
                      </p>
                    </div>
                    {/* C - Classifier */}
                    <div className="p-3 bg-white rounded-xl border border-slate-200 space-y-1">
                      <p className="text-[11px] font-black text-emerald-600">C · Classifier（分类）</p>
                      <p className="text-[10px] text-slate-500">
                        已标注难度、题型、知识标签
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
                  )}>{DIFF_CN[q.difficulty_level] || q.difficulty_level || '?'}</Badge>
                  {q.review_score != null && (
                    <Badge className={cn('text-[9px] font-bold rounded-lg border-none', q.review_score >= 0.7 ? 'bg-emerald-100 text-emerald-700' : 'bg-red-100 text-red-700')}>
                      {Number(q.review_score * 100).toFixed(0)}分
                    </Badge>
                  )}
                  {q.quality_warning && <Badge className="bg-rose-100 text-rose-700 text-[9px] font-bold rounded-lg">低质量警告</Badge>}
                </div>

                {/* A: Author 出题内容 */}
                <div className="pl-2 border-l-2 border-indigo-200 space-y-1.5">
                  <p className="text-[9px] font-bold uppercase text-indigo-500">Author 出题</p>
                  <p className="text-xs font-bold">{q.question}</p>
                  {q.options && typeof q.options === 'object' && Object.keys(q.options).length > 0 && (
                    <div className="grid grid-cols-2 gap-1">
                      {Object.entries(q.options as Record<string, string>).map(([k, v]) => (
                        <span key={k} className="text-[10px] text-slate-500"><b>{k}.</b> {v as string}</span>
                      ))}
                    </div>
                  )}
                  <div className="flex gap-3 text-[10px]">
                    {q.answer && <span className="text-emerald-600 font-bold">答案: {q.answer}</span>}
                    {q.kp_name && <span className="text-slate-400">知识点: {q.kp_name}</span>}
                  </div>
                </div>

                {/* R: Reviewer 审查结果 */}
                {(q.review_feedback || q.review_dimensions || q.iteration) && (
                  <div className="pl-2 border-l-2 border-rose-200 space-y-1.5">
                    <div className="flex items-center gap-2">
                      <p className="text-[9px] font-bold uppercase text-rose-500">Reviewer 审查</p>
                      {q.iteration && <span className="text-[9px] text-rose-400">第 {q.iteration} 轮通过</span>}
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
                    <p className="text-[9px] font-bold uppercase text-emerald-500">Classifier 分类</p>
                    <div className="flex flex-wrap gap-1.5">
                      {q.question_type && <span className="text-[9px] px-1.5 py-0.5 rounded bg-emerald-50 text-emerald-700 font-medium">{getTypeLabel(q)}</span>}
                      {(q.knowledge_tags || []).map((t: string) => (
                        <span key={t} className="text-[9px] px-1.5 py-0.5 rounded bg-slate-100 text-slate-600 font-medium">{t}</span>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setPreviewTask(null)} className="rounded-xl text-xs font-bold">关闭</Button>
            <Button onClick={() => { handleReviewAction(previewTask!.id, 'reject'); setPreviewTask(null); }} disabled={!previewTask || reviewingMap[previewTask.id]} variant="outline" className="rounded-xl border-red-200 text-red-700 text-xs font-bold">
              <XCircle className="h-3.5 w-3.5 mr-1" />拒绝全部
            </Button>
            <Button onClick={() => { handleReviewAction(previewTask!.id, 'approve'); setPreviewTask(null); }} disabled={!previewTask || reviewingMap[previewTask.id]} className="rounded-xl bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-bold">
              <CheckCircle2 className="h-3.5 w-3.5 mr-1" />批准入库
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};
