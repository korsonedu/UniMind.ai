import { useNoteMentions } from '@/pages/notes/useNoteMentions';
import React, { useState, useEffect, useLayoutEffect, useRef, useCallback } from 'react';
import { useSystemStore } from '@/store/useSystemStore';
import { Button } from '@/components/ui/button';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { PaperPlaneTilt, Spinner, ArrowCounterClockwise, Lightbulb, ClockCounterClockwise, Trash, Sparkle, Plus, ArrowUp, MagnifyingGlass, Folder, Check } from '@phosphor-icons/react';
import api from '@/lib/api';
import { cn } from '@/lib/utils';
import { toast } from 'sonner';
import { useTypewriter } from '@/hooks/useTypewriter';
import ChatBubble from '@/components/ChatBubble';
import { ToolStepMessage } from '@/components/AgentStepCard';
import { DshToolCard, type DshCard } from '@/components/DshToolCard';
import { InlineVisualCard } from '@/components/InlineVisualCard';
import {
  useAgentConversation,
  type Bot,
  type Message,
  type ConversationSession,
  RECENT_SESSION_MS,
} from '@/hooks/useAgentConversation';
import type { AgentStep } from '@/types/toolRun';
import type { Icon } from '@phosphor-icons/react';
import type { VisualData } from '@/pages/xiaoyu/visuals';
import { AgentReplyContext } from '@/pages/xiaoyu/visuals/agentReplyContext';
import { restoreVisualSteps } from '@/lib/visualHistory';
import { TaskList } from '@/components/TaskList';
import { NativeAgentShell } from '@/components/NativeAgentShell';
import { useConversationProjects, type ConversationProjectControls } from '@/hooks/useConversationProjects';
import { Link } from 'react-router-dom';
import { ContactAdminModal } from '@/components/ContactAdminModal';
import { learningReset, type AIUsage, type LearningAccess } from '@/types/learning';

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
  appearance?: 'native';
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
  beforeSend?: () => Promise<void>;
  enableNoteMentions?: boolean;
  contextPanel?: (props: { bot: Bot | null; conversationId: string }) => React.ReactNode;
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

  /** 当 sessions 加载/变化时通知父组件（用于外部 session 切换器） */
  onSessionsReady?: (data: {
    sessions: ConversationSession[];
    activeSessionId: number | null;
    loadSession: (session: ConversationSession) => void;
    deleteSession: (session: ConversationSession) => void;
    newConversation: () => void;
  }) => void;

  /** 左侧栏 render prop，传入 session 相关数据，返回 ReactNode */
  sidebar?: (props: {
    projectControls: ConversationProjectControls;
    onNewInProject: (id: number) => void;
    sessions: ConversationSession[];
    activeSessionId: number | null;
    thinkingIds: string[];
    onLoadSession: (session: ConversationSession) => void;
    onDeleteSession?: (session: ConversationSession) => void;
    onUpdateSession: ReturnType<typeof useAgentConversation>['handleUpdateSession'];
    onNewConversation: () => void;
    botDisplayName: string;
  }) => React.ReactNode;
}

// ── Component ──

export default function AgentChatLayout(props: AgentChatLayoutProps) {
  const {
    findBot, skills, typewriterWords, chatPlaceholder, resetMessage,
    landingTitle, landingDescription, skillTooltip = '技能',
    botDisplayName,
    processContent,
    getExtraPayload, beforeSend, enableNoteMentions = false, contextPanel, onStepDone, onDone, onSendReady,
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
    sidebar,
    onSessionsReady,
    appearance,
  } = props;

  const setPageHeader = useSystemStore(state => state.setPageHeader);
  const [visual, setVisual] = useState<VisualData | VisualData[] | null>(null);
  const pendingVisualsRef = useRef<VisualData[]>([]);
  const dashboardRef = useRef<HTMLDivElement>(null);
  const nativeInputRef = useRef<HTMLTextAreaElement>(null);
  const noteMentionsRef = useRef<ReturnType<typeof useNoteMentions> | null>(null);
  const [projectPickerOpen, setProjectPickerOpen] = useState(false);
  const [projectQuery, setProjectQuery] = useState('');
  const [aiUsage, setAIUsage] = useState<AIUsage | null>(null);
  const [quotaError, setQuotaError] = useState(false);
  const [contactOpen, setContactOpen] = useState(false);

  const {
    bot, messages, input, loading, generatingIds, isComposing, initialized, skillOpen,
    sessions, activeSessionId, sessionOpen, chatWidth, dragging, hasConversation, conversationId, taskList,
    scrollRef, projectId, setProjectId,
    setMessages, setInput, setBot, setInitialized, setSkillOpen, setSessionOpen,
    setIsComposition, setActiveSessionId, setSessions, setConversationId,
    handleDragStart, handleLoadSession, handleRefreshSessions, handleDeleteSession, handleUpdateSession, handleReset,
    handleSkillSelect, groupIntoSessions, doSend, recovery, recoverRequests, retryPendingRequest,
  } = useAgentConversation({
    enableProjects: appearance === 'native',
    findBot,
    getExtraPayload: () => ({ ...getExtraPayload?.(), ...(enableNoteMentions ? noteMentionsRef.current?.payload() : {}) }),
    beforeSend: async () => { await beforeSend?.(); await noteMentionsRef.current?.beforeSend(); },
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
  const noteMentions = useNoteMentions({ enabled: enableNoteMentions, disabled: loading, botId: bot?.id, conversationId, input, setInput, textareaRef: nativeInputRef });
  useLayoutEffect(() => { noteMentionsRef.current = noteMentions; }, [noteMentions]);
  const projectControls = useConversationProjects(appearance === 'native', projectId, setProjectId, setSessions);
  const selectedProjectName = projectControls.projects.find(project => project.id === projectId)?.name;

  useEffect(() => {
    if (appearance !== 'native' || generatingIds.length > 0) return;
    const controller = new AbortController();
    void api.get<LearningAccess>('/users/learning/access/', { signal: controller.signal })
      .then(({ data }) => { setAIUsage(data.ai_usage); setQuotaError(false); })
      .catch(() => { if (!controller.signal.aborted) setQuotaError(true); });
    return () => controller.abort();
  }, [appearance, generatingIds.length]);

  // Expose doSend to parent
  useEffect(() => {
    if (onSendReady && doSend) onSendReady(doSend);
  }, [onSendReady, doSend]);

  // Action card reply → send as chat message
  const onActionReply = useCallback((value: string) => {
    doSend(value, true);
  }, [doSend]);

  // 从 messages 或当前 session 中提取标题（与侧栏保持同一来源）
  const conversationTitle = React.useMemo(() => {
    // 新对话（无活跃会话，标题尚未生成）→ 空
    if (activeSessionId === null) return '';
    // 优先从消息中取（AI 刚生成的标题）
    const fromMsg = messages.find(m => m.conversation_title)?.conversation_title;
    if (fromMsg) return fromMsg;
    // 从当前 session 取 title（Conversation 模型中的 AI 标题）
    const activeSession = sessions.find(s => s.id === activeSessionId);
    if (activeSession?.title) return activeSession.title;
    // 取当前 session 的 label（首条用户消息截断，与侧栏一致）
    if (activeSession?.label) return activeSession.label;
    return '';
  }, [messages, sessions, activeSessionId]);

  // 通知父组件 sessions 变化（用于外部 session 切换器）


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
      if (appearance === 'native' && !initialConversationId) setConversationId(crypto.randomUUID());
      try {
        const bRes = await api.get('/ai/bots/');
        if (cancelled) return;
        const found = findBot(bRes.data);
        if (found) {
          setBot(found);
          const hRes = await api.get('/ai/history/', { params: { bot_id: found.id } });
          if (hRes.data.length > 0) {
            const allMsgs: Message[] = restoreVisualSteps(
              hRes.data
                .filter((m: Message) => m.content !== '[Thinking...]')
                .map((m: Message) => ({
                  ...m,
                  content: processContent ? processContent(m.content as string) : (m.content as string),
                  visible: true,
                } as Message)),
            );
            const grouped = groupIntoSessions(allMsgs);
            setSessions(grouped);
            const lastMsg = hRes.data[hRes.data.length - 1];
            const isRecent = lastMsg && Date.now() - new Date(lastMsg.timestamp).getTime() < RECENT_SESSION_MS;
            if (appearance !== 'native' && isRecent && lastMsg.conversation_id) {
              setConversationId(lastMsg.conversation_id);
            }
            // 有历史对话时，自动加载最新 session（不限制时间窗口）
            const requested = initialConversationId && grouped.find(session => session.conversationId === initialConversationId);
            if (requested || (appearance !== 'native' && grouped.length > 0)) {
              const latest = requested || grouped[grouped.length - 1];
              if (latest.conversationId) setConversationId(latest.conversationId);
              setMessages(latest.messages);
              setActiveSessionId(latest.id);
              setProjectId(latest.projectId ?? null);
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
  }, [appearance, botDisplayName, findBot, groupIntoSessions, processContent, setActiveSessionId, setBot, setConversationId, setInitialized, setMessages, setProjectId, setSessions]);

  useEffect(() => {
    const textarea = nativeInputRef.current;
    if (appearance !== 'native' || !textarea) return;
    const resize = () => {
      textarea.style.height = 'auto';
      textarea.style.height = `${Math.min(textarea.scrollHeight, 176)}px`;
    };
    resize();
    window.addEventListener('resize', resize);
    return () => window.removeEventListener('resize', resize);
  }, [input, appearance, hasConversation, initialized]);

  // 通知父组件 hasConversation 变化（用于控制外层容器宽度）
  // useLayoutEffect 确保在浏览器绘制前同步更新父组件，避免 landing→面板 的闪烁
  // ⚠️ 注意：初始化阶段不回调父组件，因为此时 hook 的 hasConversation 始终为 false，
  // 会覆盖父组件（Workbench）自己通过 API 并行获取到的正确值，导致左侧面板不显示
  useLayoutEffect(() => {
    if (!initialized) return;
    onHasConversation?.(hasConversation);
  }, [hasConversation, onHasConversation, initialized]);

  // ── Session load/reset wrappers ──

  const wrappedLoadSession = useCallback((session: ConversationSession) => {
    if (onLoadSession) {
      onLoadSession(session, handleLoadSession);
    } else {
      handleLoadSession(session);
    }
    setSessionOpen(false);
  }, [handleLoadSession, onLoadSession, setSessionOpen]);

  const wrappedReset = useCallback((notify = true, nextProjectId = projectId) => {
    if (onReset) {
      onReset(() => handleReset(notify));
    } else {
      handleReset(notify);
    }
    if (appearance === 'native') setProjectId(nextProjectId);
    setVisual(null);
  }, [appearance, handleReset, onReset, projectId, setProjectId]);

  useEffect(() => {
    onSessionsReady?.({
      sessions,
      activeSessionId,
      loadSession: wrappedLoadSession,
      deleteSession: handleDeleteSession,
      newConversation: wrappedReset,
    });
  }, [sessions, activeSessionId, onSessionsReady, wrappedLoadSession, handleDeleteSession, wrappedReset]);

  const selectNewProject = (id: number | null) => {
    wrappedReset(false, id);
    setProjectPickerOpen(false);
    setProjectQuery('');
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

  const sessionDirectory = sidebar?.({
    projectControls: { ...projectControls, remove: async id => {
      const removed = await projectControls.remove(id);
      if (removed && projectId === id) wrappedReset(false, null);
      return removed;
    } }, onNewInProject: id => wrappedReset(false, id),
    sessions, activeSessionId, thinkingIds: generatingIds, onLoadSession: wrappedLoadSession,
    onDeleteSession: onDeleteSession ? handleDeleteSession : undefined,
    onUpdateSession: handleUpdateSession,
    onNewConversation: wrappedReset, botDisplayName,
  });

  const quotaExhausted = aiUsage && !aiUsage.unlimited && aiUsage.remaining === 0;
  const quotaLow = aiUsage && !aiUsage.unlimited && aiUsage.remaining !== null && aiUsage.remaining > 0 && aiUsage.remaining <= 5;
  const quotaHint = appearance === 'native' && <>
    <p aria-live="polite" className={cn('mt-2 flex flex-wrap items-center justify-center gap-x-3 gap-y-1 px-1 text-[11px] leading-5 text-muted-foreground', quotaLow && 'text-amber-700')}>
      {quotaError ? <span>AI 额度暂时无法读取，请稍后查看。</span> : !aiUsage ? <span>正在读取 AI 额度…</span> : aiUsage.unlimited ? <span>AI 问答不限次数</span> : <>
        <span>{aiUsage.configured ? `本周 AI 剩余 ${aiUsage.base_remaining} 次` : '基础周额度待配置'}{aiUsage.addon_remaining > 0 && ` · 加量剩余 ${aiUsage.addon_remaining} 次`}{quotaLow && ' · 额度不多了'}</span>
        {quotaExhausted && aiUsage.configured && <span>{learningReset(aiUsage.resets_at)}（上海时间）恢复基础额度</span>}
        {(quotaExhausted || !aiUsage.configured) && <button type="button" className="underline underline-offset-2 hover:text-foreground" onClick={() => setContactOpen(true)}>联系科晟</button>}
        {(quotaExhausted || quotaLow) && <Link to="/pricing" className="underline underline-offset-2 hover:text-foreground">按需 AI 加量</Link>}
      </>}
    </p>
    <ContactAdminModal open={contactOpen} onOpenChange={setContactOpen} />
  </>;

  const recoveryHint = window.unimindDesktop && (recovery === 'pending' || recovery === 'unknown') && <div className="um-agent-recovery" role="status">
    <p>{recovery === 'pending' ? '上一条提问仍在执行，正在恢复已有结果。' : '上一条提问的执行结果尚未确认，可以先刷新历史；手动重试可能再次执行原提问。'}</p>
    <div><button type="button" disabled={loading} onClick={() => void recoverRequests()}>刷新历史</button>{recovery === 'unknown' && <button type="button" disabled={loading} onClick={retryPendingRequest}>手动重试原提问</button>}</div>
  </div>;

  if (!hasConversation && appearance === 'native') {
    return <TooltipProvider delayDuration={300}>
      <NativeAgentShell native sidebar={sessionDirectory} onNew={wrappedReset} label={botDisplayName} title={conversationTitle || '新对话'}>
        {contextPanel?.({ bot, conversationId })}
        <div className="um-agent-landing">
          <section className="um-agent-start" aria-label="开始对话">
            <h2 className="um-agent-start-title">{selectedProjectName ? <>我们要在 <Popover open={projectPickerOpen} onOpenChange={open => { setProjectPickerOpen(open); if (!open) setProjectQuery(''); }}>
              <PopoverTrigger asChild><button className="um-agent-project-picker-trigger" aria-label={`切换项目，当前为${selectedProjectName}`}>{selectedProjectName}</button></PopoverTrigger>
              <PopoverContent side="top" align="center" sideOffset={12} className="um-native-agent um-native-menu um-agent-project-picker" onCloseAutoFocus={event => { event.preventDefault(); nativeInputRef.current?.focus(); }}>
                <label className="um-agent-project-picker-search"><MagnifyingGlass size={16} /><input autoFocus aria-label="搜索项目" placeholder="搜索项目" value={projectQuery} onChange={event => setProjectQuery(event.target.value)} /></label>
                <div className="um-agent-project-picker-list" role="group" aria-label="切换学习项目">{projectControls.projects.filter(project => project.name.toLowerCase().includes(projectQuery.trim().toLowerCase())).map(project => <button key={project.id} aria-pressed={project.id === projectId} onClick={() => selectNewProject(project.id)}><Folder size={16} /><span>{project.name}</span>{project.id === projectId && <Check size={16} />}</button>)}</div>
                {!projectControls.projects.some(project => project.name.toLowerCase().includes(projectQuery.trim().toLowerCase())) && <p className="um-agent-project-picker-empty">没有匹配的项目</p>}
                <button className="um-agent-project-picker-none" onClick={() => selectNewProject(null)}>未分类</button>
              </PopoverContent>
            </Popover> 中做些什么？</> : contextPanel ? landingTitle : '我们要做些什么？'}</h2>
            <div className="w-full max-w-[680px]">
            <div data-tour={inputTourClass} className="um-agent-composer">
              {noteMentions.panel}
              <textarea ref={nativeInputRef} value={input} onChange={event => { setInput(event.target.value); noteMentions.updateQuery(event.target.value, event.target.selectionStart); }}
                onCompositionStart={() => setIsComposition(true)} onCompositionEnd={() => setIsComposition(false)}
                onKeyDown={event => { if (noteMentions.onKeyDown(event, isComposing)) return; if (event.key === 'Enter' && !event.shiftKey && !isComposing && !event.nativeEvent.isComposing && !loading && input.trim() && bot) { event.preventDefault(); doSend(input); } }}
                placeholder={chatPlaceholder} aria-label={`和${botDisplayName}对话`} disabled={loading || !bot} />
              <footer>
                <Popover open={skillOpen} onOpenChange={setSkillOpen}>
                  <PopoverTrigger asChild><button className="um-agent-button um-agent-task-trigger" aria-label="快捷任务" disabled={loading || !bot}><Plus size={16} />快捷任务</button></PopoverTrigger>
                  <PopoverContent align="start" side="top" className="um-native-menu w-56 p-1 max-h-[var(--radix-popover-content-available-height)] overflow-y-auto" onCloseAutoFocus={event => { event.preventDefault(); nativeInputRef.current?.focus(); }}>
                    {skills.map(skill => <button key={skill.label} className="w-full flex items-center gap-2 px-3 py-2 rounded-lg hover:bg-muted text-left" onClick={() => handleSkillSelect(skill.prompt)}><skill.icon size={16} />{skill.label}</button>)}
                  </PopoverContent>
                </Popover>
                <button className="um-agent-button um-agent-button-primary um-agent-send" disabled={loading || !input.trim() || !bot} onClick={() => doSend(input)} aria-label="发送消息"><ArrowUp size={18} /></button>
              </footer>
            </div>
            {recoveryHint}
            {quotaHint}
            </div>
          </section>
        </div>
      </NativeAgentShell>
    </TooltipProvider>;
  }

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
                      <button className="text-sm font-medium text-muted-foreground hover:text-foreground transition-colors flex items-center gap-1.5 rounded-full px-3 py-0.5 bg-muted/50 hover:bg-muted">
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
        <NativeAgentShell native={appearance === 'native'} sidebar={sessionDirectory} onNew={wrappedReset} label={botDisplayName} title={conversationTitle || '新对话'}>
          {contextPanel?.({ bot, conversationId })}

          <div className={cn("flex-1 min-w-0 flex flex-col bg-white", appearance === 'native' && 'um-agent-chat-body')}>
          {/* Header */}
          <div className={cn("shrink-0 px-4 pt-3 pb-2 flex items-center gap-2.5 border-b border-border/30", appearance === 'native' && 'um-agent-legacy-header')}>
            <div className="h-7 w-7 rounded-full bg-gradient-to-br from-primary to-primary/60 flex items-center justify-center shrink-0">
              <Sparkle className="h-3.5 w-3.5 text-primary-foreground" />
            </div>
            <span className="text-sm font-bold text-foreground flex-1 truncate">
              {conversationTitle || botDisplayName}
            </span>
            {/* 没有侧栏时保留 popover 会话切换（工作台） */}
            {!sidebar && sessions.length > 1 && (
              <Popover open={sessionOpen} onOpenChange={setSessionOpen}>
                <PopoverTrigger asChild>
                  <button className="text-[11px] font-medium text-muted-foreground hover:text-foreground transition-colors shrink-0 rounded-full px-2.5 py-0.5 bg-muted/50 hover:bg-muted">
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
            <button onClick={() => wrappedReset()}
              className="shrink-0 rounded-full px-3 py-1 text-[11px] font-medium bg-muted/60 hover:bg-muted text-muted-foreground hover:text-foreground transition-colors flex items-center gap-1">
              <Plus className="h-3 w-3" />
              新对话
            </button>
          </div>

          {/* Messages — 内联视觉卡片 */}
          <AgentReplyContext.Provider value={{ onReply: onActionReply }}>
            <div ref={scrollRef} className="um-agent-scroll flex-1 overflow-y-auto min-h-0">
              <div className="max-w-3xl mx-auto p-4 space-y-4">
                {messages.filter(m => m.role === 'user' || m.visible !== false).map((msg, i) => {
                  // render_visual → 内联 VisualCard
                  // 只用 toolStep.visual 渲染，避免与 done 消息的 metadata visual 重复渲染。
                  // metadata visual 仅用于填充 visual state（split 模式右面板），不在 inline 流中二次展示。
                  // 历史消息已在 init 时将 metadata visual 转换为 toolStep，所以历史也能正常渲染。
                  if (msg.role === 'assistant' && Array.isArray(msg.metadata?.dsh_cards)) {
                    return <React.Fragment key={msg._id || i}>
                      {(msg.metadata.dsh_cards as DshCard[]).map((card, index) => <DshToolCard key={index} card={card} />)}
                      {msg.content && <ChatBubble native={appearance === 'native'} msg={msg} isUser={false} index={i} streaming={msg.streaming} />}
                    </React.Fragment>;
                  }
                  const stepVisuals = msg.toolStep?.visuals?.length
                    ? msg.toolStep.visuals
                    : (msg.toolStep?.visual ? [msg.toolStep.visual] : []);
                  const hasVisual = msg.toolStep?.status === 'succeeded' && stepVisuals.length > 0;
                  if (hasVisual && msg.role !== 'user') {
                    return (
                      <React.Fragment key={msg._id || i}>
                        {stepVisuals.map((visual, visualIndex) => (
                          <InlineVisualCard
                            key={`${msg._id || i}-visual-${visualIndex}`}
                            visual={visual as VisualData}
                            index={i}
                          />
                        ))}
                        {msg.content && (
                          <ChatBubble native={appearance === 'native'} msg={msg} isUser={false} index={i} streaming={msg.streaming} />
                        )}
                      </React.Fragment>
                    );
                  }
                  // 其他工具步骤 → ToolStepMessage
                  // quick_generate/bulk_generate 完成后不再展示步骤卡片，
                  // 因为后续文字气泡已经说明了结果，避免两个气泡说同一件事
                  // render_visual 完成但无 visual → 后端校验拒绝了无效参数，AI 会自纠正，用户无需看到
                  if (msg.toolStep) {
                    const step = msg.toolStep;
                    const isGenDone = (step.name === 'quick_generate' || step.name === 'bulk_generate_questions') && step.status === 'succeeded';
                    if (isGenDone) return null;
                    if (step.name === 'render_visual' && step.status === 'succeeded' && !step.visual) return null;
                    return <ToolStepMessage key={msg._id || i} step={step} index={i} />;
                  }
                  // 普通消息 → ChatBubble
                  return <ChatBubble native={appearance === 'native'} key={msg._id || i} msg={msg} isUser={msg.role === 'user'} index={i} streaming={msg.streaming} />;
                })}
                {loading && (
                  <ChatBubble native={appearance === 'native'} msg={{ role: 'assistant', content: '' }} isUser={false} isThinking index={messages.length} />
                )}
              </div>
            </div>
          </AgentReplyContext.Provider>

          {/* Task progress — above input */}
          {taskList && (
            <div className="shrink-0 px-4">
              <div className="max-w-3xl mx-auto">
                <TaskList data={taskList} />
              </div>
            </div>
          )}

          {/* Input */}
          <div className={cn("shrink-0 px-4 pb-4 pt-2", appearance === 'native' && 'um-agent-chat-input')}>
            <div className="max-w-3xl mx-auto">
              {recoveryHint}
              <div data-tour={inputTourClass} className="rounded-2xl border border-border bg-white shadow-[0_2px_12px_rgba(0,0,0,0.06),0_0_0_1px_rgba(0,0,0,0.02)] overflow-hidden focus-within:border-primary/40 focus-within:ring-1 focus-within:ring-primary/20 transition-all">
                {noteMentions.panel}
                <textarea ref={nativeInputRef} rows={1}
                  value={input}
                  onChange={e => { setInput(e.target.value); noteMentions.updateQuery(e.target.value, e.target.selectionStart); }}
                  onCompositionStart={() => setIsComposition(true)}
                  onCompositionEnd={() => setIsComposition(false)}
                  onKeyDown={e => { if (noteMentions.onKeyDown(e, isComposing)) return; if (e.key === 'Enter' && !e.shiftKey && !isComposing && !e.nativeEvent.isComposing && !loading && input.trim() && bot) { e.preventDefault(); doSend(input); } }}
                  placeholder={chatPlaceholder}
                  aria-label={`和${botDisplayName}对话`}
                  autoComplete="off"
                  className="w-full bg-transparent border-none resize-none text-sm px-4 py-2 placeholder:text-muted-foreground/55 focus:outline-none min-h-[36px]"
                  disabled={loading}
                />
                <div className="flex items-center justify-end gap-1.5 px-2.5 py-1.5">
                  <Popover open={skillOpen} onOpenChange={setSkillOpen}>
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <PopoverTrigger asChild>
                          <button aria-label="快捷任务" className={cn("p-1.5 rounded-lg transition-colors", skillOpen ? "text-primary/60" : "text-muted-foreground/55 hover:text-foreground/70 hover:bg-muted")}>
                            <Plus className="h-4 w-4" />
                          </button>
                        </PopoverTrigger>
                      </TooltipTrigger>
                      <TooltipContent side="top" className="text-[10px]">{skillTooltip}</TooltipContent>
                    </Tooltip>
                    <PopoverContent align="start" side="top" className={cn("w-48 p-1 rounded-xl border-border/60 shadow-lg", appearance === 'native' && 'um-native-menu')}>
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
                  <Button aria-label="发送消息" onClick={() => doSend(input)} disabled={loading || !input.trim() || !bot} size="icon"
                    className="um-agent-send rounded-full h-9 w-9 bg-primary text-primary-foreground shadow-none active:scale-95 transition-all shrink-0 hover:opacity-90">
                    {loading ? <Spinner className="h-4 w-4 animate-spin" /> : <ArrowUp className="h-4 w-4" />}
                  </Button>
                </div>
              </div>
              {quotaHint}
            </div>
          </div>
          </div>
        </NativeAgentShell>
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
              <span className="text-xs text-foreground/70 flex-1 truncate">{conversationTitle}</span>
            ) : (
              <div className="h-7 w-7 rounded-full bg-gradient-to-br from-primary to-primary/60 flex items-center justify-center shrink-0">
                <Sparkle className="h-3.5 w-3.5 text-primary-foreground" />
              </div>
            )}
            {sessions.length > 1 && (
              <Popover open={sessionOpen} onOpenChange={setSessionOpen}>
                <PopoverTrigger asChild>
                  <button className="text-[11px] font-medium text-muted-foreground hover:text-foreground transition-colors shrink-0 rounded-full px-2.5 py-0.5 bg-muted/50 hover:bg-muted">
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
            <Button variant="ghost" size="sm" onClick={() => wrappedReset()}
              className="rounded text-muted-foreground/40 hover:text-foreground/60 gap-0.5 px-1.5 h-5 shrink-0">
              <ArrowCounterClockwise className="h-2.5 w-2.5" />
              <span className="text-[9px] font-medium">新对话</span>
            </Button>
          </div>

          <div ref={scrollRef} className="um-agent-scroll flex-1 overflow-y-auto min-h-0">
            <div className="p-2.5 space-y-3">
              {messages.filter(m => m.role === 'user' || m.visible !== false).map((msg, i) => (
                msg.toolStep ? (
                  <ToolStepMessage key={msg._id || i} step={msg.toolStep} index={i} />
                ) : (
                  <ChatBubble key={msg._id || i} msg={msg} isUser={msg.role === 'user'} index={i} compact streaming={msg.streaming} />
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
