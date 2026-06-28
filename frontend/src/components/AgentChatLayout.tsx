import React, { useState, useEffect, useLayoutEffect, useRef, useCallback } from 'react';
import { useSystemStore } from '@/store/useSystemStore';
import { Button } from '@/components/ui/button';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { PaperPlaneTilt, Spinner, ArrowCounterClockwise, Lightbulb, ClockCounterClockwise, Trash, Sparkle } from '@phosphor-icons/react';
import api from '@/lib/api';
import { processMathContent, cn } from '@/lib/utils';
import { toast } from 'sonner';
import { useTypewriter } from '@/hooks/useTypewriter';
import ClassSelector from '@/components/ClassSelector';
import ChatBubble from '@/components/ChatBubble';
import { ToolStepMessage } from '@/components/AgentStepCard';
import { InlineVisualCard } from '@/components/InlineVisualCard';
import {
  useAgentConversation,
  type Bot,
  type Message,
  type ConversationSession,
  RECENT_SESSION_MS,
} from '@/hooks/useAgentConversation';
import type { AgentStep } from '@/hooks/useAgentChat';
import type { Icon } from '@phosphor-icons/react';
import type { VisualData } from '@/pages/xiaoyu/visuals';
import { AgentReplyContext } from '@/pages/xiaoyu/visuals/ActionCardsRenderer';
import { TaskList } from '@/components/TaskList';

// ── Types ──

export interface Skill {
  icon: Icon;
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

  /** Called when doSend is ready, exposing it for external message injection */
  onSendReady?: (doSend: (text: string) => void) => void;

  /** Optional extra button in the input toolbar, next to skills */
  toolbarAction?: {
    icon: Icon;
    label: string;
    tooltip: string;
    onClick: () => void;
  };

  // Visual step handling — called internally by the layout for every render_visual step
  /** Return a visual object from a step, or null if not a visual step */
  extractVisualFromStep?: (step: AgentStep) => VisualData | null;

  /** Called when quick_generate yields question data — for populating QuestionPanel */
  onQuestionsGenerated?: (questions: AgentStep['questions']) => void;

  // Session & reset wrappers
  onLoadSession?: (session: ConversationSession, defaultHandler: (s: ConversationSession) => void) => void;
  onReset?: (defaultHandler: () => void) => void;
  onDeleteSession?: (session: ConversationSession) => void;

  /** 布局模式。'split' = 左右分屏（默认），'inline' = 单栏对话流 */
  layout?: 'split' | 'inline';

  // Right panel（仅 split 模式使用）
  renderRightPanel?: (props: RightPanelProps) => React.ReactNode;

  /** 当 hasConversation 状态变化时回调，用于父组件同步布局 */
  onHasConversation?: (hasConversation: boolean) => void;

  /** Landing 页面标题下方额外内容（如数据卡片） */
  landingBanner?: React.ReactNode;

  /** Guided tour: CSS class for the input container */
  inputTourClass?: string;

  /** External conversation ID — when provided, shared across pages */
  initialConversationId?: string;
}

// ── Component ──

export default function AgentChatLayout(props: AgentChatLayoutProps) {
  const {
    findBot, skills, typewriterWords, chatPlaceholder, resetMessage,
    landingTitle, landingDescription, skillTooltip = '技能',
    botDisplayName,
    processContent,
    getExtraPayload, onStepDone, onDone, onSendReady,
    extractVisualFromStep,
    onQuestionsGenerated,
    onLoadSession, onReset, onDeleteSession,
    renderRightPanel,
    toolbarAction,
    layout = 'split',
    onHasConversation,
    landingBanner,
    inputTourClass,
    initialConversationId,
  } = props;

  const setPageHeader = useSystemStore(state => state.setPageHeader);
  const [visual, setVisual] = useState<VisualData | VisualData[] | null>(null);
  const pendingVisualsRef = useRef<VisualData[]>([]);
  const dashboardRef = useRef<HTMLDivElement>(null);

  const {
    bot, messages, input, loading, isComposing, initialized, skillOpen,
    sessions, activeSessionId, sessionOpen, chatWidth, dragging, hasConversation, conversationId, taskList,
    scrollRef, inputRef,
    setMessages, setInput, setBot, setInitialized, setSkillOpen, setSessionOpen,
    setIsComposition, setActiveSessionId, setSessions, setConversationId,
    handleDragStart, handleLoadSession, handleRefreshSessions, handleDeleteSession, handleReset,
    handleSkillSelect, groupIntoSessions, doSend,
  } = useAgentConversation({
    findBot,
    getExtraPayload,
    onDone: () => onDone?.(handleRefreshSessions),
    onStepDone,
    initialConversationId,
    onStepDoneEffect: extractVisualFromStep ? (step) => {
      const v = extractVisualFromStep(step);
      if (v) pendingVisualsRef.current.push(v);
    } : undefined,
    onAllVisuals: (visuals) => {
      pendingVisualsRef.current = [];
      setVisual(visuals as VisualData[]);
    },
    onStepQuestions: onQuestionsGenerated,
    resetMessage,
  });

  // Expose doSend to parent
  useEffect(() => {
    if (onSendReady && doSend) onSendReady(doSend);
  }, [onSendReady, doSend]);

  // Action card reply → send as chat message
  const onActionReply = useCallback((value: string) => {
    doSend(value, true);
  }, [doSend]);

  // 从 messages 或当前 session 中提取标题
  const conversationTitle = React.useMemo(() => {
    // 优先从消息中取
    const fromMsg = messages.find(m => m.conversation_title)?.conversation_title;
    if (fromMsg) return fromMsg;
    // 从当前 session 取
    const activeSession = sessions.find(s => s.id === activeSessionId);
    if (activeSession?.title) return activeSession.title;
    // 从最近一条 session 取（refresh 后 id 可能变化）
    const lastSession = sessions[sessions.length - 1];
    return lastSession?.title || '';
  }, [messages, sessions, activeSessionId]);

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
              .map((m: Record<string, unknown>) => {
                const msg = {
                  ...m,
                  content: processContent ? processContent(m.content as string) : (m.content as string),
                  visible: true,
                } as Message;
                // 恢复 metadata 中的 visual 到 toolStep（历史加载时 visual 存储在 metadata 中）
                const meta = (m as any).metadata;
                const visuals = meta?.all_visuals || (meta?.visual ? [meta.visual] : null);
                if (visuals && visuals.length > 0) {
                  const v = visuals[0];
                  if (msg.toolStep) {
                    // Case 1: toolStep 已存在（从内存恢复的情况），只补 visual
                    if (msg.toolStep.name === 'render_visual' && msg.toolStep.status === 'done' && !msg.toolStep.visual) {
                      msg.toolStep = { ...msg.toolStep, visual: v };
                    }
                  } else {
                    // Case 2: 从 API 加载 → 无 toolStep，从 metadata 构造
                    msg.toolStep = {
                      call_id: `hist-${m.id || 0}`,
                      step: 0,
                      name: 'render_visual',
                      status: 'done',
                      label: (v.payload as any)?.title || '可视化',
                      visual: v,
                      args_summary: '',
                      result_summary: '',
                    };
                  }
                  // 清理 metadata 避免渲染时走 hasMetadataVisual 分母重复
                  if ((msg as any).metadata) {
                    delete (msg as any).metadata.visual;
                    delete (msg as any).metadata.all_visuals;
                  }
                }
                return msg;
              });
            const grouped = groupIntoSessions(allMsgs);
            setSessions(grouped);
            const lastMsg = hRes.data[hRes.data.length - 1];
            const isRecent = lastMsg && Date.now() - new Date(lastMsg.timestamp).getTime() < RECENT_SESSION_MS;
            if (isRecent && lastMsg.conversation_id) {
              setConversationId(lastMsg.conversation_id);
            }
            // 有历史对话时，自动加载最新 session（不限制时间窗口）
            if (grouped.length > 0) {
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

  // 做题后回到小宇，自动触发判分分析
  useEffect(() => {
    if (!initialized) return;
    const params = new URLSearchParams(window.location.search);
    if (params.get('practiceDone') === '1') {
      window.history.replaceState({}, '', window.location.pathname);
      setTimeout(() => doSend('帮我分析刚才的练习结果'), 500);
    }
  }, [initialized]);

  // 通知父组件 hasConversation 变化（用于控制外层容器宽度）
  // useLayoutEffect 确保在浏览器绘制前同步更新父组件，避免 landing→面板 的闪烁
  useLayoutEffect(() => {
    onHasConversation?.(hasConversation);
  }, [hasConversation, onHasConversation]);

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
        <Spinner className="h-4 w-4 animate-spin text-muted-foreground/40" />
      </div>
    );
  }

  // ── Landing state ──

  if (!hasConversation) {
    return (
      <TooltipProvider delayDuration={300}>
        <div className="h-full overflow-y-scroll animate-in fade-in duration-500" style={{ scrollSnapType: 'y mandatory' }}>
          {/* 内层：恰好一屏高度，flex 居中输入框 */}
          <div className="h-full flex flex-col items-center justify-center px-4" style={{ scrollSnapAlign: 'start' }}>
            <div className="w-full max-w-2xl">
              <div className="space-y-2 mb-6">
                <div className="flex items-center gap-2.5">
                  <img src="/unimind_logo_small.png" alt="UniMind" className="h-7 w-7 rounded-lg shrink-0" />
                  <h1 className="text-3xl font-extrabold tracking-tight text-foreground/90">{landingTitle}</h1>
                </div>
                <p className="text-xs text-foreground/60">{landingDescription}</p>
              </div>

              <div data-tour={inputTourClass} className="bg-card rounded-2xl border border-border/50 shadow-lg overflow-hidden transition-all duration-200 focus-within:border-primary/40 focus-within:ring-1 focus-within:ring-primary/20">
                <textarea
                  value={input}
                  onChange={e => setInput(e.target.value)}
                  onCompositionStart={() => setIsComposition(true)}
                  onCompositionEnd={() => setIsComposition(false)}
                  placeholder={placeholder}
                  autoComplete="off"
                  className="w-full bg-transparent border-none resize-none text-sm px-4 py-3 placeholder:text-muted-foreground/55 focus:outline-none min-h-[64px]"
                  disabled={loading}
                />
                <div className="flex items-center justify-end gap-1.5 px-3 py-2">
                  <Popover open={skillOpen} onOpenChange={setSkillOpen}>
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <PopoverTrigger asChild>
                          <button className={cn("p-1 rounded-md transition-colors", skillOpen ? "text-primary/60 bg-muted" : "text-muted-foreground/55 hover:text-foreground/65 hover:bg-muted/50")}>
                            <Lightbulb className="h-3.5 w-3.5" />
                          </button>
                        </PopoverTrigger>
                      </TooltipTrigger>
                      <TooltipContent side="top" className="text-[10px]">{skillTooltip}</TooltipContent>
                    </Tooltip>
                    <PopoverContent align="end" side="top" className="w-48 p-1 rounded-xl border-border/60 shadow-lg">
                      <div className="space-y-0.5">
                        {skills.map(skill => (
                          <button key={skill.label} onClick={() => handleSkillSelect(skill.prompt)}
                            className="w-full flex items-center gap-2 px-2.5 py-2 rounded-lg hover:bg-muted/60 transition-colors text-left">
                            <skill.icon className="h-3.5 w-3.5 shrink-0 text-muted-foreground/50" />
                            <span className="text-[12px] font-medium">{skill.label}</span>
                          </button>
                        ))}
                      </div>
                    </PopoverContent>
                  </Popover>
                  {toolbarAction && (
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <button onClick={toolbarAction.onClick}
                          className="p-1 rounded-md text-muted-foreground/55 hover:text-foreground/65 hover:bg-muted/50 transition-colors">
                          <toolbarAction.icon className="h-3.5 w-3.5" />
                        </button>
                      </TooltipTrigger>
                      <TooltipContent side="top" className="text-[10px]">{toolbarAction.tooltip}</TooltipContent>
                    </Tooltip>
                  )}
                  <ClassSelector />
                  <Button
                    onClick={() => doSend(input)}
                    disabled={loading || !input.trim()}
                    size="icon"
                    className="rounded-lg h-8 w-8 bg-foreground text-background shadow-none active:scale-95 transition-all shrink-0 hover:opacity-90"
                  >
                    {loading ? <Spinner className="h-3.5 w-3.5 animate-spin" /> : <PaperPlaneTilt className="h-3.5 w-3.5" />}
                  </Button>
                </div>
              </div>

              {sessions.length > 0 && (
                <div className="flex justify-center mt-6">
                  <Popover open={sessionOpen} onOpenChange={setSessionOpen}>
                    <PopoverTrigger asChild>
                      <button className="text-sm text-muted-foreground/65 hover:text-foreground/70 transition-colors flex items-center gap-1.5">
                        <ClockCounterClockwise className="h-3.5 w-3.5" />
                        {sessions.length} 个历史对话
                      </button>
                    </PopoverTrigger>
                    <PopoverContent align="start" side="top" className="w-72 p-1.5 rounded-lg border-border/60 shadow-lg max-h-64 overflow-y-auto">
                      <div className="space-y-0.5">
                        {[...sessions].reverse().map(session => (
                          <div key={session.id}
                            className="w-full flex items-start gap-1.5 px-2.5 py-2 rounded-md hover:bg-muted/50 transition-colors group">
                            <button onClick={() => wrappedLoadSession(session)}
                              className="flex-1 flex flex-col gap-0.5 text-left min-w-0">
                              <span className="text-[12px] font-medium truncate">{session.label}</span>
                              <span className="text-[10px] text-muted-foreground/50">
                                {session.messages.length} 条消息
                                {session.lastTime && ` · ${new Date(session.lastTime).toLocaleDateString('zh-CN', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}`}
                              </span>
                            </button>
                            {onDeleteSession && (
                              <button onClick={(e) => { e.stopPropagation(); onDeleteSession(session); }}
                                className="shrink-0 mt-0.5 p-0.5 rounded opacity-0 group-hover:opacity-100 text-muted-foreground/40 hover:text-destructive transition-all">
                                <Trash className="h-2.5 w-2.5" />
                              </button>
                            )}
                          </div>
                        ))}
                      </div>
                    </PopoverContent>
                  </Popover>
                </div>
              )}

            </div>
          </div>

          {/* 卡片区：在内层外面，不受居中逻辑影响 */}
          {landingBanner && (
            <div ref={dashboardRef} className="w-full max-w-2xl mx-auto px-4 py-6 min-h-full flex flex-col justify-center" style={{ scrollSnapAlign: 'start' }}>
              {landingBanner}
            </div>
          )}
        </div>
      </TooltipProvider>
    );
  }

  // ── Chat state ──

  if (layout === 'inline') {
    return (
      <TooltipProvider delayDuration={300}>
        <div className="h-full flex flex-col bg-white animate-in fade-in duration-300">
          {/* Header */}
          <div className="shrink-0 px-4 pt-3 pb-2 flex items-center gap-2.5 border-b border-border/30">
            <div className="h-7 w-7 rounded-full bg-gradient-to-br from-primary to-primary/60 flex items-center justify-center shrink-0">
              <Sparkle className="h-3.5 w-3.5 text-primary-foreground" />
            </div>
            <span className="text-sm font-bold text-foreground flex-1 truncate">
              {conversationTitle || botDisplayName}
            </span>
            {sessions.length > 1 && (
              <Popover open={sessionOpen} onOpenChange={setSessionOpen}>
                <PopoverTrigger asChild>
                  <button className="text-[10px] text-muted-foreground/55 hover:text-foreground/65 transition-colors shrink-0">
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
                          <span className="text-[10px] text-muted-foreground/55">
                            {session.messages.length} 条消息
                            {session.lastTime && ` · ${new Date(session.lastTime).toLocaleDateString('zh-CN', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}`}
                          </span>
                        </button>
                        {onDeleteSession && session.id !== activeSessionId && (
                          <button onClick={(e) => { e.stopPropagation(); onDeleteSession(session); }}
                            className="shrink-0 mt-0.5 p-0.5 rounded opacity-0 group-hover:opacity-100 text-muted-foreground/40 hover:text-destructive transition-all">
                            <Trash className="h-2.5 w-2.5" />
                          </button>
                        )}
                      </div>
                    ))}
                  </div>
                </PopoverContent>
              </Popover>
            )}
            <Button variant="ghost" size="sm" onClick={wrappedReset}
              className="rounded text-muted-foreground/40 hover:text-foreground/60 gap-0.5 px-1.5 h-5 shrink-0">
              <ArrowCounterClockwise className="h-2.5 w-2.5" />
              <span className="text-[9px] font-medium">新对话</span>
            </Button>
          </div>

          {/* Messages — 内联视觉卡片 */}
          <AgentReplyContext.Provider value={{ onReply: onActionReply }}>
            <div ref={scrollRef} className="flex-1 overflow-y-auto min-h-0">
              <div className="max-w-3xl mx-auto p-4 space-y-4">
                {taskList && (
                  <TaskList data={taskList} />
                )}
                {messages.filter(m => m.role === 'user' || m.visible !== false).map((msg, i) => {
                  // render_visual → 内联 VisualCard
                  // 只用 toolStep.visual 渲染，避免与 done 消息的 metadata visual 重复渲染。
                  // metadata visual 仅用于填充 visual state（split 模式右面板），不在 inline 流中二次展示。
                  // 历史消息已在 init 时将 metadata visual 转换为 toolStep，所以历史也能正常渲染。
                  const stepVisual = msg.toolStep?.visual;
                  const isRenderStep = msg.toolStep?.name === 'render_visual' && msg.toolStep.status === 'done';
                  if (isRenderStep && stepVisual) {
                    return (
                      <InlineVisualCard
                        key={msg._id || i}
                        visual={stepVisual as VisualData}
                        index={i}
                      />
                    );
                  }
                  // 其他工具步骤 → ToolStepMessage
                  // quick_generate/bulk_generate 完成后不再展示步骤卡片，
                  // 因为后续文字气泡已经说明了结果，避免两个气泡说同一件事
                  // render_visual 完成但无 visual → 后端校验拒绝了无效参数，AI 会自纠正，用户无需看到
                  if (msg.toolStep) {
                    const step = msg.toolStep;
                    const isGenDone = (step.name === 'quick_generate' || step.name === 'bulk_generate_questions') && step.status === 'done';
                    if (isGenDone) return null;
                    if (step.name === 'render_visual' && step.status === 'done' && !step.visual) return null;
                    return <ToolStepMessage key={msg._id || i} step={step} index={i} />;
                  }
                  // 普通消息 → ChatBubble
                  return <ChatBubble key={msg._id || i} msg={msg} isUser={msg.role === 'user'} index={i} />;
                })}
                {loading && (
                  <ChatBubble msg={{ role: 'assistant', content: '' }} isUser={false} isThinking index={messages.length} />
                )}
              </div>
            </div>
          </AgentReplyContext.Provider>

          {/* Input */}
          <div className="shrink-0 px-4 pb-4 pt-2">
            <div className="max-w-3xl mx-auto">
              <div data-tour={inputTourClass} className="rounded-2xl border border-border bg-white shadow-[0_2px_12px_rgba(0,0,0,0.06),0_0_0_1px_rgba(0,0,0,0.02)] overflow-hidden focus-within:border-primary/40 focus-within:ring-1 focus-within:ring-primary/20 transition-all">
                <textarea
                  value={input}
                  onChange={e => setInput(e.target.value)}
                  onCompositionStart={() => setIsComposition(true)}
                  onCompositionEnd={() => setIsComposition(false)}
                  onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey && !isComposing) { e.preventDefault(); doSend(input); } }}
                  placeholder={chatPlaceholder}
                  autoComplete="off"
                  className="w-full bg-transparent border-none resize-none text-sm px-4 py-2 placeholder:text-muted-foreground/55 focus:outline-none min-h-[36px]"
                  disabled={loading}
                />
                <div className="flex items-center justify-end gap-1.5 px-2.5 py-1.5">
                  <Popover open={skillOpen} onOpenChange={setSkillOpen}>
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <PopoverTrigger asChild>
                          <button className={cn("p-1.5 rounded-lg transition-colors", skillOpen ? "text-primary/60" : "text-muted-foreground/55 hover:text-foreground/70 hover:bg-muted")}>
                            <Lightbulb className="h-3.5 w-3.5" />
                          </button>
                        </PopoverTrigger>
                      </TooltipTrigger>
                      <TooltipContent side="top" className="text-[10px]">{skillTooltip}</TooltipContent>
                    </Tooltip>
                    <PopoverContent align="start" side="top" className="w-48 p-1 rounded-xl border-border/60 shadow-lg">
                      <div className="space-y-0.5">
                        {skills.map(skill => (
                          <button key={skill.label} onClick={() => handleSkillSelect(skill.prompt)}
                            className="w-full flex items-center gap-2 px-2.5 py-2 rounded-lg hover:bg-muted/60 transition-colors text-left">
                            <skill.icon className="h-3.5 w-3.5 shrink-0 text-muted-foreground/50" />
                            <span className="text-[12px] font-medium">{skill.label}</span>
                          </button>
                        ))}
                      </div>
                    </PopoverContent>
                  </Popover>
                  {toolbarAction && (
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <button onClick={toolbarAction.onClick}
                          className="p-1.5 rounded-lg text-muted-foreground/55 hover:text-foreground/70 hover:bg-muted transition-colors">
                          <toolbarAction.icon className="h-3.5 w-3.5" />
                        </button>
                      </TooltipTrigger>
                      <TooltipContent side="top" className="text-[10px]">{toolbarAction.tooltip}</TooltipContent>
                    </Tooltip>
                  )}
                  <div className="flex-1" />
                  <ClassSelector />
                  <Button onClick={() => doSend(input)} disabled={loading || !input.trim()} size="icon"
                    className="rounded-xl h-9 w-9 bg-primary text-primary-foreground shadow-none active:scale-95 transition-all shrink-0 hover:opacity-90">
                    {loading ? <Spinner className="h-4 w-4 animate-spin" /> : <PaperPlaneTilt className="h-4 w-4" />}
                  </Button>
                </div>
              </div>
            </div>
          </div>
        </div>
      </TooltipProvider>
    );
  }

  // split mode
  return (
    <TooltipProvider delayDuration={300}>
      <div className="h-full flex animate-in fade-in duration-300">
        {renderRightPanel && (
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
        )}

        <div
          className={cn("shrink-0 flex flex-col h-full border-l border-border/60 bg-card hidden md:flex relative shadow-[-2px_0_12px_rgba(0,0,0,0.04)]", dragging && "select-none")}
          style={{ width: chatWidth }}
        >
          <div className="absolute left-0 top-0 bottom-0 w-1.5 cursor-col-resize group z-10" onMouseDown={handleDragStart}>
            <div className="w-px h-full bg-border/0 group-hover:bg-primary/30 transition-colors mx-auto" />
          </div>

          <div className="shrink-0 px-4 pt-3 pb-2 flex items-center gap-2.5 border-b border-border/30">
            {conversationTitle ? (
              <span className="text-xs text-black/70 flex-1 truncate">{conversationTitle}</span>
            ) : (
              <div className="h-7 w-7 rounded-full bg-gradient-to-br from-primary to-primary/60 flex items-center justify-center shrink-0">
                <Sparkle className="h-3.5 w-3.5 text-primary-foreground" />
              </div>
            )}
            {sessions.length > 1 && (
              <Popover open={sessionOpen} onOpenChange={setSessionOpen}>
                <PopoverTrigger asChild>
                  <button className="text-[10px] text-muted-foreground/55 hover:text-foreground/65 transition-colors shrink-0">
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
                          <span className="text-[10px] text-muted-foreground/55">
                            {session.messages.length} 条消息
                            {session.lastTime && ` · ${new Date(session.lastTime).toLocaleDateString('zh-CN', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}`}
                          </span>
                        </button>
                        {onDeleteSession && session.id !== activeSessionId && (
                          <button onClick={(e) => { e.stopPropagation(); onDeleteSession(session); }}
                            className="shrink-0 mt-0.5 p-0.5 rounded opacity-0 group-hover:opacity-100 text-muted-foreground/40 hover:text-destructive transition-all">
                            <Trash className="h-2.5 w-2.5" />
                          </button>
                        )}
                      </div>
                    ))}
                  </div>
                </PopoverContent>
              </Popover>
            )}
            <Button variant="ghost" size="sm" onClick={wrappedReset}
              className="rounded text-muted-foreground/40 hover:text-foreground/60 gap-0.5 px-1.5 h-5 shrink-0">
              <ArrowCounterClockwise className="h-2.5 w-2.5" />
              <span className="text-[9px] font-medium">新对话</span>
            </Button>
          </div>

          <div ref={scrollRef} className="flex-1 overflow-y-auto min-h-0">
            <div className="p-2.5 space-y-3">
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

          <div className="shrink-0 px-3 pb-3 pt-2">
            <div className="rounded-2xl border border-border bg-white shadow-[0_2px_12px_rgba(0,0,0,0.06),0_0_0_1px_rgba(0,0,0,0.02)] overflow-hidden focus-within:border-primary/40 focus-within:ring-1 focus-within:ring-primary/20 transition-all">
              <textarea
                value={input}
                onChange={e => setInput(e.target.value)}
                onCompositionStart={() => setIsComposition(true)}
                onCompositionEnd={() => setIsComposition(false)}
                onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey && !isComposing) { e.preventDefault(); doSend(input); } }}
                placeholder={chatPlaceholder}
                autoComplete="off"
                className="w-full bg-transparent border-none resize-none text-sm px-4 py-3 placeholder:text-muted-foreground/45 focus:outline-none min-h-[80px]"
                disabled={loading}
              />
              <div className="flex items-center gap-1.5 px-3 py-2 border-t border-border/30">
                <Popover open={skillOpen} onOpenChange={setSkillOpen}>
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <PopoverTrigger asChild>
                        <button className={cn("p-1.5 rounded-lg transition-colors", skillOpen ? "text-primary/60" : "text-muted-foreground/50 hover:text-foreground/70 hover:bg-muted")}>
                          <Lightbulb className="h-3.5 w-3.5" />
                        </button>
                      </PopoverTrigger>
                    </TooltipTrigger>
                    <TooltipContent side="top" className="text-[10px]">{skillTooltip}</TooltipContent>
                  </Tooltip>
                  <PopoverContent align="start" side="top" className="w-48 p-1 rounded-xl border-border/60 shadow-lg">
                    <div className="space-y-0.5">
                      {skills.map(skill => (
                        <button key={skill.label} onClick={() => handleSkillSelect(skill.prompt)}
                          className="w-full flex items-center gap-2 px-2.5 py-2 rounded-lg hover:bg-muted/60 transition-colors text-left">
                          <skill.icon className="h-3.5 w-3.5 shrink-0 text-muted-foreground/50" />
                          <span className="text-[12px] font-medium">{skill.label}</span>
                        </button>
                      ))}
                    </div>
                  </PopoverContent>
                </Popover>
                {toolbarAction && (
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <button onClick={toolbarAction.onClick}
                        className="p-1.5 rounded-lg text-muted-foreground/50 hover:text-foreground/70 hover:bg-muted transition-colors">
                        <toolbarAction.icon className="h-3.5 w-3.5" />
                      </button>
                    </TooltipTrigger>
                    <TooltipContent side="top" className="text-[10px]">{toolbarAction.tooltip}</TooltipContent>
                  </Tooltip>
                )}
                <div className="flex-1" />
                <Button onClick={() => doSend(input)} disabled={loading || !input.trim()} size="icon"
                  className="rounded-xl h-9 w-9 bg-foreground text-background shadow-none active:scale-95 transition-all shrink-0 hover:opacity-90">
                  {loading ? <Spinner className="h-4 w-4 animate-spin" /> : <PaperPlaneTilt className="h-4 w-4" />}
                </Button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </TooltipProvider>
  );
}
