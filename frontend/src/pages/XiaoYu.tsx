import React, { useState, useEffect, useCallback, useRef } from 'react';
import { useSystemStore } from '@/store/useSystemStore';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Progress } from '@/components/ui/progress';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';
import { Send, Loader2, RotateCcw, Lightbulb, BarChart3, Target, CheckCircle2, CalendarCheck, BookOpen, History, MessageCircleQuestion, BrainCircuit, Trash2 } from 'lucide-react';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import api from '@/lib/api';
import { processMathContent, cn } from '@/lib/utils';
import { toast } from 'sonner';
import { useTypewriter } from '@/hooks/useTypewriter';
import { VisualCanvas, type VisualData } from './xiaoyu/DashboardPanel';
import ChatBubble from '@/components/ChatBubble';
import { ToolStepMessage } from '@/components/AgentStepCard';
import { useAgentConversation, type Bot, type Message, RECENT_SESSION_MS } from '@/hooks/useAgentConversation';
import type { AgentStep } from '@/hooks/useAgentChat';

const SKILLS = [
  { icon: Target, label: '分析薄弱点', prompt: '帮我分析薄弱知识点，给出提升建议' },
  { icon: CalendarCheck, label: '制定学习计划', prompt: '根据我的现状制定一份学习计划' },
  { icon: CheckCircle2, label: '查看复习任务', prompt: '帮我看看今天有哪些需要复习的内容' },
  { icon: BarChart3, label: '学习数据总览', prompt: '帮我分析学习数据，看看整体情况' },
  { icon: BookOpen, label: '推荐课程', prompt: '根据我的薄弱点推荐适合的课程' },
  { icon: Lightbulb, label: '解释一个概念', prompt: '请帮我讲解一个知识点' },
  { icon: MessageCircleQuestion, label: '分析一道题', prompt: '帮我分析这道题的解题思路' },
  { icon: BrainCircuit, label: '总结知识点', prompt: '帮我总结某个知识点的核心内容' },
];

const extractLastVisual = (msgs: Message[]): VisualData | VisualData[] | null => {
  for (let i = msgs.length - 1; i >= 0; i--) {
    const m = msgs[i];
    const all = m.metadata?.all_visuals as VisualData[] | undefined;
    if (all?.length) return all;
    if (m.metadata?.visual) return m.metadata.visual as VisualData;
  }
  return null;
};

export const XiaoYu: React.FC = () => {
  const setPageHeader = useSystemStore(state => state.setPageHeader);
  const [visual, setVisual] = useState<VisualData | VisualData[] | null>(null);
  const pendingVisualsRef = useRef<VisualData[]>([]);

  const {
    bot, messages, input, loading, isComposing, initialized, skillOpen,
    sessions, activeSessionId, sessionOpen, chatWidth, dragging, hasConversation, conversationId,
    scrollRef, inputRef,
    setMessages, setInput, setBot, setInitialized, setSkillOpen, setSessionOpen,
    setIsComposition, setActiveSessionId, setSessions, setConversationId,
    handleDragStart, handleLoadSession, handleRefreshSessions, handleDeleteSession, handleSend, handleReset,
    handleSkillSelect, groupIntoSessions,
  } = useAgentConversation({
    findBot: (bots) => bots.find((b: Bot) => b.name === '小宇'),
    getExtraPayload: () => ({ conversation_id: conversationId }),
    onDone: () => {
      handleRefreshSessions();
    },
    onStepDone: (step, prev) => {
      const updated = prev.map(m =>
        m.toolStep?.call_id === step.call_id ? { ...m, toolStep: step } : m
      );
      return updated;
    },
    onStepDoneEffect: (step) => {
      console.log('[onStepDoneEffect]', step.name, 'hasVisual:', !!step.visual, 'callId:', step.call_id);
      if (step.name === 'render_visual' && step.visual) {
        pendingVisualsRef.current.push(step.visual as VisualData);
        console.log('[onStepDoneEffect] collected visual, total:', pendingVisualsRef.current.length);
      }
    },
    onAllVisuals: (visuals) => {
      console.log('[onAllVisuals] received', visuals.length, 'visuals');
      pendingVisualsRef.current = [];
      setVisual(visuals as VisualData[]);
    },
    resetMessage: '已开始新对话',
  });

  // Apply pending visuals after messages state updates (avoids setVisual inside setMessages updater)
  const prevMsgLenRef = useRef(0);
  useEffect(() => {
    if (messages.length !== prevMsgLenRef.current && pendingVisualsRef.current.length > 0) {
      prevMsgLenRef.current = messages.length;
      const collected = [...pendingVisualsRef.current];
      pendingVisualsRef.current = [];
      setVisual(collected.length === 1 ? collected[0] : collected);
    }
  }, [messages]);

  // Wrap handleLoadSession to also restore visual from session messages
  const handleLoadSessionWithVisual = useCallback((session: Parameters<typeof handleLoadSession>[0]) => {
    handleLoadSession(session);
    setVisual(extractLastVisual(session.messages));
  }, [handleLoadSession]);

  // Wrap handleReset to also clear visual
  const handleResetWithVisual = useCallback(() => {
    handleReset();
    setVisual(null);
  }, [handleReset]);

  const placeholder = useTypewriter({
    words: ['让小宇帮你制定学习计划', '让小宇分析薄弱知识点', '让小宇推荐适合的课程', '让小宇看看复习进度'],
    typingSpeed: 100, deletingSpeed: 100, pauseDuration: 170,
  });

  useEffect(() => {
    setPageHeader('', '');
    return () => setPageHeader('', '');
  }, [setPageHeader]);

  // Init: load bot, history, and dashboard
  useEffect(() => {
    let cancelled = false;
    const init = async () => {
      try {
        const bRes = await api.get('/ai/bots/');
        if (cancelled) return;
        const xiaoyu = bRes.data.find((b: Bot) => b.name === '小宇');
        if (xiaoyu) {
          setBot(xiaoyu);
          let foundSessionVisual: VisualData | VisualData[] | null = null;
          const hRes = await api.get('/ai/history/', { params: { bot_id: xiaoyu.id } });
          if (hRes.data.length > 0) {
            const allMsgs: Message[] = hRes.data.map((m: Record<string, unknown>) => ({
              ...m,
              content: processMathContent(m.content as string),
            }));
            const grouped = groupIntoSessions(allMsgs);
            setSessions(grouped);
            const lastMsg = hRes.data[hRes.data.length - 1];
            if (lastMsg.conversation_id) {
              setConversationId(lastMsg.conversation_id);
            }
            const isRecent = Date.now() - new Date(lastMsg.timestamp).getTime() < RECENT_SESSION_MS;
            if (isRecent && grouped.length > 0) {
              const latest = grouped[grouped.length - 1];
              setMessages(latest.messages);
              setActiveSessionId(latest.id);
              foundSessionVisual = extractLastVisual(latest.messages);
              console.log('[init] isRecent=true, msgs:', latest.messages.length, 'lastMsg metadata:', lastMsg.metadata, 'extracted visual:', foundSessionVisual);
              if (foundSessionVisual) {
                setVisual(foundSessionVisual);
              }
            }
          }
        }
      } catch {
        if (!cancelled) toast.error('Failed to load XiaoYu');
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
              <h1 className="text-base font-semibold tracking-tight text-foreground/90">小宇XiaoYu让学习更具效率。对话即学习。</h1>
              <p className="text-[11px] text-muted-foreground/50">最懂你的学习agent，从数据分析到知识讲解，一个入口搞定</p>
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
                          <div key={session.id}
                            className="w-full flex items-start gap-1 px-2 py-1.5 rounded-md hover:bg-muted/50 transition-colors group">
                            <button onClick={() => handleLoadSessionWithVisual(session)}
                              className="flex-1 flex flex-col gap-0.5 text-left min-w-0">
                              <span className="text-[11px] font-medium truncate">{session.label}</span>
                              <span className="text-[9px] text-muted-foreground/50">
                                {session.messages.length} 条消息
                                {session.lastTime && ` · ${new Date(session.lastTime).toLocaleDateString('zh-CN', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}`}
                              </span>
                            </button>
                            <button onClick={(e) => { e.stopPropagation(); handleDeleteSession(session); }}
                              className="shrink-0 mt-0.5 p-0.5 rounded opacity-0 group-hover:opacity-100 text-muted-foreground/40 hover:text-destructive transition-all">
                              <Trash2 className="h-2.5 w-2.5" />
                            </button>
                          </div>
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
                    <TooltipContent side="bottom" className="text-[10px]">技能</TooltipContent>
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
          <VisualCanvas visual={visual} />
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
              <span className="text-[12px] font-semibold text-foreground/80">小宇</span>
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
                        <div key={session.id}
                          className={cn("w-full flex items-start gap-1 px-2 py-1.5 rounded-md transition-colors group", session.id === activeSessionId ? "bg-muted/50" : "hover:bg-muted/50")}>
                          <button onClick={() => { handleLoadSessionWithVisual(session); setSessionOpen(false); }}
                            className="flex-1 flex flex-col gap-0.5 text-left min-w-0">
                            <span className="text-[11px] font-medium truncate">{session.label}</span>
                            <span className="text-[9px] text-muted-foreground/50">
                              {session.messages.length} 条消息
                              {session.lastTime && ` · ${new Date(session.lastTime).toLocaleDateString('zh-CN', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}`}
                            </span>
                          </button>
                          {session.id !== activeSessionId && (
                            <button onClick={(e) => { e.stopPropagation(); handleDeleteSession(session); }}
                              className="shrink-0 mt-0.5 p-0.5 rounded opacity-0 group-hover:opacity-100 text-muted-foreground/40 hover:text-destructive transition-all">
                              <Trash2 className="h-2.5 w-2.5" />
                            </button>
                          )}
                        </div>
                      ))}
                    </div>
                  </PopoverContent>
                </Popover>
              )}
            </div>
            <Button variant="ghost" size="sm" onClick={handleResetWithVisual}
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
                  <TooltipContent side="top" className="text-[10px]">技能</TooltipContent>
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
                placeholder="和小宇对话..."
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
};

export default XiaoYu;
