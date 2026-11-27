import { t, useLocale } from '@/i18n';
import { useEffect, useRef, useState, type RefObject } from 'react';
import { Link } from 'react-router-dom';
import { Sparkle, X } from '@phosphor-icons/react';
import { useXiaoYuChat } from '@/pages/xiaoyu/xiaoYuChatContext';
import { companionReturnHref } from '@/lib/companionVideo';
import { learningUrl, useProjectLearning } from '@/lib/projectLearning';
import { reportMessageExposure } from '@/lib/learningExposure';
import ChatBubble from '@/components/ChatBubble';
import { ToolStepMessage } from '@/components/AgentStepCard';
import { DshToolCard, type DshCard } from '@/components/DshToolCard';
import { InlineVisualCard } from '@/components/InlineVisualCard';
import type { VisualData } from '@/pages/xiaoyu/visuals';
import { AgentReplyContext } from '@/pages/xiaoyu/visuals/agentReplyContext';
import { courseCitationComponents } from './courseCitations';
import { projectCourseLinks } from './projectCourseLinks';
import type { Message } from '@/hooks/useAgentConversation';
import { useSystemStore } from '@/store/useSystemStore';
import { useCourseAIStore } from '@/store/useCourseAIStore';

interface Props {
  projectId: number; linkedConversation?: string; courseId: number; videoRef: RefObject<HTMLVideoElement | null>;
  onSeek: (seconds: number) => void;
  mode: 'floating' | 'sidebar'; visible: boolean;
  workbench?: boolean;
}
function ProjectCourseBubble({ message, index, projectId, conversationId, courseId, onSeek }: {
  message: Message; index: number; projectId: number; conversationId: string; courseId: number; onSeek: (seconds: number) => void;
}) {
  return <ChatBubble native compact msg={message} isUser={message.role === 'user'} index={index} streaming={message.streaming}
    markdownComponents={projectCourseLinks(projectId, conversationId, courseCitationComponents(message.metadata?.course_context, courseId, onSeek), courseId)} />;
}

export default function ProjectCourseChat({ projectId, linkedConversation, courseId, videoRef, onSeek, mode, visible, workbench = false }: Props) {
  useLocale();
  const { chat, activate, setPageHooks, openingProject } = useXiaoYuChat();
  const query = useProjectLearning(chat.projectId === projectId ? projectId : null);
  const [open, setOpen] = useState(mode === 'sidebar');
  const snapshot = useRef<number | null>(null);
  const bottom = useRef<HTMLDivElement>(null);
  const floating = mode === 'floating';
  const matches = chat.projectId === projectId && (!linkedConversation || chat.conversationId === linkedConversation);
  const ready = chat.initialized && matches && !openingProject;
  const returnConversation = linkedConversation || (matches ? chat.conversationId : undefined);
  const sendShortcut = useSystemStore(state => state.sendShortcut);
  useEffect(activate, [activate]);
  useEffect(() => {
    if (!ready) return;
    setPageHooks({ getExtraPayload: () => {
      const position = snapshot.current ?? Math.max(0, videoRef.current?.currentTime || 0);
      if (workbench) {
        const { transcriptCourseId, transcriptSegments } = useCourseAIStore.getState();
        if (transcriptCourseId !== courseId || !transcriptSegments.some(segment => segment.start < position + 30 && segment.end > Math.max(0, position - 30))) return {};
      }
      return { course_context: { course_id: courseId, video_seconds: position } };
    } });
    return () => setPageHooks(null);
  }, [ready, courseId, videoRef, setPageHooks, workbench]);
  useEffect(() => {
    if (!ready || !visible || (floating && !open)) return;
    for (const message of chat.messages.filter(message => message.role === 'user' || message.visible !== false).slice(-16)) {
      reportMessageExposure(message, true);
    }
  }, [ready, visible, floating, open, chat.messages]);
  useEffect(() => { bottom.current?.scrollIntoView({ block: 'end' }); }, [chat.messages.length, chat.loading]);
  const update = (text: string) => {
    if (!chat.input.trim() && text.trim()) snapshot.current = Math.max(0, videoRef.current?.currentTime || 0);
    if (!text.trim()) snapshot.current = null;
    chat.setInput(text);
  };
  const send = (text = chat.input) => {
    if (!ready || chat.loading || !text.trim()) return;
    void chat.doSend(text.trim()).finally(() => { snapshot.current = null; });
  };
  return <div className="um-course-assistant" data-mode={mode} data-expanded={floating && open || undefined} hidden={!visible}>
    {floating && !open && <button className="um-course-assistant-launcher" aria-label={t('打开小宇项目学习助手')} onClick={() => setOpen(true)}><Sparkle size={18} /><span>{t('继续项目学习')}</span></button>}
    <section className="um-course-chat" hidden={floating && !open} role={floating ? 'dialog' : 'region'} aria-label={t('小宇项目课程学习')}>
      <header className="um-course-chat-header"><Sparkle size={18} /><div className="um-course-chat-heading"><h2>{t('小宇')}</h2><p>{query.data?.name || t('项目学习')} {t('· 当前课程')}</p></div><Link to={workbench ? companionReturnHref(projectId, returnConversation) : learningUrl('/xiaoyu?learning_view=path', projectId, returnConversation)}>{t('返回项目')}</Link>{floating && <button className="um-course-assistant-icon" aria-label={t('收起项目课程助手')} onClick={() => setOpen(false)}><X size={16} /></button>}</header>
      <AgentReplyContext.Provider value={{ onReply: send, projectId: chat.projectId === projectId ? projectId : null, conversationId: chat.conversationId }}><div className="um-course-chat-messages">{!ready ? <p role="status">{(!chat.initialized || openingProject) ? t('正在恢复项目学习…') : t('请返回小宇选择可用的学习项目。')}</p> : chat.messages.filter(message => message.role === 'user' || message.visible !== false).slice(-16).map((message, index) => {
        const visuals = message.toolStep?.visuals?.length ? message.toolStep.visuals : message.toolStep?.visual ? [message.toolStep.visual] : [];
        return <article key={message.id ?? message._id ?? index} className="um-course-project-message" data-role={message.role}><small>{message.role === 'user' ? t('你') : t('小宇')}</small>
          {(message.metadata?.dsh_cards as DshCard[] | undefined)?.map((card, i) => <DshToolCard key={i} card={card} />)}
          {message.toolStep ? message.toolStep.status === 'succeeded' && visuals.length ? visuals.map((visual, i) => <InlineVisualCard key={i} visual={visual as VisualData} />) : <ToolStepMessage step={message.toolStep} /> : <ProjectCourseBubble message={message} index={index} projectId={projectId} conversationId={chat.conversationId} courseId={courseId} onSeek={onSeek} />}
        </article>;
      })}<div ref={bottom} /></div></AgentReplyContext.Provider>
      <form className="um-course-chat-composer" onSubmit={event => { event.preventDefault(); send(); }}><textarea aria-label={t('围绕当前课程继续项目学习')} value={ready ? chat.input : ''} onChange={event => update(event.target.value)} disabled={!ready || chat.loading} placeholder={t('结合当前课程，继续这个学习目标…')} onKeyDown={event => { if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing && (sendShortcut === 'enter' || event.ctrlKey || event.metaKey)) { event.preventDefault(); send(); } }} /><button className="um-agent-button um-agent-button-primary" disabled={!ready || chat.loading || !chat.input.trim()}>{chat.loading ? t('正在思考…') : t('发送')}</button></form>
    </section>
  </div>;
}
