import React from 'react';
import { useTranslation } from 'react-i18next';
import { Card } from '@/components/ui/card';
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar';
import { Activity } from 'lucide-react';
import { cn } from '@/lib/utils';

interface LeaderboardProps {
  leaderboard: any[];
}

export const Leaderboard: React.FC<LeaderboardProps> = ({ leaderboard }) => {
  const { t } = useTranslation('testLadder');
  return (
    <div className="space-y-6 pt-6">
      <div className="flex items-center justify-between px-4">
        <div className="space-y-1">
          <h3 className="text-2xl font-black text-foreground tracking-tight">{t('leaderboard.title')}</h3>
          <p className="text-[11px] font-medium text-muted-foreground leading-none">ELO Ranking</p>
        </div>
      </div>
      <Card className="border border-border shadow-sm rounded-[2.5rem] bg-card overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="border-b border-border bg-muted/30">
                <th className="px-12 py-6 text-[13px] font-bold uppercase tracking-[0.2em] text-muted-foreground">{t('leaderboard.rank')}</th>
                <th className="px-12 py-6 text-[13px] font-bold uppercase tracking-[0.2em] text-muted-foreground">{t('leaderboard.userInfo')}</th>
                <th className="px-12 py-6 text-[13px] font-bold uppercase tracking-[0.2em] text-muted-foreground text-center">{t('leaderboard.eloScore')}</th>
                <th className="px-12 py-6 text-[13px] font-bold uppercase tracking-[0.2em] text-muted-foreground text-right">{t('leaderboard.activity')}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {leaderboard.map((u, i) => (
                <tr key={u.id} className="group hover:bg-muted/50 transition-all duration-300 text-left">
                  <td className="px-12 py-8">
                    {i < 3 ? (
                      <div className={cn("h-9 w-9 rounded-2xl flex items-center justify-center font-black text-xs shadow-sm", i === 0 ? "bg-indigo-600 text-white shadow-indigo-200" : i === 1 ? "bg-muted text-foreground" : "bg-orange-100 text-orange-600")}>{i + 1}</div>
                    ) : <span className="px-3 text-sm font-black text-muted-foreground">{i + 1}</span>}
                  </td>
                  <td className="px-12 py-8">
                    <div className="flex items-center gap-5">
                      <div className="relative">
                        <Avatar className="h-12 w-12 border border-border shadow-sm group-hover:ring-8 ring-indigo-500/5 transition-all duration-500"><AvatarImage src={u.avatar_url} /><AvatarFallback className="font-bold text-xs">{(u.nickname || u.username)[0]}</AvatarFallback></Avatar>
                        {i === 0 && <div className="absolute -top-1.5 -right-1.5 h-6 w-6 bg-indigo-600 rounded-xl border-4 border-white flex items-center justify-center text-[11px] text-white shadow-sm">🏆</div>}
                      </div>
                      <div className="flex flex-col text-left"><span className="font-bold text-base text-foreground tracking-tight">{u.nickname || u.username}</span><span className="text-[11px] font-bold text-muted-foreground uppercase tracking-widest">{u.role}</span></div>
                    </div>
                  </td>
                  <td className="px-12 py-8 text-center"><span className="inline-flex px-5 py-1.5 rounded-full bg-muted text-sm font-black text-foreground tabular-nums">{u.elo_score}</span></td>
                  <td className="px-12 py-8 text-right"><Activity className="h-5 w-5 opacity-5 ml-auto group-hover:opacity-100 group-hover:text-indigo-500 transition-all duration-500" /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
};
