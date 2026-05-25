import React, { useState, useRef, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { useSystemStore } from '@/store/useSystemStore';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';
import { Send, Sparkles, Loader2, RotateCcw, Lightbulb, BarChart3, Target, FileText, CheckCircle2, CalendarCheck, BookOpen, History } from 'lucide-react';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import api from '@/lib/api';
import { processMathContent, cn } from '@/lib/utils';
import { useAuthStore } from '@/store/useAuthStore';
import { toast } from 'sonner';
import ReactMarkdown from 'react-markdown';
import remarkMath from 'remark-math';
import remarkGfm from 'remark-gfm';
import rehypeKatex from 'rehype-katex';
import { useTypewriter } from '@/hooks/useTypewriter';
import { DashboardPanel, type DashboardData } from './xiaoyu/DashboardPanel';

interface Message {
  role: 'user' | 'assistant';
  content: string;
  timestamp?: string;
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

const SKILLS = [
  { icon: Target, label: '分析薄弱点', prompt: '帮我分析薄弱知识点，给出提升建议', color: 'text-red-500' },
  { icon: CalendarCheck, label: '制定学习计划', prompt: '根据我的现状制定一份学习计划', color: 'text-blue-500' },
  { icon: CheckCircle2, label: '查看复习任务', prompt: '帮我看看今天有哪些需要复习的内容', color: 'text-amber-500' },
  { icon: BarChart3, label: '学习数据总览', prompt: '帮我分析学习数据，看看整体情况', color: 'text-emerald-500' },
  { icon: BookOpen, label: '推荐课程', prompt: '根据我的薄弱点推荐适合的课程', color: 'text-purple-500' },
];

// ── Chat bubble ──
const ChatBubble: React.FC<{
  msg: Message;
  isUser: boolean;
  userName: string;
  isThinking?: boolean;
  index: number;
}> = ({ msg, isUser, userName, isThinking = false, index }) => (
  <div
    className={cn("flex gap-2 w-full", isUser ? "flex-row-reverse" : "flex-row")}
    style={{ animationDelay: `${Math.min(index * 40, 200)}ms` }}
  >
    {!isUser && (
      <div className="h-6 w-6 rounded-full bg-gradient-to-br from-amber-500 to-orange-500 flex items-center justify-center shrink-0 mt-0.5">
        <Sparkles className="h-3 w-3 text-white" />
      </div>
    )}
    <div className={cn("flex flex-col max-w-[85%]", isUser ? "items-end" : "items-start")}>
      <div className={cn(
        "px-3 py-1.5 text-[13px] leading-relaxed w-fit animate-in fade-in slide-in-from-bottom-1 duration-300",
        isUser
          ? "bg-foreground text-background rounded-2xl rounded-tr-md font-medium"
          : "bg-muted text-foreground rounded-2xl rounded-tl-md"
      )}>
        {isThinking ? (
          <div className="flex items-center gap-1 py-0.5">
            <span className="inline-block w-1.5 h-1.5 rounded-full bg-foreground/30 animate-bounce" style={{ animationDelay: '0ms' }} />
            <span className="inline-block w-1.5 h-1.5 rounded-full bg-foreground/30 animate-bounce" style={{ animationDelay: '150ms' }} />
            <span className="inline-block w-1.5 h-1.5 rounded-full bg-foreground/30 animate-bounce" style={{ animationDelay: '300ms' }} />
          </div>
        ) : (
          <div className={cn(
            "prose prose-sm max-w-none text-left",
            "prose-p:my-1 prose-p:leading-relaxed prose-p:text-foreground",
            "prose-strong:text-foreground prose-li:text-foreground",
            "prose-headings:font-bold prose-headings:tracking-tight",
            "prose-table:text-xs prose-table:border-collapse",
            "prose-th:px-2 prose-th:py-1 prose-th:text-left prose-th:font-bold prose-th:bg-muted prose-th:border prose-th:border-border",
            "prose-td:px-2 prose-td:py-1 prose-td:border prose-td:border-border",
            "prose-thead:border-b-2 prose-thead:border-border",
            "prose-code:text-[12px] prose-code:bg-muted prose-code:px-1 prose-code:py-0.5 prose-code:rounded",
            "prose-pre:bg-muted prose-pre:border prose-pre:border-border",
          )}>
            <ReactMarkdown remarkPlugins={[remarkGfm, remarkMath]} rehypePlugins={[rehypeKatex]}>
              {msg.content}
            </ReactMarkdown>
          </div>
        )}
      </div>
    </div>
  </div>
);

export const XiaoYu: React.FC = () => {
  const navigate = useNavigate();
  const { user } = useAuthStore();
  const setPageHeader = useSystemStore(state => state.setPageHeader);
  const [bot, setBot] = useState<Bot | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [isComposing, setIsComposition] = useState(false);
  const [initialized, setInitialized] = useState(false);
  const [dashboard, setDashboard] = useState<DashboardData | null>(null);
  const [skillOpen, setSkillOpen] = useState(false);
  const [sessions, setSessions] = useState<ConversationSession[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<number | null>(null);
  const [sessionOpen, setSessionOpen] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const hasConversation = activeSessionId !== null || messages.some(m => m.role === 'user');

  // Group messages into sessions by time gaps (>30 min = new session)
  const groupIntoSessions = useCallback((allMessages: Message[]): ConversationSession[] => {
    if (allMessages.length === 0) return [];
    const GAP_MS = 30 * 60 * 1000;
    const sessions: ConversationSession[][] = [[]];
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
      '让小宇帮你制定学习计划',
      '让小宇分析薄弱知识点',
      '让小宇推荐适合的课程',
      '让小宇看看复习进度',
    ],
    typingSpeed: 100,
    deletingSpeed: 100,
    pauseDuration: 170,
  });

  useEffect(() => {
    setPageHeader('', '');
    return () => setPageHeader('', '');
  }, [setPageHeader]);

  const fetchDashboard = useCallback(async () => {
    try {
      const res = await api.get('/ai/dashboard/');
      setDashboard(res.data);
    } catch {}
  }, []);

  useEffect(() => {
    const init = async () => {
      try {
        const bRes = await api.get('/ai/bots/');
        const xiaoyu = bRes.data.find((b: Bot) => b.name === '小宇');
        if (xiaoyu) {
          setBot(xiaoyu);
          const hRes = await api.get('/ai/history/', { params: { bot_id: xiaoyu.id } });
          if (hRes.data.length > 0) {
            const allMsgs: Message[] = hRes.data.map((m: any) => ({
              ...m,
              content: processMathContent(m.content),
            }));
            const grouped = groupIntoSessions(allMsgs);
            setSessions(grouped);
            // Auto-show most recent session if within 24h
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
        toast.error('Failed to load XiaoYu');
      } finally {
        setInitialized(true);
      }
    };
    init();
    fetchDashboard();
  }, [fetchDashboard]);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, loading]);

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
    } catch {}
  }, [bot, groupIntoSessions]);

  const doSend = useCallback(async (text: string) => {
    if (!bot) return;
    setLoading(true);

    // Start a new session if needed
    if (activeSessionId === null) {
      setActiveSessionId(0); // temporary ID until refresh
    }

    // Add user message immediately
    const userMsg: Message = { role: 'user', content: text, timestamp: new Date().toISOString() };
    setMessages(prev => [...prev, userMsg]);

    // Add thinking indicator
    const thinkingMsg: Message = { role: 'assistant', content: '[Thinking...]' };
    setMessages(prev => [...prev, thinkingMsg]);

    try {
      const res = await fetch('/api/ai/chat/stream/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ message: text, bot_id: bot.id }),
      });

      if (!res.ok) throw new Error(`HTTP ${res.status}`);

      const reader = res.body?.getReader();
      if (!reader) throw new Error('Stream not available');

      const decoder = new TextDecoder();
      let collected = '';
      let leftover = '';

      // Remove thinking indicator
      setMessages(prev => prev.filter(m => m.content !== '[Thinking...]' || m.role !== 'assistant'));

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
            if (payload.done) {
              // Finalize: update existing message with processed content
              if (collected) {
                setMessages(prev => {
                  const msgs = [...prev];
                  const lastIdx = msgs.length - 1;
                  if (lastIdx >= 0 && msgs[lastIdx].role === 'assistant') {
                    msgs[lastIdx] = { ...msgs[lastIdx], content: processMathContent(collected) };
                  }
                  return msgs;
                });
              }
              fetchDashboard();
              handleRefreshSessions();
            } else if (payload.token) {
              collected += payload.token;
              // Update streaming message in real-time
              setMessages(prev => {
                const msgs = [...prev];
                const lastIdx = msgs.length - 1;
                if (lastIdx >= 0 && msgs[lastIdx].role === 'assistant') {
                  msgs[lastIdx] = { ...msgs[lastIdx], content: collected };
                } else {
                  msgs.push({ role: 'assistant', content: collected });
                }
                return msgs;
              });
            } else if (payload.error) {
              toast.error(payload.error);
            }
          } catch { /* skip malformed lines */ }
        }
      }
    } catch (err: any) {
      const msg = err?.message || '发送失败，请重试';
      toast.error(msg.includes('HTTP') ? '服务暂时不可用，请稍后再试' : '发送失败，请重试');
      setInput(text);
      setMessages(prev => prev.filter(m => m.content !== '[Thinking...]' || m.role !== 'assistant'));
    } finally {
      setLoading(false);
    }
  }, [bot, activeSessionId, fetchDashboard, handleRefreshSessions]);

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
        <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
      </div>
    );
  }

  // ── Empty state ──
  if (!hasConversation) {
    return (
      <TooltipProvider delayDuration={300}>
        <div className="h-full flex flex-col items-center justify-center px-4 pb-20 animate-in fade-in duration-500">
          <div className="w-full max-w-md space-y-5">
            <div className="text-center space-y-1.5">
              <div className="w-12 h-12 rounded-2xl bg-gradient-to-br from-amber-500 to-orange-500 flex items-center justify-center mx-auto shadow-lg shadow-amber-500/20">
                <Sparkles className="h-6 w-6 text-white" />
              </div>
              <div>
                <h1 className="text-lg font-bold tracking-tight">你好，我是小宇</h1>
                <p className="text-muted-foreground text-xs">帮你搞定一切的专属 AI 学习规划师</p>
              </div>
            </div>

            <div className="relative">
              <div className="flex items-center gap-2 bg-card rounded-xl p-1.5 border border-border shadow-sm focus-within:shadow-md focus-within:border-primary/20 transition-all duration-200">
                <Input
                  ref={inputRef}
                  value={input}
                  onChange={e => setInput(e.target.value)}
                  onCompositionStart={() => setIsComposition(true)}
                  onCompositionEnd={() => setIsComposition(false)}
                  onKeyDown={e => { if (e.key === 'Enter' && !isComposing) { e.preventDefault(); handleSend(); } }}
                  placeholder={placeholder}
                  autoComplete="off"
                  className="bg-transparent border-none shadow-none focus-visible:ring-0 text-sm h-9 px-3 font-medium placeholder:text-muted-foreground/60"
                  disabled={loading}
                />
                <Button
                  onClick={handleSend}
                  disabled={loading || !input.trim()}
                  size="icon"
                  className="rounded-lg h-9 w-9 bg-foreground text-background shadow-sm active:scale-95 transition-all shrink-0 hover:opacity-90"
                >
                  {loading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Send className="h-3.5 w-3.5" />}
                </Button>
              </div>

              {/* Bottom-left icon buttons */}
              <div className="flex items-center gap-0.5 mt-1.5 ml-0.5">
                {sessions.length > 0 && (
                  <Popover open={sessionOpen} onOpenChange={setSessionOpen}>
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <PopoverTrigger asChild>
                          <button className="p-1 rounded-md transition-colors text-muted-foreground hover:text-foreground hover:bg-muted/60">
                            <History className="h-3.5 w-3.5" />
                          </button>
                        </PopoverTrigger>
                      </TooltipTrigger>
                      <TooltipContent side="bottom" className="text-[11px] font-medium">
                        历史对话 ({sessions.length})
                      </TooltipContent>
                    </Tooltip>
                    <PopoverContent align="start" side="top" className="w-64 p-1.5 rounded-xl border-border shadow-lg max-h-60 overflow-y-auto">
                      <div className="space-y-0.5">
                        {[...sessions].reverse().map(session => (
                          <button
                            key={session.id}
                            onClick={() => handleLoadSession(session)}
                            className="w-full flex flex-col gap-0.5 px-2.5 py-2 rounded-lg hover:bg-muted transition-colors text-left"
                          >
                            <span className="text-xs font-medium truncate">{session.label}</span>
                            <span className="text-[10px] text-muted-foreground">
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
                        <button
                          className={cn(
                            "p-1 rounded-md transition-colors",
                            skillOpen
                              ? "bg-amber-50 text-amber-600"
                              : "text-muted-foreground hover:text-foreground hover:bg-muted/60"
                          )}
                        >
                          <Lightbulb className="h-3.5 w-3.5" />
                        </button>
                      </PopoverTrigger>
                    </TooltipTrigger>
                    <TooltipContent side="bottom" className="text-[11px] font-medium">
                      技能
                    </TooltipContent>
                  </Tooltip>
                  <PopoverContent
                    align="start"
                    side="top"
                    className="w-52 p-1.5 rounded-xl border-border shadow-lg"
                  >
                    <div className="space-y-0.5">
                      {SKILLS.map(skill => (
                        <button
                          key={skill.label}
                          onClick={() => handleSkillSelect(skill.prompt)}
                          className="w-full flex items-center gap-2 px-2.5 py-2 rounded-lg hover:bg-muted transition-colors text-left"
                        >
                          <skill.icon className={cn("h-3.5 w-3.5 shrink-0", skill.color)} />
                          <span className="text-xs font-medium">{skill.label}</span>
                        </button>
                      ))}
                    </div>
                  </PopoverContent>
                </Popover>
              </div>
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
          <DashboardPanel data={dashboard} onRefresh={fetchDashboard} />
        </div>

        <div className="w-[360px] shrink-0 flex flex-col h-full hidden md:flex">
          <div className="h-11 shrink-0 px-3 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <div className="h-5 w-5 rounded-md bg-gradient-to-br from-amber-500 to-orange-500 flex items-center justify-center">
                <Sparkles className="h-2.5 w-2.5 text-white" />
              </div>
              <span className="text-xs font-bold">小宇</span>
              {sessions.length > 1 && (
                <Popover open={sessionOpen} onOpenChange={setSessionOpen}>
                  <PopoverTrigger asChild>
                    <button className="text-[10px] text-muted-foreground hover:text-foreground transition-colors">
                      ({sessions.length} 个对话)
                    </button>
                  </PopoverTrigger>
                  <PopoverContent align="start" side="bottom" className="w-64 p-1.5 rounded-xl border-border shadow-lg max-h-60 overflow-y-auto">
                    <div className="space-y-0.5">
                      {[...sessions].reverse().map(session => (
                        <button
                          key={session.id}
                          onClick={() => { handleLoadSession(session); setSessionOpen(false); }}
                          className={cn(
                            "w-full flex flex-col gap-0.5 px-2.5 py-2 rounded-lg transition-colors text-left",
                            session.id === activeSessionId ? "bg-muted" : "hover:bg-muted"
                          )}
                        >
                          <span className="text-xs font-medium truncate">{session.label}</span>
                          <span className="text-[10px] text-muted-foreground">
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
              className="rounded-md text-muted-foreground hover:text-foreground gap-1 px-2 h-6"
            >
              <RotateCcw className="h-2.5 w-2.5" />
              <span className="text-[10px] font-semibold">新对话</span>
            </Button>
          </div>

          <div ref={scrollRef} className="flex-1 overflow-y-auto min-h-0">
            <div className="p-3 space-y-3">
              {messages.filter(m => m.content !== '[Thinking...]').map((msg, i) => (
                <ChatBubble
                  key={i}
                  msg={msg}
                  isUser={msg.role === 'user'}
                  userName={user?.nickname || user?.username || 'User'}
                  index={i}
                />
              ))}
              {messages.length > 0 && messages[messages.length - 1].content === '[Thinking...]' && (
                <ChatBubble
                  msg={{ role: 'assistant', content: '' }}
                  isUser={false}
                  userName=""
                  isThinking
                  index={messages.length}
                />
              )}
            </div>
          </div>

          <div className="shrink-0 p-2">
            <div className="flex items-center gap-0.5 mb-1 ml-0.5">
              <Popover open={skillOpen} onOpenChange={setSkillOpen}>
                <Tooltip>
                  <TooltipTrigger asChild>
                    <PopoverTrigger asChild>
                      <button
                        className={cn(
                          "p-1 rounded-md transition-colors",
                          skillOpen
                            ? "bg-amber-50 text-amber-600"
                            : "text-muted-foreground hover:text-foreground"
                        )}
                      >
                        <Lightbulb className="h-3 w-3" />
                      </button>
                    </PopoverTrigger>
                  </TooltipTrigger>
                  <TooltipContent side="top" className="text-[11px] font-medium">
                    技能
                  </TooltipContent>
                </Tooltip>
                <PopoverContent
                  align="start"
                  side="top"
                  className="w-52 p-1.5 rounded-xl border-border shadow-lg"
                >
                  <div className="space-y-0.5">
                    {SKILLS.map(skill => (
                      <button
                        key={skill.label}
                        onClick={() => handleSkillSelect(skill.prompt)}
                        className="w-full flex items-center gap-2 px-2.5 py-2 rounded-lg hover:bg-muted transition-colors text-left"
                      >
                        <skill.icon className={cn("h-3.5 w-3.5 shrink-0", skill.color)} />
                        <span className="text-xs font-medium">{skill.label}</span>
                      </button>
                    ))}
                  </div>
                </PopoverContent>
              </Popover>
            </div>

            <div className="flex items-center gap-1.5 bg-muted rounded-xl p-1 pr-1.5">
              <Input
                value={input}
                onChange={e => setInput(e.target.value)}
                onCompositionStart={() => setIsComposition(true)}
                onCompositionEnd={() => setIsComposition(false)}
                onKeyDown={e => { if (e.key === 'Enter' && !isComposing) { e.preventDefault(); handleSend(); } }}
                placeholder="和小宇对话..."
                autoComplete="off"
                className="bg-transparent border-none shadow-none focus-visible:ring-0 text-[13px] h-8 px-3 font-medium placeholder:text-muted-foreground/50"
                disabled={loading}
              />
              <Button
                onClick={handleSend}
                disabled={loading || !input.trim()}
                size="icon"
                className="rounded-lg h-8 w-8 bg-foreground text-background shadow-sm active:scale-95 transition-all shrink-0"
              >
                <Send className="h-3.5 w-3.5" />
              </Button>
            </div>
          </div>
        </div>
      </div>
    </TooltipProvider>
  );
};

export default XiaoYu;
