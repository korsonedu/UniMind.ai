import { useEffect, useState } from 'react';
import { Bell, ChatCircle, Info, Brain, PaperPlaneTilt } from '@phosphor-icons/react';
import { EmptyState } from '@/components/EmptyState';
import { useNotificationStore } from '@/store/useNotificationStore';
import { useAuthStore } from '@/store/useAuthStore';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { cn } from '@/lib/utils';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import api from '@/lib/api';
import { toast } from 'sonner';

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

export const NotificationBell = () => {
  const { notifications, unreadCount, fetchNotifications, fetchUnreadCount, markAsRead, clearAll } = useNotificationStore();
  const { user } = useAuthStore();
  const navigate = useNavigate();
  const { t, i18n } = useTranslation(['notifications', 'common']);
  const [isOpen, setIsOpen] = useState(false);
  const [showClearAlert, setShowClearAlert] = useState(false);
  const [showBroadcast, setShowBroadcast] = useState(false);
  const [broadcastForm, setBroadcastForm] = useState({ title: '', content: '' });
  const isAdmin = user?.is_admin || user?.is_institution_admin;

  useEffect(() => {
    fetchUnreadCount();
    const interval = setInterval(() => {
      if (document.visibilityState === 'visible') fetchUnreadCount();
    }, 30000);
    return () => clearInterval(interval);
  }, []);

  const handleOpen = (open: boolean) => {
    setIsOpen(open);
    if (open) fetchNotifications();
  };

  const handleItemClick = async (notif: any) => {
    if (!notif.is_read) await markAsRead(notif.id);
    if (notif.link) {
        if (notif.link.startsWith('/')) navigate(notif.link);
        else window.open(notif.link, '_blank', 'noopener,noreferrer');
    }
  };

  const handleBroadcast = async () => {
    if (!broadcastForm.title || !broadcastForm.content) return toast.error('标题和内容必填');
    try {
      await api.post('/notifications/broadcast/', broadcastForm);
      toast.success('广播已发送');
      setShowBroadcast(false);
      setBroadcastForm({ title: '', content: '' });
    } catch { toast.error('发送失败'); }
  };

  const getIcon = (type: string) => {
    switch (type) {
      case 'qa_reply': return <ChatCircle className="h-3 w-3 text-indigo-500" />;
      case 'memorix_reminder': return <Brain className="h-3 w-3 text-emerald-500" />;
      default: return <Info className="h-3 w-3 text-blue-500" />;
    }
  };

  return (
    <DropdownMenu open={isOpen} onOpenChange={handleOpen} modal={false}>
      <DropdownMenuTrigger asChild>
        <div className="relative cursor-pointer group">
          <Button variant="ghost" size="icon" className="h-9 w-9 rounded-xl text-muted-foreground hover:bg-muted hover:text-foreground relative" aria-label="Notifications">
            <Bell className={cn("h-4 w-4 transition-[transform]", unreadCount > 0 && "animate-pulse")} />
            {unreadCount > 0 && (
              <span className="absolute top-2.5 right-2.5 h-2 w-2 rounded-full bg-red-500 border-2 border-background" />
            )}
          </Button>
        </div>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-80 rounded-2xl p-2 bg-card/95 backdrop-blur-xl border-border shadow-lg z-[var(--z-dropdown)]">
        <DropdownMenuLabel className="flex items-center justify-between px-3 py-2">
          <span className="text-[13px] font-bold uppercase tracking-widest text-muted-foreground">{t('notifications:titleWithCount', { count: unreadCount })}</span>
          <div className="flex gap-1">
            {unreadCount > 0 && (
                <Button
                variant="ghost"
                size="sm"
                onClick={(e) => { e.stopPropagation(); markAsRead(); }}
                className="h-6 px-2 text-[11px] font-bold text-indigo-600 gap-1 hover:bg-indigo-50 rounded-lg"
                >
                {t('notifications:markRead')}
                </Button>
            )}
            <Button
              variant="ghost"
              size="sm"
              onClick={(e) => { e.stopPropagation(); setShowClearAlert(true); }}
              className="h-6 px-2 text-[11px] font-bold text-red-600 gap-1 hover:bg-red-50 rounded-lg"
            >
              {t('notifications:clear')}
            </Button>
          </div>
        </DropdownMenuLabel>
        {isAdmin && (
          <>
            <div className="px-2 pb-1">
              <Button
                variant="outline"
                size="sm"
                onClick={(e) => { e.stopPropagation(); setIsOpen(false); setShowBroadcast(true); }}
                className="w-full h-8 rounded-lg text-[11px] font-bold gap-1.5 border-dashed border-muted-foreground/20 text-muted-foreground hover:text-foreground hover:border-foreground/30"
              >
                <PaperPlaneTilt className="h-3 w-3" />
                {t('notifications:broadcast', { defaultValue: '发布广播' })}
              </Button>
            </div>
            <DropdownMenuSeparator className="bg-border" />
          </>
        )}
        <ScrollArea className="h-80">
          {notifications.length === 0 ? (
            <EmptyState icon={Bell} title={t('notifications:empty')} className="py-6" />
          ) : (
            <div className="p-1 space-y-0.5">
              {notifications.map(notif => (
                <button
                  key={notif.id}
                  onClick={() => handleItemClick(notif)}
                  className={cn(
                    "w-full text-left p-2.5 rounded-xl cursor-pointer transition-all border border-transparent",
                    notif.is_read ? "opacity-50" : "bg-muted/40 border-border/10 hover:bg-muted/60",
                    "group/item"
                  )}
                >
                  <div className="flex gap-2.5 text-left">
                    <div className="h-5 w-5 rounded-md bg-card border border-border flex items-center justify-center shrink-0 mt-0.5">
                      {getIcon(notif.ntype)}
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-[13px] font-black text-foreground leading-tight">{notif.title}</p>
                      <p className="text-[12px] font-medium text-muted-foreground leading-relaxed mt-1 break-words whitespace-pre-wrap">{notif.content}</p>
                      <p className="text-[9px] font-bold text-muted-foreground/30 uppercase tracking-tighter mt-1.5">
                        {new Date(notif.created_at).toLocaleString(i18n.language?.startsWith('zh') ? 'zh-CN' : 'en-US', {month: '2-digit', day: '2-digit', hour: '2-digit', minute:'2-digit'})}
                      </p>
                    </div>
                  </div>
                </button>
              ))}
            </div>
          )}
        </ScrollArea>
      </DropdownMenuContent>

      <AlertDialog open={showClearAlert} onOpenChange={setShowClearAlert}>
        <AlertDialogContent className="rounded-[2rem] border-none shadow-2xl bg-card">
          <AlertDialogHeader>
            <AlertDialogTitle className="text-lg font-bold">{t('notifications:clearConfirmTitle')}</AlertDialogTitle>
            <AlertDialogDescription className="text-xs font-medium text-muted-foreground">
              {t('notifications:clearConfirmDesc')}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter className="gap-2">
            <AlertDialogCancel className="rounded-xl font-bold h-10 text-xs">{t('common:cancel')}</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => { clearAll(); setIsOpen(false); }}
              className="rounded-xl bg-red-600 hover:bg-red-700 text-white font-bold h-10 text-xs"
            >
              {t('notifications:confirmClear')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <Dialog open={showBroadcast} onOpenChange={setShowBroadcast}>
        <DialogContent className="sm:max-w-[480px] rounded-3xl p-8 border-none shadow-[0_0_0_1px_rgba(0,0,0,0.04),0_4px_8px_rgba(0,0,0,0.04),0_16px_32px_rgba(0,0,0,0.08),0_32px_64px_rgba(0,0,0,0.04)] bg-white text-left">
          <DialogHeader>
            <DialogTitle className="text-lg font-semibold flex items-center gap-3">
              <PaperPlaneTilt className="h-5 w-5 text-[#6E6E73]" /> {t('notifications:broadcast', { defaultValue: '发布广播' })}
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-5 pt-4">
            <div className="space-y-1.5">
              <Label className="text-xs font-medium text-[#6E6E73] ml-1">{t('notifications:broadcastTitle', { defaultValue: '标题' })}</Label>
              <Input
                value={broadcastForm.title}
                onChange={e => setBroadcastForm({ ...broadcastForm, title: e.target.value })}
                className="bg-[#F5F5F7] border-transparent focus-visible:ring-1 focus-visible:ring-[#0071E3]/20 focus-visible:ring-offset-0 focus-visible:border-[#0071E3]/30 h-11 rounded-xl px-4 text-sm font-medium"
                placeholder={t('notifications:broadcastTitlePlaceholder', { defaultValue: '广播标题' })}
              />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs font-medium text-[#6E6E73] ml-1">{t('notifications:broadcastContent', { defaultValue: '内容' })} <span className="text-[#AEAEB2]">（最多 50 字）</span></Label>
              <textarea
                value={broadcastForm.content}
                onChange={e => setBroadcastForm({ ...broadcastForm, content: e.target.value })}
                maxLength={50}
                className="w-full bg-[#F5F5F7] border-transparent focus-visible:ring-1 focus-visible:ring-[#0071E3]/20 focus-visible:ring-offset-0 focus-visible:border-[#0071E3]/30 rounded-2xl p-5 min-h-[100px] font-medium text-sm resize-none outline-none"
                placeholder={t('notifications:broadcastContentPlaceholder', { defaultValue: '输入广播内容...' })}
              />
              <p className="text-[11px] text-[#AEAEB2] text-right">{broadcastForm.content.length}/50</p>
            </div>
            <Button onClick={handleBroadcast} className="w-full h-11 rounded-xl bg-[#0071E3] hover:bg-[#0077ED] text-white font-medium text-sm shadow-[0_1px_3px_rgba(0,113,227,0.3)] transition-[background-color,box-shadow]">
              {t('notifications:sendBroadcast', { defaultValue: '发送广播' })}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </DropdownMenu>
  );
};
