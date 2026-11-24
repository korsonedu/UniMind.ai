import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent } from 'react';
import { ArrowUp, ArrowSquareOut, ArrowsClockwise, GearSix, Plus, Sparkle, Spinner, Stop } from '@phosphor-icons/react';
import { login, loginByCode, sendVerificationCode, syncBrowserAuth } from '../../lib/auth';
import { ApiError, createApiClient, type ApiClient } from '../../lib/api';
import { extractPracticeVisuals, streamChat, type VisualData } from '../../lib/sseChat';
import { readSession, saveSession, subscribeSession, type AuthUser, type ExtensionSession } from '../../lib/storage';
import { MarkdownMessage } from '../../components/MarkdownMessage';
import { PracticeQuizCard, type PracticePayload } from '../../components/PracticeQuizCard';
import { ProjectSelector } from '../../components/ProjectSelector';
import { QuickActionsBar } from '../../components/QuickActionsBar';
import { APPEARANCE_STORAGE_KEY, SettingsDrawer } from '../../components/SettingsDrawer';
import {
  sendRuntimeMessage, sendTabMessage, UNIMIND_CAPTURE_CONTEXT_FOR_ASK,
  UNIMIND_GET_ACTIVE_VIDEO, UNIMIND_VIDEO_STATE_CHANGED, type BridgeMessage,
} from '../../shared/bridge';
import type { ActiveVideoDescriptor, CaptureContextResult, ExternalVideoContextPayload } from '../../shared/types';

interface Bot { id: number; is_xiaoyu?: boolean; bot_type?: string }
interface ConversationSummary { conversation_id: string; title?: string; project_id?: number | null; updated_at?: string }
interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  visuals: VisualData[];
  metadata?: Record<string, unknown>;
  videoSeconds?: number;
}
interface Conversation {
  id: string;
  title: string;
  projectId: number | null;
  persisted: boolean;
  messages: ChatMessage[];
}
interface HistoryMessage {
  id?: number | string;
  role: string;
  content?: string;
  metadata?: Record<string, unknown>;
}

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback;
}

async function readList<T>(api: ApiClient, path: string, signal: AbortSignal): Promise<T[]> {
  const items: T[] = [];
  const seen = new Set<string>();
  let next: string | null = path;
  while (next && !seen.has(next)) {
    seen.add(next);
    const data: T[] | { results: T[]; next?: string | null } = await api.request(next, { signal });
    if (Array.isArray(data)) return [...items, ...data];
    items.push(...data.results);
    next = data.next ?? null;
  }
  return items;
}

function newConversation(): Conversation {
  return { id: crypto.randomUUID(), title: '', projectId: null, persisted: false, messages: [] };
}

async function captureForAsk(tabId?: number): Promise<CaptureContextResult | null> {
  let timer: ReturnType<typeof setTimeout> | undefined;
  try {
    return await Promise.race([
      sendRuntimeMessage(UNIMIND_CAPTURE_CONTEXT_FOR_ASK, { tabId }).catch(() => null),
      new Promise<null>(resolve => { timer = setTimeout(() => resolve(null), 4000); }),
    ]);
  } finally { clearTimeout(timer); }
}

function matchingContext(result: CaptureContextResult | null, video: ActiveVideoDescriptor | null): ExternalVideoContextPayload | null {
  const context = result?.context;
  if (!context || !video) return null;
  return context.platform === video.platform && context.external_id === video.external_id && context.part === video.part ? context : null;
}

function LoginPanel({ session }: { session: ExtensionSession }) {
  const [tab, setTab] = useState<'code' | 'password'>('code');
  const [identifier, setIdentifier] = useState('');
  const [password, setPassword] = useState('');
  const [code, setCode] = useState('');
  const [busy, setBusy] = useState(false);
  const [sendingCode, setSendingCode] = useState(false);
  const [resendAt, setResendAt] = useState(0);
  const [countdown, setCountdown] = useState(0);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  useEffect(() => {
    if (!resendAt) return;
    function tick() {
      const seconds = Math.max(0, Math.ceil((resendAt - Date.now()) / 1000));
      setCountdown(seconds);
      return seconds;
    }
    if (!tick()) return;
    const timer = setInterval(() => { if (!tick()) clearInterval(timer); }, 250);
    return () => clearInterval(timer);
  }, [resendAt]);
  async function sendCode() {
    if (sendingCode || busy || countdown) return;
    const email = identifier.trim();
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
      setError('请输入有效的邮箱地址。');
      return;
    }
    setSendingCode(true);
    setError('');
    setNotice('');
    try {
      await sendVerificationCode(email);
      setResendAt(Date.now() + 60000);
      setCountdown(60);
      setNotice('验证码已发送，请查看邮箱。');
    } catch (failure) { setError(errorMessage(failure, '发送失败，请稍后重试。')); }
    finally { setSendingCode(false); }
  }
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (busy) return;
    setBusy(true);
    setError('');
    setNotice('');
    try {
      if (tab === 'code') await loginByCode(identifier.trim(), code.trim());
      else await login(identifier.trim(), password);
      setPassword('');
      setCode('');
    }
    catch (failure) { setError(errorMessage(failure, '登录失败，请重试。')); }
    finally { setBusy(false); }
  }
  async function sync() {
    setBusy(true);
    setError('');
    setNotice('');
    try {
      const result = await syncBrowserAuth();
      if (!result.token) setNotice('尚未找到主站登录态，也可以在这里直接登录。');
    } catch (failure) { setError(errorMessage(failure, '同步失败，请重试。')); }
    finally { setBusy(false); }
  }
  return <main className="login-panel um-auth-login">
    <section className="um-auth-panel" aria-labelledby="auth-title">
      <div className="um-auth-mark"><img src="/unimind_logo_small.png" width="48" height="48" alt="" /></div>
      <h1 id="auth-title">欢迎回来</h1>
      <div className="um-auth-fields">
        <div className="um-auth-tabs" role="tablist" aria-label="登录方式">
          {(['code', 'password'] as const).map(value => <button key={value} type="button" role="tab" id={`login-tab-${value}`}
            aria-selected={tab === value} aria-controls="login-tabpanel" tabIndex={tab === value ? 0 : -1}
            disabled={busy || sendingCode} onClick={() => { setTab(value); setError(''); setNotice(''); }}
            onKeyDown={event => {
              if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
              event.preventDefault();
              const next = event.key === 'Home' ? 'code' : event.key === 'End' ? 'password' : value === 'code' ? 'password' : 'code';
              setTab(next);
              setError('');
              setNotice('');
              document.getElementById(`login-tab-${next}`)?.focus();
            }}>{value === 'code' ? '验证码登录' : '密码登录'}</button>)}
        </div>
        <form className="login-form" id="login-tabpanel" role="tabpanel" aria-labelledby={`login-tab-${tab}`} onSubmit={event => void submit(event)}>
          <label className="field-label" htmlFor="login-identifier">{tab === 'code' ? '邮箱' : '邮箱 / 用户名'}</label>
          <input id="login-identifier" type={tab === 'code' ? 'email' : 'text'} autoComplete="username" required value={identifier}
            onChange={event => { setIdentifier(event.target.value); setError(''); }} placeholder={tab === 'code' ? 'name@example.com' : '输入邮箱或用户名'} disabled={busy || sendingCode} />
          {tab === 'code' ? <>
            <label className="field-label" htmlFor="login-code">验证码</label>
            <div className="um-auth-code-row">
              <input id="login-code" autoComplete="one-time-code" inputMode="numeric" required value={code} onChange={event => setCode(event.target.value)} placeholder="输入验证码" disabled={busy} />
              <button type="button" className="um-auth-code-button" disabled={busy || sendingCode || countdown > 0 || !identifier.trim()} onClick={() => void sendCode()}>
                {sendingCode ? '正在发送…' : countdown ? `${countdown} 秒后重发` : '发送验证码'}
              </button>
            </div>
          </> : <>
            <label className="field-label" htmlFor="login-password">密码</label>
            <input id="login-password" type="password" autoComplete="current-password" required value={password} onChange={event => setPassword(event.target.value)} placeholder="输入密码" disabled={busy} />
          </>}
          <button type="submit" className="primary-button um-auth-submit" disabled={busy || sendingCode || !identifier.trim() || !(tab === 'code' ? code.trim() : password)}>{busy && <Spinner size={16} className="spin" />}{busy ? '登录中…' : '登录'}</button>
        </form>
      </div>
      {notice && <p className="inline-notice" role="status">{notice}</p>}
      {error && <p className="inline-error" role="alert">{error}</p>}
      <div className="login-alternatives um-auth-footer">
        <button type="button" className="secondary-button" disabled={busy || sendingCode} onClick={() => void sync()}><ArrowsClockwise size={16} />同步浏览器登录态</button>
        <a className="text-button" href={`${session.serverOrigin}/login`} target="_blank" rel="noopener noreferrer">打开 UniMind 主站登录<ArrowSquareOut size={14} /><span className="login-address">前往 {new URL(session.serverOrigin).host}/login 网页登录</span></a>
      </div>
    </section>
  </main>;
}

function LearningPanel({ session, onSettings }: { session: ExtensionSession; onSettings: () => void }) {
  const api = useMemo(() => createApiClient(session), [session.serverOrigin, session.token]);
  const [botId, setBotId] = useState<number | null>(session.botId ?? null);
  const [botLoading, setBotLoading] = useState(true);
  const [botRevision, setBotRevision] = useState(0);
  const [video, setVideo] = useState<ActiveVideoDescriptor | null>(null);
  const [conversation, setConversation] = useState<Conversation | null>(null);
  const [restoring, setRestoring] = useState(false);
  const [restoreRevision, setRestoreRevision] = useState(0);
  const [sending, setSending] = useState(false);
  const [capturing, setCapturing] = useState(false);
  const [input, setInput] = useState('');
  const [error, setError] = useState('');
  const [restoreError, setRestoreError] = useState('');
  const activeTab = useRef<number | undefined>(undefined);
  const activeWindow = useRef<number | undefined>(undefined);
  const tabVersion = useRef(0);
  const conversationRef = useRef(conversation);
  const streaming = useRef<AbortController | null>(null);
  const sendingRef = useRef(false);
  const pendingProject = useRef<{ conversationId: string; projectId: number | null } | null>(null);
  const scroller = useRef<HTMLDivElement>(null);
  const keepAtBottom = useRef(true);
  const textarea = useRef<HTMLTextAreaElement>(null);
  const unknownIdentityScope = useRef(crypto.randomUUID());
  const routeKey = `${botId}:${video?.video_key ?? 'generic'}`;
  const currentRoute = useRef(routeKey);
  currentRoute.current = routeKey;
  conversationRef.current = conversation;

  const updateConversation = useCallback((update: (previous: Conversation) => Conversation) => {
    const previous = conversationRef.current;
    if (!previous) return;
    const next = update(previous);
    conversationRef.current = next;
    setConversation(next);
  }, []);

  const expireAuth = useCallback((failure: unknown) => {
    if (failure instanceof ApiError && failure.status === 401) {
      void saveSession({
        serverOrigin: session.serverOrigin, token: null, tokenSource: null, user: null, botId: null,
      }, session).catch(() => undefined);
    }
  }, [session.serverOrigin, session.token, session.tokenSource]);

  useEffect(() => {
    const controller = new AbortController();
    setBotLoading(true);
    setError('');
    void readList<Bot>(api, '/api/ai/bots/', controller.signal).then(bots => {
      if (controller.signal.aborted) return;
      const bot = bots.find(item => item.is_xiaoyu || item.bot_type === 'planner') ?? bots[0];
      if (!bot) throw new Error('当前账号暂时没有可用的小宇助手。');
      setBotId(bot.id);
      void saveSession({ serverOrigin: session.serverOrigin, botId: bot.id }, session).catch(() => undefined);
    }).catch(failure => {
      if (!controller.signal.aborted) {
        expireAuth(failure);
        setBotId(null);
        setError(errorMessage(failure, '小宇暂时无法连接。'));
      }
    }).finally(() => { if (!controller.signal.aborted) setBotLoading(false); });
    return () => controller.abort();
  }, [api, botRevision, expireAuth]);

  useEffect(() => {
    let mounted = true;
    async function refreshTab() {
      const version = ++tabVersion.current;
      const tabs = await chrome.tabs.query({ active: true, currentWindow: true }).catch(() => []);
      const tab = tabs[0];
      if (!mounted || version !== tabVersion.current) return;
      const changed = activeTab.current !== tab?.id;
      activeTab.current = tab?.id;
      activeWindow.current = tab?.windowId;
      if (changed) setVideo(null);
      let timer: ReturnType<typeof setTimeout> | undefined;
      try {
        const descriptor = tab?.id === undefined ? null : await Promise.race([
          sendTabMessage(tab.id, UNIMIND_GET_ACTIVE_VIDEO).catch(() => null),
          new Promise<null>(resolve => { timer = setTimeout(() => resolve(null), 1500); }),
        ]);
        if (mounted && version === tabVersion.current) setVideo(descriptor ?? null);
      } finally { clearTimeout(timer); }
    }
    function onActivated(info: { tabId: number; windowId: number }) {
      if (activeWindow.current === undefined || activeWindow.current === info.windowId) void refreshTab();
    }
    function onUpdated(tabId: number, change: { url?: string; status?: string }) {
      if (tabId === activeTab.current && (change.url || change.status === 'complete')) void refreshTab();
    }
    function onMessage(message: BridgeMessage, sender: chrome.runtime.MessageSender) {
      if (message?.type !== UNIMIND_VIDEO_STATE_CHANGED) return;
      if (sender.tab?.id !== undefined && sender.tab.id !== activeTab.current) return;
      ++tabVersion.current;
      setVideo(message.payload ?? null);
    }
    void refreshTab();
    chrome.tabs.onActivated.addListener(onActivated);
    chrome.tabs.onUpdated.addListener(onUpdated);
    chrome.runtime.onMessage.addListener(onMessage);
    return () => {
      mounted = false;
      ++tabVersion.current;
      chrome.tabs.onActivated.removeListener(onActivated);
      chrome.tabs.onUpdated.removeListener(onUpdated);
      chrome.runtime.onMessage.removeListener(onMessage);
    };
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    streaming.current?.abort();
    sendingRef.current = false;
    pendingProject.current = null;
    setSending(false);
    setCapturing(false);
    setInput('');
    setError('');
    setRestoreError('');
    setConversation(null);
    conversationRef.current = null;
    if (!botId) return () => controller.abort();
    const key = routeKey;
    setRestoring(true);
    async function restore() {
      let next = newConversation();
      if (video) {
        const summaries = await readList<ConversationSummary>(api,
          `/api/ai/conversations/?bot_id=${botId}&external_video_key=${encodeURIComponent(video.video_key)}`, controller.signal);
        const latest = summaries.sort((a, b) => String(b.updated_at ?? '').localeCompare(String(a.updated_at ?? '')))[0];
        if (latest) {
          const history = await readList<HistoryMessage>(api,
            `/api/ai/history/?bot_id=${botId}&conversation_id=${encodeURIComponent(latest.conversation_id)}`, controller.signal);
          next = {
            id: latest.conversation_id, title: latest.title || '', projectId: latest.project_id ?? null, persisted: true,
            messages: history.filter(message => message.role === 'user' || message.role === 'assistant').map((message, index) => {
              const context = message.metadata?.external_video_context as { video_seconds?: number } | undefined;
              return {
                id: String(message.id ?? `history-${index}`), role: message.role as 'user' | 'assistant',
                content: message.content ?? '', visuals: extractPracticeVisuals(message), metadata: message.metadata,
                videoSeconds: context?.video_seconds,
              };
            }),
          };
        }
      }
      if (!controller.signal.aborted && currentRoute.current === key) {
        conversationRef.current = next;
        setConversation(next);
      }
    }
    void restore().catch(failure => {
      if (!controller.signal.aborted && currentRoute.current === key) {
        expireAuth(failure);
        setRestoreError(errorMessage(failure, '历史对话暂时无法读取。'));
      }
    }).finally(() => {
      if (!controller.signal.aborted && currentRoute.current === key) setRestoring(false);
    });
    return () => { controller.abort(); streaming.current?.abort(); };
  }, [api, botId, video?.video_key, restoreRevision]);

  useEffect(() => {
    if (keepAtBottom.current && scroller.current) scroller.current.scrollTop = scroller.current.scrollHeight;
  }, [conversation?.messages, sending, capturing]);

  useEffect(() => () => { currentRoute.current = 'unmounted'; streaming.current?.abort(); }, []);

  async function selectProject(projectId: number | null) {
    const current = conversationRef.current;
    if (!current) return;
    const key = currentRoute.current;
    if (!current.persisted) {
      updateConversation(previous => ({ ...previous, projectId }));
      if (sendingRef.current) pendingProject.current = { conversationId: current.id, projectId };
      return;
    }
    await api.request(`/api/ai/conversations/${current.id}/`, { method: 'PATCH', body: { project_id: projectId } });
    if (currentRoute.current === key && conversationRef.current?.id === current.id) {
      updateConversation(previous => ({ ...previous, projectId }));
    }
  }

  function startNewConversation() {
    streaming.current?.abort();
    pendingProject.current = null;
    sendingRef.current = false;
    setSending(false);
    setCapturing(false);
    setRestoreError('');
    setError('');
    const next = newConversation();
    conversationRef.current = next;
    setConversation(next);
    setInput('');
    keepAtBottom.current = true;
    textarea.current?.focus();
  }

  async function ask(message: string) {
    const text = message.trim();
    const current = conversationRef.current;
    if (!text || !current || !botId || sendingRef.current || restoring) return;
    const key = currentRoute.current;
    const videoAtSend = video;
    const controller = new AbortController();
    streaming.current = controller;
    sendingRef.current = true;
    setSending(true);
    setCapturing(true);
    setError('');
    setInput('');
    keepAtBottom.current = true;
    const assistantId = crypto.randomUUID();
    let serverReady = current.persisted;
    updateConversation(previous => ({ ...previous, messages: [
      ...previous.messages,
      { id: crypto.randomUUID(), role: 'user', content: text, visuals: [] },
      { id: assistantId, role: 'assistant', content: '', visuals: [] },
    ] }));
    function stillCurrent() {
      return currentRoute.current === key && conversationRef.current?.id === current?.id && streaming.current === controller;
    }
    try {
      const capture = await captureForAsk(activeTab.current);
      if (controller.signal.aborted || !stillCurrent()) return;
      setCapturing(false);
      const context = matchingContext(capture, videoAtSend);
      const projectIdAtRequest = conversationRef.current?.projectId ?? null;
      pendingProject.current = null;
      await streamChat(api, {
        bot_id: botId, conversation_id: current.id, message: text, project_id: projectIdAtRequest,
        ...(context ? { external_video_context: context } : {}),
      }, {
        signal: controller.signal,
        onUpdate(state) {
          if (!stillCurrent()) return;
          updateConversation(previous => ({
            ...previous,
            title: state.conversationTitle || previous.title,
            messages: previous.messages.map(item => item.id === assistantId ? {
              ...item, content: state.content, visuals: state.visuals.filter(visual => visual.type === 'practice_quiz'),
              metadata: state.metadata, videoSeconds: context?.video_seconds,
            } : item),
          }));
        },
      });
      serverReady = true;
    } catch (failure) {
      if (stillCurrent() && !controller.signal.aborted) {
        expireAuth(failure);
        setError(errorMessage(failure, '小宇暂时没有连接成功，请重试。'));
      }
    } finally {
      if (stillCurrent()) {
        // The first turn creates the server conversation. Apply any assignment made while it streamed.
        while (pendingProject.current?.conversationId === current.id) {
          const assignment = pendingProject.current;
          pendingProject.current = null;
          try {
            await api.request(`/api/ai/conversations/${current.id}/`, { method: 'PATCH', body: { project_id: assignment.projectId } });
            if (!stillCurrent()) break;
            serverReady = true;
          } catch (failure) {
            if (stillCurrent()) {
              expireAuth(failure);
              setError(errorMessage(failure, '项目归属暂时保存失败，请重新选择项目。'));
            }
          }
        }
        if (stillCurrent()) {
          updateConversation(previous => ({ ...previous, persisted: serverReady }));
          sendingRef.current = false;
          streaming.current = null;
          setSending(false);
          setCapturing(false);
          textarea.current?.focus();
        }
      }
    }
  }

  const latestAnswer = conversation?.messages.findLast(message => message.role === 'assistant' && message.content.trim());
  const ready = !!botId && !!conversation && !restoring && !botLoading;
  const storageScope = `${session.serverOrigin}:${session.user?.id ?? `unverified-${unknownIdentityScope.current}`}`;
  return <div className="learning-panel">
    <header className="app-header workspace-header">
      <div className="brand"><img src="/unimind_logo_small.png" width="28" height="28" alt="" /><span>小宇</span></div>
      <div className="toolbar-actions">
        <button type="button" className="icon-button" title="新对话" aria-label="新对话" disabled={restoring || !botId} onClick={startNewConversation}><Plus size={18} /></button>
        <button type="button" className="icon-button" title="伴学设置" aria-label="伴学设置" onClick={onSettings}><GearSix size={18} /></button>
      </div>
    </header>
    <section className="context-card" aria-label="当前学习内容">
      <div className="context-heading"><span className={`platform-label ${video?.platform ?? 'generic'}`}>{video?.platform === 'bilibili' ? 'B 站' : video?.platform === 'youtube' ? 'YouTube' : '随身问答'}</span>
        {video && <span className="part-label">P{video.part || 1}</span>}
      </div>
      <h2>{video ? video.title : '通用小宇随身问答'}</h2>
      {!video && <p className="context-hint">打开 B 站或 YouTube 视频即可自动开启随堂画面与讲稿感知</p>}
      <ProjectSelector key={conversation?.id ?? routeKey} api={api} value={conversation?.projectId ?? null}
        onChange={projectId => {
          if (conversationRef.current?.id === conversation?.id) return selectProject(projectId);
        }} disabled={!conversation || restoring} />
    </section>
    <div ref={scroller} className="chat-scroll" aria-label="伴学对话" onScroll={() => {
      const element = scroller.current;
      if (element) keepAtBottom.current = element.scrollHeight - element.scrollTop - element.clientHeight < 100;
    }}>
      {(botLoading || restoring) && <div className="loading-state" role="status"><Spinner size={18} className="spin" />{botLoading ? '正在连接小宇…' : '接续这段视频的学习记录…'}</div>}
      {restoreError && <div className="restore-error" role="alert"><p>{restoreError}</p><button type="button" className="secondary-button" onClick={() => setRestoreRevision(value => value + 1)}>重新读取历史</button><button type="button" className="text-button" onClick={startNewConversation}>开启新对话</button></div>}
      {ready && !conversation.messages.length && <section className="chat-welcome">
        <img src="/unimind_logo_small.png" width="40" height="40" alt="" />
        <h1>小宇</h1>
        <p>{video ? '一起理解这段视频，从一个问题开始。' : '今天，我们要做些什么？'}</p>
        <div className="welcome-prompts">
          {(video ? ['这段内容在讲什么？', '用一个例子解释刚才的概念', '帮我梳理这里的推导过程'] : ['帮我理解一个新概念', '和我一起拆解一道题', '考考我刚学过的知识']).map(prompt =>
            <button type="button" key={prompt} onClick={() => void ask(prompt)}><Sparkle size={16} /><span>{prompt}</span><ArrowUp size={14} /></button>)}
        </div>
      </section>}
      {conversation?.messages.map(message => <article key={message.id} className={`message ${message.role}`} data-native-message={message.role}>
        <div className="message-byline">{message.role === 'assistant' ? <><span className="xiaoyu-dot" />小宇</> : '你'}</div>
        {message.content ? <MarkdownMessage content={message.content} /> : message.role === 'assistant' && sending && <p className="thinking" role="status"><span /><span /><span />{capturing ? '正在看看你学到哪里' : '小宇正在思考'}</p>}
        {message.visuals.filter(visual => visual.type === 'practice_quiz').map((visual, index) =>
          Array.isArray(visual.payload.questions) && visual.payload.practice_id
            ? <PracticeQuizCard key={String(visual.payload.practice_id)} payload={visual.payload as unknown as PracticePayload} api={api} storageScope={storageScope} />
            : <p className="inline-notice" key={index}>这份练习的数据暂不完整，请让小宇重新出题。</p>)}
      </article>)}
      {error && <div className="chat-error" role="alert"><p>{error}</p>{!botId && <button type="button" className="text-button" onClick={() => setBotRevision(value => value + 1)}>重新连接小宇</button>}</div>}
    </div>
    <footer className="composer-area">
      <form className="composer um-agent-composer" onSubmit={event => { event.preventDefault(); void ask(input); }}>
        <textarea ref={textarea} aria-label="向小宇提问" rows={2} value={input} disabled={!ready}
          onChange={event => setInput(event.target.value)} placeholder="和小宇对话，提问当前视频片段…"
          onKeyDown={event => {
            if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
              event.preventDefault();
              if (!sending) void ask(input);
            }
          }} />
        <div className="composer-bottom">
          <QuickActionsBar api={api} onAsk={ask} latestAnswer={latestAnswer?.content} video={video}
            videoSeconds={latestAnswer?.videoSeconds} disabled={!ready || sending} />
          {sending ? <button type="button" className="send-button um-agent-send stop" aria-label="停止生成" title="停止生成" onClick={() => streaming.current?.abort()}><Stop size={16} weight="fill" /></button>
            : <button type="submit" className="send-button um-agent-send" aria-label="发送消息" title="发送消息" disabled={!ready || !input.trim()}><ArrowUp size={20} /></button>}
        </div>
      </form>
    </footer>
  </div>;
}

export function App() {
  const [session, setSession] = useState<ExtensionSession | null>(null);
  const [settings, setSettings] = useState(false);
  const [initialError, setInitialError] = useState('');
  const closeSettings = useCallback(() => setSettings(false), []);
  useEffect(() => {
    let mounted = true;
    let revision = 0;
    function applyAppearance(value: unknown) {
      document.documentElement.classList.toggle('light', value === 'light');
      document.documentElement.classList.toggle('dark', value === 'dark');
    }
    function changed(changes: Record<string, chrome.storage.StorageChange>, area: string) {
      if (area !== 'local' || !changes[APPEARANCE_STORAGE_KEY]) return;
      revision++;
      applyAppearance(changes[APPEARANCE_STORAGE_KEY].newValue);
    }
    chrome.storage.onChanged.addListener(changed);
    void chrome.storage.local.get(APPEARANCE_STORAGE_KEY).then(values => {
      if (mounted && !revision) applyAppearance(values[APPEARANCE_STORAGE_KEY]);
    }).catch(() => undefined);
    return () => { mounted = false; chrome.storage.onChanged.removeListener(changed); };
  }, []);
  useEffect(() => {
    let mounted = true;
    const unsubscribe = subscribeSession(next => { if (mounted) setSession(next); });
    void readSession().then(next => {
      if (!mounted) return;
      setSession(next);
      void syncBrowserAuth().catch(() => undefined);
    }).catch(failure => { if (mounted) setInitialError(errorMessage(failure, '无法读取插件设置。')); });
    return () => { mounted = false; unsubscribe(); };
  }, []);
  useEffect(() => {
    if (!session?.token || session.user) return;
    const controller = new AbortController();
    const identitySession = session;
    void createApiClient(identitySession).request<AuthUser>('/api/users/me/', { signal: controller.signal }).then(user => {
      if (!controller.signal.aborted && user?.id !== undefined) {
        return saveSession({ serverOrigin: identitySession.serverOrigin, user }, identitySession);
      }
    }).catch(failure => {
      if (!controller.signal.aborted && failure instanceof ApiError && failure.status === 401) {
        void saveSession({
          serverOrigin: identitySession.serverOrigin, token: null, tokenSource: null, user: null, botId: null,
        }, identitySession).catch(() => undefined);
      }
    });
    return () => controller.abort();
  }, [session?.serverOrigin, session?.token, session?.tokenSource, session?.user?.id]);
  return <div className={`app-shell${session?.token ? ' um-native-agent' : ' um-auth-shell'}`}>
    {!session?.token && <header className="app-header um-auth-topbar"><div className="um-auth-wordmark">UniMind<span>.ai</span></div>
      <button type="button" className="icon-button" title="伴学设置" aria-label="伴学设置" disabled={!session} onClick={() => setSettings(true)}><GearSix size={18} /></button></header>}
    {!session ? <div className="loading-state" role="status">{initialError || <><Spinner size={18} className="spin" />正在打开伴学空间…</>}</div>
      : session.token ? <LearningPanel key={`${session.serverOrigin}:${session.token}`} session={session} onSettings={() => setSettings(true)} /> : <LoginPanel key={session.serverOrigin} session={session} />}
    {settings && session && <SettingsDrawer session={session} onClose={closeSettings} />}
  </div>;
}
