import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Target, CalendarCheck, CheckCircle, ChartBar, BookOpen, Lightbulb, ChatCircleText, Brain, Stethoscope, WarningCircle, PlayCircle, Fire, Clock, TrendUp, TrendDown, Trophy } from '@phosphor-icons/react';
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
  activity_calendar: { date: string; count: number }[];
  is_new_user: boolean;
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

  const landingBanner = !hasConversation && stats ? (
    <div className="animate-in fade-in duration-500">
      {stats.is_new_user ? (
        <div className="rounded-2xl bg-card border border-border/30 p-6 text-center">
          <div className="w-12 h-12 rounded-xl bg-primary/10 flex items-center justify-center mx-auto mb-3">
            <Stethoscope className="w-6 h-6 text-primary" />
          </div>
          <p className="text-base font-bold tracking-tight">开始你的第一次诊断测试</p>
          <p className="text-sm text-muted-foreground mt-1.5 mb-4 max-w-xs mx-auto leading-relaxed">
            5 分钟了解你的学习水平，小宇会为你定制个性化学习计划
          </p>
          <Button size="sm" onClick={() => navigate('/diagnostic')} className="rounded-full px-6 h-9">
            开始诊断
          </Button>
        </div>
      ) : (
        <>
          {/* 三卡行 */}
          <div className="grid grid-cols-3 gap-4">
            {/* 学习节奏 */}
            <div className="rounded-2xl bg-muted/30 p-5">
              <div className="flex items-center gap-1.5 mb-3">
                <Fire className="w-3.5 h-3.5 text-amber-500" />
                <span className="text-[10px] font-semibold text-muted-foreground/50 uppercase tracking-wider">节奏</span>
              </div>
              <p className="text-3xl font-black tracking-tighter tabular-nums">{stats.streak_days}<span className="text-sm font-normal text-muted-foreground/50 ml-1">天</span></p>
              <p className="text-[11px] text-muted-foreground/50 mt-0.5">连续学习</p>
              <div className="mt-4 space-y-1.5">
                {reviews && reviews.due_count > 0 ? (
                  <div className="flex items-center justify-between text-[12px]">
                    <span className="text-muted-foreground/60">待复习</span>
                    <span className="font-bold text-amber-600">{reviews.due_count} 题</span>
                  </div>
                ) : (
                  <div className="flex items-center justify-between text-[12px]">
                    <span className="text-muted-foreground/60">待复习</span>
                    <span className="text-emerald-600/70 font-medium">暂无</span>
                  </div>
                )}
                <div className="flex items-center justify-between text-[12px]">
                  <span className="text-muted-foreground/60">本周</span>
                  <span className="font-bold text-foreground/70">{stats.weekly_activity} 题</span>
                </div>
              </div>
            </div>

            {/* 学习计划 */}
            <div className="rounded-2xl bg-muted/30 p-5">
              <div className="flex items-center gap-1.5 mb-3">
                <CalendarCheck className="w-3.5 h-3.5 text-blue-500" />
                <span className="text-[10px] font-semibold text-muted-foreground/50 uppercase tracking-wider">计划</span>
              </div>
              {plan ? (
                <>
                  <p className="text-sm font-bold truncate">{plan.title}</p>
                  <div className="mt-3 mb-2 flex items-center gap-2">
                    <div className="flex-1 h-1.5 rounded-full bg-muted/80 overflow-hidden">
                      <div className="h-full rounded-full bg-blue-500 transition-all duration-500" style={{ width: `${Math.min(plan.progress_pct, 100)}%` }} />
                    </div>
                    <span className="text-[12px] font-bold text-blue-600 tabular-nums">{plan.progress_pct}%</span>
                  </div>
                  <div className="flex items-center justify-between text-[11px] text-muted-foreground/50">
                    <span>{plan.completed_tasks}/{plan.total_tasks} 任务</span>
                    {plan.progress_delta !== null && (
                      <span className={cn('font-bold flex items-center gap-0.5', plan.progress_delta >= 0 ? 'text-emerald-600' : 'text-red-500')}>
                        {plan.progress_delta >= 0 ? <TrendUp className="w-3 h-3" /> : <TrendDown className="w-3 h-3" />}
                        {plan.progress_delta >= 0 ? '领先' : '落后'} {Math.abs(plan.progress_delta)}%
                      </span>
                    )}
                  </div>
                  {plan.total_days > 0 && (
                    <div className="mt-2 flex items-center gap-1.5 text-[11px] text-muted-foreground/40">
                      <Clock className="w-3 h-3" />第 {plan.elapsed_days}/{plan.total_days} 天
                    </div>
                  )}
                </>
              ) : (
                <div className="flex flex-col items-center justify-center py-6 text-center">
                  <CalendarCheck className="w-6 h-6 text-muted-foreground/15 mb-2" />
                  <p className="text-[12px] text-muted-foreground/50">暂无计划</p>
                  <p className="text-[10px] text-muted-foreground/30 mt-0.5">对话制定</p>
                </div>
              )}
            </div>

            {/* 学习成果 */}
            <div className="rounded-2xl bg-muted/30 p-5">
              <div className="flex items-center gap-1.5 mb-3">
                <Trophy className="w-3.5 h-3.5 text-emerald-500" />
                <span className="text-[10px] font-semibold text-muted-foreground/50 uppercase tracking-wider">成果</span>
              </div>
              <p className="text-3xl font-black tracking-tighter tabular-nums">{stats.accuracy}<span className="text-sm font-normal text-muted-foreground/50 ml-0.5">%</span></p>
              <p className="text-[11px] text-muted-foreground/50 mt-0.5">正确率</p>
              <div className="mt-4 space-y-1.5">
                <div className="flex items-center justify-between text-[12px]">
                  <span className="text-muted-foreground/60">累计做题</span>
                  <span className="font-bold text-foreground/70">{stats.total_attempted}</span>
                </div>
                {lastExam ? (
                  <div className="flex items-center justify-between text-[12px]">
                    <span className="text-muted-foreground/60">最近考试</span>
                    <span className="flex items-center gap-1">
                      <span className="font-bold text-foreground/70">{lastExam.total_score}/{lastExam.max_score}</span>
                      {lastExam.elo_change !== 0 && (
                        <span className={cn('text-[11px] font-bold', lastExam.elo_change >= 0 ? 'text-emerald-600' : 'text-red-500')}>
                          {lastExam.elo_change >= 0 ? '+' : ''}{lastExam.elo_change}
                        </span>
                      )}
                    </span>
                  </div>
                ) : (
                  <div className="flex items-center justify-between text-[12px]">
                    <span className="text-muted-foreground/60">最近考试</span>
                    <span className="text-muted-foreground/40">暂无</span>
                  </div>
                )}
              </div>
            </div>
          </div>

          {/* 热力图脚注 */}
          {stats.activity_calendar && stats.activity_calendar.length > 0 && (
            <div className="mt-4 flex items-center gap-2 text-[10px] text-muted-foreground/40">
              <span className="font-medium shrink-0">28 天活跃</span>
              <div className="flex gap-[3px] flex-wrap flex-1">
                {stats.activity_calendar.map((d, i) => {
                  const level = d.count === 0 ? 0 : d.count <= 3 ? 1 : d.count <= 8 ? 2 : d.count <= 15 ? 3 : 4;
                  return (
                    <div key={i} className={cn('w-3 h-3 rounded-[2px]',
                      level === 0 && 'bg-muted/50',
                      level === 1 && 'bg-emerald-200/50',
                      level === 2 && 'bg-emerald-300/60',
                      level === 3 && 'bg-emerald-400/70',
                      level === 4 && 'bg-emerald-500',
                    )} title={`${d.date}: ${d.count} 次复习`} />
                  );
                })}
              </div>
            </div>
          )}
        </>
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
