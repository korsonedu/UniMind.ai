import { useEffect, useState, useRef, useCallback } from 'react';
import { FileText, CheckSquareOffset, Users, ChartBar, Brain, ArrowLeft, Files, Lightning, Hourglass, Database, ClipboardText, Spinner } from '@phosphor-icons/react';
import api from '@/lib/api';
import { processMathContent, cn } from '@/lib/utils';
import AgentChatLayout from '@/components/AgentChatLayout';
import QuestionPanel from '@/pages/workbench/QuestionPanel';
import { BulkInitCard } from '@/pages/workbench/BulkInitCard';
import { QuickStartPanel } from '@/pages/workbench/QuickStartPanel';
import type { Bot, Message, ConversationSession } from '@/hooks/useAgentConversation';
import type { AgentStep } from '@/hooks/useAgentChat';

interface InstitutionStats {
  weekly_active_students: number;
  top_weak_points: { label: string; weak_count: number }[];
  pending_grading?: number;
  active_assignments?: number;
}

interface InstitutionInfo {
  id: number;
  name: string;
  plan: string;
  plan_label: string;
  max_students: number;
  student_count: number;
  staff_count: number;
}

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
}

const SKILLS = [
  { icon: FileText, label: '出题', prompt: '帮我出5道题' },
  { icon: Lightning, label: '精修出题', prompt: '对刚才的题目启动 ARC 精修' },
  { icon: ChartBar, label: '查薄弱点', prompt: '班级薄弱知识点有哪些' },
  { icon: Users, label: '查学生', prompt: '帮我看看学生的学习情况' },
  { icon: CheckSquareOffset, label: '查作业', prompt: '作业提交情况' },
  { icon: Hourglass, label: '管线进度', prompt: '检查出题任务进度' },
  { icon: Database, label: '题库统计', prompt: '帮我看看题库统计情况' },
  { icon: Files, label: '浏览题目', prompt: '帮我看看题库里有什么题目' },
  { icon: ClipboardText, label: '布置作业', prompt: '帮我把题目布置给学生' },
];

type ViewMode = 'overview' | 'questions' | 'landing';

// ── localStorage persistence ──

const STORAGE_KEY = 'unimind_workbench';

function loadState(): { questions: QuestionData[]; savedIndices: number[] } | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (parsed.questions?.length) return parsed;
    return null;
  } catch { return null; }
}

function saveState(questions: QuestionData[], savedIndices: Set<number>) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({
      questions,
      savedIndices: Array.from(savedIndices),
    }));
  } catch { /* quota */ }
}

function clearState() {
  try { localStorage.removeItem(STORAGE_KEY); } catch { /* */ }
}

// ── Copilot Overview ──

function CopilotOverview({ institution, stats, questionCount, onEnterQuestions, onSend }: {
  institution: InstitutionInfo;
  stats: InstitutionStats;
  questionCount: number;
  onEnterQuestions: () => void;
  onSend: (msg: string) => void;
}) {
  return (
    <div className="space-y-6">
      <QuickStartPanel studentCount={institution.student_count} />

      <div className="flex items-center gap-2">
        <Brain className="h-5 w-5 text-primary" />
        <h2 className="text-lg font-black tracking-tight">Copilot</h2>
        <span className="text-xs text-muted-foreground font-bold uppercase tracking-wider ml-auto">
          {institution.plan_label} · {institution.student_count}/{institution.max_students} 学员
        </span>
      </div>

      {stats.pending_grading ? (
        <div className="rounded-xl border border-amber-500/30 bg-amber-50/50 p-4 flex items-center gap-3">
          <div className="h-2 w-2 rounded-full bg-amber-500 animate-pulse shrink-0" />
          <div className="flex-1 min-w-0">
            <span className="text-sm font-bold text-amber-700">{stats.pending_grading} 份作业待批改</span>
            <span className="text-xs text-amber-600/70 ml-2">学生正在等待反馈</span>
          </div>
          <button
            onClick={() => onSend('帮我看看待批改的作业')}
            className="text-xs font-bold text-amber-700 hover:text-amber-900 transition-colors shrink-0"
          >
            查看 →
          </button>
        </div>
      ) : null}

      <BulkInitCard />

      {questionCount > 0 && (
        <button
          onClick={onEnterQuestions}
          className="w-full rounded-xl border border-primary/30 bg-primary/5 p-4 text-left hover:bg-primary/10 transition-colors"
        >
          <div className="flex items-center gap-2">
            <Files className="h-4 w-4 text-primary" />
            <span className="text-sm font-bold text-foreground">题目面板</span>
            <span className="text-xs text-primary font-bold ml-auto">{questionCount} 题待处理 →</span>
          </div>
          <p className="text-xs text-muted-foreground mt-1">勾选题目存入题库或启动 ARC 精修</p>
        </button>
      )}

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="rounded-xl bg-muted/30 p-4">
          <div className="flex items-center gap-2 text-muted-foreground text-xs font-bold uppercase tracking-wider mb-2">
            <Users className="h-3.5 w-3.5" />
            本周活跃
          </div>
          <div className="text-2xl font-black">{stats.weekly_active_students}</div>
          <div className="text-xs text-muted-foreground mt-0.5">
            共 {institution.student_count} 名学员 / {institution.staff_count} 名教师
          </div>
        </div>

        <div className="rounded-xl border border-primary/20 bg-primary/[0.03] p-4">
          <div className="flex items-center gap-2 text-muted-foreground text-xs font-bold uppercase tracking-wider mb-2">
            <ChartBar className="h-3.5 w-3.5" />
            薄弱知识点
          </div>
          {stats.top_weak_points.length > 0 ? (
            <>
              <div className="text-sm font-bold">{stats.top_weak_points[0].label}</div>
              <div className="text-xs text-muted-foreground mt-0.5">
                {stats.top_weak_points[0].weak_count} 名学员薄弱
              </div>
              <button
                onClick={() => onSend(`针对${stats.top_weak_points[0].label}出${Math.min(stats.top_weak_points[0].weak_count * 2, 5)}道题`)}
                className="mt-2 text-xs font-bold text-primary hover:text-primary/80 transition-colors flex items-center gap-0.5"
              >
                <Lightning className="h-3 w-3" /> 出针对性练习
              </button>
            </>
          ) : (
            <div className="text-sm font-bold text-muted-foreground">暂无数据</div>
          )}
        </div>

        <div className="rounded-xl border border-border bg-card p-4 flex flex-col">
          <div className="flex items-center gap-2 text-muted-foreground text-xs font-bold uppercase tracking-wider mb-2">
            <Brain className="h-3.5 w-3.5" />
            Agent
          </div>
          {stats.pending_grading ? (
            <>
              <div className="text-sm font-bold text-amber-500">{stats.pending_grading} 份待批改</div>
              <button
                onClick={() => onSend(`帮我看看待批改的作业`)}
                className="mt-2 text-xs font-bold text-primary hover:text-primary/80 transition-colors flex items-center gap-0.5"
              >
                <Lightning className="h-3 w-3" /> 查看详情
              </button>
            </>
          ) : stats.active_assignments ? (
            <>
              <div className="text-sm font-bold">{stats.active_assignments} 个作业进行中</div>
              <div className="text-xs text-muted-foreground mt-0.5 flex-1">学生正在完成中</div>
            </>
          ) : (
            <>
              <div className="text-sm font-bold">随时待命</div>
              <div className="text-xs text-muted-foreground mt-0.5 flex-1">对话中直接告诉我需求</div>
            </>
          )}
        </div>
      </div>

      {stats.top_weak_points.length > 0 && (
        <div className="rounded-xl border border-border bg-card/50 p-4">
          <div className="text-xs font-bold uppercase tracking-wider text-muted-foreground mb-3">待处理建议</div>
          <div className="space-y-1">
            {stats.top_weak_points.slice(0, 5).map((kp, i) => (
              <div key={i} className="flex items-center gap-3 text-sm py-1.5 group">
                <span className="h-1.5 w-1.5 rounded-full bg-primary shrink-0" />
                <span className="font-bold flex-1 min-w-0 truncate">{kp.label}</span>
                <span className="text-muted-foreground text-xs shrink-0">{kp.weak_count} 人薄弱</span>
                <button
                  onClick={() => onSend(`针对${kp.label}出${Math.min(kp.weak_count * 2, 5)}道题`)}
                  className="text-xs font-bold text-primary/60 hover:text-primary transition-colors shrink-0"
                >
                  <Lightning className="h-3 w-3 inline" /> 出题
                </button>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ── Main Component ──

export default function Workbench() {
  const [instInfo, setInstInfo] = useState<InstitutionInfo | null>(null);
  const [stats, setStats] = useState<InstitutionStats | null>(null);
  const [bot, setBot] = useState<Bot | null>(null);

  // 从 localStorage 恢复
  const persisted = loadState();
  const [generatedQuestions, setGeneratedQuestions] = useState<QuestionData[]>(
    persisted?.questions ?? []
  );
  const [savedIndices, setSavedIndices] = useState<Set<number>>(
    persisted?.savedIndices?.length ? new Set(persisted.savedIndices) : new Set()
  );
  const [pipelineTaskId, setPipelineTaskId] = useState<number | null>(null);
  const [viewMode, setViewMode] = useState<ViewMode>('overview');
  const [wasResetManually, setWasResetManually] = useState(false);
  const [hasConversation, setHasConversation] = useState<boolean | null>(null);

  const doSendRef = useRef<((text: string) => void) | null>(null);

  // sync to localStorage on state change
  useEffect(() => {
    if (generatedQuestions.length > 0) {
      saveState(generatedQuestions, savedIndices);
    }
  }, [generatedQuestions, savedIndices]);

  useEffect(() => {
    api.get('/users/institution/me/')
      .then(res => {
        const d = res.data;
        setInstInfo(d.institution);
        setStats(d.stats);
      })
      .catch(() => {});
    api.get('/ai/bots/')
      .then(res => {
        const found = (res.data as Bot[]).find(b => b.bot_type === 'exam_generator');
        if (found) {
          setBot(found);
          // 预加载对话历史，避免 landing→面板 的闪光
          return api.get('/ai/history/', { params: { bot_id: found.id } });
        }
        setHasConversation(false);
        return null;
      })
      .then(hRes => {
        if (hRes) {
          setHasConversation(hRes.data.length > 0);
        }
      })
      .catch(() => {
        setHasConversation(false);
      });
  }, []);

  const handleQuestionsGenerated = useCallback((questions: AgentStep['questions']) => {
    if (!questions?.length) return;
    const mapped: QuestionData[] = questions.map((q: any) => ({
      question: q.question || '',
      q_type: q.q_type || 'objective',
      subjective_type: q.subjective_type || null,
      options: q.options || null,
      answer: q.answer || q.answer_preview || '',
      grading_points: q.grading_points || null,
      difficulty_level: q.difficulty_level || 'normal',
      kp_name: q.kp_name || '',
      kp_code: q.kp_code || '',
    }));
    setGeneratedQuestions(prev => [...prev, ...mapped]);
    setSavedIndices(new Set());
    setViewMode('questions');
  }, []);

  const handleQuestionsSaved = useCallback((indices: number[]) => {
    setSavedIndices(prev => {
      const next = new Set(prev);
      indices.forEach(i => next.add(i));
      return next;
    });
  }, []);

  const handlePipelineStart = useCallback((taskId: number) => {
    setPipelineTaskId(taskId);
  }, []);

  const handleSystemMessage = useCallback((msg: string) => {
    doSendRef.current?.(msg);
  }, []);

  const handleResetQuestions = useCallback(() => {
    setGeneratedQuestions([]);
    setSavedIndices(new Set());
    setPipelineTaskId(null);
    setViewMode('overview');
    clearState();
  }, []);

  // 侧栏可拖动宽度
  const [sidebarWidth, setSidebarWidth] = useState(320);
  const [dragging, setDragging] = useState(false);

  const handleSidebarDragStart = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    setDragging(true);
    const startX = e.clientX;
    const startWidth = sidebarWidth;
    const onMove = (ev: MouseEvent) => {
      setSidebarWidth(Math.max(280, Math.min(600, startWidth + startX - ev.clientX)));
    };
    const onUp = () => { setDragging(false); document.removeEventListener('mousemove', onMove); document.removeEventListener('mouseup', onUp); };
    document.addEventListener('mousemove', onMove);
    document.addEventListener('mouseup', onUp);
  }, [sidebarWidth]);

  // 未处理的题目数
  const remainingCount = generatedQuestions.length - savedIndices.size;

  // 加载中：等待 hasConversation 预检完成，避免 landing→面板 的闪光
  if (hasConversation === null) {
    return (
      <div className="h-full flex items-center justify-center">
        <Spinner className="h-4 w-4 animate-spin text-muted-foreground/40" />
      </div>
    );
  }

  return (
    <div className="flex h-full min-h-0">
      {/* Left: QuestionPanel or Copilot Overview — 仅对话时显示，landing 隐藏 */}
      {hasConversation && (viewMode !== 'questions' || generatedQuestions.length === 0 ? (
        !wasResetManually && instInfo && stats && (
          <div className="flex-1 min-w-0 overflow-y-auto bg-muted/50">
            <div className="p-4 md:p-6">
              <CopilotOverview
                institution={instInfo}
                stats={stats}
                questionCount={remainingCount}
                onEnterQuestions={() => setViewMode('questions')}
                onSend={handleSystemMessage}
              />
            </div>
          </div>
        )
      ) : (
        <div className="flex-1 min-w-0 overflow-y-auto bg-muted/50">
          <div className="h-full flex flex-col">
            <div className="shrink-0 px-4 py-2 border-b bg-muted/30 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <button
                  onClick={() => setViewMode('overview')}
                  className="p-0.5 rounded hover:bg-muted transition-colors text-muted-foreground hover:text-foreground"
                  title="返回工作台"
                >
                  <ArrowLeft className="h-3.5 w-3.5" />
                </button>
                <span className="text-xs font-bold text-foreground">
                  题目面板 · {remainingCount}/{generatedQuestions.length} 题
                </span>
              </div>
              <button
                onClick={handleResetQuestions}
                className="text-xs text-muted-foreground hover:text-foreground transition-colors"
              >
                清空
              </button>
            </div>
            <div className="flex-1 min-h-0">
              <QuestionPanel
                questions={generatedQuestions}
                savedIndices={savedIndices}
                pipelineTaskId={pipelineTaskId}
                bot={bot}
                onPipelineStart={handlePipelineStart}
                onQuestionsSaved={handleQuestionsSaved}
                onSystemMessage={handleSystemMessage}
              />
            </div>
          </div>
        </div>
      ))}

      {/* Right: Agent Chat — landing 时全宽居中，对话时侧栏宽度 */}
      <div className={cn(
        "hidden md:flex flex-col relative",
        !hasConversation ? "flex-1 min-w-0" : "border-l border-border/30 shrink-0",
        dragging && "select-none"
      )} style={!hasConversation ? undefined : { width: sidebarWidth }}>
        {/* 拖拽手柄 — 仅对话时显示 */}
        {hasConversation && (
          <div
            className="absolute left-0 top-0 bottom-0 w-1.5 cursor-col-resize z-10"
            onMouseDown={handleSidebarDragStart}
          />
        )}
        <AgentChatLayout
          layout="inline"
          findBot={(bots) => bots.find((b: Bot) => b.bot_type === 'exam_generator')}
          skills={SKILLS}
          typewriterWords={['出题、查学生、管作业...', '根据薄弱知识点出题', '看看学员学习情况']}
          chatPlaceholder="告诉 Agent 你要做什么..."
          resetMessage="已开始新对话"
          landingTitle="UniMind 让你的教学更高效"
          landingDescription="出题 · 查学生数据 · 管作业资产"
          botDisplayName="工作台"
          processContent={processMathContent}
          onHasConversation={setHasConversation}
          onSendReady={(fn) => { doSendRef.current = fn; }}
          toolbarAction={{
            icon: Brain,
            label: '智能分析',
            tooltip: 'Agent 智能分析',
            onClick: () => doSendRef.current?.('帮我分析当前机构学习情况，给出洞察和建议'),
          }}
          onQuestionsGenerated={handleQuestionsGenerated}
          onLoadSession={(session, defaultHandler) => {
            setWasResetManually(false);
            setViewMode('overview');
            defaultHandler(session);
          }}
          onReset={(defaultHandler) => {
            setGeneratedQuestions([]);
            setSavedIndices(new Set());
            setPipelineTaskId(null);
            setViewMode('overview');
            setWasResetManually(true);
            clearState();
            setHasConversation(false);
            defaultHandler();
          }}
          onDone={(refreshSessions) => {
            setWasResetManually(false);
            refreshSessions();
          }}
        />
      </div>
    </div>
  );
}
