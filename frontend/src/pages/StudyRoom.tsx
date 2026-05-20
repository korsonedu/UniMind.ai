import React, { useState, useEffect, useRef } from 'react';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { 
  Send, Users, MessageSquare, Play, Pause, 
  RotateCcw, CheckCircle2, MoreHorizontal, 
  Plus, Zap, Timer, XCircle, ListTodo, Circle,
  Trophy, Clock, Radio, Eye, Smile, Image as ImageIcon, Camera,
  FileVideo, ArrowDown, Loader2, Calendar, Trash2
} from 'lucide-react';
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar';
import { cn } from '@/lib/utils';
import { useAuthStore } from '@/store/useAuthStore';
import { useSystemStore } from '@/store/useSystemStore';
import api from '@/lib/api';
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import {
  HoverCard,
  HoverCardContent,
  HoverCardTrigger,
} from "@/components/ui/hover-card";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { toast } from "sonner";
import { useTranslation } from 'react-i18next';
import { Slider } from "@/components/ui/slider";
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";
import { Badge } from '@/components/ui/badge';
import { processMathContent } from '@/lib/utils';
import ReactMarkdown from 'react-markdown';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import 'katex/dist/katex.min.css';

interface Message {
  id: number;
  user_detail: { username: string; nickname: string; avatar_url: string; role: string; };
  content: string;
  timestamp: string;
  related_plan?: number;
}

interface Plan { id: number; content: string; is_completed: boolean; }

const remarkSoftBreaks = () => {
  const skipTypes = new Set(['code', 'inlineCode', 'math', 'inlineMath', 'html']);

  const walk = (node: any) => {
    if (!node || skipTypes.has(node.type) || !Array.isArray(node.children)) return;

    const nextChildren: any[] = [];
    node.children.forEach((child: any) => {
      if (child?.type === 'text' && typeof child.value === 'string' && child.value.includes('\n')) {
        const normalizedValue = child.value.replace(/\r\n?/g, '\n');
        const lines = normalizedValue.split('\n');
        lines.forEach((line: string, index: number) => {
          if (line) {
            nextChildren.push({ ...child, value: line });
          }
          if (index < lines.length - 1) {
            nextChildren.push({ type: 'break' });
          }
        });
        return;
      }

      walk(child);
      nextChildren.push(child);
    });

    node.children = nextChildren;
  };

  return (tree: any) => {
    walk(tree);
  };
};

export const StudyRoom: React.FC = () => {
  const { user, updateUser } = useAuthStore();
  const { setPageHeader } = useSystemStore();
  const { t } = useTranslation('studyRoom');
  const [timeLeft, setTimeLeft] = useState(25 * 60);

  useEffect(() => {
    setPageHeader(t('pageTitle'), t('pageSubtitle'));
  }, [setPageHeader, t]);

  const [isActive, setIsActive] = useState(false);
  const [activePlanId, setActivePlanId] = useState<number | null>(null);
  const [duration, setDuration] = useState(25);
  const [taskName, setTaskName] = useState(t('deepFocus'));
  const [onlineUsers, setOnlineUsers] = useState<any[]>([]);
  const [messages, setMessages] = useState<Message[]>([]);
  const [plans, setPlans] = useState<Plan[]>([]);
  const [newPlan, setNewPlan] = useState('');
  const [chatInput, setChatInput] = useState('');
  const [showStopAlert, setShowStopAlert] = useState(false);
  const [isTimerOpen, setIsTimerOpen] = useState(false);
  const [isMobile, setIsMobile] = useState(false);
  const [showMobileTimerSetup, setShowMobileTimerSetup] = useState(false);
  const [showMobileTimerFullscreen, setShowMobileTimerFullscreen] = useState(false);
  const [isAtBottom, setIsAtBottom] = useState(true);
  const [isComposing, setIsComposing] = useState(false);
  const [giphySearch, setGiphySearch] = useState('');
  const [giphyResults, setGiphyResults] = useState<any[]>([]);
  const [isGiphyLoading, setIsGiphyLoading] = useState(false);
  const [isDragging, setIsDragging] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const cameraInputRef = useRef<HTMLInputElement>(null);
  const chatTextareaRef = useRef<HTMLTextAreaElement>(null);
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const lastMessageIdRef = useRef<number | null>(null);
  const isActiveRef = useRef<boolean>(false);
  const taskNameRef = useRef<string>('');
  const timeLeftRef = useRef<number>(25 * 60);
  
  const [allowBroadcast, setAllowBroadcast] = useState(user?.allow_broadcast ?? true);
  const [showOthersBroadcast, setShowOthersBroadcast] = useState(user?.show_others_broadcast ?? true);

  const updateSettings = async (field: string, val: boolean) => {
    try {
      await api.patch('/users/me/update/', { [field]: val });
      if (field === 'allow_broadcast') setAllowBroadcast(val);
      if (field === 'show_others_broadcast') setShowOthersBroadcast(val);
      updateUser({ ...user, [field]: val } as any);
      toast.success(t('preferencesUpdated'));
    } catch (e) { toast.error(t('updateFailed')); }
  };

  const fetchOnline = async () => { try { const res = await api.get('/users/online/'); setOnlineUsers(res.data); } catch (e) { console.error('fetchOnline failed', e); } };
  const fetchMessages = async () => { try { const res = await api.get('/study/messages/'); setMessages(res.data); } catch (e) { console.error('fetchMessages failed', e); } };
  const fetchPlans = async () => { try { const res = await api.get('/users/plans/'); setPlans(res.data); } catch (e) { console.error('fetchPlans failed', e); } };

  const resizeChatTextarea = () => {
    const el = chatTextareaRef.current;
    if (!el) return;
    if (isMobile) {
      el.style.height = '40px';
      el.style.overflowY = 'auto';
      return;
    }
    el.style.height = 'auto';
    const maxHeight = 128;
    const nextHeight = Math.min(el.scrollHeight, maxHeight);
    el.style.height = `${nextHeight}px`;
    el.style.overflowY = el.scrollHeight > maxHeight ? 'auto' : 'hidden';
  };

  const isTaskStateMessage = (content: string) => (
    content.includes('💪')
    || content.includes('✅')
    || content.includes('❌')
    || content.includes('📅')
  );

  const undoMessage = async (messageId: number) => {
    try {
      await api.post(`/study/messages/${messageId}/undo/`);
      toast.success(t('undoSuccess'));
      fetchMessages();
      fetchPlans();
    } catch (e: any) {
      toast.error(e?.response?.data?.error || t('undoFailed'));
    }
  };

  const getHeartbeatPayload = () => {
    if (isActiveRef.current) {
      return {
        current_task: taskNameRef.current.trim() || t('deepFocus'),
        current_timer_end: new Date(Date.now() + Math.max(timeLeftRef.current, 0) * 1000).toISOString(),
      };
    }
    return {
      current_task: null,
      current_timer_end: null,
    };
  };

  const sendHeartbeat = async (override?: { current_task?: string | null; current_timer_end?: string | null }) => {
    try {
      await api.post('/users/heartbeat/', {
        ...getHeartbeatPayload(),
        ...(override || {}),
      });
    } catch (e) {}
  };

  useEffect(() => {
    isActiveRef.current = isActive;
  }, [isActive]);

  useEffect(() => {
    taskNameRef.current = taskName;
  }, [taskName]);

  useEffect(() => {
    timeLeftRef.current = timeLeft;
  }, [timeLeft]);

  useEffect(() => {
    fetchOnline();
    fetchMessages();
    fetchPlans();
    sendHeartbeat();

    const syncInterval = setInterval(() => {
      fetchOnline();
      fetchMessages();
    }, 5000);
    const heartbeatInterval = setInterval(() => {
      sendHeartbeat();
    }, 30000);

    return () => {
      clearInterval(syncInterval);
      clearInterval(heartbeatInterval);
      sendHeartbeat({ current_task: null, current_timer_end: null });
    };
  }, []);

  useEffect(() => {
    if (typeof window === 'undefined') return;
    const media = window.matchMedia('(max-width: 767px)');
    const sync = () => setIsMobile(media.matches);
    sync();
    media.addEventListener('change', sync);
    return () => media.removeEventListener('change', sync);
  }, []);

  useEffect(() => {
    sendHeartbeat();
  }, [isActive]);

  useEffect(() => {
    resizeChatTextarea();
  }, [chatInput, isMobile]);

  const handleScroll = () => {
    if (!scrollContainerRef.current) return;
    const { scrollTop, scrollHeight, clientHeight } = scrollContainerRef.current;
    const isBottom = scrollHeight - scrollTop - clientHeight < 150;
    setIsAtBottom(isBottom);
  };

  const scrollToBottom = (force = false) => {
    if (scrollContainerRef.current && (isAtBottom || force)) {
      scrollContainerRef.current.scrollTop = scrollContainerRef.current.scrollHeight;
    }
  };

  useEffect(() => {
    if (messages.length === 0) return;
    const lastMsg = messages[messages.length - 1];
    if (lastMsg.id !== lastMessageIdRef.current) {
      const isMe = lastMsg?.user_detail?.username === user?.username;
      if (isMe || isAtBottom) {
        setTimeout(() => scrollToBottom(true), 50);
      }
      lastMessageIdRef.current = lastMsg.id;
    }
  }, [messages, user?.username, isAtBottom]);

  const fetchGiphy = async (query: string, append = false) => {
    if (isGiphyLoading) return;
    const q = query || 'study';
    const offset = append ? giphyResults.length : 0;
    setIsGiphyLoading(true);
    try {
      const url = q === 'study' && !query
        ? `https://api.giphy.com/v1/gifs/trending?api_key=9pr9qW2ISY8cIz1AGhgyB7SE7xLuDafc&limit=20&offset=${offset}&rating=g`
        : `https://api.giphy.com/v1/gifs/search?api_key=9pr9qW2ISY8cIz1AGhgyB7SE7xLuDafc&q=${encodeURIComponent(q)}&limit=20&offset=${offset}&rating=g`;
      
      const res = await fetch(url);
      const data = await res.json();
      if (data.data) {
        setGiphyResults(prev => append ? [...prev, ...data.data] : data.data);
      }
    } catch (e) { console.error("Giphy error", e); }
    finally { setIsGiphyLoading(false); }
  };

  const sendGif = async (url: string) => {
    try {
      await api.post('/study/messages/', { content: `![gif](${url})` });
      fetchMessages();
      setIsAtBottom(true);
      setTimeout(() => scrollToBottom(true), 100);
    } catch (e) {
      toast.error(t('gifSendFailed'));
    }
  };

  const handleGiphyScroll = (e: React.UIEvent<HTMLDivElement>) => {
    const { scrollTop, scrollHeight, clientHeight } = e.currentTarget;
    if (scrollHeight - scrollTop - clientHeight < 50) {
      fetchGiphy(giphySearch, true);
    }
  };

  const uploadImage = async (file: File) => {
    const formData = new FormData();
    formData.append('image', file);
    const tid = toast.loading(t('imageProcessing'));
    try {
      const res = await api.post('/study/upload-image/', formData);
      setChatInput(prev => (prev ? prev + '\n' : '') + `![image](${res.data.url})`);
      toast.success(t('imageReady'), { id: tid });
    } catch (e) {
      toast.error(t('imageProcessFailed'), { id: tid });
    }
  };

  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) uploadImage(file);
  };

  const onDrop = async (e: React.DragEvent) => {
    e.preventDefault(); e.stopPropagation();
    setIsDragging(false);
    const file = e.dataTransfer.files?.[0];
    if (file && file.type.startsWith('image/')) return uploadImage(file);
    const imageUrl = e.dataTransfer.getData('text/html').match(/src="([^"]+)"/)?.[1] || e.dataTransfer.getData('text/plain');
    if (imageUrl && (imageUrl.startsWith('http') || imageUrl.startsWith('data:image'))) {
      setChatInput(prev => (prev ? prev + '\n' : '') + `![image](${imageUrl})`);
    }
  };

  const sendMessage = async () => {
    if (!chatInput.trim()) return;
    const content = chatInput;
    setChatInput('');
    try {
      await api.post('/study/messages/', { content });
      fetchMessages();
      setIsAtBottom(true);
      setTimeout(() => scrollToBottom(true), 100);
    } catch (e) {
      setChatInput(content);
      toast.error(t('sendFailed'));
    }
  };

  const formatTime = (s: number) => {
    const m = Math.floor(s / 60);
    const sec = s % 60;
    return `${m.toString().padStart(2, '0')}:${sec.toString().padStart(2, '0')}`;
  };

  const handleDurationChange = (val: number) => {
    const v = Math.min(120, Math.max(1, val));
    setDuration(v);
    if (!isActive) setTimeLeft(v * 60);
  };

  const handleStartTask = async () => {
    if (!taskName.trim()) return toast.error(t('enterTaskName'));
    setIsActive(true);
    setIsTimerOpen(false);
    sendHeartbeat({
      current_task: taskName.trim(),
      current_timer_end: new Date(Date.now() + Math.max(timeLeft, 0) * 1000).toISOString(),
    });
    if (allowBroadcast) {
      try {
        await api.post('/study/messages/', { content: t('taskStarted', { emoji: '💪', taskName, duration }) });
        fetchMessages();
      } catch (e) {}
    }
  };

  const handleEnterMobileFocus = async () => {
    if (!taskName.trim()) return toast.error(t('enterTaskName'));
    if (!isActive) await handleStartTask();
    setShowMobileTimerSetup(false);
    setShowMobileTimerFullscreen(true);
  };

  const handleCompleteTask = async (isManual: boolean) => {
    setIsActive(false);
    sendHeartbeat({ current_task: null, current_timer_end: null });
    const focusedMins = Math.floor((duration * 60 - timeLeft) / 60);
    
    if (isManual) {
      if (allowBroadcast) {
        try {
          await api.post('/study/messages/', { content: t('taskAborted', { emoji: '❌', taskName, focusedMins }) });
          fetchMessages();
        } catch (e) {}
      }
    } else {
      // Completed successfully
      if (activePlanId) {
        // It was a plan task
        try {
          await api.patch(`/users/plans/${activePlanId}/`, { is_completed: true });
          fetchPlans();
          if (allowBroadcast) {
            await api.post('/study/messages/', {
              content: t('planCompleted', { emoji: '✅', plan: taskName }),
              related_plan_id: activePlanId
            });
            fetchMessages();
          }
        } catch (e) {}
        setActivePlanId(null); // Reset
      } else {
        // Normal task
        if (allowBroadcast) {
          try {
            await api.post('/study/messages/', {
              content: t('taskCompleted', { emoji: '✅', taskName, duration })
            });
            fetchMessages();
          } catch (e) {}
        }
      }
      toast.success(t('focusAchieved'));
    }
  };

  useEffect(() => {
    let interval: any = null;
    if (isActive && timeLeft > 0) {
      interval = setInterval(() => setTimeLeft(prev => prev - 1), 1000);
    } else if (timeLeft === 0 && isActive) {
      handleCompleteTask(false);
    }
    return () => clearInterval(interval);
  }, [isActive, timeLeft]);

  const myMessages = messages.filter(m => m.user_detail.username === user?.username);
  const myTaskMessages = myMessages.filter(m => isTaskStateMessage(m.content));
  const lastMyMessageId = myMessages.length > 0 ? myMessages[myMessages.length - 1].id : null;
  const lastMyTaskMessageId = myTaskMessages.length > 0 ? myTaskMessages[myTaskMessages.length - 1].id : null;

  return (
    <div className={cn(
      "overflow-hidden animate-in fade-in duration-300 text-left text-foreground",
      isMobile ? "h-full min-h-0 flex flex-col gap-0" : "h-[calc(100vh-6.5rem)] flex gap-6"
    )}>
      <div 
        className={cn(
          isMobile
            ? "flex-1 min-h-0 flex flex-col bg-background overflow-hidden relative transition-all duration-300"
            : "flex-1 flex flex-col bg-card rounded-3xl shadow-sm border border-border overflow-hidden relative transition-all duration-300",
          isDragging && "ring-4 ring-primary/20 bg-primary/5 border-primary border-dashed z-50",
        )}
        onDragOver={(e) => { e.preventDefault(); e.stopPropagation(); setIsDragging(true); }}
        onDragEnter={(e) => { e.preventDefault(); e.stopPropagation(); setIsDragging(true); }}
        onDragLeave={(e) => { e.preventDefault(); e.stopPropagation(); setIsDragging(false); }}
        onDrop={onDrop}
      >
        <header className={cn(
          "border-b border-border flex items-center justify-between bg-card/80 backdrop-blur-md sticky top-0 z-20",
          isMobile ? "px-3 py-2.5" : "px-8 py-3"
        )}>
          <div className="flex items-center gap-4">
            <div className="h-9 w-9 rounded-xl bg-primary flex items-center justify-center shadow-lg text-primary-foreground"><MessageSquare className="h-4 w-4" /></div>
            <h2 className="text-sm font-bold tracking-tight">{t('chatRoomTitle')}</h2>
          </div>
          <div className="flex items-center gap-2">
            {!isMobile && (
              <Popover open={isTimerOpen} onOpenChange={setIsTimerOpen}>
                <PopoverTrigger asChild><Button className={cn("rounded-2xl h-10 px-5 gap-3 transition-all duration-500 shadow border border-black/5", isActive ? "bg-emerald-500 text-white" : "bg-primary text-primary-foreground hover:opacity-90")}><Timer className="h-4 w-4" /><span className="font-mono font-bold text-sm tracking-tight tabular-nums">{formatTime(timeLeft)}</span></Button></PopoverTrigger>
                <PopoverContent className="w-80 rounded-[2.5rem] p-8 border-none shadow-lg bg-card/95 backdrop-blur-xl z-[100]" side="bottom" align="end">
                  <div className="space-y-5 text-center">
                    <div className="text-5xl font-mono font-bold tracking-tighter text-foreground tabular-nums">{formatTime(timeLeft)}</div>
                    <div className="space-y-4 text-left">
                      <div className="space-y-2">
                        <div className="flex justify-between items-center mb-1"><label className="text-[11px] font-bold uppercase tracking-widest opacity-30 text-foreground">{t('timer.duration')}</label>
                        <div className="flex items-center gap-1"><Input type="number" disabled={isActive} value={duration} onChange={e => handleDurationChange(parseInt(e.target.value) || 0)} className="w-12 h-6 p-0 text-center border-none bg-muted rounded-md text-[11px] font-bold text-foreground" /><span className="text-[11px] font-bold opacity-30 uppercase text-foreground">{t('timer.min')}</span></div></div>
                        <Slider disabled={isActive} value={[duration]} onValueChange={v => handleDurationChange(v[0])} max={120} min={1} step={1}/>
                      </div>
                      <div className="space-y-2"><label className="text-[11px] font-bold uppercase tracking-widest opacity-30 ml-1 text-foreground">{t('timer.taskGoal')}</label><Input value={taskName} onChange={e => setTaskName(e.target.value)} placeholder={t('timer.taskPlaceholder')} className="bg-muted border-none h-11 rounded-xl text-center font-bold text-sm text-foreground" /></div>
                    </div>
                    <div className="flex justify-center gap-2.5 pt-1">
                      <Button size="lg" onClick={isActive ? () => setIsActive(false) : handleStartTask} className={cn("rounded-2xl flex-1 font-bold h-12 shadow-lg", isActive ? "bg-muted text-foreground" : "bg-primary text-primary-foreground shadow-primary/10")}>{isActive ? <Pause className="mr-2 h-4 w-4" /> : <Play className="mr-2 h-4 w-4" />}{isActive ? t('timer.pause') : t('timer.startStudy')}</Button>
                      {isActive && <Button variant="destructive" onClick={() => setShowStopAlert(true)} className="rounded-2xl h-12 w-12 shadow"><XCircle className="h-5 w-5" /></Button>}
                    </div>
                  </div>
                </PopoverContent>
              </Popover>
            )}

            <DropdownMenu modal={false}>
              <DropdownMenuTrigger asChild>
                <Button variant="ghost" size="icon" className="rounded-xl h-9 w-9 text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"><MoreHorizontal className="h-4 w-4"/></Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-64 rounded-2xl p-4 space-y-4 bg-card border-border shadow-lg">
                <div className="space-y-1">
                  <h4 className="text-[11px] font-bold uppercase tracking-widest text-muted-foreground">{t('privacy.title')}</h4>
                  <p className="text-[11px] text-muted-foreground/50">{t('privacy.description')}</p>
                </div>
                <div className="space-y-3 pt-2">
                  <div className="flex items-center justify-between">
                    <Label className="text-xs font-bold">{t('privacy.broadcastTasks')}</Label>
                    <Switch checked={allowBroadcast} onCheckedChange={(v) => updateSettings('allow_broadcast', v)} />
                  </div>
                  <div className="flex items-center justify-between">
                    <Label className="text-xs font-bold">{t('privacy.receiveBroadcasts')}</Label>
                    <Switch checked={showOthersBroadcast} onCheckedChange={(v) => updateSettings('show_others_broadcast', v)} />
                  </div>
                </div>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        </header>

        <div
          ref={scrollContainerRef}
          onScroll={handleScroll}
          className={cn(
            "flex-1 overflow-y-auto space-y-4 scrollbar-thin scrollbar-thumb-primary/10 relative",
            isMobile ? "min-h-0 p-3" : "p-8"
          )}
        >
          <div className="max-w-4xl mx-auto space-y-4 pb-4">
            {messages.map((msg) => {
              const isMe = msg.user_detail.username === user?.username;
              const isTask = isTaskStateMessage(msg.content);
              if (isTask && !showOthersBroadcast && !isMe) return null;
              if (isTask) return (
                <div key={msg.id} className="flex flex-col items-center py-0.5 animate-in fade-in zoom-in-95 duration-300">
                  <div className={cn("px-6 py-1.5 rounded-2xl border flex items-center gap-3 shadow-sm relative group/task",
                    msg.content.includes('💪') ? "bg-emerald-500/10 text-emerald-600 border-emerald-500/20" :
                    msg.content.includes('✅') ? "bg-blue-500/10 text-blue-600 border-blue-500/20" :
                    msg.content.includes('📅') ? "bg-orange-500/10 text-orange-600 border-orange-500/20" :
                    "bg-red-500/10 text-red-600 border-red-500/20"
                  )}>
                     {msg.content.includes('💪') ? <Zap className="h-3 w-3 fill-emerald-500 text-emerald-500" /> :
                      msg.content.includes('✅') ? <CheckCircle2 className="h-3 w-3 text-blue-500" /> :
                      msg.content.includes('📅') ? <Calendar className="h-3 w-3 text-orange-500" /> :
                      <XCircle className="h-3 w-3 text-red-500" />
                     }
                     <span className="text-[11px] font-bold tracking-tight text-foreground"><span className="opacity-70">{msg.user_detail.nickname || msg.user_detail.username}</span> {msg.content.split(msg.user_detail.username)[1] || msg.content}</span>
                     
                     {isMe && msg.id === lastMyTaskMessageId && (
                        <button
                          onClick={() => undoMessage(msg.id)}
                          className="ml-3 text-[11px] font-bold text-muted-foreground/50 hover:text-red-500 underline decoration-dotted underline-offset-2 transition-colors cursor-pointer"
                        >
                          {t('undo')}
                        </button>
                     )}
                  </div>
                </div>
              );
              const isMediaOnly = msg.content.trim().startsWith('![') && msg.content.trim().endsWith(')');
              
              return (
                <div key={msg.id} className={cn("flex gap-4 group animate-in fade-in slide-in-from-bottom-2 duration-300", isMe ? "flex-row-reverse text-right" : "flex-row text-left")}>
                  <Avatar className="h-9 w-9 border border-border shadow-sm shrink-0 group-hover:scale-105 transition-transform"><AvatarImage src={msg.user_detail.avatar_url} /><AvatarFallback className="text-[11px] font-bold bg-muted">{(msg.user_detail.nickname || msg.user_detail.username)[0]}</AvatarFallback></Avatar>
                  <div className={cn("flex flex-col gap-1 max-w-[70%] w-fit", isMe ? "items-end" : "items-start")}>
                    <div className="flex items-center gap-2 px-1 text-muted-foreground"><span className="text-[11px] font-bold uppercase tracking-widest">{msg.user_detail.nickname || msg.user_detail.username}</span></div>
                    <div 
                      className={cn(
                        "text-[13px] leading-relaxed break-words overflow-hidden text-left w-fit h-fit", 
                        !isMediaOnly && (isMe ? "p-2 px-3 bg-slate-900 text-white rounded-2xl rounded-tr-none shadow-sm font-medium" : "p-2 px-3 rounded-2xl rounded-tl-none shadow-sm font-medium")
                      )}
                      style={!isMediaOnly && !isMe ? { backgroundColor: '#ffb0b3', color: '#0f172a' } : {}}
                    >
                      <ReactMarkdown 
                        remarkPlugins={[remarkMath, remarkSoftBreaks]} 
                        rehypePlugins={[rehypeKatex]} 
                        components={{ 
                          img: ({node, ...props}) => <img {...props} className="max-w-[130px] md:max-w-[200px] rounded-lg my-0.5 cursor-zoom-in hover:opacity-90 transition-opacity" onClick={() => window.open(props.src || '', '_blank')}/>, 
                          p: ({node, ...props}) => <p {...props} className="m-0 leading-normal w-fit" />,
                          div: ({node, ...props}) => <div {...props} className="w-fit" />,
                          br: () => <br />
                        }}
                      >
                        {processMathContent(msg.content)}
                      </ReactMarkdown>
                    </div>
                    <div className="mt-0.3 flex items-center gap-2 px-1">
                      <span className="text-[11px] text-muted-foreground/40 font-medium">
                        {new Date(msg.timestamp).toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'})}
                      </span>
                      {isMe && msg.id === lastMyMessageId && (
                        <button
                          onClick={() => undoMessage(msg.id)}
                          className="text-[11px] font-bold text-muted-foreground/50 hover:text-red-500 underline decoration-dotted underline-offset-2 transition-colors cursor-pointer"
                        >
                          {t('undo')}
                        </button>
                      )}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {!isAtBottom && (
          <Button onClick={() => scrollToBottom(true)} size="icon" className="absolute bottom-24 right-8 rounded-full h-10 w-10 shadow-lg bg-primary text-primary-foreground z-50 hover:scale-110 transition-transform opacity-80 hover:opacity-100 border border-white/10"><ArrowDown className="h-5 w-5"/></Button>
        )}

        <footer className={cn(
          "bg-card/80 backdrop-blur-md border-t border-border z-20",
          isMobile ? "p-2 pb-[calc(4.9rem+env(safe-area-inset-bottom))] shrink-0" : "p-4"
        )}>
          <div className="max-w-4xl mx-auto space-y-3">
            <div className="flex gap-2 px-1">
              {isMobile && (
                <Popover open={showMobileTimerSetup} onOpenChange={setShowMobileTimerSetup}>
                  <PopoverTrigger asChild>
                    <Button
                      variant="ghost"
                      size="icon"
                      className={cn(
                        "h-8 w-8 rounded-lg transition-colors",
                        isActive
                          ? "text-emerald-600 hover:text-emerald-700 hover:bg-emerald-50"
                          : "text-muted-foreground hover:text-foreground hover:bg-muted"
                      )}
                    >
                      <Timer className="h-4 w-4" />
                    </Button>
                  </PopoverTrigger>
                  <PopoverContent side="top" align="start" className="w-[82vw] max-w-72 rounded-2xl p-4 border-none shadow-lg bg-card/95 backdrop-blur-xl z-[100]">
                    <div className="space-y-3">
                      <div className="flex items-center justify-between">
                        <p className="text-xs font-black uppercase tracking-widest text-muted-foreground">{t('mobile.pomodoro')}</p>
                        <span className="font-mono font-black text-lg tabular-nums">{formatTime(timeLeft)}</span>
                      </div>
                      <Input value={taskName} onChange={e => setTaskName(e.target.value)} placeholder={t('mobile.taskPlaceholder')} className="h-10 rounded-xl bg-muted border-none text-sm font-bold" />
                      <div className="space-y-2">
                        <div className="flex items-center justify-between text-[11px] font-bold text-muted-foreground uppercase">
                          <span>{t('mobile.duration')}</span>
                          <span>{t('mobile.durationFormat', { duration })}</span>
                        </div>
                        <Slider disabled={isActive} value={[duration]} onValueChange={v => handleDurationChange(v[0])} max={120} min={1} step={1} />
                      </div>
                      <Button onClick={handleEnterMobileFocus} className="w-full h-10 rounded-xl bg-slate-900 text-white font-black">
                        {t('mobile.enterFullscreen')}
                      </Button>
                    </div>
                  </PopoverContent>
                </Popover>
              )}
              <Popover>
                <PopoverTrigger asChild><Button variant="ghost" size="icon" className="h-8 w-8 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"><Smile className="h-4 w-4"/></Button></PopoverTrigger>
                <PopoverContent side="top" className="w-64 p-2 rounded-2xl border-border shadow-lg bg-card"><div className="grid grid-cols-8 gap-1">{['😊','😂','🤣','😍','😒','🤔','😭','👍','🙌','🔥','✨','💯','📚','🎓','💪','🎯','❤️','✔️','❌','⚠️','🚀','💡','🌟','🎉'].map(e => (<button key={e} onClick={() => setChatInput(prev => prev + e)} className="h-8 w-8 flex items-center justify-center hover:bg-muted rounded-lg text-lg transition-colors">{e}</button>))}</div></PopoverContent>
              </Popover>
              <Popover onOpenChange={(open) => open && giphyResults.length === 0 && fetchGiphy('')}>
                <PopoverTrigger asChild><Button variant="ghost" size="icon" className="h-8 w-8 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"><FileVideo className="h-4 w-4"/></Button></PopoverTrigger>
                <PopoverContent side="top" className="w-80 p-3 rounded-2xl border-border shadow-lg space-y-3 bg-card z-[100]">
                  <Input placeholder={t('giphySearch')} value={giphySearch} onChange={e => { setGiphySearch(e.target.value); fetchGiphy(e.target.value); }} className="h-9 text-xs rounded-xl bg-muted border-none text-foreground placeholder:opacity-50 focus-visible:ring-1 focus-visible:ring-primary/20" />
                  <div onScroll={handleGiphyScroll} className="grid grid-cols-4 gap-2 h-72 overflow-y-auto pr-1 scrollbar-thin">
                    {giphyResults.map(g => (
                      <div key={g.id} className="relative group/gif">
                        <button 
                          type="button"
                          onClick={() => sendGif(g.images.original.url)}
                          className="w-full aspect-square rounded-lg overflow-hidden bg-muted transition-all hover:ring-2 ring-primary"
                        >
                          <img src={g.images.fixed_height_small.url} className="w-full h-full object-cover" />
                        </button>
                        <div className="absolute left-1/2 bottom-full mb-2 -translate-x-1/2 scale-0 group-hover/gif:scale-100 transition-all z-[110] pointer-events-none origin-bottom">
                          <div className="w-32 aspect-square rounded-xl overflow-hidden shadow-lg border-2 border-primary bg-card">
                            <img src={g.images.fixed_height_small.url} className="w-full h-full object-cover" />
                          </div>
                        </div>
                      </div>
                    ))}
                    {isGiphyLoading && (
                      <div className="col-span-4 py-2 flex justify-center">
                        <Loader2 className="h-4 w-4 animate-spin text-muted-foreground opacity-30" />
                      </div>
                    )}
                  </div>
                  <p className="text-[11px] text-center text-muted-foreground font-bold opacity-50 uppercase tracking-tighter">Powered by GIPHY</p>
                </PopoverContent>
              </Popover>
              <Button variant="ghost" size="icon" onClick={() => fileInputRef.current?.click()} className="h-8 w-8 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"><ImageIcon className="h-4 w-4"/></Button>
              {isMobile && (
                <Button variant="ghost" size="icon" onClick={() => cameraInputRef.current?.click()} className="h-8 w-8 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted transition-colors">
                  <Camera className="h-4 w-4" />
                </Button>
              )}
              <input type="file" ref={fileInputRef} onChange={(e) => handleFileUpload(e)} className="hidden" accept="image/*" />
              <input type="file" ref={cameraInputRef} onChange={(e) => handleFileUpload(e)} className="hidden" accept="image/*" capture="environment" />
            </div>
            <div className="flex gap-3 bg-muted rounded-2xl p-1.5 focus-within:bg-card focus-within:ring-2 focus-within:ring-primary/5 transition-all shadow-inner border border-border">
              <textarea
                ref={chatTextareaRef}
                value={chatInput}
                onChange={e => setChatInput(e.target.value)}
                onCompositionStart={() => setIsComposing(true)}
                onCompositionEnd={() => setIsComposing(false)}
                onKeyDown={e => {
                  if (e.key === 'Enter' && !e.shiftKey && !isComposing) {
                    e.preventDefault();
                    sendMessage();
                  }
                }}
                placeholder=""
                className={cn(
                  "flex-1 bg-transparent border-none shadow-none focus:outline-none focus-visible:ring-0 text-[13px] px-4 py-2.5 text-foreground placeholder:text-muted-foreground/50 resize-none leading-5",
                  isMobile ? "h-10 min-h-10 max-h-10" : "min-h-10 max-h-32"
                )}
                rows={1}
              />
              <Button onClick={sendMessage} size="icon" className="rounded-xl h-10 w-10 bg-primary text-primary-foreground shadow shrink-0 hover:opacity-90 active:scale-95 transition-transform"><Send className="h-4 w-4" /></Button>
            </div>
          </div>
        </footer>

      </div>

      <div className="hidden md:flex w-72 flex-col gap-6 shrink-0 text-foreground">
        <Card className="border-none shadow-sm rounded-2xl md:rounded-3xl bg-card overflow-hidden p-4 md:p-6 md:flex-1 min-h-0 flex flex-col border border-border">
          <header className="mb-4 flex items-center justify-between"><CardTitle className="text-[13px] font-bold uppercase tracking-widest text-muted-foreground">{t('onlineUsers.title')}</CardTitle><Users className="h-4 w-4 text-muted-foreground opacity-20" /></header>
          <div className="flex-1 overflow-y-auto space-y-3 pr-2 scrollbar-none">
            {onlineUsers.map((u, i) => (<HoverCard key={i}><HoverCardTrigger asChild><div className="flex items-center gap-3 p-2.5 rounded-2xl hover:bg-muted transition-all cursor-pointer border border-transparent hover:border-border group"><div className="relative shrink-0"><Avatar className="h-9 w-9 border border-border shadow-sm group-hover:ring-2 ring-emerald-500/20 transition-all"><AvatarImage src={u.avatar_url}/></Avatar><span className="absolute bottom-0 right-0 h-2.5 w-2.5 rounded-full bg-emerald-500 border-2 border-background shadow-sm"/></div><div className="flex-1 min-w-0"><p className="text-xs font-bold text-foreground truncate">{u.nickname || u.username} {u.username === user?.username && t('onlineUsers.self')}</p><p className="text-[11px] text-emerald-600 font-bold truncate mt-0.5 uppercase tracking-tight">{u.current_task || t('onlineUsers.online')}</p></div></div></HoverCardTrigger><HoverCardContent side="left" className="w-80 rounded-[2rem] p-6 border-none shadow-lg bg-card/95 backdrop-blur-xl z-50 text-left text-foreground"><div className="flex space-x-4"><Avatar className="h-12 w-12 border border-border shadow-sm"><AvatarImage src={u.avatar_url}/></Avatar><div className="space-y-3 flex-1 text-left"><div className="flex justify-between items-center"><h4 className="text-sm font-bold">{u.nickname || u.username}</h4><Badge variant="outline" className="text-[11px] border-emerald-500/20 text-emerald-600 rounded-full">ELO {u.elo_score}</Badge></div><div className="space-y-2 pt-2 border-t border-border"><div className="flex items-center gap-2 text-muted-foreground"><Clock className="h-3.5 w-3.5"/><span className="text-[11px] font-bold uppercase tracking-widest">{t('onlineUsers.todayFocus', { minutes: u.today_focused_minutes })}</span></div><div className="flex items-center gap-2 text-muted-foreground"><CheckCircle2 className="h-3.5 w-3.5"/><span className="text-[11px] font-bold uppercase tracking-widest">{t('onlineUsers.todayCompleted', { count: u.today_completed_tasks?.length || 0 })}</span></div></div></div></div></HoverCardContent></HoverCard>))}</div>
        </Card>
        <Card className="border-none shadow-sm rounded-2xl md:rounded-3xl bg-card overflow-hidden p-4 md:p-6 md:flex-1 min-h-0 flex flex-col border border-border">
          <header className="mb-4 flex items-center justify-between border-b border-border pb-4"><CardTitle className="text-[13px] font-bold uppercase tracking-widest text-muted-foreground">{t('planList.title')}</CardTitle><ListTodo className="h-4 w-4 text-muted-foreground opacity-20" /></header>
          <div className="flex-1 overflow-y-auto space-y-1.5 pr-2 scrollbar-none">
            {plans.map(p => (
              <div key={p.id} className={cn("group flex items-center gap-3 p-2 rounded-2xl transition-all border border-transparent", p.is_completed ? "bg-muted/30 opacity-60" : "hover:bg-muted hover:border-border")}>
                <button
                  disabled={p.is_completed}
                  className={cn("transition-colors", p.is_completed ? "cursor-not-allowed" : "cursor-pointer")}
                  onClick={async () => {
                    if (p.is_completed) return;
                    try {
                      await api.patch(`/users/plans/${p.id}/`, { is_completed: true });
                      fetchPlans();
                      if (allowBroadcast) {
                        await api.post('/study/messages/', {
                          content: t('planCompleted', { emoji: '✅', plan: p.content }),
                          related_plan_id: p.id
                        });
                        fetchMessages();
                      }
                    } catch (e) {}
                  }}
                >
                  {p.is_completed ? <CheckCircle2 className="h-4 w-4 text-emerald-500" /> : <Circle className="h-4 w-4 text-muted-foreground/20 group-hover:text-emerald-500" />}
                </button>
                <span onClick={() => { if(!p.is_completed) { setTaskName(p.content); setActivePlanId(p.id); setIsTimerOpen(true); } }} className={cn("text-xs font-bold truncate flex-1", p.is_completed ? "line-through text-muted-foreground cursor-default" : "text-foreground cursor-pointer")}>{p.content}</span>

                <button
                  onClick={async (e) => {
                    e.stopPropagation();
                    try {
                      await api.delete(`/users/plans/${p.id}/`);
                      fetchPlans();
                      toast.success(t('planList.planDeleted'));
                    } catch (e) { toast.error(t('planList.deleteFailed')); }
                  }}
                  className="opacity-0 group-hover:opacity-100 transition-all p-1.5 hover:bg-red-100 rounded-lg text-muted-foreground/50 hover:text-red-500 cursor-pointer"
                  title={t('planList.deletePlan')}
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </button>
              </div>
            ))}
          </div>
          <div className="mt-4 flex gap-2">
            <Input
              value={newPlan}
              onChange={e => setNewPlan(e.target.value)}
              onKeyDown={async (e) => {
                if (e.key === 'Enter' && !(e.nativeEvent as any).isComposing) {
                  if (!newPlan.trim()) return;
                  const res = await api.post('/users/plans/', { content: newPlan });
                  if (allowBroadcast) {
                    await api.post('/study/messages/', {
                      content: t('planList.planCreated', { emoji: '📅', plan: newPlan }),
                      related_plan_id: res.data.id
                    });
                    fetchMessages();
                  }
                  fetchPlans();
                  setNewPlan('');
                }
              }}
              placeholder={t('planList.addTarget')}
              className="bg-muted border-none h-8 rounded-lg text-[11px] font-bold px-3 text-foreground focus-visible:ring-1 focus-visible:ring-primary/20"
            />
            <Button
              onClick={async () => {
                if (!newPlan.trim()) return;
                const res = await api.post('/users/plans/', { content: newPlan });
                if (allowBroadcast) {
                  await api.post('/study/messages/', {
                    content: t('planList.planCreated', { emoji: '📅', plan: newPlan }),
                    related_plan_id: res.data.id
                  });
                  fetchMessages();
                }
                fetchPlans();
                setNewPlan('');
              }}
              size="icon"
              className="h-8 w-8 bg-primary text-primary-foreground rounded-lg shrink-0 hover:opacity-90 active:scale-95 transition-all"
            >
              <Plus className="h-3.5 w-3.5"/>
            </Button>
          </div>
        </Card>
      </div>

      <div className={cn("fixed inset-0 z-[120] md:hidden bg-black/95 text-white flex flex-col items-center justify-center gap-6 transition-all duration-300", showMobileTimerFullscreen ? "opacity-100 pointer-events-auto" : "opacity-0 pointer-events-none")}>
        <button onClick={() => setShowMobileTimerFullscreen(false)} className="absolute top-6 right-6 h-10 w-10 rounded-full bg-white/10 flex items-center justify-center">
          <XCircle className="h-5 w-5" />
        </button>
        <p className="text-xs font-black uppercase tracking-[0.25em] text-white/40">{t('focusMode.title')}</p>
        <p className="font-mono font-black text-[72px] leading-none tabular-nums">{formatTime(timeLeft)}</p>
        <p className="text-base font-bold text-white/80 px-8 text-center">{taskName || t('deepFocus')}</p>
        <div className="flex items-center gap-3">
          <Button
            size="lg"
            onClick={isActive ? () => setIsActive(false) : handleStartTask}
            className={cn("rounded-2xl px-6 h-12 font-black", isActive ? "bg-white/20 text-white hover:bg-white/30" : "bg-emerald-500 text-white hover:bg-emerald-600")}
          >
            {isActive ? <Pause className="mr-2 h-4 w-4" /> : <Play className="mr-2 h-4 w-4" />}
            {isActive ? t('focusMode.pause') : t('focusMode.start')}
          </Button>
          <Button
            size="lg"
            variant="ghost"
            onClick={() => setShowStopAlert(true)}
            className="rounded-2xl px-6 h-12 font-black text-white border border-white/20 hover:bg-white/10"
          >
            {t('focusMode.end')}
          </Button>
        </div>
      </div>

      <AlertDialog open={showStopAlert} onOpenChange={setShowStopAlert}>
        <AlertDialogContent className="rounded-[2.5rem] border-none shadow-2xl bg-card">
          <AlertDialogHeader><AlertDialogTitle className="text-foreground">{t('focusMode.confirmTitle')}</AlertDialogTitle><AlertDialogDescription className="text-muted-foreground">{t('focusMode.confirmDesc')}</AlertDialogDescription></AlertDialogHeader>
          <AlertDialogFooter><AlertDialogCancel onClick={() => setShowStopAlert(false)} className="rounded-xl border-border text-foreground hover:bg-muted">{t('focusMode.keepFocusing')}</AlertDialogCancel><AlertDialogAction onClick={async () => {
            setIsActive(false); setShowStopAlert(false);
            sendHeartbeat({ current_task: null, current_timer_end: null });
            const focusedMins = Math.floor((duration * 60 - timeLeft) / 60);
            if (allowBroadcast) {
              await api.post('/study/messages/', { content: t('taskAborted', { emoji: '❌', taskName, focusedMins }) });
              fetchMessages();
            }
          }} className="rounded-xl bg-red-500 hover:bg-red-600 text-white font-bold">{t('focusMode.abortAndLeave')}</AlertDialogAction></AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
};
