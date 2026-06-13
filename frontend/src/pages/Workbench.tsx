import { useEffect, useState, useRef, useCallback } from 'react';
import { FileText, GraduationCap, MagicWand, CheckSquareOffset, Users, ChartBar, Brain, ArrowLeft, Files, Lightning } from '@phosphor-icons/react';
import api from '@/lib/api';
import { processMathContent } from '@/lib/utils';
import AgentChatLayout from '@/components/AgentChatLayout';
import QuestionPanel from '@/pages/workbench/QuestionPanel';
import type { Bot, Message, ConversationSession } from '@/hooks/useAgentConversation';
import type { AgentStep } from '@/hooks/useAgentChat';

interface InstitutionStats {
  weekly_active_students: number;
  top_weak_points: { label: string; weak_count: number }[];
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
  { icon: FileText, label: '针对薄弱点出题', prompt: '根据班级薄弱知识点出题' },
  { icon: GraduationCap, label: '出一套模拟卷', prompt: '出一套期末模拟卷，30题，难度适中' },
  { icon: MagicWand, label: '自定义出题', prompt: '帮我出10道微积分极限的客观题' },
  { icon: CheckSquareOffset, label: '周测出题', prompt: '出一套周测，15题，覆盖最近学的知识点' },
];

type ViewMode = 'overview' | 'questions';

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
      <div className="flex items-center gap-2">
        <Brain className="h-5 w-5 text-primary" />
        <h2 className="text-lg font-black tracking-tight">Copilot</h2>
        <span className="text-xs text-muted-foreground font-bold uppercase tracking-wider ml-auto">
          {institution.plan_label} · {institution.student_count}/{institution.max_students} 学员
        </span>
      </div>

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
        <div className="rounded-xl border border-border bg-card p-4">
          <div className="flex items-center gap-2 text-muted-foreground text-xs font-bold uppercase tracking-wider mb-2">
            <Users className="h-3.5 w-3.5" />
            本周活跃
          </div>
          <div className="text-2xl font-black">{stats.weekly_active_students}</div>
          <div className="text-xs text-muted-foreground mt-0.5">
            共 {institution.student_count} 名学员 / {institution.staff_count} 名教师
          </div>
        </div>

        <div className="rounded-xl border border-border bg-card p-4">
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
          <div className="text-sm font-bold">随时待命</div>
          <div className="text-xs text-muted-foreground mt-0.5 flex-1">
            对话中直接告诉我需求
          </div>
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
                  className="text-xs font-bold text-primary/60 hover:text-primary transition-colors shrink-0 opacity-0 group-hover:opacity-100"
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
  const [viewMode, setViewMode] = useState<ViewMode>(
    persisted?.questions?.length ? 'overview' : 'overview'
  );

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
        if (found) setBot(found);
      })
      .catch(() => {});
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

  // 未处理的题目数
  const remainingCount = generatedQuestions.length - savedIndices.size;

  return (
    <div className="flex h-full min-h-0">
      {/* Left: QuestionPanel or Copilot Overview */}
      <div className="flex-1 min-w-0 overflow-y-auto">
        {viewMode === 'questions' && generatedQuestions.length > 0 ? (
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
        ) : (
          <div className="p-4 md:p-6">
            {instInfo && stats && (
              <CopilotOverview
                institution={instInfo}
                stats={stats}
                questionCount={remainingCount}
                onEnterQuestions={() => setViewMode('questions')}
                onSend={handleSystemMessage}
              />
            )}
          </div>
        )}
      </div>

      {/* Right: Agent Chat Sidebar */}
      <div className="w-80 shrink-0 border-l border-border/40 hidden md:flex flex-col">
        <AgentChatLayout
          layout="inline"
          findBot={(bots) => bots.find((b: Bot) => b.bot_type === 'exam_generator')}
          skills={SKILLS}
          typewriterWords={['出题需求...', '根据薄弱知识点出题', '出一套模拟卷']}
          chatPlaceholder="和命题官对话..."
          resetMessage="已开始新对话"
          landingTitle="命题官"
          landingDescription="告诉我需要什么题"
          botDisplayName="命题官"
          processContent={processMathContent}
          onQuestionsGenerated={handleQuestionsGenerated}
          onReset={(defaultHandler) => {
            setGeneratedQuestions([]);
            setSavedIndices(new Set());
            setPipelineTaskId(null);
            setViewMode('overview');
            clearState();
            defaultHandler();
          }}
          onDone={(refreshSessions) => {
            refreshSessions();
          }}
        />
      </div>
    </div>
  );
}
