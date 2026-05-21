import React, { useEffect, useState } from 'react';
import { Bell, CheckCheck, MessageCircle, Info, Brain, Trash2 } from 'lucide-react';
import { EmptyState } from '@/components/EmptyState';
import { useNotificationStore } from '@/store/useNotificationStore';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Button } from '@/components/ui/button';
import { ScrollArea } from '@/components/ui/scroll-area';
import { cn } from '@/lib/utils';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';

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
  const navigate = useNavigate();
  const { t, i18n } = useTranslation(['notifications', 'common']);
  const [isOpen, setIsOpen] = useState(false);
  const [showClearAlert, setShowClearAlert] = useState(false);

  useEffect(() => {
    fetchUnreadCount();
    const interval = setInterval(fetchUnreadCount, 5000); 
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
        else window.open(notif.link, '_blank');
    }
  };

  const getIcon = (type: string) => {
    switch (type) {
      case 'qa_reply': return <MessageCircle className="h-3 w-3 text-indigo-500" />;
      case 'fsrs_reminder': return <Brain className="h-3 w-3 text-emerald-500" />;
      default: return <Info className="h-3 w-3 text-blue-500" />;
    }
  };

  return (
    <DropdownMenu open={isOpen} onOpenChange={handleOpen} modal={false}>
      <DropdownMenuTrigger asChild>
        <div className="relative cursor-pointer group">
          <Button variant="ghost" size="icon" className="h-9 w-9 rounded-xl text-muted-foreground hover:bg-muted hover:text-foreground relative">
            <Bell className={cn("h-4 w-4 transition-transform", unreadCount > 0 && "animate-pulse")} />
            {unreadCount > 0 && (
              <span className="absolute top-2.5 right-2.5 h-2 w-2 rounded-full bg-red-500 border-2 border-background" />
            )}
          </Button>
        </div>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-80 rounded-2xl p-2 bg-card/95 backdrop-blur-xl border-border shadow-lg z-[100]">
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
        <DropdownMenuSeparator className="bg-border" />
        <ScrollArea className="h-80">
          {notifications.length === 0 ? (
            <EmptyState icon={Bell} title={t('notifications:empty')} className="py-6" />
          ) : (
            <div className="p-1 space-y-0.5">
              {notifications.map(notif => (
                <div
                  key={notif.id}
                  onClick={() => handleItemClick(notif)}
                  className={cn(
                    "p-2.5 rounded-xl cursor-pointer transition-all border border-transparent",
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
                </div>
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
    </DropdownMenu>
  );
};
