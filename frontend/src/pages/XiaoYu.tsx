import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { Target, CalendarCheck, CheckCircle, ChartBar, BookOpen, Lightbulb, ChatCircleText, Brain, Stethoscope, WarningCircle, PlayCircle, Fire, Trophy } from '@phosphor-icons/react';
import AgentChatLayout from '@/components/AgentChatLayout';
import SessionSidebar from '@/components/SessionSidebar';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import api from '@/lib/api';
import type { Bot, ConversationSession } from '@/hooks/useAgentConversation';
import { useXiaoYuStore } from '@/store/useXiaoYuStore';

const SKILL_ICONS = [Target, CalendarCheck, CheckCircle, ChartBar, BookOpen, Lightbulb, ChatCircleText, Brain, Stethoscope, WarningCircle, PlayCircle];

interface DashPlan {
  id: number; title: string;
  total_tasks: number; completed_tasks: number;
  progress_pct: number; expected_progress_pct?: number | null;
  progress_delta?: number | null;
  total_days?: number; elapsed_days?: number;
  goal?: string; deadline?: string | null; subject?: string;
  target_score?: number | null; current_level?: string;
  teaching_plan_id?: number; teaching_plan_title?: string;
}
interface DashStats {
  streak_days: number; weekly_activity: number;
  accuracy: number; total_attempted: number;
  heatmap_days: { date: string; count: number }[];
  is_new_user: boolean;
  today_checked_in: boolean;
  checkin_streak: number;
  checkin_history: { date: string; checked_in: boolean }[];
  unlocked_achievement_count: number;
  next_achievements: { key: string; name: string; description: string; icon: string; category: string }[];
}
interface DashReviews { due_count: number; }
interface DashExam { id: number; total_score: number; max_score: number; percentage: number; elo_change: number; created_at: string; }
interface DashData {
  plan: DashPlan | null;
  stats: DashStats;
  reviews: DashReviews;
  exams: DashExam[];
}

export const XiaoYu: React.FC = () => {
  const navigate = useNavigate();
  const { t } = useTranslation('xiaoyu');
  const sharedConversationId = useXiaoYuStore(s => s.conversationId);
  const [dash, setDash] = useState<DashData | null>(null);
  const [dashError, setDashError] = useState(false);
  const [hasConversation, setHasConversation] = useState(false);

  const fetchDashboard = () => {
    setDashError(false);
    api.get('/ai/dashboard/').then(r => {
      if (r.data) setDash(r.data);
    }).catch((e: any) => {
      console.error('Dashboard load failed:', e?.response?.status, e?.response?.data || e?.message);
      setDashError(true);
    });
  };

  useEffect(() => {
    fetchDashboard();
  }, []);

  const rawSkills = t('skills', { returnObjects: true }) as Array<{ label: string; prompt: string }>;
  const SKILLS = rawSkills.map((s, i) => ({ icon: SKILL_ICONS[i], label: s.label, prompt: s.prompt }));

  const stats = dash?.stats;
  const plan = dash?.plan;
  const reviews = dash?.reviews;
  const lastExam = dash?.exams?.[0];

  const [checkingIn, setCheckingIn] = useState(false);
  const [checkedIn, setCheckedIn] = useState(false);

  useEffect(() => {
    if (stats?.today_checked_in !== undefined) setCheckedIn(stats.today_checked_in);
  }, [stats?.today_checked_in]);

  const handleCheckIn = async () => {
    setCheckingIn(true);
    try {
      await api.post('/users/me/checkin/');
      // Refetch dashboard to update streak + checked-in status
      const r = await api.get('/ai/dashboard/');
      if (r.data) {
        setDash(r.data);
      }
    } catch (e: any) {
      console.error('Checkin failed:', e?.response?.status, e?.response?.data || e?.message);
    } finally {
      setCheckingIn(false);
    }
  };

  /* Heatmap helper — horizontal row, newest on right */
  const renderHeatmap = (days: { date: string; count: number }[]) => {
    return (
      <div className="flex items-center gap-[3px] flex-wrap">
        {days.map((d, i) => {
          const level = d.count === 0 ? 0 : d.count <= 3 ? 1 : d.count <= 8 ? 2 : d.count <= 15 ? 3 : 4;
          return (
            <div
              key={i}
              className={cn(
                'w-[14px] h-[14px] rounded-[2px]',
                level === 0 && 'bg-muted/30',
                level === 1 && 'bg-xiaoyu-100',
                level === 2 && 'bg-xiaoyu-200',
                level === 3 && 'bg-xiaoyu-400',
                level === 4 && 'bg-xiaoyu-500',
              )}
              title={`${d.date}: ${d.count} 次练习`}
            />
          );
        })}
      </div>
    );
  };

  const landingBanner = !hasConversation ? (
    stats ? (
    <div className="animate-in fade-in duration-500">
      {stats.is_new_user ? (
        /* New user: diagnostic CTA + value-prop pills */
        <div className="space-y-8">
          <div className="rounded-2xl bg-card border border-border/40 p-8 text-center">
            <div className="w-14 h-14 rounded-2xl bg-xiaoyu-50 dark:bg-xiaoyu-500/20 flex items-center justify-center mx-auto mb-4">
              <Stethoscope className="w-7 h-7 text-xiaoyu-500 dark:text-xiaoyu-300" />
            </div>
            <h3 className="text-lg font-bold text-foreground">{t('newUserTitle')}</h3>
            <p className="text-sm text-muted-foreground mt-1.5 mb-5 max-w-sm mx-auto leading-relaxed">
              {t('newUserDesc')}
            </p>
            <Button size="sm" onClick={() => navigate('/diagnostic')} className="rounded-full px-6 h-9 bg-xiaoyu-500 hover:bg-xiaoyu-600 text-white">
              {t('startDiagnostic')}
            </Button>
          </div>

          <div className="flex flex-wrap justify-center gap-3">
            {[
              { icon: Target, label: t('valuePropWeakPoints') },
              { icon: Brain, label: t('valuePropPath') },
              { icon: ChartBar, label: t('valuePropProgress') },
            ].map((item) => (
              <div key={item.label} className="flex items-center gap-2 px-4 py-2.5 rounded-xl bg-muted/40 border border-border/30">
                <item.icon className="w-4 h-4 text-xiaoyu-500/60 dark:text-xiaoyu-300/60" />
                <span className="text-[12px] font-medium text-foreground/70">{item.label}</span>
              </div>
            ))}
          </div>
        </div>

      ) : (
        /* Returning user: 2x2 asymmetric Bento Grid */
        <div className="space-y-4">
          {/* Row 1: streak + accuracy */}
          <div className="grid grid-cols-1 md:grid-cols-[1.2fr_1fr] gap-4">
            {/* Streak + check-in */}
            <div className="rounded-2xl bg-card border border-border/40 p-5 flex flex-col justify-between">
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2.5">
                  <div className="w-8 h-8 rounded-lg bg-xiaoyu-50 dark:bg-xiaoyu-500/20 flex items-center justify-center shrink-0">
                    <Fire className="w-4 h-4 text-xiaoyu-500 dark:text-xiaoyu-300" />
                  </div>
                  <span className="text-[13px] font-semibold text-foreground/80">{t('streakLabel')}</span>
                </div>
                <button
                  onClick={handleCheckIn}
                  disabled={checkedIn || checkingIn}
                  className={cn(
                    'text-[11px] font-semibold px-3 py-1.5 rounded-full transition-all shrink-0',
                    checkedIn
                      ? 'bg-emerald-50 dark:bg-emerald-900/20 text-emerald-600 border border-emerald-200 dark:border-emerald-800'
                      : 'bg-xiaoyu-500 dark:bg-xiaoyu-300 text-white hover:bg-xiaoyu-600 dark:hover:bg-xiaoyu-400',
                    checkingIn && 'opacity-60 pointer-events-none',
                  )}
                >
                  {checkingIn ? t('checkingIn') : checkedIn ? t('checkedIn') : t('checkInToday')}
                </button>
              </div>
              <p className="text-4xl font-black tracking-tighter tabular-nums text-xiaoyu-500 dark:text-xiaoyu-300">
                {stats.streak_days}<span className="text-base font-normal text-muted-foreground ml-1">{t('daysUnit')}</span>
              </p>
              <div className="mt-4 flex flex-wrap items-center gap-x-4 gap-y-1 text-[12px]">
                <span className="text-muted-foreground/60">
                  {t('thisWeek')} <span className="font-semibold text-foreground/70">{stats.weekly_activity}</span> {t('questionsUnit')}
                </span>
                {reviews && reviews.due_count > 0 ? (
                  <span className="text-muted-foreground/60">
                    {t('pendingReview')} <span className="font-semibold text-amber-600">{reviews.due_count}</span> {t('questionsUnit')}
                  </span>
                ) : (
                  <span className="text-muted-foreground/40">{t('noPendingReview')}</span>
                )}
              </div>
            </div>

            {/* Accuracy */}
            <div className="rounded-2xl bg-card border border-border/40 p-5 flex flex-col justify-between">
              <div className="flex items-center gap-2.5 mb-3">
                <div className="w-8 h-8 rounded-lg bg-xiaoyu-50 dark:bg-xiaoyu-500/20 flex items-center justify-center shrink-0">
                  <Trophy className="w-4 h-4 text-xiaoyu-500 dark:text-xiaoyu-300" />
                </div>
                <span className="text-[13px] font-semibold text-foreground/80">{t('accuracyLabel')}</span>
              </div>
              <p className="text-4xl font-black tracking-tighter tabular-nums text-xiaoyu-500 dark:text-xiaoyu-300">
                {stats.accuracy}<span className="text-base font-normal text-muted-foreground ml-0.5">%</span>
              </p>
              <div className="mt-4 flex flex-wrap items-center gap-x-4 gap-y-1 text-[12px]">
                <span className="text-muted-foreground/60">
                  {t('totalQuestions')} <span className="font-semibold text-foreground/70">{stats.total_attempted}</span> {t('questionsUnit')}
                </span>
                {lastExam ? (
                  <span className="text-muted-foreground/60">
                    {t('recentExam')} <span className="font-semibold text-foreground/70">{lastExam.total_score}/{lastExam.max_score}</span>
                    {lastExam.elo_change !== 0 && (
                      <span className={cn('ml-1 font-semibold', lastExam.elo_change >= 0 ? 'text-emerald-600' : 'text-red-500')}>
                        {lastExam.elo_change >= 0 ? '+' : ''}{lastExam.elo_change}
                      </span>
                    )}
                  </span>
                ) : (
                  <span className="text-muted-foreground/40">{t('noExamYet')}</span>
                )}
              </div>
            </div>
          </div>

          {/* Row 2: Learning plan - full width */}
          <div className="rounded-2xl bg-card border border-border/40 p-5">
            {plan ? (
              <div>
                <div className="flex items-center gap-2.5 mb-3">
                  <div className="w-8 h-8 rounded-lg bg-xiaoyu-50 dark:bg-xiaoyu-500/20 flex items-center justify-center shrink-0">
                    <CalendarCheck className="w-4 h-4 text-xiaoyu-500 dark:text-xiaoyu-300" />
                  </div>
                  <span className="text-[13px] font-semibold text-foreground/80 truncate">{plan.title}</span>
                  {plan.progress_delta != null && !Number.isNaN(plan.progress_delta) && plan.progress_delta !== 0 && (
                    <span className={cn('text-[11px] font-semibold ml-auto shrink-0', plan.progress_delta > 0 ? 'text-emerald-600' : 'text-red-500')}>
                      {plan.progress_delta > 0 ? t('ahead') : t('behind')} {Math.abs(plan.progress_delta).toFixed(0)}%
                    </span>
                  )}
                </div>
                {plan.goal && (
                  <p className="text-[12px] text-muted-foreground/60 mb-2">
                    🎯 {plan.goal}
                    {plan.deadline && <span className="ml-2">· 截止 {plan.deadline}</span>}
                  </p>
                )}
                {plan.teaching_plan_title && (
                  <p className="text-[11px] text-muted-foreground/40 mb-2">📋 来自 {plan.teaching_plan_title}</p>
                )}
                <div className="w-full h-1.5 bg-muted/50 rounded-full mb-2 overflow-hidden">
                  <div className="h-full bg-xiaoyu-400 rounded-full transition-all" style={{ width: `${Math.min(plan.progress_pct, 100)}%` }} />
                </div>
                <div className="flex flex-wrap items-center gap-x-6 gap-y-1 text-[12px] text-muted-foreground/60">
                  <span>{t('tasksCompleted')} <span className="font-semibold text-foreground/70">{plan.completed_tasks}/{plan.total_tasks}</span> {t('tasksUnit')}</span>
                  <span>{t('progressLabel')} <span className="font-semibold text-xiaoyu-500 dark:text-xiaoyu-300">{plan.progress_pct}%</span></span>
                  {plan.total_days != null && plan.total_days > 0 && (
                    <span>{t('dayLabel')} <span className="font-semibold text-foreground/70">{plan.elapsed_days}/{plan.total_days}</span> {t('daysLabel')}</span>
                  )}
                </div>
                <div className="mt-3 pt-3 border-t border-border/30 flex gap-2">
                  <Button size="sm" variant="outline" onClick={() => navigate('/plan')} className="h-8 text-[12px] gap-1">
                    {t('adjustPlan')}
                  </Button>
                </div>
              </div>
            ) : (
              <div className="flex flex-col items-center justify-center py-6 text-center">
                <CalendarCheck className="w-6 h-6 text-muted-foreground/15 mb-2" />
                <p className="text-[12px] text-muted-foreground/50">{t('noPlan')}</p>
                <p className="text-[10px] text-muted-foreground/30 mt-0.5">{t('noPlanHint')}</p>
              </div>
            )}
          </div>

          {/* Row 3: Activity heatmap */}
          <div className="rounded-2xl bg-card border border-border/40 p-5">
            <p className="text-[12px] font-semibold text-foreground/70 mb-3">
              {stats.heatmap_days && stats.heatmap_days.length > 0 ? t('heatmapActive') : t('heatmapDefault')}
            </p>
            {stats.heatmap_days && stats.heatmap_days.length > 0 ? (
              <>
                {renderHeatmap(stats.heatmap_days)}
                <div className="flex items-center justify-end gap-1 mt-3 text-[10px] text-muted-foreground/40">
                  <span>{t('heatmapLess')}</span>
                  <div className="w-[10px] h-[10px] rounded-[2px] bg-muted/40 border border-border/20" />
                  <div className="w-[10px] h-[10px] rounded-[2px] bg-xiaoyu-100" />
                  <div className="w-[10px] h-[10px] rounded-[2px] bg-xiaoyu-200" />
                  <div className="w-[10px] h-[10px] rounded-[2px] bg-xiaoyu-400" />
                  <div className="w-[10px] h-[10px] rounded-[2px] bg-xiaoyu-500" />
                  <span>{t('heatmapMore')}</span>
                </div>
              </>
            ) : (
              <p className="text-[12px] text-muted-foreground/40 py-3 text-center">{t('heatmapEmpty')}</p>
            )}
          </div>

          {/* Row 4: Achievements */}
          {stats.next_achievements && stats.next_achievements.length > 0 && (
            <div className="rounded-2xl bg-card border border-border/40 p-5">
              <div className="flex items-center justify-between mb-3">
                <p className="text-[12px] font-semibold text-foreground/70">
                  {t('nextAchievement')}
                  {stats.unlocked_achievement_count > 0 && (
                    <span className="text-muted-foreground/40 ml-1">({t('achievementUnlocked', { count: stats.unlocked_achievement_count })})</span>
                  )}
                </p>
              </div>
              <div className="flex gap-3">
                {stats.next_achievements.map((a) => (
                  <div key={a.key} className="flex items-center gap-2 px-3 py-2 rounded-xl bg-muted/40 border border-border/30 flex-1 min-w-0">
                    <span className="text-lg shrink-0">{a.icon}</span>
                    <div className="min-w-0">
                      <p className="text-[12px] font-semibold text-foreground/80 truncate">{a.name}</p>
                      <p className="text-[10px] text-muted-foreground/50 truncate">{a.description}</p>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
    ) : dashError ? (
      <div className="animate-in fade-in duration-500">
        <div className="rounded-2xl bg-card border border-border/40 p-8 text-center">
          <div className="w-14 h-14 rounded-2xl bg-muted/40 flex items-center justify-center mx-auto mb-4">
            <WarningCircle className="w-7 h-7 text-muted-foreground/50" />
          </div>
          <h3 className="text-lg font-bold text-foreground">{t('dashboardErrorTitle')}</h3>
          <p className="text-sm text-muted-foreground mt-1.5 mb-5 max-w-sm mx-auto leading-relaxed">
            {t('dashboardErrorHint')}
          </p>
          <Button size="sm" variant="outline" onClick={fetchDashboard} className="rounded-full px-6 h-9">
            {t('retry')}
          </Button>
        </div>
      </div>
    ) : (
      <div className="animate-in fade-in duration-500">
        <div className="rounded-2xl bg-card border border-border/40 p-8 flex items-center justify-center">
          <div className="w-5 h-5 border-2 border-xiaoyu-300 border-t-transparent rounded-full animate-spin" />
        </div>
      </div>
    )
  ) : null;

  return (
    <AgentChatLayout
      layout="inline"
      inputTourClass="xiaoyu-input"
      sidebar={(sidebarProps) => (
        <SessionSidebar
          sessions={sidebarProps.sessions}
          activeSessionId={sidebarProps.activeSessionId}
          onSelect={sidebarProps.onLoadSession}
          onDelete={sidebarProps.onDeleteSession}
          onNew={sidebarProps.onNewConversation}
          botDisplayName={sidebarProps.botDisplayName}
        />
      )}
      findBot={(bots) => bots.find((b: Bot) => b.name === '小宇')}
      skills={SKILLS}
      typewriterWords={t('typewriterWords', { returnObjects: true }) as string[]}
      chatPlaceholder={t('chatPlaceholder')}
      resetMessage={t('resetMessage')}
      landingTitle={t('landingTitle')}
      landingDescription={t('landingDesc')}
      botDisplayName={t('botDisplayName')}
      landingBanner={landingBanner}
      onHasConversation={setHasConversation}
      onDeleteSession={() => {}}
      onLoadSession={(session, defaultHandler) => { defaultHandler(session); }}
      onDone={(refreshSessions) => { refreshSessions(); }}
      onStepDone={(step, prev) => prev.map(m =>
        m.toolStep?.call_id === step.call_id ? { ...m, toolStep: step } : m
      )}
      initialConversationId={sharedConversationId}
    />
  );
};

export default XiaoYu;
