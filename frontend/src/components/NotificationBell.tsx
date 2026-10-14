import { useEffect, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { queryKeys } from '@/lib/queryKeys';
import { Bell, ChatCircle, Info, Brain } from '@phosphor-icons/react';
import { EmptyState } from '@/components/EmptyState';
import { useNotificationStore } from '@/store/useNotificationStore';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Button } from '@/components/ui/button';
import { ScrollArea } from '@/components/ui/scroll-area';
import { cn } from '@/lib/utils';
import { useNavigate } from 'react-router-dom';
import api from '@/lib/api';

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
  const { notifications, unreadCount, fetchNotifications, markAsRead, clearAll } = useNotificationStore();
  const navigate = useNavigate();
  const [isOpen, setIsOpen] = useState(false);
  const [showClearAlert, setShowClearAlert] = useState(false);

  const { data: unreadData } = useQuery({
    queryKey: queryKeys.notifications.unreadCount,
    queryFn: () => api.get('/notifications/unread-count/').then(r => r.data),
    refetchInterval: 30000,
    refetchIntervalInBackground: false,
  });

  // Sync React Query data to store (markAsRead still calls fetchUnreadCount internally)
  useEffect(() => {
    if (unreadData?.unread_count !== undefined) {
      useNotificationStore.setState({ unreadCount: unreadData.unread_count });
    }
  }, [unreadData]);

  const handleOpen = (open: boolean) => {
    setIsOpen(open);
    if (open) fetchNotifications();
  };

  const handleItemClick = async (notif: ReturnType<typeof useNotificationStore.getState>['notifications'][number]) => {
    if (!notif.is_read) await markAsRead(notif.id);
    if (notif.link) {
        if (notif.link.startsWith('/')) navigate(notif.link);
        else window.open(notif.link, '_blank', 'noopener,noreferrer');
    }
  };

  const getIcon = (type: string) => {
    switch (type) {
      case 'qa_reply': return <ChatCircle className="h-3 w-3 text-muted-foreground" />;
      case 'memorix_reminder': return <Brain className="h-3 w-3 text-muted-foreground" />;
      default: return <Info className="h-3 w-3 text-muted-foreground" />;
    }
  };

  return (
    <DropdownMenu open={isOpen} onOpenChange={handleOpen} modal={false}>
      <DropdownMenuTrigger asChild>
        <div className="relative cursor-pointer group">
          <Button variant="ghost" size="icon" className="um-app-notification-button h-9 w-9 text-muted-foreground hover:bg-muted hover:text-foreground relative" aria-label={unreadCount ? `通知，${unreadCount} 条未读` : '通知'}>
            <Bell className="h-4 w-4" />
            {unreadCount > 0 && (
              <span className="absolute top-2.5 right-2.5 h-2 w-2 rounded-full bg-red-500 border-2 border-background" />
            )}
          </Button>
        </div>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="um-app-notifications w-80 p-2 z-[var(--z-dropdown)]">
        <DropdownMenuLabel className="flex items-center justify-between px-3 py-2">
          <span className="text-[13px] font-semibold text-muted-foreground">{`通知中心 (${unreadCount})`}</span>
          <div className="flex gap-1">
            {unreadCount > 0 && (
                <Button
                variant="ghost"
                size="sm"
                onClick={(e) => { e.stopPropagation(); markAsRead(); }}
                className="h-6 px-2 text-xs font-medium text-primary gap-1 hover:bg-accent rounded-lg"
                >
                已读
                </Button>
            )}
            <Button
              variant="ghost"
              size="sm"
              onClick={(e) => { e.stopPropagation(); setShowClearAlert(true); }}
              className="h-6 px-2 text-[11px] font-bold text-red-600 gap-1 hover:bg-red-50 rounded-lg"
            >
              清除
            </Button>
          </div>
        </DropdownMenuLabel>
        <ScrollArea className="h-80">
          {notifications.length === 0 ? (
            <EmptyState icon={Bell} title="暂无消息通知" className="py-6" />
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
                      <p className="text-[13px] font-medium text-foreground leading-tight">{notif.title}</p>
                      <p className="text-[12px] font-medium text-muted-foreground leading-relaxed mt-1 break-words whitespace-pre-wrap">{notif.content}</p>
                      <p className="text-xs text-muted-foreground mt-1.5">
                        {new Date(notif.created_at).toLocaleString('zh-CN', {month: '2-digit', day: '2-digit', hour: '2-digit', minute:'2-digit'})}
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
            <AlertDialogTitle className="text-lg font-bold">确认清除所有通知？</AlertDialogTitle>
            <AlertDialogDescription className="text-xs font-medium text-muted-foreground">
              此操作将永久删除你的所有历史通知记录，不可恢复。
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter className="gap-2">
            <AlertDialogCancel className="rounded-xl font-bold h-10 text-xs">取消</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => { clearAll(); setIsOpen(false); }}
              className="rounded-xl bg-red-600 hover:bg-red-700 text-white font-bold h-10 text-xs"
            >
              确认清除
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

    </DropdownMenu>
  );
};
