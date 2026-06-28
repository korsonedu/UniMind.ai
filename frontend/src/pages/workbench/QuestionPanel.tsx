import { useState, useEffect, useCallback, useRef } from 'react';
import { Button } from '@/components/ui/button';
import { Spinner, Sparkle, Check, CheckSquareOffset, MagicWand } from '@phosphor-icons/react';
import api from '@/lib/api';
import { cn } from '@/lib/utils';
import { toast } from 'sonner';
import PipelineProgress from './PipelineProgress';

interface QuestionData {
  question: string;
  q_type: string;
  subjective_type?: string | null;
  options?: string[] | null;
  answer: string;
  grading_points?: string[] | null;
  difficulty_level: string;
  kp_name?: string;
  kp_code?: string;
  kp_id?: number;
  source?: 'quick_generate' | 'arc_refine';
}

interface TaskStatus {
  id: number;
  status: string;
  progress: number;
  title: string;
  current_stage: string;
  status_text: string;
  stages: Array<{ stage: string; count?: number; timestamp?: string }>;
  questions?: Array<Record<string, unknown>>;
}

interface Bot {
  id: number;
  name: string;
}

interface Props {
  questions: QuestionData[];
  savedIndices: Set<number>;
  pipelineTaskId: number | null;
  bot: Bot | null;
  onPipelineStart?: (taskId: number) => void;
  onPipelineComplete?: (questions: Array<Record<string, unknown>>, taskId: number) => void;
  onQuestionsSaved?: (indices: number[]) => void;
  onSystemMessage?: (msg: string) => void;
}

const DIFFICULTY_LABEL: Record<string, string> = {
  entry: '入门',
  easy: '简单',
  normal: '适中',
  hard: '困难',
  extreme: '极限',
};

const DIFFICULTY_COLOR: Record<string, string> = {
  entry: 'bg-green-100 text-green-700',
  easy: 'bg-emerald-100 text-emerald-700',
  normal: 'bg-blue-100 text-blue-700',
  hard: 'bg-amber-100 text-amber-700',
  extreme: 'bg-red-100 text-red-700',
};

const QTYPE_LABEL: Record<string, string> = {
  objective: '客观题',
  subjective: '主观题',
};

const SOURCE_BADGE: Record<string, { label: string; cls: string }> = {
  quick_generate: { label: '一键生成', cls: 'bg-blue-50 text-blue-600' },
  arc_refine: { label: 'ARC 精修', cls: 'bg-purple-50 text-purple-600' },
};

const POLL_INITIAL = 5000;
const POLL_MAX = 60000;

export default function QuestionPanel({ questions, savedIndices, pipelineTaskId, bot, onPipelineStart, onPipelineComplete, onQuestionsSaved, onSystemMessage }: Props) {
  // 过滤掉已保存的题目，用原始索引
  const displayQuestions = questions
    .map((q, i) => ({ q, originalIndex: i }))
    .filter(({ originalIndex }) => !savedIndices.has(originalIndex));

  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [saving, setSaving] = useState(false);
  const [taskStatus, setTaskStatus] = useState<TaskStatus | null>(null);

  // Refs for recursive polling
  const cancelledRef = useRef(false);
  const timeoutRef = useRef<ReturnType<typeof setTimeout>>();
  const backoffRef = useRef(POLL_INITIAL);
  const completedHandledRef = useRef(false);
  const doPollRef = useRef<() => void>();

  // ── Polling effect ──
  useEffect(() => {
    if (!pipelineTaskId) {
      setTaskStatus(null);
      completedHandledRef.current = false;
      return;
    }

    cancelledRef.current = false;
    backoffRef.current = POLL_INITIAL;
    completedHandledRef.current = false;

    const doPoll = async () => {
      if (cancelledRef.current) return;

      if (document.visibilityState === 'hidden') {
        timeoutRef.current = setTimeout(doPoll, backoffRef.current);
        return;
      }

      try {
        const res = await api.get(`/quizzes/workbench/tasks/${pipelineTaskId}/status/`);
        if (cancelledRef.current) return;

        const data: TaskStatus = res.data;
        setTaskStatus(data);

        if (data.status === 'completed' || data.status === 'failed' || data.status === 'cancelled') {
          if (data.status === 'completed' && data.questions?.length && !completedHandledRef.current) {
            completedHandledRef.current = true;
            onPipelineComplete?.(data.questions, pipelineTaskId);
          }
          return; // stop polling
        }

        backoffRef.current = POLL_INITIAL;
      } catch {
        backoffRef.current = Math.min(backoffRef.current * 2, POLL_MAX);
      }

      timeoutRef.current = setTimeout(doPoll, backoffRef.current);
    };

    doPollRef.current = doPoll;
    doPoll(); // immediate first fetch

    return () => {
      cancelledRef.current = true;
      clearTimeout(timeoutRef.current);
    };
  }, [pipelineTaskId, onPipelineComplete]);

  // ── Visibility change: poll immediately when tab becomes visible ──
  useEffect(() => {
    const handleVisibility = () => {
      if (document.visibilityState === 'visible') {
        backoffRef.current = POLL_INITIAL;
        doPollRef.current?.();
      }
    };
    document.addEventListener('visibilitychange', handleVisibility);
    return () => document.removeEventListener('visibilitychange', handleVisibility);
  }, []);

  const toggleSelect = useCallback((index: number) => {
    setSelected(prev => {
      const next = new Set(prev);
      if (next.has(index)) next.delete(index);
      else next.add(index);
      return next;
    });
  }, []);

  const toggleAll = useCallback(() => {
    if (selected.size === displayQuestions.length) {
      setSelected(new Set());
    } else {
      setSelected(new Set(displayQuestions.map((_, i) => i)));
    }
  }, [selected.size, displayQuestions.length]);

  const handleSave = useCallback(async () => {
    const selectedDisplayIndices = selected.size > 0 ? Array.from(selected) : undefined;
    // 映射回原始索引
    const originalIndices = selectedDisplayIndices
      ? selectedDisplayIndices.map(i => displayQuestions[i].originalIndex)
      : displayQuestions.map(d => d.originalIndex);
    const toSave = originalIndices.map(i => questions[i]);
    setSaving(true);
    try {
      const res = await api.post('/quizzes/workbench/save-questions/', { questions: toSave });
      toast.success(`已入库 ${res.data.saved} 题`);
      onQuestionsSaved?.(originalIndices);
      // 通知 LLM
      const summary = toSave.map(q => q.question?.substring(0, 20)).join('、');
      onSystemMessage?.(`用户已将以下题目存入题库：${summary}`);
      setSelected(new Set());
    } catch {
      toast.error('入库失败');
    }
    setSaving(false);
  }, [selected, displayQuestions, questions, onQuestionsSaved, onSystemMessage]);

  const handleArcRefine = useCallback(async () => {
    if (selected.size === 0) return;
    const selectedDisplayIndices = Array.from(selected);
    const toRefine = selectedDisplayIndices.map(i => displayQuestions[i].q);
    setSaving(true);
    try {
      const res = await api.post('/quizzes/workbench/launch-arc/', { questions: toRefine });
      toast.success('ARC 精修已启动');
      if (res.data.task_id) onPipelineStart?.(res.data.task_id);
    } catch {
      toast.error('启动失败');
    }
    setSaving(false);
  }, [selected, displayQuestions, onPipelineStart]);

  // 空状态
  if (displayQuestions.length === 0 && !pipelineTaskId) {
    return (
      <div className="h-full flex flex-col items-center justify-center text-unimind-text-quaternary">
        <Sparkle className="h-10 w-10 mb-3 opacity-20" />
        <p className="text-sm font-medium">在右侧对话框描述出题需求</p>
        <p className="text-xs mt-1">题目生成后将展示在这里</p>
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col">
      {/* 管线进度（如果有） */}
      {taskStatus && (
        <div className="shrink-0 p-4 border-b">
          <PipelineProgress
            progress={taskStatus.progress}
            currentStage={taskStatus.current_stage}
            statusText={taskStatus.status_text}
            stages={taskStatus.stages}
            status={taskStatus.status}
          />
        </div>
      )}

      {/* 题目列表 */}
      {displayQuestions.length > 0 && (
        <>
          {/* 汇总栏 */}
          <div className="shrink-0 px-4 py-2.5 border-b bg-muted/30 flex items-center justify-between">
            <div className="flex items-center gap-3">
              <span className="text-xs font-bold text-foreground">
                共 {displayQuestions.length} 题
              </span>
              <button
                onClick={toggleAll}
                className="text-[11px] text-primary hover:underline font-medium"
              >
                {selected.size === displayQuestions.length ? '取消全选' : '全选'}
              </button>
              {selected.size > 0 && (
                <span className="text-[11px] text-unimind-text-tertiary">
                  已选 {selected.size} 题
                </span>
              )}
            </div>
            <div className="flex items-center gap-1.5">
              {selected.size > 0 && (
                <Button
                  size="sm"
                  variant="outline"
                  className="text-xs h-7 gap-1"
                  onClick={handleArcRefine}
                  disabled={saving}
                >
                  <MagicWand className="h-3 w-3" />
                  ARC 精修
                </Button>
              )}
              <Button
                size="sm"
                className="text-xs h-7 gap-1"
                onClick={handleSave}
                disabled={saving}
              >
                {saving ? <Spinner className="h-3 w-3 animate-spin" /> : <CheckSquareOffset className="h-3 w-3" />}
                存入题库
              </Button>
            </div>
          </div>

          {/* 题目卡片 */}
          <div className="flex-1 overflow-y-auto p-4 space-y-3">
            {displayQuestions.map(({ q, originalIndex }, i) => (
              <div
                key={originalIndex}
                className={cn(
                  "border rounded-lg p-3.5 transition-all cursor-pointer",
                  selected.has(i) ? "border-primary bg-primary/5" : "hover:border-border/80",
                )}
                onClick={() => toggleSelect(i)}
              >
                {/* 头部：序号 + 来源 + 类型 + 难度 + 知识点 */}
                <div className="flex items-center gap-2 mb-2 flex-wrap">
                  <div className={cn(
                    "w-5 h-5 rounded border flex items-center justify-center shrink-0",
                    selected.has(i) ? "bg-primary border-primary" : "border-border",
                  )}>
                    {selected.has(i) && <Check className="h-3 w-3 text-white" />}
                  </div>
                  <span className="text-xs font-bold text-foreground">#{i + 1}</span>
                  {q.source && SOURCE_BADGE[q.source] && (
                    <span className={cn(
                      "text-[10px] font-bold px-1.5 py-0.5 rounded",
                      SOURCE_BADGE[q.source].cls,
                    )}>
                      {SOURCE_BADGE[q.source].label}
                    </span>
                  )}
                  <span className={cn(
                    "text-[10px] font-bold px-1.5 py-0.5 rounded",
                    q.q_type === 'objective' ? 'bg-blue-100 text-blue-700' : 'bg-purple-100 text-purple-700',
                  )}>
                    {QTYPE_LABEL[q.q_type] || q.q_type}
                  </span>
                  <span className={cn(
                    "text-[10px] font-bold px-1.5 py-0.5 rounded",
                    DIFFICULTY_COLOR[q.difficulty_level] || 'bg-muted text-foreground',
                  )}>
                    {DIFFICULTY_LABEL[q.difficulty_level] || q.difficulty_level}
                  </span>
                  {q.kp_name && (
                    <span className="text-[10px] text-unimind-text-quaternary truncate">
                      {q.kp_code ? `${q.kp_code} ` : ''}{q.kp_name}
                    </span>
                  )}
                </div>

                {/* 题干 */}
                <p className="text-[13px] leading-relaxed text-foreground whitespace-pre-wrap">
                  {q.question}
                </p>

                {/* 客观题选项 */}
                {q.q_type === 'objective' && q.options && (
                  <div className="mt-2 space-y-1">
                    {(Array.isArray(q.options) ? q.options : Object.entries(q.options).map(([k, v]) => `${k}. ${v}`)).map((opt: string, j: number) => (
                      <div key={j} className="text-xs text-unimind-text-secondary pl-2">
                        {opt}
                      </div>
                    ))}
                  </div>
                )}

                {/* 答案预览 */}
                <div className="mt-2 text-xs text-unimind-text-tertiary">
                  <span className="font-semibold">答案：</span>
                  {(q.answer || '').substring(0, 150)}
                  {(q.answer || '').length > 150 && '...'}
                </div>
              </div>
            ))}
          </div>
        </>
      )}

      {/* 管线运行中但尚无题目 */}
      {displayQuestions.length === 0 && pipelineTaskId && taskStatus && (
        <div className="flex-1 flex items-center justify-center text-unimind-text-quaternary">
          <div className="text-center">
            <Spinner className="h-8 w-8 animate-spin text-primary mx-auto mb-2" />
            <p className="text-sm">ARC 管线运行中，题目即将生成...</p>
          </div>
        </div>
      )}
    </div>
  );
}
