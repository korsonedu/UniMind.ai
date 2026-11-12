import ProjectCourseChat from './ProjectCourseChat';
import { memo, useEffect, useRef, useState, type RefObject } from 'react';
import { ArrowUp, ArrowCounterClockwise, ArrowsOut, ArrowsIn, Clock, NotePencil, Sparkle, ClockCounterClockwise, X } from '@phosphor-icons/react';
import { Link, useSearchParams } from 'react-router-dom';
import { useSystemStore } from '@/store/useSystemStore';
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from '@/components/ui/dropdown-menu';
import api from '@/lib/api';
import { notesApi } from '@/lib/notes';
import { normalizeApiError } from '@/lib/apiError';
import { useAuthStore } from '@/store/useAuthStore';
import type { ExperiencePreferences } from '@/store/useSystemStore';
import { useAgentConversation, type Bot, type Message } from '@/hooks/useAgentConversation';
import { findAssistantBot } from '@/pages/xiaoyu/xiaoYuChatContext';
import { AgentReplyContext } from '@/pages/xiaoyu/visuals/agentReplyContext';
import { InlineVisualCard } from '@/components/InlineVisualCard';
import { ToolStepMessage } from '@/components/AgentStepCard';
import ChatBubble from '@/components/ChatBubble';
import type { VisualData } from '@/pages/xiaoyu/visuals';
import { restoreVisualSteps } from '@/lib/visualHistory';
import { formatDuration } from '@/lib/utils';
import { toast } from 'sonner';
import { courseCitationComponents } from './courseCitations';
import { readRecovery, recoveryScope } from '@/lib/conversationRecovery';
import { captureCourseFrame, CourseFrameBuffer, type CourseVisual } from '@/lib/courseVisual';

interface DraftSnapshot { position: number; visual?: CourseVisual; error?: string; textOnly?: boolean }

interface CourseAnchor {
  course_id: number;
  video_seconds: number;
  start_seconds?: number;
  end_seconds?: number;
  visual?: CourseVisual;
}

interface CourseChatPanelProps {
  courseId: number;
  videoRef: RefObject<HTMLVideoElement | null>;
  onSeek: (seconds: number) => void;
  mode: ExperiencePreferences['courseAssistantMode'];
  visible: boolean;
  onModeChange: (mode: ExperiencePreferences['courseAssistantMode']) => void;
  onExpandSidebar: () => void;
}

export const CourseChatPanel = memo(function CourseChatPanel(props: CourseChatPanelProps) {
  const userId = useAuthStore(state => state.user?.id);
  const [params] = useSearchParams();
  const projectId = Number(params.get('project'));
  if (Number.isSafeInteger(projectId) && projectId > 0) return <ProjectCourseChat projectId={projectId} courseId={props.courseId} videoRef={props.videoRef} mode={props.mode} visible={props.visible} />;
  return <CourseChatSession key={`${props.courseId}:${userId}:${params.get('conversation') || ''}`} {...props} />;
});

function CourseChatSession({ courseId, videoRef, onSeek, mode, visible, onModeChange, onExpandSidebar }: CourseChatPanelProps) {
  const userId = useAuthStore(state => state.user?.id);
  const sentSnapshot = useRef<DraftSnapshot>({ position: 0 });
  const draftRef = useRef<DraftSnapshot | null>(null);
  const draftTextRef = useRef('');
  const buffer = useRef(new CourseFrameBuffer());
  const [draft, setDraft] = useState<DraftSnapshot | null>(null);
  const sendShortcut = useSystemStore(state => state.sendShortcut);
  const [searchParams] = useSearchParams();
  const linkedConversation = searchParams.get('conversation') || undefined;
  const [loadError, setLoadError] = useState('');
  const [loadVersion, setLoadVersion] = useState(0);
  const [open, setOpen] = useState(!!linkedConversation);
  const [expanded, setExpanded] = useState(!!linkedConversation);
  const [savingNote, setSavingNote] = useState<number | null>(null);
  const [savedNotes, setSavedNotes] = useState<Record<number, number>>({});
  const launcherRef = useRef<HTMLButtonElement>(null);
  const composerRef = useRef<HTMLTextAreaElement>(null);
  const floating = mode === 'floating';
  const { setBot, setInitialized, groupIntoSessions, setSessions, handleLoadSession,
    bot, conversationId, input, setInput, messages, loading, initialized, scrollRef, doSend,
    recovery, recoverRequests, handleReset, sessions, handleRefreshSessions,
    coursePosition, setCoursePosition } = useAgentConversation({
    findBot: findAssistantBot,
    courseId,
    initialConversationId: linkedConversation,
    getExtraPayload: () => ({ course_context: {
      course_id: courseId, video_seconds: sentSnapshot.current.position,
      ...(sentSnapshot.current.visual ? { visual: sentSnapshot.current.visual } : {}),
    } }),
  });
  const updateDraft = (snapshot: DraftSnapshot | null) => {
    draftRef.current = snapshot;
    setDraft(snapshot);
    setCoursePosition(snapshot?.position ?? null);
  };

  useEffect(() => {
    if (!userId) return;
    let cancelled = false;
    setInitialized(false);
    const load = async () => {
      try {
        const response = await api.get('/ai/bots/');
        if (cancelled) return;
        const bots: Bot[] = Array.isArray(response.data) ? response.data : response.data.results;
        const bot = findAssistantBot(bots);
        if (!bot) throw new Error('暂时无法连接小宇。');
        setBot(bot);
        const history = await api.get('/ai/history/', { params: { bot_id: bot.id, course_id: courseId } });
        if (cancelled) return;
        const sessions = groupIntoSessions(restoreVisualSteps((history.data as Message[])
          .filter(message => message.content !== '[Thinking...]')
          .map(message => ({ ...message, visible: true }))));
        setSessions(sessions);
        if (sessions.length) handleLoadSession(sessions.find(row => row.conversationId === linkedConversation) ?? sessions[sessions.length - 1], true);
        setInitialized(true);
      } catch (error) {
        if (!cancelled) setLoadError(error instanceof Error ? error.message : '课程问答加载失败。');
      }
    };
    void load();
    return () => { cancelled = true; };
  }, [courseId, userId, linkedConversation, loadVersion, setBot, setInitialized, groupIntoSessions, setSessions, handleLoadSession]);

  // Recovery owns the immutable original payload, including after a page reload.
  const pending = userId && bot ? readRecovery(`${recoveryScope(userId, bot.id)}:course:${courseId}`)
    .conversations[conversationId]?.pending : undefined;
  const recovering = !!pending || recovery === 'unknown' || recovery === 'pending';
  const pendingAnchor = pending ? JSON.parse(pending.key).course_context as CourseAnchor : undefined;
  const selected: DraftSnapshot | null = pendingAnchor ? {
    position: pendingAnchor.video_seconds, visual: pendingAnchor.visual,
  } : draft;
  const selectedPosition = selected?.position ?? null;
  useEffect(() => { draftTextRef.current = input; }, [input]);

  // Restored drafts keep their fragment; without a captured frame they send as transcript-only.
  useEffect(() => {
    if (!initialized || recovering || draftRef.current || coursePosition === null || !input.trim()) return;
    updateDraft({ position: coursePosition, textOnly: true });
  }, [initialized, recovering, coursePosition, input]);

  useEffect(() => {
    let attached: HTMLVideoElement | null = null;
    const clear = () => buffer.current.clear();
    const sample = () => {
      const video = videoRef.current;
      if (video !== attached) {
        attached?.removeEventListener('seeking', clear);
        attached?.removeEventListener('emptied', clear);
        clear(); attached = video;
        attached?.addEventListener('seeking', clear);
        attached?.addEventListener('emptied', clear);
      }
      if (!video) return;
      const last = buffer.current.frames[buffer.current.frames.length - 1];
      // Release expired samples even if decoding/capture subsequently fails or playback is paused.
      if (last && video.currentTime - last.video_seconds >= 8) clear();
      if (video.paused || video.seeking) return;
      if (last && video.currentTime - last.video_seconds < 1) return;
      try {
        buffer.current.add(captureCourseFrame(video));
      }
      catch { /* Draft capture surfaces the concrete error; sampling sends nothing. */ }
    };
    sample();
    const timer = window.setInterval(sample, 1000);
    return () => { window.clearInterval(timer); attached?.removeEventListener('seeking', clear); attached?.removeEventListener('emptied', clear); clear(); };
  }, [videoRef]);

  const freeze = (): DraftSnapshot => {
    try {
      const frame = captureCourseFrame(videoRef.current);
      const previous = buffer.current.previous(frame.video_seconds);
      return { position: frame.video_seconds, visual: { current: frame, ...(previous ? { previous } : {}) } };
    } catch (error) {
      return { position: videoRef.current?.currentTime ?? 0, error: error instanceof Error ? error.message : '无法读取视频画面。' };
    }
  };
  const editDraft = (text: string) => {
    if (!recovering) {
      if (!text.trim()) updateDraft(null);
      else if (!draftTextRef.current.trim() || !draftRef.current) updateDraft(freeze());
    }
    draftTextRef.current = text;
    setInput(text);
  };
  const send = (text: string, fromDraft = false) => {
    if (!text.trim() || loading || !initialized) return;
    if (!recovering) {
      const snapshot = fromDraft && draftRef.current ? draftRef.current : freeze();
      updateDraft(snapshot);
      if (!snapshot.visual && !snapshot.textOnly) {
        if (!fromDraft) { draftTextRef.current = text; setInput(text); }
        return;
      }
      sentSnapshot.current = { position: snapshot.position, visual: snapshot.visual };
    }
    void doSend(text.trim());
  };

  useEffect(() => {
    if (!visible || (floating && !open)) return;
    composerRef.current?.focus();
    if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
  }, [open, floating, visible, initialized, scrollRef]);

  const close = () => {
    setOpen(false);
    requestAnimationFrame(() => launcherRef.current?.focus());
  };
  const saveNote = async (messageId: number) => {
    setSavingNote(messageId);
    try {
      const note = await notesApi.saveCourseReply(messageId);
      setSavedNotes(current => ({ ...current, [messageId]: note.id }));
      toast.success('已保存到“我的笔记”。');
    } catch (error) {
      toast.error(normalizeApiError(error, '笔记保存失败，请稍后再试。').message);
    } finally {
      setSavingNote(null);
    }
  };
  const lastQuestion = messages.map(message => message.role).lastIndexOf('user');
  const visibleMessages = !floating || expanded ? messages : messages.slice(Math.max(0, lastQuestion));

  return <div hidden={!visible} className="um-course-assistant" data-mode={mode} data-expanded={(floating && expanded) || undefined}>
    {floating && !open && <button ref={launcherRef} type="button" className="um-course-assistant-launcher" aria-label="打开小宇课程助手" aria-expanded={false} onClick={() => setOpen(true)}>
      <span className="um-course-assistant-orb" data-thinking={loading || undefined}><Sparkle size={19} weight="fill" /></span>
      <span>{loading ? '小宇思考中' : '问小宇'}</span>
    </button>}
    <section hidden={floating && !open} className="um-course-chat" role={floating ? 'dialog' : 'region'} aria-modal={floating ? false : undefined} aria-label="小宇课程助手" onKeyDown={event => { if (floating && event.key === 'Escape') close(); }}>
    <header className="um-course-chat-header">
      <span className="um-course-assistant-orb" data-thinking={loading || undefined}><Sparkle size={18} weight="fill" /></span>
      <div className="um-course-chat-heading"><h2>小宇</h2><p>{loading ? '正在查看课程内容…' : '结合本段讲稿回答'}</p></div>
      <DropdownMenu onOpenChange={value => { if (value) void handleRefreshSessions(); }}>
        <DropdownMenuTrigger asChild><button type="button" className="um-course-assistant-icon" aria-label="本课对话" title="本课对话" disabled={!initialized}><ClockCounterClockwise size={18} /></button></DropdownMenuTrigger>
        <DropdownMenuContent className="um-course-chat-history" align="end">
          {sessions.length ? [...sessions].reverse().map(session => <DropdownMenuItem key={session.id} aria-current={session.conversationId === conversationId ? 'true' : undefined} onSelect={() => handleLoadSession(session)}>{session.label}</DropdownMenuItem>) : <DropdownMenuItem disabled>暂无本课历史对话</DropdownMenuItem>}
        </DropdownMenuContent>
      </DropdownMenu>
      <div className="um-course-chat-modes" role="group" aria-label="小宇显示方式">
        <button type="button" aria-pressed={floating} onClick={() => { setOpen(true); onModeChange('floating'); }}>浮动</button>
        <button type="button" aria-pressed={!floating} onClick={() => { onModeChange('sidebar'); onExpandSidebar(); }}><span className="um-course-mode-desktop">右侧</span><span className="um-course-mode-mobile">页内</span></button>
      </div>
      {floating && <>
        <button type="button" className="um-course-assistant-icon" onClick={() => setExpanded(value => !value)} aria-label={expanded ? '收起文字与公式' : '展开文字与公式'} aria-expanded={expanded}>{expanded ? <ArrowsIn size={16} /> : <ArrowsOut size={16} />}</button>
        <button type="button" className="um-course-assistant-icon" aria-label="收起小宇" onClick={close}><X size={17} /></button>
      </>}
    </header>
    {loadError ? <div role="alert" className="um-course-chat-status"><p>{loadError}</p><button type="button" onClick={() => { setLoadError(''); setLoadVersion(version => version + 1); }}>重新加载</button></div>
      : !initialized ? <p className="um-course-chat-status" role="status">正在加载课程问答…</p>
      : <>
        <AgentReplyContext.Provider value={{ onReply: send }}>
          <div className="um-course-chat-messages" ref={scrollRef} aria-live="polite">
            {!messages.length && <div className="um-course-chat-empty"><p>哪里没听懂，直接问我</p><span>我会结合截图和这段课程的讲稿来回答。</span>
              <div className="um-course-chat-suggestions"><button type="button" onClick={() => send('请解释一下这里的核心概念。')}>解释这一步</button><button type="button" onClick={() => send('结合这里的讲解，举一个简单的例子。')}>举个例子</button></div>
            </div>}
            {visibleMessages.map((message, index) => {
              const anchor = message.metadata?.course_context as CourseAnchor | undefined;
              const noteId = message.id
                ? savedNotes[message.id] ?? (message.metadata?.saved_note_id as number | undefined)
                : undefined;
              return <div className="um-course-chat-message" key={message._id ?? message.id ?? index}>
                {anchor && message.role === 'user' && <button type="button" className="um-course-chat-time" onClick={() => onSeek(anchor.video_seconds)} aria-label={`回到提问位置 ${formatDuration(anchor.video_seconds)}`}><Clock size={13} />{formatDuration(anchor.video_seconds)}</button>}
                {anchor?.visual && message.role === 'user' && <CourseVisualPreview visual={anchor.visual} compact />}
                {message.toolStep ? <ToolStepMessage step={message.toolStep} /> : <>
                  {(message.metadata?.dsh_cards as VisualData[] | undefined)?.map((visual, cardIndex) => <InlineVisualCard key={cardIndex} visual={visual} />)}
                  <ChatBubble native compact msg={message} isUser={message.role === 'user'} index={index} streaming={message.streaming} markdownComponents={courseCitationComponents(message.metadata?.course_context, courseId, onSeek)} />
                </>}
                {anchor?.start_seconds !== undefined && anchor.end_seconds !== undefined && message.role === 'assistant' && <button type="button" className="um-course-chat-source" onClick={() => onSeek(anchor.start_seconds!)}><Clock size={13} />讲稿参考 {formatDuration(anchor.start_seconds)}–{formatDuration(anchor.end_seconds)} · 点击回看</button>}
                {anchor && message.role === 'assistant' && !message.toolStep && message.id && !message.streaming && <div className="um-course-chat-note">
                  {noteId ? <Link to={`/notes/${noteId}`}><NotePencil size={13} />打开笔记</Link>
                    : <button type="button" disabled={savingNote !== null} onClick={() => void saveNote(message.id!)}><NotePencil size={13} />{savingNote === message.id ? '正在保存…' : '存为笔记'}</button>}
                </div>}
              </div>;
            })}
            {loading && !messages.some(message => message.streaming) && <p className="um-course-chat-status" role="status">小宇正在查看课程内容…</p>}
          </div>
        </AgentReplyContext.Provider>
        {recovering && <p className="um-course-chat-status">这条提问的结果正在确认，沿用原提问片段，确认前不能更新。<button type="button" onClick={() => void recoverRequests()}>刷新结果</button></p>}
        {selected?.visual && <CourseVisualPreview visual={selected.visual} />}
        {draft?.error && !recovering && <div className="um-course-visual-error" role="alert"><p>{draft.error}</p>
          {draft.textOnly ? <p>已选择仅用讲稿提问。</p> : <button type="button" disabled={loading} onClick={() => { if (draftRef.current) updateDraft({ ...draftRef.current, textOnly: true }); }}>仅用讲稿提问</button>}
        </div>}
        <form className="um-course-chat-composer" onSubmit={event => { event.preventDefault(); send(input, true); }}>
          <div className="um-course-chat-fragment"><span><Clock size={14} />{input.trim() && selectedPosition !== null
            ? `已固定 ${formatDuration(Math.max(0, selectedPosition - 30))}–${formatDuration(selectedPosition + 30)}`
            : input.trim() ? '请重新选择提问片段' : '输入时固定提问片段'}</span>
            <div>{input.trim() && selectedPosition !== null && <button type="button" disabled={loading} onClick={() => onSeek(Math.max(0, selectedPosition - 30))}>回看</button>}
              <button type="button" disabled={loading || recovering || !input.trim()} onClick={() => { updateDraft(freeze()); }}>改问当前片段</button></div>
          </div>
          <div className="um-course-chat-field">
            <textarea ref={composerRef} value={input} onChange={event => editDraft(event.target.value)} disabled={loading} aria-label="向小宇提问" placeholder="问问这段课程…" rows={2}
              onKeyDown={event => { if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing && (sendShortcut === 'enter' || event.ctrlKey || event.metaKey)) { event.preventDefault(); send(input, true); } }} />
            <div className="um-course-chat-send-row"><span>{sendShortcut === 'enter' ? 'Enter 发送 · Shift+Enter 换行' : '⌘ / Ctrl+Enter 发送'}</span>
              <button type="submit" disabled={loading || !input.trim() || (!recovering && !draft?.visual && !draft?.textOnly)} aria-label="发送课程问题"><ArrowUp size={18} /></button></div>
          </div>
        </form>
        {messages.length > 0 && <footer className="um-course-chat-footer">{floating && <button type="button" className="um-course-chat-details" onClick={() => setExpanded(value => !value)}>{expanded ? '收起本次对话' : '展开本次对话'}</button>}<button className="um-course-chat-new" type="button" disabled={loading} onClick={() => { updateDraft(null); draftTextRef.current = ''; setInput(''); handleReset(false); }}><ArrowCounterClockwise size={13} />新对话</button></footer>}
      </>}
  </section>
  </div>;
}

function CourseVisualPreview({ visual, compact = false }: { visual: CourseVisual; compact?: boolean }) {
  return <details className="um-course-visual" open={compact ? undefined : true}>
    <summary><img src={visual.current.image} alt="提问画面缩略图" />画面 {formatDuration(visual.current.video_seconds)} · 查看原图</summary>
    <div className="um-course-visual-content">
      <img src={visual.current.image} alt={`提问时的完整画面 ${formatDuration(visual.current.video_seconds)}`} />
      {visual.previous && <>
        <p>此前画面 {formatDuration(visual.previous.video_seconds)}</p>
        <img src={visual.previous.image} alt={`此前的完整画面 ${formatDuration(visual.previous.video_seconds)}`} />
      </>}
    </div>
  </details>;
}
