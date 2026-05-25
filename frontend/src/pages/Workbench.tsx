import { useState, useRef, useEffect, useCallback } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Send, Sparkles, Loader2, RotateCcw, FileQuestion, GraduationCap, Wand2, BookCheck } from 'lucide-react';
import api from '@/lib/api';
import { processMathContent, cn } from '@/lib/utils';
import { useAuthStore } from '@/store/useAuthStore';
import { useSystemStore } from '@/store/useSystemStore';
import { toast } from 'sonner';
import ReactMarkdown from 'react-markdown';
import remarkMath from 'remark-math';
import remarkGfm from 'remark-gfm';
import rehypeKatex from 'rehype-katex';
import QuestionPanel from './workbench/QuestionPanel';

interface Message {
  role: 'user' | 'assistant';
  content: string;
  metadata?: {
    generated_questions?: QuestionData[];
    pipeline_task_id?: number | null;
  };
}

interface Bot {
  id: number;
  name: string;
  avatar: string | null;
  bot_type: string;
}

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

const SUGGESTIONS = [
  { icon: FileQuestion, label: '针对薄弱点出题', message: '根据班级薄弱知识点出题' },
  { icon: GraduationCap, label: '出一套模拟卷', message: '出一套期末模拟卷，30题，难度适中' },
  { icon: Wand2, label: '自定义出题', message: '帮我出10道微积分极限的客观题' },
  { icon: BookCheck, label: '周测出题', message: '出一套周测，15题，覆盖最近学的知识点' },
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
      <div className="h-6 w-6 rounded-full bg-gradient-to-br from-violet-500 to-indigo-500 flex items-center justify-center shrink-0 mt-0.5">
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

export default function Workbench() {
  const { user } = useAuthStore();
  const setPageHeader = useSystemStore(state => state.setPageHeader);
  const [bot, setBot] = useState<Bot | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [isComposing, setIsComposition] = useState(false);
  const [initialized, setInitialized] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const hasConversation = messages.some(m => m.role === 'user');

  // 从 messages 的 metadata 中提取生成的题目和管线 task_id
  const generatedQuestions = messages
    .filter(m => m.role === 'assistant' && m.metadata?.generated_questions?.length)
    .flatMap(m => m.metadata!.generated_questions!);

  const activePipelineTaskId = messages
    .filter(m => m.role === 'assistant' && m.metadata?.pipeline_task_id)
    .map(m => m.metadata!.pipeline_task_id!)
    .pop() || null;

  useEffect(() => {
    setPageHeader('', '');
    return () => setPageHeader('', '');
  }, [setPageHeader]);

  // 初始化：加载 bot 和历史消息
  useEffect(() => {
    const init = async () => {
      try {
        const bRes = await api.get('/ai/bots/');
        const agent = bRes.data.find((b: Bot) => b.name === '出题助手');
        if (agent) {
          setBot(agent);
          const hRes = await api.get('/ai/history/', { params: { bot_id: agent.id } });
          if (hRes.data.length > 0) {
            setMessages(hRes.data.map((m: any) => ({
              ...m,
              content: processMathContent(m.content),
            })));
          }
        }
      } catch {
        toast.error('加载出题助手失败');
      } finally {
        setInitialized(true);
      }
    };
    init();
  }, []);

  // 自动滚动到底部
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, loading]);

  // 轮询等待 AI 回复
  useEffect(() => {
    if (!bot) return;
    const lastMsg = messages[messages.length - 1];
    const needsPolling = lastMsg && (lastMsg.role === 'user' || lastMsg.content === '[Thinking...]');
    if (needsPolling) {
      const timer = setInterval(() => {
        api.get('/ai/history/', { params: { bot_id: bot.id } }).then(res => {
          if (res.data.length > 0) {
            const processed = res.data.map((m: any) => ({
              ...m,
              content: processMathContent(m.content),
            }));
            const newLast = processed[processed.length - 1];
            if (newLast.content !== '[Thinking...]') {
              setMessages(processed);
              setLoading(false);
            } else if (messages.length !== processed.length) {
              setMessages(processed);
            }
          }
        });
      }, 2000);
      return () => clearInterval(timer);
    }
  }, [messages, bot]);

  const doSend = useCallback(async (text: string) => {
    if (!bot) return;
    setLoading(true);
    try {
      await api.post('/ai/chat/', { message: text, bot_id: bot.id });
      const res = await api.get('/ai/history/', { params: { bot_id: bot.id } });
      if (res.data.length > 0) {
        setMessages(res.data.map((m: any) => ({
          ...m,
          content: processMathContent(m.content),
        })));
      }
    } catch {
      toast.error('发送失败，请重试');
      setInput(text);
    } finally {
      setLoading(false);
    }
  }, [bot]);

  const handleSend = useCallback(() => {
    if (!input.trim() || loading || !bot) return;
    const text = input;
    setInput('');
    doSend(text);
  }, [input, loading, bot, doSend]);

  const handleReset = useCallback(async () => {
    if (!bot) return;
    try {
      await api.post('/ai/reset/', { bot_id: bot.id });
      setMessages([]);
      toast.success('会话已清空');
    } catch {
      toast.error('重置失败');
    }
  }, [bot]);

  const handleSuggestion = useCallback((msg: string) => {
    setInput(msg);
    setTimeout(() => inputRef.current?.focus(), 0);
  }, []);

  if (!initialized) {
    return (
      <div className="h-full flex items-center justify-center">
        <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
      </div>
    );
  }

  // ── 空状态 ──
  if (!hasConversation) {
    return (
      <div className="h-full flex flex-col items-center justify-center px-4 pb-20 animate-in fade-in duration-500">
        <div className="w-full max-w-md space-y-5">
          <div className="text-center space-y-1.5">
            <div className="w-12 h-12 rounded-2xl bg-gradient-to-br from-violet-500 to-indigo-500 flex items-center justify-center mx-auto shadow-lg shadow-violet-500/20">
              <Sparkles className="h-6 w-6 text-white" />
            </div>
            <div>
              <h1 className="text-lg font-bold tracking-tight">出题助手</h1>
              <p className="text-muted-foreground text-xs">你的 AI 出题工作台</p>
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
                placeholder="描述你的出题需求..."
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
          </div>

          <div className="flex flex-wrap justify-center gap-1.5">
            {SUGGESTIONS.map(s => (
              <button
                key={s.label}
                onClick={() => handleSuggestion(s.message)}
                className="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg bg-muted/60 hover:bg-muted transition-colors text-[11px] font-medium text-muted-foreground hover:text-foreground"
              >
                <s.icon className="h-3 w-3" />
                {s.label}
              </button>
            ))}
          </div>
        </div>
      </div>
    );
  }

  // ── 对话状态：左侧题目面板 + 右侧聊天 ──
  return (
    <div className="h-full flex animate-in fade-in duration-300">
      {/* 左侧：生成的题目 */}
      <div className="flex-1 min-w-0 h-full">
        <QuestionPanel
          questions={generatedQuestions}
          pipelineTaskId={activePipelineTaskId}
          bot={bot}
        />
      </div>

      {/* 右侧：聊天 */}
      <div className="w-[360px] shrink-0 flex flex-col h-full hidden md:flex">
        {/* Header */}
        <div className="h-11 shrink-0 px-3 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="h-5 w-5 rounded-md bg-gradient-to-br from-violet-500 to-indigo-500 flex items-center justify-center">
              <Sparkles className="h-2.5 w-2.5 text-white" />
            </div>
            <span className="text-xs font-bold">出题助手</span>
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

        {/* Messages */}
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

        {/* Input */}
        <div className="shrink-0 p-2">
          <div className="flex items-center gap-1.5 bg-muted rounded-xl p-1 pr-1.5">
            <Input
              value={input}
              onChange={e => setInput(e.target.value)}
              onCompositionStart={() => setIsComposition(true)}
              onCompositionEnd={() => setIsComposition(false)}
              onKeyDown={e => { if (e.key === 'Enter' && !isComposing) { e.preventDefault(); handleSend(); } }}
              placeholder="描述出题需求..."
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
  );
}
