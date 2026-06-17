import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Target, CalendarCheck, CheckCircle, ChartBar, BookOpen, Lightbulb, ChatCircleText, Brain, Stethoscope, WarningCircle, PlayCircle, Fire, Trophy } from '@phosphor-icons/react';
import AgentChatLayout from '@/components/AgentChatLayout';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import api from '@/lib/api';
import type { Bot, ConversationSession } from '@/hooks/useAgentConversation';

const SKILLS = [
  { icon: Target, label: '分析薄弱点', prompt: '帮我分析薄弱知识点，给出提升建议' },
  { icon: CalendarCheck, label: '制定学习计划', prompt: '根据我的现状制定一份学习计划' },
  { icon: CheckCircle, label: '查看复习任务', prompt: '帮我看看今天有哪些需要复习的内容' },
  { icon: ChartBar, label: '学习数据总览', prompt: '帮我分析学习数据，看看整体情况' },
  { icon: BookOpen, label: '推荐课程', prompt: '根据我的薄弱点推荐适合的课程' },
  { icon: Lightbulb, label: '解释一个概念', prompt: '请帮我讲解一个知识点' },
  { icon: ChatCircleText, label: '分析一道题', prompt: '帮我分析这道题的解题思路' },
  { icon: Brain, label: '总结知识点', prompt: '帮我总结某个知识点的核心内容' },
  { icon: Stethoscope, label: '做诊断测试', prompt: '帮我做一次诊断测试，了解我的学习水平' },
  { icon: WarningCircle, label: '查看错题', prompt: '帮我分析错题，找出薄弱环节' },
  { icon: PlayCircle, label: '开始刷题', prompt: '帮我出几道题练习一下' },
];

interface DashPlan {
  id: number; title: string;
  total_tasks: number; completed_tasks: number;
  progress_pct: number; expected_progress_pct: number | null;
  progress_delta: number | null;
  total_days: number; elapsed_days: number;
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
  const [dash, setDash] = useState<DashData | null>(null);
  const [hasConversation, setHasConversation] = useState(false);

  useEffect(() => {
    api.get('/ai/dashboard/').then(r => {
      if (r.data) setDash(r.data);
    }).catch(() => {});
  }, []);

  const stats = dash?.stats;
  const plan = dash?.plan;
  const reviews = dash?.reviews;
  const lastExam = dash?.exams?.[0];

  const [checkingIn, setCheckingIn] = useState(false);
  const [checkedIn, setCheckedIn] = useState(stats?.today_checked_in || false);

  useEffect(() => {
    if (stats?.today_checked_in !== undefined) setCheckedIn(stats.today_checked_in);
  }, [stats?.today_checked_in]);

  const handleCheckIn = async () => {
    setCheckingIn(true);
    try {
      await api.post('/users/me/checkin/');
      setCheckedIn(true);
      // Refresh dashboard to get updated checkin_streak + achievements
      const r = await api.get('/ai/dashboard/');
      if (r.data) setDash(r.data);
    } catch {
      // already checked in or network error — ignore
    } finally {
      setCheckingIn(false);
    }
  };

  /* ── Heatmap helper: chunk flat 28-day array into rows of 7 ── */
  const renderHeatmap = (days: { date: string; count: number }[]) => {
    const rows: { date: string; count: number }[][] = [];
    for (let i = 0; i < days.length; i += 7) rows.push(days.slice(i, i + 7));
    return (
      <div className="flex gap-[4px]">
        {rows.map((row, ri) => (
          <div key={ri} className="flex flex-col gap-[4px]">
            {row.map((d, di) => {
              const level = d.count === 0 ? 0 : d.count <= 3 ? 1 : d.count <= 8 ? 2 : d.count <= 15 ? 3 : 4;
              return (
                <div
                  key={`${ri}-${di}`}
                  className={cn(
                    'w-[15px] h-[15px] rounded-[3px] border border-border/20',
                    level === 0 && 'bg-muted/40',
                    level === 1 && 'bg-xiaoyu-100',
                    level === 2 && 'bg-xiaoyu-200',
                    level === 3 && 'bg-xiaoyu-400',
                    level === 4 && 'bg-xiaoyu-500',
                  )}
                  title={`${d.date}: ${d.count} 道题`}
                />
              );
            })}
          </div>
        ))}
      </div>
    );
  };

  const landingBanner = !hasConversation && stats ? (
    <div className="animate-in fade-in duration-500">
      {stats.is_new_user ? (
        /* ── 新用户：诊断 CTA + value-prop pills ── */
        <div className="space-y-8">
          <div className="rounded-2xl bg-card border border-border/40 p-8 text-center">
            <div className="w-14 h-14 rounded-2xl bg-xiaoyu-50 dark:bg-xiaoyu-500/20 flex items-center justify-center mx-auto mb-4">
              <Stethoscope className="w-7 h-7 text-xiaoyu-500 dark:text-xiaoyu-300" />
            </div>
            <h3 className="text-lg font-bold text-foreground">开始你的第一次诊断测试</h3>
            <p className="text-sm text-muted-foreground mt-1.5 mb-5 max-w-sm mx-auto leading-relaxed">
              5 分钟了解你的学习水平，小宇会为你定制个性化学习计划
            </p>
            <Button size="sm" onClick={() => navigate('/diagnostic')} className="rounded-full px-6 h-9 bg-xiaoyu-500 hover:bg-xiaoyu-600 text-white">
              开始诊断
            </Button>
          </div>

          <div className="flex flex-wrap justify-center gap-3">
            {[
              { icon: Target, label: '定位薄弱知识点' },
              { icon: Brain, label: '获得个性化学习路径' },
              { icon: ChartBar, label: '实时追踪学习进度' },
            ].map((item) => (
              <div key={item.label} className="flex items-center gap-2 px-4 py-2.5 rounded-xl bg-muted/40 border border-border/30">
                <item.icon className="w-4 h-4 text-xiaoyu-500/60 dark:text-xiaoyu-300/60" />
                <span className="text-[12px] font-medium text-foreground/70">{item.label}</span>
              </div>
            ))}
          </div>
        </div>
      ) : (
        /* ── 回访用户：2x2 不对称 Bento Grid ── */
        <div className="space-y-4">
          {/* Row 1: 连续学习 + 正确率 */}
          <div className="grid grid-cols-1 md:grid-cols-[1.2fr_1fr] gap-4">
            {/* 连续学习 + 打卡 */}
            <div className="rounded-2xl bg-card border border-border/40 p-5 flex flex-col justify-between">
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2.5">
                  <div className="w-8 h-8 rounded-lg bg-xiaoyu-50 dark:bg-xiaoyu-500/20 flex items-center justify-center shrink-0">
                    <Fire className="w-4 h-4 text-xiaoyu-500 dark:text-xiaoyu-300" />
                  </div>
                  <span className="text-[13px] font-semibold text-foreground/80">连续学习</span>
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
                  {checkingIn ? '签到中...' : checkedIn ? '✓ 已打卡' : '今日打卡'}
                </button>
              </div>
              <p className="text-4xl font-black tracking-tighter tabular-nums text-xiaoyu-500 dark:text-xiaoyu-300">
                {stats.streak_days}<span className="text-base font-normal text-muted-foreground ml-1">天</span>
              </p>
              <div className="mt-4 flex flex-wrap items-center gap-x-4 gap-y-1 text-[12px]">
                <span className="text-muted-foreground/60">
                  本周 <span className="font-semibold text-foreground/70">{stats.weekly_activity}</span> 题
                </span>
                {reviews && reviews.due_count > 0 ? (
                  <span className="text-muted-foreground/60">
                    待复习 <span className="font-semibold text-amber-600">{reviews.due_count}</span> 题
                  </span>
                ) : (
                  <span className="text-muted-foreground/40">暂无待复习</span>
                )}
              </div>
            </div>

            {/* 正确率 */}
            <div className="rounded-2xl bg-card border border-border/40 p-5 flex flex-col justify-between">
              <div className="flex items-center gap-2.5 mb-3">
                <div className="w-8 h-8 rounded-lg bg-xiaoyu-50 dark:bg-xiaoyu-500/20 flex items-center justify-center shrink-0">
                  <Trophy className="w-4 h-4 text-xiaoyu-500 dark:text-xiaoyu-300" />
                </div>
                <span className="text-[13px] font-semibold text-foreground/80">正确率</span>
              </div>
              <p className="text-4xl font-black tracking-tighter tabular-nums text-xiaoyu-500 dark:text-xiaoyu-300">
                {stats.accuracy}<span className="text-base font-normal text-muted-foreground ml-0.5">%</span>
              </p>
              <div className="mt-4 flex flex-wrap items-center gap-x-4 gap-y-1 text-[12px]">
                <span className="text-muted-foreground/60">
                  累计 <span className="font-semibold text-foreground/70">{stats.total_attempted}</span> 题
                </span>
                {lastExam ? (
                  <span className="text-muted-foreground/60">
                    最近 <span className="font-semibold text-foreground/70">{lastExam.total_score}/{lastExam.max_score}</span>
                    {lastExam.elo_change !== 0 && (
                      <span className={cn('ml-1 font-semibold', lastExam.elo_change >= 0 ? 'text-emerald-600' : 'text-red-500')}>
                        {lastExam.elo_change >= 0 ? '+' : ''}{lastExam.elo_change}
                      </span>
                    )}
                  </span>
                ) : (
                  <span className="text-muted-foreground/40">暂无考试</span>
                )}
              </div>
            </div>
          </div>

          {/* Row 2: 学习计划 — 全宽 */}
          <div className="rounded-2xl bg-card border border-border/40 p-5">
            {plan ? (
              <div>
                <div className="flex items-center gap-2.5 mb-3">
                  <div className="w-8 h-8 rounded-lg bg-xiaoyu-50 dark:bg-xiaoyu-500/20 flex items-center justify-center shrink-0">
                    <CalendarCheck className="w-4 h-4 text-xiaoyu-500 dark:text-xiaoyu-300" />
                  </div>
                  <span className="text-[13px] font-semibold text-foreground/80 truncate">{plan.title}</span>
                  {plan.progress_delta !== null && plan.progress_delta !== 0 && (
                    <span className={cn('text-[11px] font-semibold ml-auto shrink-0', plan.progress_delta > 0 ? 'text-emerald-600' : 'text-red-500')}>
                      {plan.progress_delta > 0 ? '领先' : '落后'} {Math.abs(plan.progress_delta)}%
                    </span>
                  )}
                </div>
                <div className="flex flex-wrap items-center gap-x-6 gap-y-1 text-[12px] text-muted-foreground/60">
                  <span>已完成 <span className="font-semibold text-foreground/70">{plan.completed_tasks}/{plan.total_tasks}</span> 任务</span>
                  <span>进度 <span className="font-semibold text-xiaoyu-500 dark:text-xiaoyu-300">{plan.progress_pct}%</span></span>
                  {plan.total_days > 0 && (
                    <span>第 <span className="font-semibold text-foreground/70">{plan.elapsed_days}/{plan.total_days}</span> 天</span>
                  )}
                </div>
              </div>
            ) : (
              <div className="flex flex-col items-center justify-center py-6 text-center">
                <CalendarCheck className="w-6 h-6 text-muted-foreground/15 mb-2" />
                <p className="text-[12px] text-muted-foreground/50">暂无学习计划</p>
                <p className="text-[10px] text-muted-foreground/30 mt-0.5">和小宇对话来制定</p>
              </div>
            )}
          </div>

          {/* Row 3: 活跃热力图 */}
          <div className="rounded-2xl bg-card border border-border/40 p-5">
            <p className="text-[12px] font-semibold text-foreground/70 mb-3">
              {stats.heatmap_days && stats.heatmap_days.length > 0 ? '28 天学习活跃度' : '学习活跃度'}
            </p>
            {stats.heatmap_days && stats.heatmap_days.length > 0 ? (
              <>
                {renderHeatmap(stats.heatmap_days)}
                <div className="flex items-center justify-end gap-1 mt-3 text-[10px] text-muted-foreground/40">
                  <span>少</span>
                  <div className="w-[10px] h-[10px] rounded-[2px] bg-muted/40 border border-border/20" />
                  <div className="w-[10px] h-[10px] rounded-[2px] bg-xiaoyu-100" />
                  <div className="w-[10px] h-[10px] rounded-[2px] bg-xiaoyu-200" />
                  <div className="w-[10px] h-[10px] rounded-[2px] bg-xiaoyu-400" />
                  <div className="w-[10px] h-[10px] rounded-[2px] bg-xiaoyu-500" />
                  <span>多</span>
                </div>
              </>
            ) : (
              <p className="text-[12px] text-muted-foreground/40 py-3 text-center">开始学习后这里将显示你的每日活跃情况</p>
            )}
          </div>

          {/* Row 4: 成就进度 — 下一个要解锁的成就 */}
          {stats.next_achievements && stats.next_achievements.length > 0 && (
            <div className="rounded-2xl bg-card border border-border/40 p-5">
              <div className="flex items-center justify-between mb-3">
                <p className="text-[12px] font-semibold text-foreground/70">
                  下一个成就
                  {stats.unlocked_achievement_count > 0 && (
                    <span className="text-muted-foreground/40 ml-1">（已解锁 {stats.unlocked_achievement_count} 个）</span>
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
  ) : null;

  return (
    <AgentChatLayout
      layout="inline"
      findBot={(bots) => bots.find((b: Bot) => b.name === '小宇')}
      skills={SKILLS}
      typewriterWords={['让小宇帮你制定学习计划', '让小宇分析薄弱知识点', '让小宇推荐适合的课程', '让小宇看看复习进度']}
      chatPlaceholder="和小宇对话..."
      resetMessage="已开始新对话"
      landingTitle="小宇XiaoYu让学习更具效率。对话即学习。"
      landingDescription="最懂你的学习agent，从数据分析到知识讲解，一个入口搞定"
      botDisplayName="小宇"
      landingBanner={landingBanner}
      onHasConversation={setHasConversation}
      onDeleteSession={() => {}}
      onLoadSession={(session, defaultHandler) => { defaultHandler(session); }}
      onDone={(refreshSessions) => { refreshSessions(); }}
      onStepDone={(step, prev) => prev.map(m =>
        m.toolStep?.call_id === step.call_id ? { ...m, toolStep: step } : m
      )}
    />
  );
};

export default XiaoYu;
