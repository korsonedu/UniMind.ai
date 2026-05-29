import { useState, useRef, useEffect, useCallback } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { Send, Loader2, RotateCcw, Lightbulb, FileQuestion, GraduationCap, Wand2, BookCheck, History } from 'lucide-react';
import api from '@/lib/api';
import { processMathContent, cn } from '@/lib/utils';
import { useAuthStore } from '@/store/useAuthStore';
import { useSystemStore } from '@/store/useSystemStore';
import { toast } from 'sonner';
import { useTypewriter } from '@/hooks/useTypewriter';
import ChatBubble from '@/components/ChatBubble';
import { ToolStepMessage } from '@/components/AgentStepCard';
import QuestionPanel from './workbench/QuestionPanel';
import type { AgentStep } from '@/hooks/useAgentChat';

interface Message {
  role: 'user' | 'assistant';
  content: string;
  timestamp?: string;
  toolStep?: AgentStep;
  visible?: boolean;
  _id?: string;
  metadata?: {
    generated_questions?: QuestionData[];
    pipeline_task_id?: number | null;
  };
}

interface ConversationSession {
  id: number;
  label: string;
  messages: Message[];
  lastTime: string;
}

interface Bot {
  id: number;
  name: string;
  avatar: string | null;
  bot_type: string;
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
  review_score?: number;
  review_feedback?: string;
}

const SKILLS = [
  { icon: FileQuestion, label: '针对薄弱点出题', prompt: '根据班级薄弱知识点出题' },
  { icon: GraduationCap, label: '出一套模拟卷', prompt: '出一套期末模拟卷，30题，难度适中' },
  { icon: Wand2, label: '自定义出题', prompt: '帮我出10道微积分极限的客观题' },
  { icon: BookCheck, label: '周测出题', prompt: '出一套周测，15题，覆盖最近学的知识点' },
];

export default function Workbench() {
  const { user } = useAuthStore();
  const setPageHeader = useSystemStore(state => state.setPageHeader);
  const [bot, setBot] = useState<Bot | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [isComposing, setIsComposition] = useState(false);
  const [initialized, setInitialized] = useState(false);
  const [skillOpen, setSkillOpen] = useState(false);
  const [sessions, setSessions] = useState<ConversationSession[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<number | null>(null);
  const [sessionOpen, setSessionOpen] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const messagesRef = useRef(messages);
  useEffect(() => { messagesRef.current = messages; }, [messages]);
  const [chatWidth, setChatWidth] = useState(() => Math.round(window.innerWidth / 3));
  const [manualPipelineTaskId, setManualPipelineTaskId] = useState<number | null>(null);
  const [savedIndices, setSavedIndices] = useState<Set<number>>(new Set());
  const [dragging, setDragging] = useState(false);
  const isDragging = useRef(false);
  const dragStartX = useRef(0);
  const dragStartWidth = useRef(0);

  const handleDragStart = useCallback((e: React.MouseEvent) => {
    isDragging.current = true;
    setDragging(true);
    dragStartX.current = e.clientX;
    dragStartWidth.current = chatWidth;
    document.body.style.cursor = 'col-resize';

    const handleMouseMove = (e: MouseEvent) => {
      if (!isDragging.current) return;
      const delta = dragStartX.current - e.clientX;
      const newWidth = Math.min(Math.max(dragStartWidth.current + delta, 280), Math.round(window.innerWidth * 0.5));
      setChatWidth(newWidth);
    };

    const handleMouseUp = () => {
      isDragging.current = false;
      setDragging(false);
      document.body.style.cursor = '';
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseup', handleMouseUp);
    };

    document.addEventListener('mousemove', handleMouseMove);
    document.addEventListener('mouseup', handleMouseUp);
  }, [chatWidth]);

  const hasConversation = activeSessionId !== null || messages.some(m => m.role === 'user');

  const groupIntoSessions = useCallback((allMessages: Message[]): ConversationSession[] => {
    if (allMessages.length === 0) return [];
    const GAP_MS = 30 * 60 * 1000;
    const sessions: Message[][] = [[]];
    for (const msg of allMessages) {
      const current = sessions[sessions.length - 1];
      if (current.length > 0 && msg.timestamp) {
        const lastTime = new Date(current[current.length - 1].timestamp || 0).getTime();
        const thisTime = new Date(msg.timestamp).getTime();
        if (thisTime - lastTime > GAP_MS) {
          sessions.push([]);
        }
      }
      sessions[sessions.length - 1].push(msg);
    }
    return sessions.map((msgs, i) => {
      const firstUser = msgs.find(m => m.role === 'user');
      const label = firstUser ? firstUser.content.slice(0, 30) + (firstUser.content.length > 30 ? '...' : '') : '对话';
      return {
        id: i,
        label,
        messages: msgs,
        lastTime: msgs[msgs.length - 1].timestamp || '',
      };
    });
  }, []);

  const placeholder = useTypewriter({
    words: [
      '描述你的出题需求...',
      '根据薄弱知识点出题',
      '出一套期末模拟卷',
      '帮我出10道微积分客观题',
    ],
    typingSpeed: 100,
    deletingSpeed: 100,
    pauseDuration: 170,
  });

  // 从 messages 的 metadata 中提取生成的题目和管线 task_id
  const generatedQuestions = messages
    .filter(m => m.role === 'assistant' && m.metadata?.generated_questions?.length)
    .flatMap(m => m.metadata!.generated_questions!);

  const activePipelineTaskId = manualPipelineTaskId || messages
    .filter(m => m.role === 'assistant' && m.metadata?.pipeline_task_id)
    .map(m => m.metadata!.pipeline_task_id!)
    .pop() || null;

  useEffect(() => {
    setPageHeader('', '');
    return () => setPageHeader('', '');
  }, [setPageHeader]);

  const handleLoadSession = useCallback((session: ConversationSession) => {
    setMessages(session.messages);
    setActiveSessionId(session.id);
    setSessionOpen(false);
  }, []);

  const handleRefreshSessions = useCallback(async () => {
    if (!bot) return;
    try {
      const hRes = await api.get('/ai/history/', { params: { bot_id: bot.id } });
      if (hRes.data.length > 0) {
        const allMsgs: Message[] = hRes.data.map((m: any) => ({
          ...m,
          content: processMathContent(m.content),
        }));
        setSessions(groupIntoSessions(allMsgs));
      }
    } catch { /* ignore */ }
  }, [bot, groupIntoSessions]);

  // 从 history API 获取 metadata 并合并到当前 messages（不替换 step 气泡）
  const refreshMetadata = useCallback(async () => {
    if (!bot) return;
    try {
      const hRes = await api.get('/ai/history/', { params: { bot_id: bot.id } });
      if (hRes.data.length > 0) {
        // 更新 session 列表
        const allMsgs: Message[] = hRes.data.map((m: any) => ({
          ...m,
          content: processMathContent(m.content),
        }));
        setSessions(groupIntoSessions(allMsgs));
        // 将 metadata 合并到当前 messages 的最后一条 assistant 消息
        const lastHistMsg = hRes.data[hRes.data.length - 1];
        if (lastHistMsg?.metadata) {
          setMessages(prev => {
            const updated = [...prev];
            for (let i = updated.length - 1; i >= 0; i--) {
              if (updated[i].role === 'assistant' && !updated[i].toolStep && !updated[i].metadata) {
                updated[i] = { ...updated[i], metadata: lastHistMsg.metadata };
                break;
              }
            }
            return updated;
          });
        }
      }
    } catch { /* ignore */ }
  }, [bot, groupIntoSessions]);

  // 初始化：加载 bot 和历史消息
  useEffect(() => {
    const init = async () => {
      try {
        const bRes = await api.get('/ai/bots/');
        const agent = bRes.data.find((b: Bot) => b.bot_type === 'exam_generator');
        if (agent) {
          setBot(agent);
          const hRes = await api.get('/ai/history/', { params: { bot_id: agent.id } });
          if (hRes.data.length > 0) {
            const allMsgs: Message[] = hRes.data.map((m: any) => ({
              ...m,
              content: processMathContent(m.content),
            }));
            const grouped = groupIntoSessions(allMsgs);
            setSessions(grouped);
            const lastMsg = hRes.data[hRes.data.length - 1];
            const isRecent = Date.now() - new Date(lastMsg.timestamp).getTime() < 86400000;
            if (isRecent && grouped.length > 0) {
              const latest = grouped[grouped.length - 1];
              setMessages(latest.messages);
              setActiveSessionId(latest.id);
            }
          }
        }
      } catch {
        toast.error('加载命题官失败');
      } finally {
        setInitialized(true);
      }
    };
    init();
  }, []);

  // 自动滚动到底部
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, loading]);

  const doSend = useCallback(async (text: string) => {
    if (!bot) return;
    setLoading(true);

    if (activeSessionId === null) {
      setActiveSessionId(0);
    }

    let msgId = 0;
    const nextId = () => `msg_${++msgId}_${Date.now()}`;

    const userMsg: Message = { _id: nextId(), role: 'user', content: text, timestamp: new Date().toISOString() };
    setMessages(prev => [...prev, userMsg]);

    try {
      const authHeaders: Record<string, string> = { 'Content-Type': 'application/json' };
      try {
        const stored = localStorage.getItem('auth-storage');
        if (stored) {
          const token = JSON.parse(stored)?.state?.token;
          if (token) authHeaders['Authorization'] = `Token ${token}`;
        }
      } catch { /* ignore */ }
      const res = await fetch('/api/ai/chat/stream/', {
        method: 'POST',
        headers: authHeaders,
        credentials: 'include',
        body: JSON.stringify({ message: text, bot_id: bot.id }),
      });

      if (!res.ok) throw new Error(`HTTP ${res.status}`);

      const reader = res.body?.getReader();
      if (!reader) throw new Error('Stream not available');

      const decoder = new TextDecoder();
      let leftover = '';
      const shownCount = { current: 0 };
      const STEP_DELAY_MS = 600;

      function scheduleShow(id: string, pos: number) {
        const delay = Math.max(0, pos - shownCount.current) * STEP_DELAY_MS;
        setTimeout(() => {
          shownCount.current = Math.max(shownCount.current, pos + 1);
          setMessages(prev => prev.map(m => m._id === id ? { ...m, visible: true } : m));
        }, delay);
      }

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        leftover += decoder.decode(value, { stream: true });
        const lines = leftover.split('\n');
        leftover = lines.pop() || '';

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;
          try {
            const payload = JSON.parse(line.slice(6));
            if (payload.type === 'step') {
              const step = payload as AgentStep;
              if (step.status === 'calling') {
                const id = nextId();
                setMessages(prev => {
                  scheduleShow(id, prev.length);
                  return [...prev, {
                    _id: id,
                    role: 'assistant' as const,
                    content: '',
                    toolStep: step,
                    visible: false,
                    timestamp: new Date().toISOString(),
                  }];
                });
              } else if (step.status === 'done') {
                setMessages(prev => prev.map(m =>
                  m.toolStep?.call_id === step.call_id ? { ...m, toolStep: step } : m
                ));
              }
            } else if (payload.type === 'text_delta') {
              // Ignore streaming text, wait for final done event
            } else if (payload.type === 'error') {
              toast.error(payload.message || 'AI 调用失败');
            } else if (payload.done) {
              const finalContent = payload.full_content || '';
              if (payload.is_error) {
                toast.error(finalContent || 'AI 调用失败');
              } else if (finalContent) {
                const id = nextId();
                setMessages(prev => {
                  scheduleShow(id, prev.length);
                  return [...prev, {
                    _id: id,
                    role: 'assistant' as const,
                    content: processMathContent(finalContent),
                    visible: false,
                    timestamp: new Date().toISOString(),
                  }];
                });
              }
              setLoading(false);
              refreshMetadata();
            } else if (payload.error) {
              toast.error(payload.error);
            }
          } catch { /* ignore parse errors */ }
        }
      }
    } catch {
      toast.error('发送失败，请重试');
      setInput(text);
    } finally {
      setLoading(false);
    }
  }, [bot, activeSessionId, refreshMetadata]);

  const handleSend = useCallback(() => {
    if (!input.trim() || loading || !bot) return;
    const text = input;
    setInput('');
    doSend(text);
  }, [input, loading, bot, doSend]);

  const handleReset = useCallback(async () => {
    if (!bot) return;
    setMessages([]);
    setActiveSessionId(null);
    toast.success('已开始新对话');
  }, [bot]);

  const handleSkillSelect = useCallback((prompt: string) => {
    setInput(prompt);
    setSkillOpen(false);
    setTimeout(() => inputRef.current?.focus(), 0);
  }, []);

  if (!initialized) {
    return (
      <div className="h-full flex items-center justify-center">
        <Loader2 className="h-4 w-4 animate-spin text-muted-foreground/40" />
      </div>
    );
  }

  // ── Landing state ──
  if (!hasConversation) {
    return (
      <TooltipProvider delayDuration={300}>
        <div className="h-full flex flex-col items-center justify-center px-4 animate-in fade-in duration-500">
          <div className="w-full max-w-sm space-y-4">
            {/* Greeting */}
            <div className="text-center space-y-1">
              <h1 className="text-base font-semibold tracking-tight text-foreground/90">你好，我是命题官</h1>
              <p className="text-[11px] text-muted-foreground/50">你的 AI 命题官</p>
            </div>

            {/* Input */}
            <div className="relative">
              <div className="flex items-center gap-1.5 bg-card rounded-xl p-1 border border-border/60 transition-all duration-200 focus-within:border-border">
                <Input
                  ref={inputRef}
                  value={input}
                  onChange={e => setInput(e.target.value)}
                  onCompositionStart={() => setIsComposition(true)}
                  onCompositionEnd={() => setIsComposition(false)}
                  onKeyDown={e => { if (e.key === 'Enter' && !isComposing) { e.preventDefault(); handleSend(); } }}
                  placeholder={placeholder}
                  autoComplete="off"
                  className="bg-transparent border-none shadow-none focus-visible:ring-0 text-[13px] h-8 px-2.5 placeholder:text-muted-foreground/40"
                  disabled={loading}
                />
                <Button
                  onClick={handleSend}
                  disabled={loading || !input.trim()}
                  size="icon"
                  className="rounded-lg h-8 w-8 bg-foreground text-background shadow-none active:scale-95 transition-all shrink-0 hover:opacity-90"
                >
                  {loading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Send className="h-3.5 w-3.5" />}
                </Button>
              </div>

              {/* Bottom-left icon buttons */}
              <div className="flex items-center gap-0 mt-1 ml-0.5">
                {sessions.length > 0 && (
                  <Popover open={sessionOpen} onOpenChange={setSessionOpen}>
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <PopoverTrigger asChild>
                          <button className="p-1 rounded text-muted-foreground/40 hover:text-foreground/60 transition-colors">
                            <History className="h-3 w-3" />
                          </button>
                        </PopoverTrigger>
                      </TooltipTrigger>
                      <TooltipContent side="bottom" className="text-[10px]">
                        历史对话 ({sessions.length})
                      </TooltipContent>
                    </Tooltip>
                    <PopoverContent align="start" side="top" className="w-56 p-1 rounded-lg border-border/60 shadow-lg max-h-52 overflow-y-auto">
                      <div className="space-y-0.5">
                        {[...sessions].reverse().map(session => (
                          <button
                            key={session.id}
                            onClick={() => handleLoadSession(session)}
                            className="w-full flex flex-col gap-0.5 px-2 py-1.5 rounded-md hover:bg-muted/50 transition-colors text-left"
                          >
                            <span className="text-[11px] font-medium truncate">{session.label}</span>
                            <span className="text-[9px] text-muted-foreground/50">
                              {session.messages.length} 条消息
                              {session.lastTime && ` · ${new Date(session.lastTime).toLocaleDateString('zh-CN', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}`}
                            </span>
                          </button>
                        ))}
                      </div>
                    </PopoverContent>
                  </Popover>
                )}

                <Popover open={skillOpen} onOpenChange={setSkillOpen}>
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <PopoverTrigger asChild>
                        <button className={cn(
                          "p-1 rounded transition-colors",
                          skillOpen ? "text-primary/60" : "text-muted-foreground/40 hover:text-foreground/60"
                        )}>
                          <Lightbulb className="h-3 w-3" />
                        </button>
                      </PopoverTrigger>
                    </TooltipTrigger>
                    <TooltipContent side="bottom" className="text-[10px]">
                      快捷出题
                    </TooltipContent>
                  </Tooltip>
                  <PopoverContent
                    align="start"
                    side="top"
                    className="w-48 p-1 rounded-lg border-border/60 shadow-lg"
                  >
                    <div className="space-y-0.5">
                      {SKILLS.map(skill => (
                        <button
                          key={skill.label}
                          onClick={() => handleSkillSelect(skill.prompt)}
                          className="w-full flex items-center gap-1.5 px-2 py-1.5 rounded-md hover:bg-muted/50 transition-colors text-left"
                        >
                          <skill.icon className="h-3 w-3 shrink-0 text-muted-foreground/40" />
                          <span className="text-[11px] font-medium">{skill.label}</span>
                        </button>
                      ))}
                    </div>
                  </PopoverContent>
                </Popover>
              </div>
            </div>

            {/* Skill pills */}
            <div className="flex flex-wrap justify-center gap-1.5">
              {SKILLS.map(skill => (
                <button
                  key={skill.label}
                  onClick={() => handleSkillSelect(skill.prompt)}
                  className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full border border-border/50 text-[10px] text-muted-foreground/60 hover:text-foreground/80 hover:border-border transition-colors"
                >
                  {skill.label}
                </button>
              ))}
            </div>
          </div>
        </div>
      </TooltipProvider>
    );
  }

  // ── Chat state ──
  return (
    <TooltipProvider delayDuration={300}>
      <div className="h-full flex animate-in fade-in duration-300">
        {/* 左侧：生成的题目 */}
        <div className="flex-1 min-w-0 h-full">
          <QuestionPanel
            questions={generatedQuestions.filter((_, i) => !savedIndices.has(i))}
            pipelineTaskId={activePipelineTaskId}
            bot={bot}
            onPipelineStart={setManualPipelineTaskId}
            onQuestionsSaved={(indices) => setSavedIndices(prev => { const next = new Set(prev); indices.forEach(i => next.add(i)); return next; })}
          />
        </div>

        {/* 右侧：聊天 */}
        <div
          className={cn("shrink-0 flex flex-col h-full border-l border-border/40 hidden md:flex relative", dragging && "select-none")}
          style={{ width: chatWidth }}
        >
          {/* Drag handle */}
          <div
            className="absolute left-0 top-0 bottom-0 w-1.5 cursor-col-resize group z-10"
            onMouseDown={handleDragStart}
          >
            <div className="w-px h-full bg-border/0 group-hover:bg-primary/30 transition-colors mx-auto" />
          </div>
          {/* Header */}
          <div className="h-10 shrink-0 px-3 flex items-center justify-between">
            <div className="flex items-center gap-1.5">
              <span className="text-[12px] font-semibold text-foreground/80">命题官</span>
              {sessions.length > 1 && (
                <Popover open={sessionOpen} onOpenChange={setSessionOpen}>
                  <PopoverTrigger asChild>
                    <button className="text-[9px] text-muted-foreground/40 hover:text-foreground/60 transition-colors">
                      {sessions.length} 个对话
                    </button>
                  </PopoverTrigger>
                  <PopoverContent align="start" side="bottom" className="w-56 p-1 rounded-lg border-border/60 shadow-lg max-h-52 overflow-y-auto">
                    <div className="space-y-0.5">
                      {[...sessions].reverse().map(session => (
                        <button
                          key={session.id}
                          onClick={() => { handleLoadSession(session); setSessionOpen(false); }}
                          className={cn(
                            "w-full flex flex-col gap-0.5 px-2 py-1.5 rounded-md transition-colors text-left",
                            session.id === activeSessionId ? "bg-muted/50" : "hover:bg-muted/50"
                          )}
                        >
                          <span className="text-[11px] font-medium truncate">{session.label}</span>
                          <span className="text-[9px] text-muted-foreground/50">
                            {session.messages.length} 条消息
                            {session.lastTime && ` · ${new Date(session.lastTime).toLocaleDateString('zh-CN', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}`}
                          </span>
                        </button>
                      ))}
                    </div>
                  </PopoverContent>
                </Popover>
              )}
            </div>
            <Button
              variant="ghost"
              size="sm"
              onClick={handleReset}
              className="rounded text-muted-foreground/40 hover:text-foreground/60 gap-0.5 px-1.5 h-5"
            >
              <RotateCcw className="h-2.5 w-2.5" />
              <span className="text-[9px] font-medium">新对话</span>
            </Button>
          </div>

          {/* Messages */}
          <div ref={scrollRef} className="flex-1 overflow-y-auto min-h-0">
            <div className="p-2.5 space-y-2">
              {messages.filter(m => m.role === 'user' || m.visible !== false).map((msg, i) => (
                msg.toolStep ? (
                  <ToolStepMessage
                    key={msg._id || i}
                    step={msg.toolStep}
                    index={i}
                  />
                ) : (
                  <ChatBubble
                    key={msg._id || i}
                    msg={msg}
                    isUser={msg.role === 'user'}
                    index={i}
                    compact
                  />
                )
              ))}
              {loading && (
                <ChatBubble
                  msg={{ role: 'assistant', content: '' }}
                  isUser={false}
                  isThinking
                  index={messages.length}
                  compact
                />
              )}
            </div>
          </div>

          {/* Input */}
          <div className="shrink-0 p-2">
            <div className="flex items-center gap-0 mb-0.5 ml-0.5">
              <Popover open={skillOpen} onOpenChange={setSkillOpen}>
                <Tooltip>
                  <TooltipTrigger asChild>
                    <PopoverTrigger asChild>
                      <button className={cn(
                        "p-0.5 rounded transition-colors",
                        skillOpen ? "text-primary/60" : "text-muted-foreground/40 hover:text-foreground/60"
                      )}>
                        <Lightbulb className="h-2.5 w-2.5" />
                      </button>
                    </PopoverTrigger>
                  </TooltipTrigger>
                  <TooltipContent side="top" className="text-[10px]">
                    快捷出题
                  </TooltipContent>
                </Tooltip>
                <PopoverContent
                  align="start"
                  side="top"
                  className="w-48 p-1 rounded-lg border-border/60 shadow-lg"
                >
                  <div className="space-y-0.5">
                    {SKILLS.map(skill => (
                      <button
                        key={skill.label}
                        onClick={() => handleSkillSelect(skill.prompt)}
                        className="w-full flex items-center gap-1.5 px-2 py-1.5 rounded-md hover:bg-muted/50 transition-colors text-left"
                      >
                        <skill.icon className="h-3 w-3 shrink-0 text-muted-foreground/40" />
                        <span className="text-[11px] font-medium">{skill.label}</span>
                      </button>
                    ))}
                  </div>
                </PopoverContent>
              </Popover>
            </div>

            <div className="flex items-center gap-1 bg-muted/40 rounded-lg p-0.5">
              <Input
                value={input}
                onChange={e => setInput(e.target.value)}
                onCompositionStart={() => setIsComposition(true)}
                onCompositionEnd={() => setIsComposition(false)}
                onKeyDown={e => { if (e.key === 'Enter' && !isComposing) { e.preventDefault(); handleSend(); } }}
                placeholder="描述出题需求..."
                autoComplete="off"
                className="bg-transparent border-none shadow-none focus-visible:ring-0 text-[12px] h-7 px-2.5 placeholder:text-muted-foreground/35"
                disabled={loading}
              />
              <Button
                onClick={handleSend}
                disabled={loading || !input.trim()}
                size="icon"
                className="rounded-md h-7 w-7 bg-foreground text-background shadow-none active:scale-95 transition-all shrink-0"
              >
                <Send className="h-3 w-3" />
              </Button>
            </div>
          </div>
        </div>
      </div>
    </TooltipProvider>
  );
}
