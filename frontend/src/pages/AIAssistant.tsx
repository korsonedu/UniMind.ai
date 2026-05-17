import React, { useState, useRef, useEffect } from 'react';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Send, Sparkles, Loader2, Eraser } from 'lucide-react';
import api from '@/lib/api';
import { processMathContent } from '@/lib/utils';
import { cn } from '@/lib/utils';
import { useAuthStore } from '@/store/useAuthStore';
import { toast } from 'sonner';
import { PageWrapper } from '@/components/PageWrapper';
import { PointsConfirmDialog } from '@/components/PointsConfirmDialog';

// Modularized Components
import { BotSelector } from './ai-assistant/BotSelector';
import { ChatMessage } from './ai-assistant/ChatMessage';

interface Message {
  role: 'user' | 'assistant';
  content: string;
}

interface Bot {
  id: number;
  name: string;
  avatar: string;
  system_prompt: string;
}

export const AIAssistant: React.FC = () => {
  const { user } = useAuthStore();
  const [bots, setBots] = useState<Bot[]>([]);
  const [selectedBot, setSelectedBot] = useState<Bot | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [isInitialLoading, setIsInitialLoading] = useState(true);
  const [isComposing, setIsComposition] = useState(false);
  const [showPointsConfirm, setShowPointsConfirm] = useState(false);
  const [pendingMessage, setPendingMessage] = useState('');
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const init = async () => {
      try {
        const bRes = await api.get('/ai/bots/');
        setBots(bRes.data);
        const savedBotId = sessionStorage.getItem('last_selected_bot_id');
        if (savedBotId) {
          const savedBot = bRes.data.find((b: Bot) => b.id.toString() === savedBotId);
          if (savedBot) setSelectedBot(savedBot);
        }
      } catch (e: any) {
        toast.error("加载助教列表失败");
      } finally {
        setIsInitialLoading(false);
      }
    };
    init();
  }, []);

  useEffect(() => {
    if (selectedBot) {
      sessionStorage.setItem('last_selected_bot_id', selectedBot.id.toString());
      api.get('/ai/history/', { params: { bot_id: selectedBot.id } }).then(res => {
        if (res.data.length > 0) {
          setMessages(res.data.map((m: any) => ({
            ...m,
            content: processMathContent(m.content)
          })));
        } else {
          setMessages([{ role: 'assistant', content: `你好！我是${selectedBot.name}。开始我们的学术交流吧！` }]);
        }
      }).catch(e => { toast.error("加载历史失败"); });
    }
  }, [selectedBot]);

  useEffect(() => {
    if (scrollRef.current) {
      const viewport = scrollRef.current.querySelector('[data-radix-scroll-area-viewport]');
      if (viewport) viewport.scrollTop = viewport.scrollHeight;
    }
  }, [messages, loading]);

  useEffect(() => {
    if (!selectedBot) return;
    const lastMsg = messages[messages.length - 1];
    const needsPolling = lastMsg && (lastMsg.role === 'user' || lastMsg.content === '[Thinking...]');
    if (needsPolling) {
      const timer = setInterval(() => {
        api.get('/ai/history/', { params: { bot_id: selectedBot.id } }).then(res => {
          if (res.data.length > 0) {
            const processedHistory = res.data.map((m: any) => ({
              ...m,
              content: processMathContent(m.content)
            }));
            const newLastMsg = processedHistory[processedHistory.length - 1];
            if (newLastMsg.content !== '[Thinking...]') {
               setMessages(processedHistory);
               setLoading(false);
            } else if (messages.length !== processedHistory.length) {
               setMessages(processedHistory);
            }
          }
        });
      }, 2000);
      return () => clearInterval(timer);
    }
  }, [messages, selectedBot]);

  const doSend = async (text: string) => {
    setLoading(true);
    try {
      await api.post('/ai/chat/', { message: text, bot_id: selectedBot!.id });
      const res = await api.get('/ai/history/', { params: { bot_id: selectedBot!.id } });
      if (res.data.length > 0) {
        setMessages(res.data.map((m: any) => ({ ...m, content: processMathContent(m.content) })));
      }
    } catch (err: any) {
      // 402 积分不足 由 api 拦截器处理 toast
      if (err.response?.status !== 402) {
        toast.error("发送失败");
      }
      setInput(text);
    } finally {
      setLoading(false);
    }
  };

  const handleSend = async () => {
    if (!selectedBot) return toast.error("请选择 AI 助教");
    if (!input.trim() || loading) return;
    const text = input;
    setInput('');
    setPendingMessage(text);
    setShowPointsConfirm(true);
  };

  const handleReset = async () => {
    if (!selectedBot) return;
    try {
      await api.post('/ai/reset/', { bot_id: selectedBot.id });
      setMessages([{ role: 'assistant', content: '会话历史已清空。' }]);
      toast.success("会话已重置");
    } catch (e) { toast.error("重置失败"); }
  };

  if (isInitialLoading) return (
    <PageWrapper title="AI 实验室" subtitle="与您的专属数字导师进行深度学术对话。">
      <div className="h-[calc(100vh-6.5rem)] flex flex-col items-center justify-center gap-4 opacity-20">
        <Loader2 className="h-8 w-8 animate-spin text-foreground" />
        <p className="text-[11px] font-bold uppercase tracking-widest text-foreground">Initializing AI Laboratory...</p>
      </div>
    </PageWrapper>
  );

  return (
    <PageWrapper title="AI 实验室" subtitle="与您的专属数字导师进行深度学术对话。">
      <div className="h-[calc(100vh-6.5rem)] flex flex-col animate-in fade-in duration-300 max-w-5xl mx-auto text-left relative text-foreground px-4">
        <Card className="flex-1 flex flex-col bg-card rounded-3xl shadow-sm border border-border overflow-hidden relative">
          <header className="px-8 py-3 border-b border-border flex items-center justify-between bg-card/80 backdrop-blur-md sticky top-0 z-10">
            <BotSelector bots={bots} selectedBot={selectedBot} onSelect={setSelectedBot} />
            {selectedBot && (
              <Button variant="ghost" size="sm" onClick={handleReset} className="rounded-xl text-muted-foreground hover:text-foreground gap-2 px-3 h-8">
                <Eraser className="w-3.5 h-3.5" />
                <span className="text-[11px] font-bold uppercase">Clear History</span>
              </Button>
            )}
          </header>

          <ScrollArea className="flex-1" ref={scrollRef}>
            {!selectedBot ? (
              <div className="h-full flex flex-col items-center justify-center p-8 text-center space-y-6">
                <div className="h-20 w-20 rounded-3xl bg-muted flex items-center justify-center animate-bounce"><Sparkles className="h-10 w-10 text-primary opacity-20" /></div>
                <div className="space-y-2">
                  <h3 className="text-lg font-bold">Welcome to AI Laboratory</h3>
                  <p className="text-sm text-muted-foreground font-medium">Please select an AI assistant to begin.</p>
                </div>
              </div>
            ) : (
              <div className="p-8 space-y-8 max-w-4xl mx-auto w-full">
                {messages.filter(msg => msg.content !== '[Thinking...]').map((msg, i) => (
                  <ChatMessage 
                    key={i} 
                    msg={msg} 
                    isUser={msg.role === 'user'} 
                    avatar={selectedBot.avatar} 
                    botName={selectedBot.name} 
                    userName={user?.nickname || user?.username || 'User'} 
                  />
                ))}
                {messages.length > 0 && messages[messages.length - 1].content === '[Thinking...]' && (
                  <ChatMessage 
                    msg={{ role: 'assistant', content: '' }} 
                    isUser={false} 
                    avatar={selectedBot.avatar} 
                    botName={selectedBot.name} 
                    userName="" 
                    isThinking 
                  />
                )}
              </div>
            )}
          </ScrollArea>

          <footer className="p-4 bg-card/80 backdrop-blur-md border-t border-border z-20">
            <div className={cn("max-w-4xl mx-auto flex gap-3 bg-muted rounded-2xl p-1.5 pr-2 transition-all shadow-inner border border-border", !selectedBot && "opacity-50 grayscale pointer-events-none")}>
              <Input 
                value={input}
                onChange={e => setInput(e.target.value)}
                onCompositionStart={() => setIsComposition(true)}
                onCompositionEnd={() => setIsComposition(false)}
                onKeyDown={e => { if (e.key === 'Enter' && !isComposing) { e.preventDefault(); handleSend(); } }}
                placeholder={selectedBot ? "Ask a question..." : "Select an assistant first"} 
                className="bg-transparent border-none shadow-none focus-visible:ring-0 text-[13px] h-9 px-4 font-medium" 
                disabled={loading || !selectedBot}
              />
              <Button onClick={handleSend} disabled={loading || !input.trim() || !selectedBot} size="icon" className="rounded-xl h-9 w-9 bg-primary text-primary-foreground shadow-xl active:scale-95 transition-all shrink-0"><Send className="h-3.5 w-3.5" /></Button>
            </div>
          </footer>
        </Card>
      </div>
      <PointsConfirmDialog
        open={showPointsConfirm}
        onOpenChange={setShowPointsConfirm}
        cost={8}
        featureName="AI 助教对话"
        balance={user?.elo_points ?? 0}
        onConfirm={() => {
          setShowPointsConfirm(false);
          doSend(pendingMessage);
        }}
        loading={loading}
      />
    </PageWrapper>
  );
};
