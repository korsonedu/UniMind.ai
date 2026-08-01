import { useState, useEffect, useCallback, useRef } from 'react';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Spinner, Sparkle, Check, CheckSquareOffset, MagicWand } from '@phosphor-icons/react';
import api from '@/lib/api';
import { cn } from '@/lib/utils';
import { toast } from 'sonner';
import PipelineProgress from './PipelineProgress';
import { MarkdownContent } from '@/components/MarkdownContent';

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
  const [detailQuestion, setDetailQuestion] = useState<QuestionData | null>(null);

  // Refs for recursive polling
  const cancelledRef = useRef(false);
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const backoffRef = useRef(POLL_INITIAL);
  const completedHandledRef = useRef(false);
  const doPollRef = useRef<(() => void) | undefined>(undefined);

  // ── Polling effect ──
  useEffect(() => {
    if (!pipelineTaskId) {
      setTaskStatus(null);
      completedHandledRef.current = false;
      doPollRef.current = undefined;
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

  const toggleSelect = useCallback((index: number, e?: React.MouseEvent) => {
    e?.stopPropagation();
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
              {(() => {
                const hasNonArcSelected = selected.size > 0 && Array.from(selected).some(i => displayQuestions[i]?.q.source !== 'arc_refine');
                return hasNonArcSelected && (
                <Button
                  size="sm"
                  variant="outline"
                  className="text-xs h-7 gap-1"
                  onClick={handleArcRefine}
                  disabled={saving || pipelineTaskId != null}
                >
                  <MagicWand className="h-3 w-3" />
                  ARC 精修
                </Button>
              )})()}
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
                  "border rounded-lg transition-all",
                  selected.has(i) ? "border-primary bg-primary/5" : "hover:border-border/80",
                )}
              >
                {/* 点击卡片主体 → 打开详情弹窗 */}
                <div
                  className="p-3.5 cursor-pointer"
                  onClick={() => setDetailQuestion(q)}
                >
                  {/* 头部：勾选框 + 序号 + 来源 + 类型 + 难度 + 知识点 */}
                  <div className="flex items-center gap-2 mb-2 flex-wrap">
                    <div
                      className={cn(
                        "w-5 h-5 rounded border flex items-center justify-center shrink-0",
                        selected.has(i) ? "bg-primary border-primary" : "border-border",
                      )}
                      onClick={(e) => toggleSelect(i, e)}
                      role="checkbox"
                      aria-checked={selected.has(i)}
                    >
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

                  {/* 题干 — 带 LaTeX 渲染 */}
                  <div className="text-[13px] leading-relaxed text-foreground">
                    <MarkdownContent
                      content={q.question}
                      className="prose-sm prose-p:my-0 prose-ul:my-1 max-w-none [&_.katex-display]:my-1 [&_.katex-display]:overflow-x-auto"
                    />
                  </div>

                  {/* 客观题选项 */}
                  {q.q_type === 'objective' && q.options && (
                    <div className="mt-2 space-y-1">
                      {(Array.isArray(q.options) ? q.options : Object.entries(q.options).map(([k, v]) => `${k}. ${v}`)).map((opt: string, j: number) => (
                        <div key={j} className="text-xs text-unimind-text-secondary pl-2">
                          <MarkdownContent
                            content={opt}
                            className="text-xs prose-p:my-0 max-w-none [&_.katex]:text-[11px]"
                          />
                        </div>
                      ))}
                    </div>
                  )}

                  {/* 答案预览 */}
                  <div className="mt-2 text-xs text-unimind-text-tertiary">
                    <span className="font-semibold">答案：</span>
                    <span className="inline">
                      <MarkdownContent
                        content={(q.answer || '').substring(0, 150) + ((q.answer || '').length > 150 ? '...' : '')}
                        className="text-xs prose-p:my-0 max-w-none [&_.katex]:text-[11px] inline"
                      />
                    </span>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </>
      )}

      {/* 管线运行中但尚无题目 */}
      {displayQuestions.length === 0 && pipelineTaskId && taskStatus && (
        <div className="flex-1 flex items-center justify-center">
          <div className="text-center px-6">
            <Spinner className="h-8 w-8 animate-spin text-primary mx-auto mb-3" />
            <p className="text-sm font-bold text-foreground">
              {taskStatus.status_text || 'ARC 管线运行中...'}
            </p>
            {taskStatus.progress != null && (
              <p className="text-xs text-unimind-text-tertiary mt-1">
                进度 {taskStatus.progress}% · {taskStatus.title || `任务 #${taskStatus.id}`}
              </p>
            )}
          </div>
        </div>
      )}

      {/* 题目详情弹窗 */}
      <Dialog open={!!detailQuestion} onOpenChange={(open) => { if (!open) setDetailQuestion(null); }}>
        <DialogContent className="sm:max-w-[720px] max-h-[85vh] overflow-y-auto rounded-2xl">
          {detailQuestion && (
            <>
              <DialogHeader>
                <DialogTitle className="text-base font-bold flex items-center gap-2 flex-wrap">
                  {detailQuestion.source && SOURCE_BADGE[detailQuestion.source] && (
                    <span className={cn(
                      "text-[10px] font-bold px-1.5 py-0.5 rounded",
                      SOURCE_BADGE[detailQuestion.source].cls,
                    )}>
                      {SOURCE_BADGE[detailQuestion.source].label}
                    </span>
                  )}
                  <span className={cn(
                    "text-[10px] font-bold px-1.5 py-0.5 rounded",
                    detailQuestion.q_type === 'objective' ? 'bg-blue-100 text-blue-700' : 'bg-purple-100 text-purple-700',
                  )}>
                    {QTYPE_LABEL[detailQuestion.q_type] || detailQuestion.q_type}
                  </span>
                  <span className={cn(
                    "text-[10px] font-bold px-1.5 py-0.5 rounded",
                    DIFFICULTY_COLOR[detailQuestion.difficulty_level] || 'bg-muted text-foreground',
                  )}>
                    {DIFFICULTY_LABEL[detailQuestion.difficulty_level] || detailQuestion.difficulty_level}
                  </span>
                  {detailQuestion.kp_name && (
                    <span className="text-[10px] text-unimind-text-quaternary">
                      {detailQuestion.kp_code ? `${detailQuestion.kp_code} ` : ''}{detailQuestion.kp_name}
                    </span>
                  )}
                </DialogTitle>
              </DialogHeader>

              <div className="space-y-4 mt-2">
                {/* 题干 */}
                <div>
                  <h4 className="text-xs font-bold text-unimind-text-tertiary mb-1.5 uppercase tracking-wider">题干</h4>
                  <div className="text-sm leading-relaxed text-foreground bg-muted/30 rounded-lg p-4">
                    <MarkdownContent
                      content={detailQuestion.question}
                      className="prose-sm prose-p:my-1 max-w-none [&_.katex-display]:my-2 [&_.katex-display]:overflow-x-auto"
                    />
                  </div>
                </div>

                {/* 选项（客观题） */}
                {detailQuestion.q_type === 'objective' && detailQuestion.options && (
                  <div>
                    <h4 className="text-xs font-bold text-unimind-text-tertiary mb-1.5 uppercase tracking-wider">选项</h4>
                    <div className="space-y-1.5 bg-muted/30 rounded-lg p-4">
                      {(Array.isArray(detailQuestion.options)
                        ? detailQuestion.options
                        : Object.entries(detailQuestion.options).map(([k, v]) => `${k}. ${v}`)
                      ).map((opt: string, j: number) => (
                        <div key={j} className="text-sm text-unimind-text-secondary">
                          <MarkdownContent
                            content={opt}
                            className="prose-sm prose-p:my-0 max-w-none [&_.katex]:text-sm"
                          />
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* 答案 */}
                <div>
                  <h4 className="text-xs font-bold text-unimind-text-tertiary mb-1.5 uppercase tracking-wider">答案</h4>
                  <div className="text-sm leading-relaxed text-foreground bg-muted/30 rounded-lg p-4">
                    <MarkdownContent
                      content={detailQuestion.answer || '（无）'}
                      className="prose-sm prose-p:my-1 max-w-none [&_.katex-display]:my-2 [&_.katex-display]:overflow-x-auto"
                    />
                  </div>
                </div>

                {/* 评分要点（主观题） */}
                {detailQuestion.grading_points && Array.isArray(detailQuestion.grading_points) && detailQuestion.grading_points.length > 0 && (
                  <div>
                    <h4 className="text-xs font-bold text-unimind-text-tertiary mb-1.5 uppercase tracking-wider">评分要点</h4>
                    <div className="text-sm leading-relaxed text-foreground bg-muted/30 rounded-lg p-4">
                      <ul className="list-disc pl-4 space-y-1">
                        {detailQuestion.grading_points.map((point: string, j: number) => (
                          <li key={j}>
                            <MarkdownContent
                              content={point}
                              className="prose-sm prose-p:my-0 max-w-none [&_.katex]:text-sm"
                            />
                          </li>
                        ))}
                      </ul>
                    </div>
                  </div>
                )}
              </div>
            </>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
