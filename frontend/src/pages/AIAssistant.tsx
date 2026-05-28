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
import { useTranslation } from 'react-i18next';

// Agent integration
import { useAgentChat } from '@/hooks/useAgentChat';
import { AgentStepCard } from '@/components/AgentStepCard';

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
  bot_type?: string;
}

const AGENT_BOT_TYPES = ['exam_generator', 'planner'];
const isAgentBot = (bot: Bot) => !!bot.bot_type && AGENT_BOT_TYPES.includes(bot.bot_type);

export const AIAssistant: React.FC = () => {
  const { user } = useAuthStore();
  const { t } = useTranslation('aiAssistant');
  const [bots, setBots] = useState<Bot[]>([]);
  const [selectedBot, setSelectedBot] = useState<Bot | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [isInitialLoading, setIsInitialLoading] = useState(true);
  const [isComposing, setIsComposition] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const agentChat = useAgentChat(selectedBot?.id || 0);
  const messagesRef = useRef(messages);
  useEffect(() => { messagesRef.current = messages; }, [messages]);

  useEffect(() => {
    const init = async () => {
      try {
        const bRes = await api.get('/ai/bots/');
        // Filter out XiaoYu — it's now an independent agent at /xiaoyu
        const filteredBots = bRes.data.filter((b: Bot) => b.name !== '小宇');
        setBots(filteredBots);
        const savedBotId = sessionStorage.getItem('last_selected_bot_id');
        if (savedBotId) {
          const savedBot = filteredBots.find((b: Bot) => b.id.toString() === savedBotId);
          if (savedBot) setSelectedBot(savedBot);
        }
      } catch (e: any) {
        toast.error(t('loadBotsFailed'));
      } finally {
        setIsInitialLoading(false);
      }
    };
    init();
  }, []);

  useEffect(() => {
    if (selectedBot) {
      agentChat.reset();
      sessionStorage.setItem('last_selected_bot_id', selectedBot.id.toString());
      api.get('/ai/history/', { params: { bot_id: selectedBot.id } }).then(res => {
        if (res.data.length > 0) {
          setMessages(res.data.map((m: any) => ({
            ...m,
            content: processMathContent(m.content)
          })));
        } else {
          setMessages([{ role: 'assistant', content: t('welcomeMessage', { botName: selectedBot.name }) }]);
        }
      }).catch(() => { toast.error(t('loadHistoryFailed')); });
    }
  }, [selectedBot]);

  useEffect(() => {
    if (scrollRef.current) {
      const viewport = scrollRef.current.querySelector('[data-radix-scroll-area-viewport]');
      if (viewport) viewport.scrollTop = viewport.scrollHeight;
    }
  }, [messages, loading]);

  useEffect(() => {
    if (!selectedBot || isAgentBot(selectedBot)) return;
    const lastMsg = messagesRef.current[messagesRef.current.length - 1];
    const needsPolling = lastMsg && (lastMsg.role === 'user' || lastMsg.content === '[Thinking...]');
    if (!needsPolling) return;

    const timer = setInterval(() => {
      api.get('/ai/history/', { params: { bot_id: selectedBot.id } }).then(res => {
        if (res.data.length > 0) {
          const processedHistory = res.data.map((m: any) => ({
            ...m,
            content: processMathContent(m.content)
          }));
          const newLastMsg = processedHistory[processedHistory.length - 1];
          const currentMessages = messagesRef.current;
          if (newLastMsg.content !== '[Thinking...]') {
             setMessages(processedHistory);
             setLoading(false);
          } else if (currentMessages.length !== processedHistory.length) {
             setMessages(processedHistory);
          }
        }
      });
    }, 2000);
    return () => clearInterval(timer);
  }, [selectedBot]);

  useEffect(() => {
    if (agentChat.isDone && agentChat.streamingText) {
      setMessages(prev => [...prev, {
        role: 'assistant' as const,
        content: processMathContent(agentChat.streamingText),
      }]);
      const timer = setTimeout(() => agentChat.reset(), 500);
      return () => clearTimeout(timer);
    }
  }, [agentChat.isDone, agentChat.streamingText]);

  useEffect(() => {
    if (agentChat.error) {
      toast.error(agentChat.error);
    }
  }, [agentChat.error]);

  const doSend = async (text: string) => {
    // Agent bots (exam_generator, planner) use WebSocket mode
    if (selectedBot && isAgentBot(selectedBot)) {
      setMessages(prev => [...prev, { role: 'user', content: text }]);
      agentChat.sendMessage(text);
      return;
    }

    // Other bots: existing polling mode
    setLoading(true);
    try {
      await api.post('/ai/chat/', { message: text, bot_id: selectedBot!.id });
      const res = await api.get('/ai/history/', { params: { bot_id: selectedBot!.id } });
      if (res.data.length > 0) {
        setMessages(res.data.map((m: any) => ({ ...m, content: processMathContent(m.content) })));
      }
    } catch (err: any) {
      toast.error(t('sendFailed'));
      setInput(text);
    } finally {
      setLoading(false);
    }
  };

  const handleSend = async () => {
    if (!selectedBot) return toast.error(t('selectBotFirst'));
    if (!input.trim() || loading) return;
    const text = input;
    setInput('');
    doSend(text);
  };

  const handleReset = async () => {
    if (!selectedBot) return;
    try {
      await api.post('/ai/reset/', { bot_id: selectedBot.id });
      setMessages([{ role: 'assistant', content: t('sessionCleared') }]);
      toast.success(t('sessionReset'));
    } catch (e) { toast.error(t('resetFailed')); }
  };

  if (isInitialLoading) return (
    <PageWrapper title={t('pageTitle')} subtitle={t('pageSubtitle')}>
      <div className="h-[calc(100vh-6.5rem)] flex flex-col items-center justify-center gap-4 opacity-20">
        <Loader2 className="h-8 w-8 animate-spin text-foreground" />
        <p className="text-[11px] font-bold uppercase tracking-widest text-foreground">Initializing AI Laboratory...</p>
      </div>
    </PageWrapper>
  );

  return (
    <PageWrapper title={t('pageTitle')} subtitle={t('pageSubtitle')}>
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
                {/* Agent mode: show step cards + streaming text */}
                {agentChat.steps.length > 0 && (
                  <div className="space-y-3">
                    {agentChat.steps.map(step => (
                      <AgentStepCard key={step.call_id} step={step} />
                    ))}
                  </div>
                )}
                {agentChat.streamingText && (
                  <ChatMessage
                    msg={{ role: 'assistant', content: agentChat.streamingText }}
                    isUser={false}
                    avatar={selectedBot.avatar}
                    botName={selectedBot.name}
                    userName=""
                  />
                )}

                {/* History messages (after agent done, final message appears here) */}
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
                {/* Thinking indicator (non-agent mode only) */}
                {agentChat.steps.length === 0 && messages.length > 0 && messages[messages.length - 1].content === '[Thinking...]' && (
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
                autoComplete="off"
                className="bg-transparent border-none shadow-none focus-visible:ring-0 text-[13px] h-9 px-4 font-medium"
                disabled={(loading || agentChat.isConnected) || !selectedBot}
              />
              <Button onClick={handleSend} disabled={(loading || agentChat.isConnected) || !input.trim() || !selectedBot} size="icon" className="rounded-xl h-9 w-9 bg-primary text-primary-foreground shadow active:scale-95 transition-[transform,colors] shrink-0" aria-label="Send message"><Send className="h-3.5 w-3.5" /></Button>
            </div>
          </footer>
        </Card>
      </div>
    </PageWrapper>
  );
};
