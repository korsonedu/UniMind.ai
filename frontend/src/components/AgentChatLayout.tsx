import React, { useState, useEffect, useRef } from 'react';
import { useSystemStore } from '@/store/useSystemStore';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { Send, Loader2, RotateCcw, Lightbulb, History, Trash2 } from 'lucide-react';
import api from '@/lib/api';
import { processMathContent, cn } from '@/lib/utils';
import { toast } from 'sonner';
import { useTypewriter } from '@/hooks/useTypewriter';
import ChatBubble from '@/components/ChatBubble';
import { ToolStepMessage } from '@/components/AgentStepCard';
import {
  useAgentConversation,
  type Bot,
  type Message,
  type ConversationSession,
  RECENT_SESSION_MS,
} from '@/hooks/useAgentConversation';
import type { AgentStep } from '@/hooks/useAgentChat';
import type { LucideIcon } from 'lucide-react';
import type { VisualData } from '../pages/xiaoyu/DashboardPanel';

// ── Types ──

export interface Skill {
  icon: LucideIcon;
  label: string;
  prompt: string;
}

export interface RightPanelProps {
  bot: Bot;
  messages: Message[];
  loading: boolean;
  conversationId: string;
  visual: VisualData | VisualData[] | null;
  setVisual: React.Dispatch<React.SetStateAction<VisualData | VisualData[] | null>>;
  handleRefreshSessions: () => void;
  doSend: (text: string) => void;
  setSessions: React.Dispatch<React.SetStateAction<ConversationSession[]>>;
  groupIntoSessions: (msgs: Message[]) => ConversationSession[];
}

export interface AgentChatLayoutProps {
  // Bot & skills
  findBot: (bots: Bot[]) => Bot | undefined;
  skills: Skill[];
  typewriterWords: string[];
  chatPlaceholder: string;
  resetMessage?: string;

  // Landing page
  landingTitle: string;
  landingDescription: string;
  skillTooltip?: string;

  // Chat header
  botDisplayName: string;

  // Init
  /** Process message content during init (e.g. processMathContent). Default: identity */
  processContent?: (content: string) => string;

  // useAgentConversation callbacks
  getExtraPayload?: () => Record<string, unknown>;
  onStepDone?: (step: AgentStep, prev: Message[]) => Message[] | null;
  /** Called after SSE 'done'. Receives refreshSessions; defaults to calling it. */
  onDone?: (refreshSessions: () => void) => void;

  // Visual step handling — called internally by the layout for every render_visual step
  /** Return a visual object from a step, or null if not a visual step */
  extractVisualFromStep?: (step: AgentStep) => VisualData | null;

  // Session & reset wrappers
  onLoadSession?: (session: ConversationSession, defaultHandler: (s: ConversationSession) => void) => void;
  onReset?: (defaultHandler: () => void) => void;
  onDeleteSession?: (session: ConversationSession) => void;

  // Right panel
  renderRightPanel: (props: RightPanelProps) => React.ReactNode;
}

// ── Component ──

export default function AgentChatLayout(props: AgentChatLayoutProps) {
  const {
    findBot, skills, typewriterWords, chatPlaceholder, resetMessage,
    landingTitle, landingDescription, skillTooltip = '技能',
    botDisplayName,
    processContent,
    getExtraPayload, onStepDone, onDone,
    extractVisualFromStep,
    onLoadSession, onReset, onDeleteSession,
    renderRightPanel,
  } = props;

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
    handleSkillSelect, groupIntoSessions, doSend,
  } = useAgentConversation({
    findBot,
    getExtraPayload,
    onDone: () => onDone?.(handleRefreshSessions),
    onStepDone,
    onStepDoneEffect: extractVisualFromStep ? (step) => {
      const v = extractVisualFromStep(step);
      if (v) pendingVisualsRef.current.push(v);
    } : undefined,
    onAllVisuals: (visuals) => {
      pendingVisualsRef.current = [];
      setVisual(visuals as VisualData[]);
    },
    resetMessage,
  });

  // Apply pending visuals after messages state updates
  const prevMsgLenRef = useRef(0);
  useEffect(() => {
    if (messages.length !== prevMsgLenRef.current && pendingVisualsRef.current.length > 0) {
      prevMsgLenRef.current = messages.length;
      const collected = [...pendingVisualsRef.current];
      pendingVisualsRef.current = [];
      setVisual(collected.length === 1 ? collected[0] : collected);
    }
  }, [messages]);

  const placeholder = useTypewriter({
    words: typewriterWords,
    typingSpeed: 100, deletingSpeed: 100, pauseDuration: 170,
  });

  useEffect(() => {
    setPageHeader('', '');
    return () => setPageHeader('', '');
  }, [setPageHeader]);

  // Init: load bot, history, and restore recent session
  useEffect(() => {
    let cancelled = false;
    const init = async () => {
      try {
        const bRes = await api.get('/ai/bots/');
        if (cancelled) return;
        const found = findBot(bRes.data);
        if (found) {
          setBot(found);
          const hRes = await api.get('/ai/history/', { params: { bot_id: found.id } });
          if (hRes.data.length > 0) {
            const allMsgs: Message[] = hRes.data
              .filter((m: Record<string, unknown>) => m.content !== '[Thinking...]')
              .map((m: Record<string, unknown>) => ({
                ...m,
                content: processContent ? processContent(m.content as string) : (m.content as string),
                visible: true,
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
            }
          }
        }
      } catch {
        if (!cancelled) toast.error(`Failed to load ${botDisplayName}`);
      } finally {
        if (!cancelled) setInitialized(true);
      }
    };
    init();
    return () => { cancelled = true; };
  }, []);

  // ── Session load/reset wrappers ──

  const wrappedLoadSession = (session: ConversationSession) => {
    if (onLoadSession) {
      onLoadSession(session, handleLoadSession);
    } else {
      handleLoadSession(session);
    }
    setSessionOpen(false);
  };

  const wrappedReset = () => {
    if (onReset) {
      onReset(handleReset);
    } else {
      handleReset();
    }
  };

  // ── Loading ──

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
              <h1 className="text-base font-semibold tracking-tight text-foreground/90">{landingTitle}</h1>
              <p className="text-[11px] text-muted-foreground/50">{landingDescription}</p>
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
                            <button onClick={() => wrappedLoadSession(session)}
                              className="flex-1 flex flex-col gap-0.5 text-left min-w-0">
                              <span className="text-[11px] font-medium truncate">{session.label}</span>
                              <span className="text-[9px] text-muted-foreground/50">
                                {session.messages.length} 条消息
                                {session.lastTime && ` · ${new Date(session.lastTime).toLocaleDateString('zh-CN', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}`}
                              </span>
                            </button>
                            {onDeleteSession && (
                              <button onClick={(e) => { e.stopPropagation(); onDeleteSession(session); }}
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

                <Popover open={skillOpen} onOpenChange={setSkillOpen}>
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <PopoverTrigger asChild>
                        <button className={cn("p-1 rounded transition-colors", skillOpen ? "text-primary/60" : "text-muted-foreground/40 hover:text-foreground/60")}>
                          <Lightbulb className="h-3 w-3" />
                        </button>
                      </PopoverTrigger>
                    </TooltipTrigger>
                    <TooltipContent side="bottom" className="text-[10px]">{skillTooltip}</TooltipContent>
                  </Tooltip>
                  <PopoverContent align="start" side="top" className="w-48 p-1 rounded-lg border-border/60 shadow-lg">
                    <div className="space-y-0.5">
                      {skills.map(skill => (
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
              {skills.map(skill => (
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
        <div className="flex-1 min-w-0 h-full" style={{ minWidth: '55%' }}>
          {renderRightPanel({
            bot: bot!,
            messages,
            loading,
            conversationId,
            visual,
            setVisual,
            handleRefreshSessions,
            doSend,
            setSessions,
            groupIntoSessions,
          })}
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
              <span className="text-[12px] font-semibold text-foreground/80">{botDisplayName}</span>
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
                          <button onClick={() => { wrappedLoadSession(session); }}
                            className="flex-1 flex flex-col gap-0.5 text-left min-w-0">
                            <span className="text-[11px] font-medium truncate">{session.label}</span>
                            <span className="text-[9px] text-muted-foreground/50">
                              {session.messages.length} 条消息
                              {session.lastTime && ` · ${new Date(session.lastTime).toLocaleDateString('zh-CN', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}`}
                            </span>
                          </button>
                          {onDeleteSession && session.id !== activeSessionId && (
                            <button onClick={(e) => { e.stopPropagation(); onDeleteSession(session); }}
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
            <Button variant="ghost" size="sm" onClick={wrappedReset}
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
                  <TooltipContent side="top" className="text-[10px]">{skillTooltip}</TooltipContent>
                </Tooltip>
                <PopoverContent align="start" side="top" className="w-48 p-1 rounded-lg border-border/60 shadow-lg">
                  <div className="space-y-0.5">
                    {skills.map(skill => (
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
                placeholder={chatPlaceholder}
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
