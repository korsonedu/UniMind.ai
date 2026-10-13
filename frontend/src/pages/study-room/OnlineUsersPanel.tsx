import React from 'react';
import { Card, CardTitle } from '@/components/ui/card';
import { Clock, CheckCircle } from '@phosphor-icons/react';
import { Avatar, AvatarImage } from '@/components/ui/avatar';
import {
  HoverCard,
  HoverCardContent,
  HoverCardTrigger,
} from '@/components/ui/hover-card';
import { Badge } from '@/components/ui/badge';

interface OnlineUsersPanelProps {
  onlineUsers: any[];
  currentUsername?: string;
}

const OnlineUsersPanel: React.FC<OnlineUsersPanelProps> = ({ onlineUsers, currentUsername }) => {
  return (
    <Card className="um-study-online border-0 shadow-none rounded-none bg-transparent overflow-hidden p-4 min-h-0 flex flex-col">
      <header className="um-study-section-header mb-3 flex items-center justify-between">
        <CardTitle className="text-[13px] font-semibold text-foreground">
          在线人数
        </CardTitle>
        <span className="text-xs tabular-nums text-muted-foreground">{onlineUsers.length}</span>
      </header>
      <div className="flex-1 overflow-y-auto space-y-3 pr-2 scrollbar-none">
        {onlineUsers.map((u: any) => (
          <HoverCard key={u.id || u.username}>
            <HoverCardTrigger asChild>
              <div className="um-study-online-user flex items-center gap-3 p-2 rounded-lg transition-colors cursor-pointer group">
                <div className="relative shrink-0">
                  <Avatar className="h-8 w-8 border border-border transition-colors">
                    <AvatarImage src={u.avatar_url} />
                  </Avatar>
                  <span className="absolute bottom-0 right-0 h-2.5 w-2.5 rounded-full bg-emerald-500 border-2 border-background shadow-sm" />
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-[13px] font-medium text-foreground truncate">
                    {u.nickname || u.username}{' '}
                    {u.username === currentUsername && '(你)'}
                  </p>
                  <p className="text-xs text-muted-foreground truncate mt-0.5">
                    {u.current_task || '在线中'}
                  </p>
                </div>
              </div>
            </HoverCardTrigger>
            <HoverCardContent
              side="left"
              className="um-study-hover-card w-80 p-5 z-50 text-left text-foreground"
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
                        {`今日专注: ${u.today_focused_minutes} min`}
                      </span>
                    </div>
                    <div className="flex items-center gap-2 text-muted-foreground">
                      <CheckCircle className="h-3.5 w-3.5" />
                      <span className="label-apple">
                        {`今日已完成: ${u.today_completed_tasks?.length || 0} tasks`}
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
