import { useEffect, useCallback, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { Send, Loader2, RotateCcw, Lightbulb, FileQuestion, GraduationCap, Wand2, BookCheck, History } from 'lucide-react';
import api from '@/lib/api';
import { processMathContent, cn } from '@/lib/utils';
import { useSystemStore } from '@/store/useSystemStore';
import { toast } from 'sonner';
import { useTypewriter } from '@/hooks/useTypewriter';
import ChatBubble from '@/components/ChatBubble';
import { ToolStepMessage } from '@/components/AgentStepCard';
import QuestionPanel from './workbench/QuestionPanel';
import { useAgentConversation, type Bot, type Message, RECENT_SESSION_MS } from '@/hooks/useAgentConversation';

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
  const setPageHeader = useSystemStore(state => state.setPageHeader);
  const [manualPipelineTaskId, setManualPipelineTaskId] = useState<number | null>(null);
  const [savedIndices, setSavedIndices] = useState<Set<number>>(() => {
    try {
      const stored = localStorage.getItem('wb_saved_indices');
      return stored ? new Set(JSON.parse(stored)) : new Set();
    } catch { return new Set(); }
  });

  // 持久化入库状态
  useEffect(() => {
    try { localStorage.setItem('wb_saved_indices', JSON.stringify(Array.from(savedIndices))); } catch {}
  }, [savedIndices]);

  const {
    bot, messages, input, loading, isComposing, initialized, skillOpen,
    sessions, activeSessionId, sessionOpen, chatWidth, dragging, hasConversation, conversationId,
    scrollRef, inputRef,
    setMessages, setInput, setBot, setInitialized, setSkillOpen, setSessionOpen,
    setIsComposition, setActiveSessionId, setSessions, setConversationId,
    handleDragStart, handleLoadSession, handleRefreshSessions, handleSend, handleReset,
    handleSkillSelect, groupIntoSessions, doSend,
  } = useAgentConversation({
    findBot: (bots) => bots.find((b: Bot) => b.bot_type === 'exam_generator'),
    getExtraPayload: () => ({ conversation_id: conversationId }),
    onDone: () => {
      refreshMetadata();
    },
    resetMessage: '已开始新对话',
  });

  // 新对话时清空入库状态（加 initialized 守卫，避免页面加载时误清空）
  useEffect(() => {
    if (initialized && messages.length === 0) setSavedIndices(new Set());
  }, [initialized, messages.length]);

  const placeholder = useTypewriter({
    words: ['描述你的出题需求...', '根据薄弱知识点出题', '出一套期末模拟卷', '帮我出10道微积分客观题'],
    typingSpeed: 100, deletingSpeed: 100, pauseDuration: 170,
  });

  // Extract generated questions and pipeline task from messages metadata
  const generatedQuestions = messages
    .filter(m => m.role === 'assistant' && (m.metadata as { generated_questions?: QuestionData[] })?.generated_questions?.length)
    .flatMap(m => (m.metadata as { generated_questions: QuestionData[] }).generated_questions);

  const activePipelineTaskId = manualPipelineTaskId || messages
    .filter(m => m.role === 'assistant' && (m.metadata as { pipeline_task_id?: number | null })?.pipeline_task_id)
    .map(m => (m.metadata as { pipeline_task_id: number }).pipeline_task_id)
    .pop() || null;

  useEffect(() => {
    setPageHeader('', '');
    return () => setPageHeader('', '');
  }, [setPageHeader]);

  // Metadata refresh: update sessions sidebar from backend history.
  // Metadata (generated_questions etc.) is already set on the final message
  // by the SSE 'done' event payload — no need to patch in-memory messages.
  const refreshMetadata = useCallback(async () => {
    if (!bot) return;
    try {
      const hRes = await api.get('/ai/history/', { params: { bot_id: bot.id, conversation_id: conversationId } });
      if (hRes.data.length > 0) {
        const allMsgs: Message[] = hRes.data
          .filter((m: Record<string, unknown>) => m.content !== '[Thinking...]')
          .map((m: Record<string, unknown>) => ({
            ...m,
            content: processMathContent(m.content as string),
            visible: true,  // History messages are always visible
          }));
        setSessions(groupIntoSessions(allMsgs));
      }
    } catch (e) { console.error('[Workbench] metadata fetch failed:', e); }
  }, [bot, conversationId, groupIntoSessions, setSessions]);

  // Init: load bot and history
  useEffect(() => {
    let cancelled = false;
    const init = async () => {
      try {
        const bRes = await api.get('/ai/bots/');
        if (cancelled) return;
        const agent = bRes.data.find((b: Bot) => b.bot_type === 'exam_generator');
        if (agent) {
          setBot(agent);
          const hRes = await api.get('/ai/history/', { params: { bot_id: agent.id } });
          if (hRes.data.length > 0) {
            const allMsgs: Message[] = hRes.data
              .filter((m: Record<string, unknown>) => m.content !== '[Thinking...]')
              .map((m: Record<string, unknown>) => ({
                ...m,
                content: processMathContent(m.content as string),
                visible: true,  // History messages are always visible
              }));
            const grouped = groupIntoSessions(allMsgs);
            setSessions(grouped);
            // 从历史记录中恢复最近的 conversation_id，避免刷新后新建对话
            const lastMsg = hRes.data[hRes.data.length - 1];
            if (lastMsg.conversation_id) {
              setConversationId(lastMsg.conversation_id);
            }
            const isRecent = Date.now() - new Date(lastMsg.timestamp).getTime() < RECENT_SESSION_MS;
            if (isRecent && grouped.length > 0) {
              const latest = grouped[grouped.length - 1];
              setMessages(latest.messages);
              setActiveSessionId(latest.id);
            }
          }
        }
      } catch {
        if (!cancelled) toast.error('加载命题官失败');
      } finally {
        if (!cancelled) setInitialized(true);
      }
    };
    init();
    return () => { cancelled = true; };
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
            <div className="text-center space-y-1">
              <h1 className="text-base font-semibold tracking-tight text-foreground/90">你好，我是命题官</h1>
              <p className="text-[11px] text-muted-foreground/50">你的 AI 命题官</p>
            </div>

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
                      <TooltipContent side="bottom" className="text-[10px]">历史对话 ({sessions.length})</TooltipContent>
                    </Tooltip>
                    <PopoverContent align="start" side="top" className="w-56 p-1 rounded-lg border-border/60 shadow-lg max-h-52 overflow-y-auto">
                      <div className="space-y-0.5">
                        {[...sessions].reverse().map(session => (
                          <button key={session.id} onClick={() => handleLoadSession(session)}
                            className="w-full flex flex-col gap-0.5 px-2 py-1.5 rounded-md hover:bg-muted/50 transition-colors text-left">
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
                        <button className={cn("p-1 rounded transition-colors", skillOpen ? "text-primary/60" : "text-muted-foreground/40 hover:text-foreground/60")}>
                          <Lightbulb className="h-3 w-3" />
                        </button>
                      </PopoverTrigger>
                    </TooltipTrigger>
                    <TooltipContent side="bottom" className="text-[10px]">快捷出题</TooltipContent>
                  </Tooltip>
                  <PopoverContent align="start" side="top" className="w-48 p-1 rounded-lg border-border/60 shadow-lg">
                    <div className="space-y-0.5">
                      {SKILLS.map(skill => (
                        <button key={skill.label} onClick={() => handleSkillSelect(skill.prompt)}
                          className="w-full flex items-center gap-1.5 px-2 py-1.5 rounded-md hover:bg-muted/50 transition-colors text-left">
                          <skill.icon className="h-3 w-3 shrink-0 text-muted-foreground/40" />
                          <span className="text-[11px] font-medium">{skill.label}</span>
                        </button>
                      ))}
                    </div>
                  </PopoverContent>
                </Popover>
              </div>
            </div>

            <div className="flex flex-wrap justify-center gap-1.5">
              {SKILLS.map(skill => (
                <button key={skill.label} onClick={() => handleSkillSelect(skill.prompt)}
                  className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full border border-border/50 text-[10px] text-muted-foreground/60 hover:text-foreground/80 hover:border-border transition-colors">
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
        <div className="flex-1 min-w-0 h-full">
          <QuestionPanel
            questions={generatedQuestions}
            savedIndices={savedIndices}
            pipelineTaskId={activePipelineTaskId}
            bot={bot}
            onPipelineStart={setManualPipelineTaskId}
            onQuestionsSaved={(indices) => setSavedIndices(prev => { const next = new Set(prev); indices.forEach(i => next.add(i)); return next; })}
            onSystemMessage={(msg) => doSend(msg)}
          />
        </div>

        <div
          className={cn("shrink-0 flex flex-col h-full border-l border-border/40 hidden md:flex relative", dragging && "select-none")}
          style={{ width: chatWidth }}
        >
          <div className="absolute left-0 top-0 bottom-0 w-1.5 cursor-col-resize group z-10" onMouseDown={handleDragStart}>
            <div className="w-px h-full bg-border/0 group-hover:bg-primary/30 transition-colors mx-auto" />
          </div>

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
                        <button key={session.id} onClick={() => { handleLoadSession(session); setSessionOpen(false); }}
                          className={cn("w-full flex flex-col gap-0.5 px-2 py-1.5 rounded-md transition-colors text-left", session.id === activeSessionId ? "bg-muted/50" : "hover:bg-muted/50")}>
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
            <Button variant="ghost" size="sm" onClick={handleReset}
              className="rounded text-muted-foreground/40 hover:text-foreground/60 gap-0.5 px-1.5 h-5">
              <RotateCcw className="h-2.5 w-2.5" />
              <span className="text-[9px] font-medium">新对话</span>
            </Button>
          </div>

          <div ref={scrollRef} className="flex-1 overflow-y-auto min-h-0">
            <div className="p-2.5 space-y-2">
              {messages.filter(m => m.role === 'user' || m.visible !== false).map((msg, i) => (
                msg.toolStep ? (
                  <ToolStepMessage key={msg._id || i} step={msg.toolStep} index={i} />
                ) : (
                  <ChatBubble key={msg._id || i} msg={msg} isUser={msg.role === 'user'} index={i} compact />
                )
              ))}
              {loading && (
                <ChatBubble msg={{ role: 'assistant', content: '' }} isUser={false} isThinking index={messages.length} compact />
              )}
            </div>
          </div>

          <div className="shrink-0 p-2">
            <div className="flex items-center gap-0 mb-0.5 ml-0.5">
              <Popover open={skillOpen} onOpenChange={setSkillOpen}>
                <Tooltip>
                  <TooltipTrigger asChild>
                    <PopoverTrigger asChild>
                      <button className={cn("p-0.5 rounded transition-colors", skillOpen ? "text-primary/60" : "text-muted-foreground/40 hover:text-foreground/60")}>
                        <Lightbulb className="h-2.5 w-2.5" />
                      </button>
                    </PopoverTrigger>
                  </TooltipTrigger>
                  <TooltipContent side="top" className="text-[10px]">快捷出题</TooltipContent>
                </Tooltip>
                <PopoverContent align="start" side="top" className="w-48 p-1 rounded-lg border-border/60 shadow-lg">
                  <div className="space-y-0.5">
                    {SKILLS.map(skill => (
                      <button key={skill.label} onClick={() => handleSkillSelect(skill.prompt)}
                        className="w-full flex items-center gap-1.5 px-2 py-1.5 rounded-md hover:bg-muted/50 transition-colors text-left">
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
              <Button onClick={handleSend} disabled={loading || !input.trim()} size="icon"
                className="rounded-md h-7 w-7 bg-foreground text-background shadow-none active:scale-95 transition-all shrink-0">
                <Send className="h-3 w-3" />
              </Button>
            </div>
          </div>
        </div>
      </div>
    </TooltipProvider>
  );
}
