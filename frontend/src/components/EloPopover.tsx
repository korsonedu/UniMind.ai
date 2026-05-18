import React, { useState, useEffect } from 'react';
import { Sparkles, Trophy, Medal, Loader2, Building2, Coins, HelpCircle, ArrowUpRight, ArrowDownRight, History } from 'lucide-react';
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover';
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar';
import { cn } from '@/lib/utils';
import { useAuthStore } from '@/store/useAuthStore';
import api from '@/lib/api';

interface RankedUser {
  id: number;
  username: string;
  nickname: string;
  elo_score: number;
  avatar_url: string;
  email: string;
  institution_role: string;
}

interface LedgerEntry {
  id: number;
  amount: number;
  balance_after: number;
  reason: string;
  description: string;
  created_at: string;
}

const REASON_LABELS: Record<string, string> = {
  exam_complete: '测验完成',
  question_graded: '题目判分',
  course_complete: '课程完成',
  course_reward_claim: '课程奖励',
  shop_redeem: '积分兑换',
  admin_adjust: '管理员调整',
  elo_reset: 'ELO重置',
};

const rankBadge = (rank: number) => {
  if (rank === 1) return <Trophy className="h-4 w-4 text-amber-500 fill-amber-500" />;
  if (rank === 2) return <Medal className="h-4 w-4 text-slate-400 fill-slate-400" />;
  if (rank === 3) return <Medal className="h-4 w-4 text-orange-600 fill-orange-600" />;
  return <span className="text-[11px] font-black text-muted-foreground tabular-nums w-4 text-center">{rank}</span>;
};

export const EloPopover: React.FC = () => {
  const { user } = useAuthStore();
  const [ranking, setRanking] = useState<RankedUser[]>([]);
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<'ranking' | 'points'>('ranking');
  const [ledger, setLedger] = useState<LedgerEntry[]>([]);
  const [ledgerLoading, setLedgerLoading] = useState(false);

  const hasInstitution = !!user?.institution_id;

  const fetchRanking = async () => {
    if (!hasInstitution) return;
    setLoading(true);
    setError(null);
    try {
      const res = await api.get('/users/institution/me/students/ranking/');
      setRanking(res.data || []);
    } catch {
      setError('failed');
    } finally {
      setLoading(false);
    }
  };

  const fetchLedger = async () => {
    setLedgerLoading(true);
    try {
      const res = await api.get('/users/me/points/ledger/', { params: { page: 1 } });
      setLedger(res.data.results?.slice(0, 10) || []);
    } catch {
      setLedger([]);
    } finally {
      setLedgerLoading(false);
    }
  };

  useEffect(() => {
    if (open && user) {
      fetchRanking();
    }
  }, [open, user?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (open && user && activeTab === 'points' && ledger.length === 0) {
      fetchLedger();
    }
  }, [open, activeTab, user?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  const currentUserRank = ranking.findIndex(u => u.id === user?.id) + 1;
  const currentUserInList = currentUserRank > 0;
  const points = user?.elo_points ?? 0;

  return (
    <Popover open={open} onOpenChange={(v) => { setOpen(v); if (!v) setActiveTab('ranking'); }}>
      <PopoverTrigger asChild>
        <button
          className={cn(
            "flex items-center gap-2 px-3.5 py-1.5 bg-card rounded-full shadow-sm border border-border",
            "hover:bg-muted hover:border-primary/30 transition-all duration-200 cursor-pointer",
            "focus:outline-none focus:ring-2 focus:ring-primary/20",
            open && "border-primary/40 bg-muted"
          )}
        >
          <Sparkles className="h-3.5 w-3.5 text-amber-500 fill-amber-500" />
          <span className="text-xs font-bold text-foreground">{user?.elo_score}</span>
          <span className="text-[10px] font-semibold text-muted-foreground">| {points}</span>
          <HelpCircle className="h-3 w-3 text-muted-foreground/50" />
        </button>
      </PopoverTrigger>
      <PopoverContent
        align="end"
        sideOffset={8}
        className="w-[360px] rounded-2xl p-0 bg-card/95 backdrop-blur-xl border-border shadow-2xl overflow-hidden"
      >
        {/* Tabs */}
        <div className="flex border-b border-border">
          <button
            className={cn(
              "flex-1 text-xs font-bold py-3 text-center transition-colors",
              activeTab === 'ranking' ? "text-foreground border-b-2 border-amber-500" : "text-muted-foreground hover:text-foreground"
            )}
            onClick={() => setActiveTab('ranking')}
          >
            <Trophy className="h-3.5 w-3.5 inline mr-1.5" />
            ELO 排名
          </button>
          <button
            className={cn(
              "flex-1 text-xs font-bold py-3 text-center transition-colors",
              activeTab === 'points' ? "text-foreground border-b-2 border-amber-500" : "text-muted-foreground hover:text-foreground"
            )}
            onClick={() => setActiveTab('points')}
          >
            <Coins className="h-3.5 w-3.5 inline mr-1.5" />
            积分
          </button>
        </div>

        {/* Ranking Tab */}
        {activeTab === 'ranking' && (
          <>
            <div className="px-5 pt-5 pb-3">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-[11px] font-bold text-muted-foreground uppercase tracking-[0.15em]">ELO 评分</p>
                  <p className="text-2xl font-black text-foreground tracking-tight">{user?.elo_score}</p>
                </div>
                <div className="h-12 w-12 rounded-2xl bg-amber-500/10 flex items-center justify-center">
                  <Sparkles className="h-6 w-6 text-amber-500 fill-amber-500" />
                </div>
              </div>
              {currentUserInList && (
                <p className="text-[11px] text-muted-foreground mt-1">
                  本机构排名第 <span className="font-black text-foreground">{currentUserRank}</span> / {ranking.length} 人
                </p>
              )}
              <p className="text-[11px] text-muted-foreground leading-relaxed mt-2">
                ELO 评分根据答题正确率、题目难度动态计算，反应你的真实学术水平。
              </p>
            </div>

            <div className="border-t border-border" />

            <div className="px-1 py-2">
              <div className="flex items-center gap-2 px-4 pb-2">
                <Building2 className="h-3.5 w-3.5 text-muted-foreground" />
                <span className="text-[11px] font-bold text-muted-foreground uppercase tracking-[0.15em]">机构排名</span>
              </div>

              {!hasInstitution && (
                <div className="px-4 py-6 text-center">
                  <Building2 className="h-8 w-8 text-muted-foreground/30 mx-auto mb-2" />
                  <p className="text-xs font-bold text-muted-foreground">暂未加入机构</p>
                  <p className="text-[10px] text-muted-foreground/60 mt-1">加入机构后可查看内部排名</p>
                </div>
              )}

              {hasInstitution && loading && (
                <div className="flex items-center justify-center py-8">
                  <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
                </div>
              )}

              {hasInstitution && error === 'failed' && (
                <div className="px-4 py-6 text-center">
                  <p className="text-xs text-muted-foreground">排名加载失败，请稍后重试</p>
                </div>
              )}

              {hasInstitution && !loading && !error && ranking.length > 0 && (
                <div className="max-h-[300px] overflow-y-auto">
                  {ranking.slice(0, 15).map((u, i) => {
                    const rank = i + 1;
                    const isMe = u.id === user?.id;
                    return (
                      <div
                        key={u.id}
                        className={cn(
                          "flex items-center gap-3 px-4 py-2 mx-1 rounded-xl transition-colors",
                          isMe && "bg-primary/5 border border-primary/10"
                        )}
                      >
                        <div className="w-6 flex justify-center">{rankBadge(rank)}</div>
                        <Avatar className="h-7 w-7 border border-border">
                          <AvatarImage src={u.avatar_url} />
                          <AvatarFallback className="text-[9px] font-bold">{(u.nickname || u.username)[0]}</AvatarFallback>
                        </Avatar>
                        <span className={cn(
                          "flex-1 text-xs font-bold truncate",
                          isMe ? "text-primary" : "text-foreground"
                        )}>
                          {u.nickname || u.username}
                          {isMe && <span className="text-[10px] text-muted-foreground ml-1">(你)</span>}
                        </span>
                        <span className={cn(
                          "text-xs font-black tabular-nums",
                          isMe ? "text-primary" : "text-muted-foreground"
                        )}>
                          {u.elo_score}
                        </span>
                      </div>
                    );
                  })}

                  {!currentUserInList && (
                    <div className="px-4 py-3 text-center">
                      <div className="text-[10px] text-muted-foreground/60 mb-1">...</div>
                      <div className="flex items-center gap-3 px-4 py-2 mx-1 rounded-xl bg-primary/5 border border-primary/10">
                        <div className="w-6 flex justify-center">
                          <span className="text-[11px] font-black text-muted-foreground tabular-nums">-</span>
                        </div>
                        <Avatar className="h-7 w-7 border border-border">
                          <AvatarImage src={user?.avatar_url} />
                          <AvatarFallback className="text-[9px] font-bold">{user?.username?.[0]}</AvatarFallback>
                        </Avatar>
                        <span className="flex-1 text-xs font-bold text-primary truncate">
                          {user?.nickname || user?.username}
                          <span className="text-[10px] text-muted-foreground ml-1">(你)</span>
                        </span>
                        <span className="text-xs font-black tabular-nums text-primary">{user?.elo_score}</span>
                      </div>
                    </div>
                  )}
                </div>
              )}

              {hasInstitution && !loading && !error && ranking.length === 0 && (
                <div className="px-4 py-6 text-center">
                  <p className="text-xs text-muted-foreground">暂无排名数据</p>
                </div>
              )}
            </div>
          </>
        )}

        {/* Points Tab */}
        {activeTab === 'points' && (
          <>
            {/* Points balance */}
            <div className="px-5 pt-5 pb-3">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-[11px] font-bold text-muted-foreground uppercase tracking-[0.15em]">可用积分</p>
                  <p className="text-2xl font-black text-foreground tracking-tight">{points}</p>
                </div>
                <div className="h-12 w-12 rounded-2xl bg-emerald-500/10 flex items-center justify-center">
                  <Coins className="h-6 w-6 text-emerald-500" />
                </div>
              </div>
              <p className="text-[11px] text-muted-foreground leading-relaxed mt-2">
                刷题和看课可获得积分，积分可用于解锁 AI 功能。学得越多，能用越多。
              </p>
            </div>

            <div className="border-t border-border" />

            {/* Pricing reference */}
            <div className="px-5 py-3">
              <div className="flex items-center gap-2 mb-2">
                <HelpCircle className="h-3.5 w-3.5 text-muted-foreground" />
                <span className="text-[11px] font-bold text-muted-foreground uppercase tracking-[0.15em]">积分能做什么</span>
              </div>
              <div className="space-y-1.5">
                <div className="flex justify-between text-[11px]">
                  <span className="text-muted-foreground">AI 助教会话（不限轮数）</span>
                  <span className="font-bold text-foreground tabular-nums">30 积分</span>
                </div>
                <div className="flex justify-between text-[11px]">
                  <span className="text-muted-foreground">模拟面试（全场，含分析）</span>
                  <span className="font-bold text-foreground tabular-nums">50 积分</span>
                </div>
                <div className="flex justify-between text-[11px]">
                  <span className="text-muted-foreground">简历优化</span>
                  <span className="font-bold text-foreground tabular-nums">15 积分</span>
                </div>
              </div>
            </div>

            <div className="border-t border-border" />

            {/* How to earn */}
            <div className="px-5 py-3">
              <div className="flex items-center gap-2 mb-2">
                <ArrowUpRight className="h-3.5 w-3.5 text-emerald-500" />
                <span className="text-[11px] font-bold text-muted-foreground uppercase tracking-[0.15em]">如何获得积分</span>
              </div>
              <div className="space-y-1">
                <p className="text-[11px] text-muted-foreground">• 刷题 ELO 上涨时 1:1 获得</p>
                <p className="text-[11px] text-muted-foreground">• 完成视频课程 +50 积分</p>
                <p className="text-[11px] text-muted-foreground">• 每日登录 +5 积分</p>
              </div>
            </div>

            <div className="border-t border-border" />

            {/* Recent ledger */}
            <div className="px-1 py-2">
              <div className="flex items-center gap-2 px-4 pb-2">
                <History className="h-3.5 w-3.5 text-muted-foreground" />
                <span className="text-[11px] font-bold text-muted-foreground uppercase tracking-[0.15em]">最近流水</span>
              </div>

              {ledgerLoading && (
                <div className="flex items-center justify-center py-6">
                  <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
                </div>
              )}

              {!ledgerLoading && ledger.length === 0 && (
                <div className="px-4 py-4 text-center">
                  <p className="text-[11px] text-muted-foreground">暂无积分记录</p>
                  <p className="text-[10px] text-muted-foreground/60 mt-1">开始刷题获得第一笔积分吧</p>
                </div>
              )}

              {!ledgerLoading && ledger.length > 0 && (
                <div className="max-h-[200px] overflow-y-auto">
                  {ledger.map((entry) => (
                    <div key={entry.id} className="flex items-center gap-3 px-4 py-2 mx-1 rounded-lg">
                      <div className={cn(
                        "h-7 w-7 rounded-lg flex items-center justify-center shrink-0",
                        entry.amount > 0 ? "bg-emerald-500/10" : "bg-red-500/10"
                      )}>
                        {entry.amount > 0
                          ? <ArrowUpRight className="h-3.5 w-3.5 text-emerald-500" />
                          : <ArrowDownRight className="h-3.5 w-3.5 text-red-500" />
                        }
                      </div>
                      <div className="flex-1 min-w-0">
                        <p className="text-[11px] font-bold text-foreground truncate">
                          {REASON_LABELS[entry.reason] || entry.reason}
                        </p>
                        {entry.description && (
                          <p className="text-[10px] text-muted-foreground truncate">{entry.description}</p>
                        )}
                      </div>
                      <span className={cn(
                        "text-xs font-black tabular-nums shrink-0",
                        entry.amount > 0 ? "text-emerald-500" : "text-red-500"
                      )}>
                        {entry.amount > 0 ? '+' : ''}{entry.amount}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </>
        )}
      </PopoverContent>
    </Popover>
  );
};
