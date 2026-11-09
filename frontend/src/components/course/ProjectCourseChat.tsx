import { useEffect, useRef, useState, type RefObject } from 'react';
import { Link } from 'react-router-dom';
import { Sparkle, X } from '@phosphor-icons/react';
import { useXiaoYuChat } from '@/pages/xiaoyu/xiaoYuChatContext';
import { useProjectLearning } from '@/lib/projectLearning';
import ChatBubble from '@/components/ChatBubble';
import { ToolStepMessage } from '@/components/AgentStepCard';
import { DshToolCard, type DshCard } from '@/components/DshToolCard';
import { InlineVisualCard } from '@/components/InlineVisualCard';
import type { VisualData } from '@/pages/xiaoyu/visuals';
import { AgentReplyContext } from '@/pages/xiaoyu/visuals/agentReplyContext';
import { courseCitationComponents } from './courseCitations';
import { useSystemStore } from '@/store/useSystemStore';

interface Props {
  projectId: number; courseId: number; videoRef: RefObject<HTMLVideoElement | null>;
  mode: 'floating' | 'sidebar'; visible: boolean;
}
export default function ProjectCourseChat({ projectId, courseId, videoRef, mode, visible }: Props) {
  const { chat, activate, setPageHooks, openingProject } = useXiaoYuChat();
  const query = useProjectLearning(chat.projectId === projectId ? projectId : null);
  const [open, setOpen] = useState(mode === 'sidebar');
  const snapshot = useRef<number | null>(null);
  const bottom = useRef<HTMLDivElement>(null);
  const floating = mode === 'floating';
  const sendShortcut = useSystemStore(state => state.sendShortcut);
  useEffect(activate, [activate]);
  useEffect(() => {
    if (chat.projectId !== projectId) return;
    setPageHooks({ getExtraPayload: () => ({ course_context: { course_id: courseId,
      video_seconds: snapshot.current ?? Math.max(0, videoRef.current?.currentTime || 0) } }) });
    return () => setPageHooks(null);
  }, [projectId, chat.projectId, courseId, videoRef, setPageHooks]);
  useEffect(() => { bottom.current?.scrollIntoView({ block: 'end' }); }, [chat.messages.length, chat.loading]);
  const ready = chat.initialized && chat.projectId === projectId && !openingProject;
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
    {floating && !open && <button className="um-course-assistant-launcher" aria-label="打开小宇项目学习助手" onClick={() => setOpen(true)}><Sparkle size={18} /><span>继续项目学习</span></button>}
    <section className="um-course-chat" hidden={floating && !open} role={floating ? 'dialog' : 'region'} aria-label="小宇项目课程学习">
      <header className="um-course-chat-header"><Sparkle size={18} /><div className="um-course-chat-heading"><h2>小宇</h2><p>{query.data?.name || '项目学习'} · 当前课程</p></div><Link to="/xiaoyu">返回项目</Link>{floating && <button className="um-course-assistant-icon" aria-label="收起项目课程助手" onClick={() => setOpen(false)}><X size={16} /></button>}</header>
      <AgentReplyContext.Provider value={{ onReply: send }}><div className="um-course-chat-messages">{!ready ? <p role="status">{openingProject ? '正在恢复项目学习…' : '请返回小宇选择可用的学习项目。'}</p> : chat.messages.filter(message => message.role === 'user' || message.visible !== false).slice(-16).map((message, index) => {
        const visuals = message.toolStep?.visuals?.length ? message.toolStep.visuals : message.toolStep?.visual ? [message.toolStep.visual] : [];
        return <article key={message.id ?? message._id ?? index} className="um-course-project-message" data-role={message.role}><small>{message.role === 'user' ? '你' : '小宇'}</small>
          {(message.metadata?.dsh_cards as DshCard[] | undefined)?.map((card, i) => <DshToolCard key={i} card={card} />)}
          {message.toolStep ? message.toolStep.status === 'succeeded' && visuals.length ? visuals.map((visual, i) => <InlineVisualCard key={i} visual={visual as VisualData} />) : <ToolStepMessage step={message.toolStep} /> : <ChatBubble native compact msg={message} isUser={message.role === 'user'} index={index} streaming={message.streaming} markdownComponents={courseCitationComponents(message.metadata?.course_context, courseId, seconds => { if (videoRef.current) videoRef.current.currentTime = seconds; })} />}
        </article>;
      })}<div ref={bottom} /></div></AgentReplyContext.Provider>
      <form className="um-course-chat-composer" onSubmit={event => { event.preventDefault(); send(); }}><textarea aria-label="围绕当前课程继续项目学习" value={chat.input} onChange={event => update(event.target.value)} disabled={!ready || chat.loading} placeholder="结合当前课程，继续这个学习目标…" onKeyDown={event => { if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing && (sendShortcut === 'enter' || event.ctrlKey || event.metaKey)) { event.preventDefault(); send(); } }} /><button className="um-agent-button um-agent-button-primary" disabled={!ready || chat.loading || !chat.input.trim()}>{chat.loading ? '正在思考…' : '发送'}</button></form>
    </section>
  </div>;
}
