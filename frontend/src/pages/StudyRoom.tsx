import React, { useState, useEffect, useRef, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { useIsMobile } from '@/lib/useIsMobile';
import { Button } from '@/components/ui/button';
import { Play, Pause, Chat, DotsThree, XCircle, CaretLeft } from '@phosphor-icons/react';
import {
  DropdownMenu, DropdownMenuContent,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel,
  AlertDialogContent, AlertDialogDescription, AlertDialogFooter,
  AlertDialogHeader, AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { cn } from '@/lib/utils';
import { useAuthStore } from '@/store/useAuthStore';
import { useSystemStore } from '@/store/useSystemStore';
import api from '@/lib/api';
import { toast } from 'sonner';
import { useTranslation } from 'react-i18next';
import { Switch } from '@/components/ui/switch';
import { Label } from '@/components/ui/label';
import { FocusTimer } from '@/pages/study-room/FocusTimer';
import { ChatMessageList } from '@/pages/study-room/ChatMessageList';
import { ChatInput } from '@/pages/study-room/ChatInput';
import { OnlineUsersPanel } from '@/pages/study-room/OnlineUsersPanel';
import { PlanList } from '@/pages/study-room/PlanList';

interface Message {
  id: number;
  user_detail: { username: string; nickname: string; avatar_url: string; role: string; };
  content: string;
  timestamp: string;
  related_plan?: number;
}

interface Plan { id: number; content: string; is_completed: boolean; }

const isTaskStateMessage = (content: string) =>
  content.includes('💪') || content.includes('✅') || content.includes('❌') || content.includes('📅');

const formatTime = (s: number) => {
  const m = Math.floor(s / 60);
  const sec = s % 60;
  return `${m.toString().padStart(2, '0')}:${sec.toString().padStart(2, '0')}`;
};

export const StudyRoom: React.FC = () => {
  const { user, updateUser } = useAuthStore();
  const { setPageHeader } = useSystemStore();
  const { t } = useTranslation('studyRoom');

  // ── Timer state ──
  const [timeLeft, setTimeLeft] = useState(25 * 60);
  const [isActive, setIsActive] = useState(false);
  const [activePlanId, setActivePlanId] = useState<number | null>(null);
  const [duration, setDuration] = useState(25);
  const [taskName, setTaskName] = useState(t('deepFocus'));

  // ── Chat & plans state ──
  const [onlineUsers, setOnlineUsers] = useState<any[]>([]);
  const [messages, setMessages] = useState<Message[]>([]);
  const [plans, setPlans] = useState<Plan[]>([]);
  const [chatInput, setChatInput] = useState('');

  // ── UI state ──
  const [showStopAlert, setShowStopAlert] = useState(false);
  const isMobile = useIsMobile();
  const navigate = useNavigate();
  const [showMobileTimerSetup, setShowMobileTimerSetup] = useState(false);
  const [showMobileTimerFullscreen, setShowMobileTimerFullscreen] = useState(false);
  const [isAtBottom, setIsAtBottom] = useState(true);
  const [isComposing, setIsComposing] = useState(false);
  const [isDragging, setIsDragging] = useState(false);

  // ── Privacy settings ──
  const [allowBroadcast, setAllowBroadcast] = useState(user?.allow_broadcast ?? true);
  const [showOthersBroadcast, setShowOthersBroadcast] = useState(user?.show_others_broadcast ?? true);

  // ── Refs ──
  const fileInputRef = useRef<HTMLInputElement>(null);
  const cameraInputRef = useRef<HTMLInputElement>(null);
  const chatTextareaRef = useRef<HTMLTextAreaElement>(null);
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const lastMessageIdRef = useRef<number | null>(null);
  const isActiveRef = useRef<boolean>(false);
  const taskNameRef = useRef<string>('');
  const timeLeftRef = useRef<number>(25 * 60);

  // ── Sync refs ──
  useEffect(() => { isActiveRef.current = isActive; }, [isActive]);
  useEffect(() => { taskNameRef.current = taskName; }, [taskName]);
  useEffect(() => { timeLeftRef.current = timeLeft; }, [timeLeft]);

  // ── Page header ──
  useEffect(() => {
    setPageHeader(t('pageTitle'), t('pageSubtitle'));
  }, [setPageHeader, t]);

  // ── API calls ──
  const fetchOnline = async () => { try { const res = await api.get('/users/online/'); setOnlineUsers(res.data); } catch (e) { console.error('fetchOnline failed', e); } };
  const fetchMessages = async () => { try { const res = await api.get('/study/messages/'); setMessages(res.data); } catch (e) { console.error('fetchMessages failed', e); } };
  const fetchPlans = async () => { try { const res = await api.get('/users/plans/'); setPlans(res.data); } catch (e) { console.error('fetchPlans failed', e); } };

  // ── Heartbeat ──
  const getHeartbeatPayload = useCallback(() => {
    if (isActiveRef.current) {
      return {
        current_task: taskNameRef.current.trim() || t('deepFocus'),
        current_timer_end: new Date(Date.now() + Math.max(timeLeftRef.current, 0) * 1000).toISOString(),
      };
    }
    return { current_task: null, current_timer_end: null };
  }, [t]);

  const sendHeartbeat = async (override?: { current_task?: string | null; current_timer_end?: string | null }) => {
    try { await api.post('/users/heartbeat/', { ...getHeartbeatPayload(), ...(override || {}) }); } catch (e) { console.warn('heartbeat failed', e); }
  };

  // ── Initial load + polling ──
  useEffect(() => {
    fetchOnline(); fetchMessages(); fetchPlans(); sendHeartbeat();
    const sync = setInterval(() => { fetchOnline(); fetchMessages(); }, 5000);
    const hb = setInterval(() => { sendHeartbeat(); }, 30000);
    return () => {
      clearInterval(sync); clearInterval(hb);
      sendHeartbeat({ current_task: null, current_timer_end: null });
    };
  }, []);

  useEffect(() => { sendHeartbeat(); }, [isActive]);

  // ── Textarea resize ──
  useEffect(() => {
    const el = chatTextareaRef.current;
    if (!el) return;
    if (isMobile) { el.style.height = '40px'; el.style.overflowY = 'auto'; return; }
    el.style.height = 'auto';
    const maxH = 128;
    const h = Math.min(el.scrollHeight, maxH);
    el.style.height = `${h}px`;
    el.style.overflowY = el.scrollHeight > maxH ? 'auto' : 'hidden';
  }, [chatInput, isMobile]);

  // ── Scroll ──
  const handleScroll = () => {
    if (!scrollContainerRef.current) return;
    const { scrollTop, scrollHeight, clientHeight } = scrollContainerRef.current;
    setIsAtBottom(scrollHeight - scrollTop - clientHeight < 150);
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
      if (isMe || isAtBottom) setTimeout(() => scrollToBottom(true), 50);
      lastMessageIdRef.current = lastMsg.id;
    }
  }, [messages, user?.username, isAtBottom]);

  // ── Timer logic ──
  const handleDurationChange = (val: number) => {
    const v = Math.min(120, Math.max(1, val));
    setDuration(v);
    if (!isActive) setTimeLeft(v * 60);
  };

  const handleStartTask = async () => {
    if (!taskName.trim()) return toast.error(t('enterTaskName'));
    setIsActive(true);
    sendHeartbeat({
      current_task: taskName.trim(),
      current_timer_end: new Date(Date.now() + Math.max(timeLeft, 0) * 1000).toISOString(),
    });
    if (allowBroadcast) {
      try {
        await api.post('/study/messages/', { content: t('taskStarted', { emoji: '💪', taskName, duration }) });
        fetchMessages();
      } catch (e) { toast.error(t('sendFailed')); }
    }
  };

  const handlePause = () => { setIsActive(false); };

  const handleAbort = async () => {
    setIsActive(false);
    sendHeartbeat({ current_task: null, current_timer_end: null });
    const focusedMins = Math.floor((duration * 60 - timeLeft) / 60);
    if (allowBroadcast) {
      try {
        await api.post('/study/messages/', { content: t('taskAborted', { emoji: '❌', taskName, focusedMins }) });
        fetchMessages();
      } catch (e) { toast.error(t('sendFailed')); }
    }
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
        } catch (e) { toast.error(t('sendFailed')); }
      }
    } else {
      if (activePlanId) {
        try {
          await api.patch(`/users/plans/${activePlanId}/`, { is_completed: true });
          fetchPlans();
          if (allowBroadcast) {
            await api.post('/study/messages/', { content: t('planCompleted', { emoji: '✅', plan: taskName }), related_plan_id: activePlanId });
            fetchMessages();
          }
        } catch (e) { toast.error(t('sendFailed')); }
        setActivePlanId(null);
      } else {
        if (allowBroadcast) {
          try {
            await api.post('/study/messages/', { content: t('taskCompleted', { emoji: '✅', taskName, duration }) });
            fetchMessages();
          } catch (e) { toast.error(t('sendFailed')); }
        }
      }
      toast.success(t('focusAchieved'));
    }
  };

  // ── Countdown interval ──
  const completedRef = useRef(false);

  useEffect(() => {
    if (!isActive) return;
    completedRef.current = false;
    const id = setInterval(() => setTimeLeft(prev => {
      if (prev <= 1) { clearInterval(id); return 0; }
      return prev - 1;
    }), 1000);
    return () => clearInterval(id);
  }, [isActive]);

  useEffect(() => {
    if (timeLeft === 0 && isActive && !completedRef.current) {
      completedRef.current = true;
      handleCompleteTask(false);
    }
  }, [timeLeft, isActive, handleCompleteTask]);

  // ── Chat actions ──
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

  const handleSendGif = async (url: string) => {
    try {
      await api.post('/study/messages/', { content: `![gif](${url})` });
      fetchMessages();
      setIsAtBottom(true);
      setTimeout(() => scrollToBottom(true), 100);
    } catch (e) {
      toast.error(t('gifSendFailed'));
    }
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

  const updateSettings = async (field: string, val: boolean) => {
    try {
      await api.patch('/users/me/update/', { [field]: val });
      if (field === 'allow_broadcast') setAllowBroadcast(val);
      if (field === 'show_others_broadcast') setShowOthersBroadcast(val);
      updateUser({ ...user, [field]: val } as any);
      toast.success(t('preferencesUpdated'));
    } catch (e) { toast.error(t('updateFailed')); }
  };

  const handleEnterMobileFocus = async () => {
    if (!taskName.trim()) return toast.error(t('enterTaskName'));
    if (!isActive) await handleStartTask();
    setShowMobileTimerSetup(false);
    setShowMobileTimerFullscreen(true);
  };

  // ── Derived data ──
  const myMessages = messages.filter(m => m.user_detail?.username === user?.username);
  const myTaskMessages = myMessages.filter(m => isTaskStateMessage(m.content));
  const lastMyMessageId = myMessages.length > 0 ? myMessages[myMessages.length - 1].id : null;
  const lastMyTaskMessageId = myTaskMessages.length > 0 ? myTaskMessages[myTaskMessages.length - 1].id : null;

  // ── Render ──
  return (
    <div className={cn(
      "overflow-hidden animate-in fade-in duration-300 text-left text-foreground",
      isMobile ? "h-full min-h-0 flex flex-col gap-0" : "h-[calc(100vh-6.5rem)] flex gap-6"
    )}>
      {/* ── Main chat area ── */}
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
        {/* Header */}
        <header className={cn(
          "border-b border-border flex items-center justify-between bg-card/80 backdrop-blur-md sticky top-0 z-20",
          isMobile ? "px-3 py-2.5" : "px-8 py-3"
        )}>
          <div className="flex items-center gap-4">
            {isMobile && (
              <Button variant="ghost" size="icon" className="h-8 w-8 -ml-1 rounded-lg" onClick={() => navigate(-1)}>
                <CaretLeft className="h-4 w-4" />
              </Button>
            )}
            <div className="h-9 w-9 rounded-xl bg-primary flex items-center justify-center shadow-lg text-primary-foreground">
              <Chat className="h-4 w-4" />
            </div>
            <h2 className="text-sm font-bold tracking-tight">{t('chatRoomTitle')}</h2>
          </div>
          <div className="flex items-center gap-2">
            {!isMobile && (
              <FocusTimer
                isActive={isActive}
                duration={duration}
                timeLeft={timeLeft}
                taskName={taskName}
                onDurationChange={handleDurationChange}
                onTaskNameChange={setTaskName}
                onStart={handleStartTask}
                onPause={handlePause}
                onAbort={handleAbort}
              />
            )}

            <DropdownMenu modal={false}>
              <DropdownMenuTrigger asChild>
                <Button variant="ghost" size="icon" className="rounded-xl h-9 w-9 text-muted-foreground hover:text-foreground hover:bg-muted transition-colors">
                  <DotsThree className="h-4 w-4"/>
                </Button>
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

        {/* Messages */}
        <ChatMessageList
          messages={messages}
          currentUsername={user?.username || ''}
          showOthersBroadcast={showOthersBroadcast}
          lastMyMessageId={lastMyMessageId}
          lastMyTaskMessageId={lastMyTaskMessageId}
          isAtBottom={isAtBottom}
          isMobile={isMobile}
          scrollContainerRef={scrollContainerRef}
          onScroll={handleScroll}
          onScrollToBottom={scrollToBottom}
          onUndoMessage={undoMessage}
        />

        {/* Input */}
        <ChatInput
          chatInput={chatInput}
          isMobile={isMobile}
          isComposing={isComposing}
          isActive={isActive}
          chatTextareaRef={chatTextareaRef}
          fileInputRef={fileInputRef}
          cameraInputRef={cameraInputRef}
          onChatInputChange={setChatInput}
          onCompositionStart={() => setIsComposing(true)}
          onCompositionEnd={() => setIsComposing(false)}
          onSendMessage={sendMessage}
          onFileUpload={handleFileUpload}
          onSendGif={handleSendGif}
          showMobileTimerSetup={showMobileTimerSetup}
          setShowMobileTimerSetup={setShowMobileTimerSetup}
          timeLeft={timeLeft}
          taskName={taskName}
          duration={duration}
          onTaskNameChange={setTaskName}
          onDurationChange={handleDurationChange}
          onEnterMobileFocus={handleEnterMobileFocus}
          formatTime={formatTime}
        />
      </div>

      {/* ── Right sidebar (desktop) ── */}
      <div className="hidden md:flex w-72 flex-col gap-6 shrink-0 text-foreground">
        <OnlineUsersPanel onlineUsers={onlineUsers} currentUsername={user?.username} />
        <PlanList
          plans={plans}
          allowBroadcast={allowBroadcast}
          onRefresh={fetchPlans}
          onStartPlan={(content, planId) => { setTaskName(content); setActivePlanId(planId); }}
          onPlanCompleted={() => fetchMessages()}
          onPlanDeleted={() => fetchPlans()}
        />
      </div>

      {/* ── Mobile fullscreen timer ── */}
      <div className={cn(
        "fixed inset-0 z-[var(--z-overlay)] md:hidden bg-black/95 text-white flex flex-col items-center justify-center gap-6 transition-all duration-300",
        showMobileTimerFullscreen ? "opacity-100 pointer-events-auto" : "opacity-0 pointer-events-none",
      )}>
        <button onClick={() => setShowMobileTimerFullscreen(false)} className="absolute top-6 right-6 h-10 w-10 rounded-full bg-white/10 flex items-center justify-center">
          <XCircle className="h-5 w-5" />
        </button>
        <p className="text-xs font-semibold text-white/40">{t('focusMode.title')}</p>
        <p className="font-mono font-black text-[72px] leading-none tabular-nums">{formatTime(timeLeft)}</p>
        <p className="text-base font-bold text-white/80 px-8 text-center">{taskName || t('deepFocus')}</p>
        <div className="flex items-center gap-3">
          <Button
            size="lg"
            onClick={isActive ? handlePause : handleStartTask}
            className={cn(
              "rounded-2xl px-6 h-12 font-black",
              isActive ? "bg-white/20 text-white hover:bg-white/30" : "bg-emerald-500 text-white hover:bg-emerald-600",
            )}
          >
            {isActive ? <Pause className="mr-2 h-4 w-4" /> : <Play className="mr-2 h-4 w-4" />}
            {isActive ? t('focusMode.pause') : t('focusMode.start')}
          </Button>
          <Button
            size="lg" variant="ghost"
            onClick={() => setShowStopAlert(true)}
            className="rounded-2xl px-6 h-12 font-black text-white border border-white/20 hover:bg-white/10"
          >
            {t('focusMode.end')}
          </Button>
        </div>
      </div>

      {/* ── Stop alert (mobile fullscreen) ── */}
      <AlertDialog open={showStopAlert} onOpenChange={setShowStopAlert}>
        <AlertDialogContent className="rounded-[2.5rem] border-none shadow-2xl bg-card">
          <AlertDialogHeader>
            <AlertDialogTitle className="text-foreground">{t('focusMode.confirmTitle')}</AlertDialogTitle>
            <AlertDialogDescription className="text-muted-foreground">{t('focusMode.confirmDesc')}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel onClick={() => setShowStopAlert(false)} className="rounded-xl border-border text-foreground hover:bg-muted">
              {t('focusMode.keepFocusing')}
            </AlertDialogCancel>
            <AlertDialogAction
              onClick={() => { handleAbort(); setShowStopAlert(false); setShowMobileTimerFullscreen(false); }}
              className="rounded-xl bg-red-500 hover:bg-red-600 text-white font-bold"
            >
              {t('focusMode.abortAndLeave')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
};
