import React, { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
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

const rankBadge = (rank: number) => {
  if (rank === 1) return <Trophy className="h-4 w-4 text-amber-500 fill-amber-500" aria-hidden="true" />;
  if (rank === 2) return <Medal className="h-4 w-4 text-slate-400 fill-slate-400" aria-hidden="true" />;
  if (rank === 3) return <Medal className="h-4 w-4 text-orange-600 fill-orange-600" aria-hidden="true" />;
  return <span className="text-[11px] font-black text-muted-foreground tabular-nums w-4 text-center">{rank}</span>;
};

export const EloPopover: React.FC = () => {
  const { user } = useAuthStore();
  const { t } = useTranslation('elo');
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
          aria-label="ELO score and ranking"
          className={cn(
            "flex items-center gap-2 px-3.5 py-1.5 bg-card rounded-full shadow-sm border border-border",
            "hover:bg-muted hover:border-primary/30 transition-colors duration-200 cursor-pointer",
            "focus-visible:ring-2 focus-visible:ring-primary/20 focus-visible:outline-none",
            open && "border-primary/40 bg-muted"
          )}
        >
          <Sparkles className="h-3.5 w-3.5 text-amber-500 fill-amber-500" aria-hidden="true" />
          <span className="text-xs font-bold text-foreground">{user?.elo_score}</span>
          <span className="text-[10px] font-semibold text-muted-foreground">| {points}</span>
          <HelpCircle className="h-3 w-3 text-muted-foreground/50" aria-hidden="true" />
        </button>
      </PopoverTrigger>
      <PopoverContent
        align="end"
        sideOffset={8}
        className="w-[360px] rounded-2xl p-0 bg-card/95 backdrop-blur-xl border-border shadow-lg overflow-hidden"
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
            <Trophy className="h-3.5 w-3.5 inline mr-1.5" aria-hidden="true" />
            {t('rankingTab')}
          </button>
          <button
            className={cn(
              "flex-1 text-xs font-bold py-3 text-center transition-colors",
              activeTab === 'points' ? "text-foreground border-b-2 border-amber-500" : "text-muted-foreground hover:text-foreground"
            )}
            onClick={() => setActiveTab('points')}
          >
            <Coins className="h-3.5 w-3.5 inline mr-1.5" />
            {t('pointsTab')}
          </button>
        </div>

        {/* Ranking Tab */}
        {activeTab === 'ranking' && (
          <>
            <div className="px-5 pt-5 pb-3">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-[11px] font-bold text-muted-foreground uppercase tracking-[0.15em]">{t('eloScore')}</p>
                  <p className="text-2xl font-black text-foreground tracking-tight">{user?.elo_score}</p>
                </div>
                <div className="h-12 w-12 rounded-2xl bg-amber-500/10 flex items-center justify-center">
                  <Sparkles className="h-6 w-6 text-amber-500 fill-amber-500" />
                </div>
              </div>
              {currentUserInList && (
                <p className="text-[11px] text-muted-foreground mt-1">
                  {t('rankOfTotal', { rank: currentUserRank, total: ranking.length })}
                </p>
              )}
              <p className="text-[11px] text-muted-foreground leading-relaxed mt-2">
                {t('eloDescription')}
              </p>
            </div>

            <div className="border-t border-border" />

            <div className="px-1 py-2">
              <div className="flex items-center gap-2 px-4 pb-2">
                <Building2 className="h-3.5 w-3.5 text-muted-foreground" />
                <span className="text-[11px] font-bold text-muted-foreground uppercase tracking-[0.15em]">{t('institutionRank')}</span>
              </div>

              {!hasInstitution && (
                <div className="px-4 py-6 text-center">
                  <Building2 className="h-8 w-8 text-muted-foreground/30 mx-auto mb-2" />
                  <p className="text-xs font-bold text-muted-foreground">{t('noInstitution')}</p>
                  <p className="text-[10px] text-muted-foreground/60 mt-1">{t('noInstitutionDesc')}</p>
                </div>
              )}

              {hasInstitution && loading && (
                <div className="flex items-center justify-center py-8" aria-live="polite" aria-busy="true">
                  <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
                </div>
              )}

              {hasInstitution && error === 'failed' && (
                <div className="px-4 py-6 text-center" aria-live="polite">
                  <p className="text-xs text-muted-foreground">{t('rankError')}</p>
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
                          {isMe && <span className="text-[10px] text-muted-foreground ml-1">{t('self')}</span>}
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
                      <div className="text-[10px] text-muted-foreground/60 mb-1">…</div>
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
                          <span className="text-[10px] text-muted-foreground ml-1">{t('self')}</span>
                        </span>
                        <span className="text-xs font-black tabular-nums text-primary">{user?.elo_score}</span>
                      </div>
                    </div>
                  )}
                </div>
              )}

              {hasInstitution && !loading && !error && ranking.length === 0 && (
                <div className="px-4 py-6 text-center">
                  <p className="text-xs text-muted-foreground">{t('noRankingData')}</p>
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
                  <p className="text-[11px] font-bold text-muted-foreground uppercase tracking-[0.15em]">{t('availablePoints')}</p>
                  <p className="text-2xl font-black text-foreground tracking-tight">{points}</p>
                </div>
                <div className="h-12 w-12 rounded-2xl bg-emerald-500/10 flex items-center justify-center">
                  <Coins className="h-6 w-6 text-emerald-500" />
                </div>
              </div>
              <p className="text-[11px] text-muted-foreground leading-relaxed mt-2">
                {t('pointsEarnDesc')}
              </p>
            </div>

            <div className="border-t border-border" />

            {/* Pricing reference */}
            <div className="px-5 py-3">
              <div className="flex items-center gap-2 mb-2">
                <HelpCircle className="h-3.5 w-3.5 text-muted-foreground" />
                <span className="text-[11px] font-bold text-muted-foreground uppercase tracking-[0.15em]">{t('whatCanPointsDo')}</span>
              </div>
              <div className="space-y-1.5">
                <div className="flex justify-between text-[11px]">
                  <span className="text-muted-foreground">{t('aiSession')}</span>
                  <span className="font-bold text-foreground tabular-nums">{t('aiSessionCost', { cost: 30 })}</span>
                </div>
                <div className="flex justify-between text-[11px]">
                  <span className="text-muted-foreground">{t('mockInterview')}</span>
                  <span className="font-bold text-foreground tabular-nums">{t('mockInterviewCost')}</span>
                </div>
                <div className="flex justify-between text-[11px]">
                  <span className="text-muted-foreground">{t('resumeOptimization')}</span>
                  <span className="font-bold text-foreground tabular-nums">{t('resumeOptimizationCost')}</span>
                </div>
              </div>
            </div>

            <div className="border-t border-border" />

            {/* How to earn */}
            <div className="px-5 py-3">
              <div className="flex items-center gap-2 mb-2">
                <ArrowUpRight className="h-3.5 w-3.5 text-emerald-500" />
                <span className="text-[11px] font-bold text-muted-foreground uppercase tracking-[0.15em]">{t('howToEarnPoints')}</span>
              </div>
              <div className="space-y-1">
                <p className="text-[11px] text-muted-foreground">• {t('earnRule1')}</p>
                <p className="text-[11px] text-muted-foreground">• {t('earnRule2')}</p>
                <p className="text-[11px] text-muted-foreground">• {t('earnRule3')}</p>
              </div>
            </div>

            <div className="border-t border-border" />

            {/* Recent ledger */}
            <div className="px-1 py-2">
              <div className="flex items-center gap-2 px-4 pb-2">
                <History className="h-3.5 w-3.5 text-muted-foreground" />
                <span className="text-[11px] font-bold text-muted-foreground uppercase tracking-[0.15em]">{t('recentLedger')}</span>
              </div>

              {ledgerLoading && (
                <div className="flex items-center justify-center py-6" aria-live="polite" aria-busy="true">
                  <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
                </div>
              )}

              {!ledgerLoading && ledger.length === 0 && (
                <div className="px-4 py-4 text-center">
                  <p className="text-[11px] text-muted-foreground">{t('noLedger')}</p>
                  <p className="text-[10px] text-muted-foreground/60 mt-1">{t('noLedgerDesc')}</p>
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
                          {t(`ledger.reasons.${entry.reason}`, entry.reason)}
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
