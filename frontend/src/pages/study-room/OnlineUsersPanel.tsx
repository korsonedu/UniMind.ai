import React from 'react';
import { Card, CardTitle } from '@/components/ui/card';
import { Users, Clock, CheckCircle } from '@phosphor-icons/react';
import { Avatar, AvatarImage } from '@/components/ui/avatar';
import {
  HoverCard,
  HoverCardContent,
  HoverCardTrigger,
} from '@/components/ui/hover-card';
import { Badge } from '@/components/ui/badge';
import { useTranslation } from 'react-i18next';

interface OnlineUsersPanelProps {
  onlineUsers: any[];
  currentUsername?: string;
}

const OnlineUsersPanel: React.FC<OnlineUsersPanelProps> = ({ onlineUsers, currentUsername }) => {
  const { t } = useTranslation('studyRoom');

  return (
    <Card className="border-none shadow-sm rounded-2xl md:rounded-3xl bg-card overflow-hidden p-4 md:p-6 md:flex-1 min-h-0 flex flex-col border border-border">
      <header className="mb-4 flex items-center justify-between">
        <CardTitle className="text-[13px] font-bold uppercase tracking-widest text-muted-foreground">
          {t('onlineUsers.title')}
        </CardTitle>
        <Users className="h-4 w-4 text-muted-foreground opacity-20" />
      </header>
      <div className="flex-1 overflow-y-auto space-y-3 pr-2 scrollbar-none">
        {onlineUsers.map((u: any) => (
          <HoverCard key={u.id || u.username}>
            <HoverCardTrigger asChild>
              <div className="flex items-center gap-3 p-2.5 rounded-2xl hover:bg-muted transition-all cursor-pointer border border-transparent hover:border-border group">
                <div className="relative shrink-0">
                  <Avatar className="h-9 w-9 border border-border shadow-sm group-hover:ring-2 ring-emerald-500/20 transition-all">
                    <AvatarImage src={u.avatar_url} />
                  </Avatar>
                  <span className="absolute bottom-0 right-0 h-2.5 w-2.5 rounded-full bg-emerald-500 border-2 border-background shadow-sm" />
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-xs font-bold text-foreground truncate">
                    {u.nickname || u.username}{' '}
                    {u.username === currentUsername && t('onlineUsers.self')}
                  </p>
                  <p className="text-[11px] text-emerald-600 font-bold truncate mt-0.5 uppercase tracking-tight">
                    {u.current_task || t('onlineUsers.online')}
                  </p>
                </div>
              </div>
            </HoverCardTrigger>
            <HoverCardContent
              side="left"
              className="w-80 rounded-apple-2xl p-6 border-none shadow-lg bg-card/95 backdrop-blur-xl z-50 text-left text-foreground"
            >
              <div className="flex space-x-4">
                <Avatar className="h-12 w-12 border border-border shadow-sm">
                  <AvatarImage src={u.avatar_url} />
                </Avatar>
                <div className="space-y-3 flex-1 text-left">
                  <div className="flex justify-between items-center">
                    <h4 className="text-sm font-bold">
                      {u.nickname || u.username}
                    </h4>
                    <Badge
                      variant="outline"
                      className="text-[11px] border-emerald-500/20 text-emerald-600 rounded-full"
                    >
                      ELO {u.elo_score}
                    </Badge>
                  </div>
                  <div className="space-y-2 pt-2 border-t border-border">
                    <div className="flex items-center gap-2 text-muted-foreground">
                      <Clock className="h-3.5 w-3.5" />
                      <span className="label-apple">
                        {t('onlineUsers.todayFocus', { minutes: u.today_focused_minutes })}
                      </span>
                    </div>
                    <div className="flex items-center gap-2 text-muted-foreground">
                      <CheckCircle className="h-3.5 w-3.5" />
                      <span className="label-apple">
                        {t('onlineUsers.todayCompleted', { count: u.today_completed_tasks?.length || 0 })}
                      </span>
                    </div>
                  </div>
                </div>
              </div>
            </HoverCardContent>
          </HoverCard>
        ))}
      </div>
    </Card>
  );
};

export { OnlineUsersPanel };
