import React, { useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { Badge } from '@/components/ui/badge';
import { Checkbox } from '@/components/ui/checkbox';
import { Button } from '@/components/ui/button';
import { Progress } from '@/components/ui/progress';
import {
  CalendarCheck,
  Trophy,
  BrainCircuit,
  Flame,
  Target,
  Clock,
  ArrowRight,
  CheckCircle2,
  AlertCircle,
  TrendingUp,
  FileText,
  Sparkles,
  BarChart3,
} from 'lucide-react';
import api from '@/lib/api';
import { cn } from '@/lib/utils';

export interface DashboardData {
  plan: {
    id: number;
    title: string;
    summary: string;
    total_tasks: number;
    completed_tasks: number;
    progress_pct: number;
    tasks: Array<{
      id: string;
      title: string;
      description?: string;
      day: number;
      subject?: string;
      estimated_minutes?: number;
      status: 'pending' | 'completed' | 'skipped';
    }>;
    created_at: string;
    subjects_covered: string[];
  } | null;
  stats: {
    total_attempted: number;
    correct_count: number;
    accuracy: number;
    wrong_count: number;
    streak_days: number;
    weekly_activity: number;
    is_new_user: boolean;
  };
  mastery: Record<string, Array<{
    kp_id: number;
    kp_code: string;
    kp_name: string;
    mastery_score: number;
  }>>;
  reviews: {
    due_count: number;
    items: Array<{
      question_id: number;
      question_text: string;
      kp_name: string;
      wrong_count: number;
      stability: number;
    }>;
  };
  exams: Array<{
    id: number;
    total_score: number;
    max_score: number;
    percentage: number;
    elo_change: number;
    created_at: string;
  }>;
  dashboard_config: {
    section_order: string[];
    highlight: string;
  };
}

interface DashboardPanelProps {
  data: DashboardData | null;
  onRefresh: () => void;
}

// ── Empty state ──
const EmptyState: React.FC = () => {
  const navigate = useNavigate();
  return (
    <div className="h-full flex flex-col items-center justify-center px-6 animate-in fade-in duration-500">
      <div className="w-12 h-12 rounded-2xl bg-gradient-to-br from-amber-500 to-orange-500 flex items-center justify-center mb-3 shadow-lg shadow-amber-500/20">
        <Sparkles className="h-6 w-6 text-white" />
      </div>
      <h2 className="text-base font-bold mb-0.5">欢迎使用小宇</h2>
      <p className="text-xs text-muted-foreground mb-4 text-center max-w-[240px]">
        和我聊聊，我会为你生成个性化学习面板
      </p>
      <Button
        variant="outline"
        size="sm"
        className="rounded-full gap-1.5 text-xs h-8"
        onClick={() => navigate('/tests')}
      >
        <Target className="h-3 w-3" />
        开始诊断测试
      </Button>
    </div>
  );
};

// ── Section header (reusable) ──
const SectionHead: React.FC<{
  icon: React.ReactNode;
  title: string;
  action?: React.ReactNode;
}> = ({ icon, title, action }) => (
  <div className="flex items-center justify-between mb-2">
    <div className="flex items-center gap-1.5">
      {icon}
      <span className="text-xs font-bold">{title}</span>
    </div>
    {action}
  </div>
);

// ── Plan: hero card with accent ──
const StudyPlanCard: React.FC<{
  plan: DashboardData['plan'];
  onTaskToggle: (planId: number, taskId: string, status: string) => void;
  highlighted?: boolean;
}> = ({ plan, onTaskToggle, highlighted }) => {
  const navigate = useNavigate();
  if (!plan) return null;
  const todayTasks = plan.tasks.filter(t => t.status === 'pending').slice(0, 3);

  return (
    <div className={cn(
      "rounded-xl border bg-card overflow-hidden animate-in fade-in slide-in-from-bottom-2 duration-300",
      highlighted ? "border-blue-300 shadow-md shadow-blue-500/10" : "border-border"
    )}>
      {/* Accent top bar */}
      <div className="h-1 bg-gradient-to-r from-blue-500 to-cyan-500" />

      <div className="p-3.5">
        <SectionHead
          icon={<CalendarCheck className="h-3.5 w-3.5 text-blue-500" />}
          title={plan.title}
          action={
            <Button
              variant="ghost"
              size="sm"
              className="h-6 text-[10px] font-semibold text-muted-foreground gap-0.5 px-1.5"
              onClick={() => navigate('/plan')}
            >
              全部 <ArrowRight className="h-2.5 w-2.5" />
            </Button>
          }
        />

        {/* Progress bar */}
        <div className="mb-3">
          <div className="flex justify-between text-[10px] mb-1">
            <span className="text-muted-foreground">{plan.completed_tasks}/{plan.total_tasks} 完成</span>
            <span className="font-bold">{Math.round(plan.progress_pct)}%</span>
          </div>
          <Progress value={plan.progress_pct} className="h-1.5" />
        </div>

        {/* Tasks */}
        {todayTasks.length > 0 && (
          <div className="space-y-1">
            {todayTasks.map(task => (
              <div
                key={task.id}
                className="flex items-center gap-2 py-1 px-1.5 rounded-lg hover:bg-muted/50 transition-colors group"
              >
                <Checkbox
                  checked={task.status === 'completed'}
                  onCheckedChange={() => onTaskToggle(plan.id, task.id, task.status === 'completed' ? 'pending' : 'completed')}
                  className="h-3.5 w-3.5"
                />
                <span className={cn(
                  "text-[11px] font-medium flex-1 truncate",
                  task.status === 'completed' && "line-through text-muted-foreground"
                )}>
                  {task.title}
                </span>
                {task.subject && (
                  <Badge variant="secondary" className="text-[9px] px-1 py-0 h-3.5 shrink-0 font-semibold">{task.subject}</Badge>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

// ── Stats: compact inline grid ──
const StatsInline: React.FC<{ stats: DashboardData['stats']; highlighted?: boolean }> = ({ stats, highlighted }) => {
  const navigate = useNavigate();
  if (stats.is_new_user) {
    return (
      <div className={cn(
        "rounded-xl border bg-card p-3 text-center animate-in fade-in slide-in-from-bottom-2 duration-300",
        highlighted ? "border-emerald-300 shadow-md shadow-emerald-500/10" : "border-border"
      )} style={{ animationDelay: '50ms' }}>
        <Target className="h-6 w-6 text-muted-foreground mx-auto mb-1.5" />
        <p className="text-[11px] text-muted-foreground mb-1.5">还没有学习数据</p>
        <Button variant="outline" size="sm" className="rounded-full text-[10px] h-6 gap-0.5" onClick={() => navigate('/tests')}>
          开始刷题 <ArrowRight className="h-2.5 w-2.5" />
        </Button>
      </div>
    );
  }

  const items = [
    { label: '正确率', value: `${stats.accuracy}%`, icon: <TrendingUp className="h-3 w-3 text-emerald-500" /> },
    { label: '连续学习', value: `${stats.streak_days}天`, icon: <Flame className="h-3 w-3 text-orange-500" /> },
    { label: '已练习', value: stats.total_attempted, icon: <BarChart3 className="h-3 w-3 text-blue-500" /> },
    { label: '待复习', value: stats.wrong_count, icon: <AlertCircle className="h-3 w-3 text-amber-500" /> },
  ];

  return (
    <div className={cn(
      "grid grid-cols-4 gap-2 animate-in fade-in slide-in-from-bottom-2 duration-300",
      highlighted && "ring-1 ring-emerald-300/50 rounded-xl"
    )} style={{ animationDelay: '50ms' }}>
      {items.map(item => (
        <div key={item.label} className="rounded-xl border border-border bg-card p-2.5 text-center">
          <div className="flex items-center justify-center gap-1 mb-1">
            {item.icon}
            <span className="text-[9px] text-muted-foreground font-semibold uppercase tracking-wider">{item.label}</span>
          </div>
          <p className="text-base font-black">{item.value}</p>
        </div>
      ))}
    </div>
  );
};

// ── Mastery: compact bars ──
const MasteryBars: React.FC<{ mastery: DashboardData['mastery']; highlighted?: boolean }> = ({ mastery, highlighted }) => {
  const navigate = useNavigate();
  const subjects = Object.keys(mastery);
  if (subjects.length === 0) return null;

  return (
    <div className={cn(
      "rounded-xl border bg-card p-3 animate-in fade-in slide-in-from-bottom-2 duration-300",
      highlighted ? "border-purple-300 shadow-md shadow-purple-500/10" : "border-border"
    )} style={{ animationDelay: '100ms' }}>
      <SectionHead
        icon={<BrainCircuit className="h-3.5 w-3.5 text-purple-500" />}
        title="知识掌握度"
        action={
          <Button
            variant="ghost"
            size="sm"
            className="h-6 text-[10px] font-semibold text-muted-foreground gap-0.5 px-1.5"
            onClick={() => navigate('/knowledge-map')}
          >
            地图 <ArrowRight className="h-2.5 w-2.5" />
          </Button>
        }
      />
      <div className="space-y-2.5">
        {subjects.slice(0, 3).map(subj => {
          const kps = mastery[subj];
          const avg = kps.reduce((s, k) => s + k.mastery_score, 0) / kps.length;
          const weak = kps.filter(k => k.mastery_score < 0.4).length;
          return (
            <div key={subj} className="space-y-1">
              <div className="flex justify-between items-center">
                <span className="text-[11px] font-bold">{subj}</span>
                <div className="flex items-center gap-2">
                  <span className="text-[10px] text-muted-foreground">{Math.round(avg * 100)}%</span>
                  {weak > 0 && (
                    <span className="text-[9px] text-orange-500 font-semibold">{weak} 薄弱</span>
                  )}
                </div>
              </div>
              <div className="relative h-1.5 bg-muted rounded-full overflow-hidden">
                <div
                  className={cn(
                    "absolute inset-y-0 left-0 rounded-full transition-all duration-500",
                    avg >= 0.7 ? "bg-emerald-500" : avg >= 0.4 ? "bg-amber-500" : "bg-red-500"
                  )}
                  style={{ width: `${avg * 100}%` }}
                />
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};

// ── Reviews: compact list ──
const ReviewsList: React.FC<{ reviews: DashboardData['reviews']; highlighted?: boolean }> = ({ reviews, highlighted }) => {
  const navigate = useNavigate();
  if (reviews.due_count === 0) return null;

  return (
    <div className={cn(
      "rounded-xl border bg-card p-3 animate-in fade-in slide-in-from-bottom-2 duration-300",
      highlighted ? "border-amber-300 shadow-md shadow-amber-500/10" : "border-border"
    )} style={{ animationDelay: '150ms' }}>
      <SectionHead
        icon={<CheckCircle2 className="h-3.5 w-3.5 text-amber-500" />}
        title="待复习"
        action={
          <Badge variant="secondary" className="text-[9px] px-1.5 py-0 h-4 font-bold">{reviews.due_count} 题</Badge>
        }
      />
      <div className="space-y-1">
        {reviews.items.slice(0, 3).map(item => (
          <div key={item.question_id} className="flex items-center gap-2 py-1 px-1 rounded-lg hover:bg-muted/50 transition-colors">
            <div className="h-1.5 w-1.5 rounded-full bg-amber-500 shrink-0" />
            <div className="flex-1 min-w-0">
              <p className="text-[11px] font-medium truncate">{item.question_text}</p>
            </div>
          </div>
        ))}
        {reviews.due_count > 3 && (
          <Button
            variant="ghost"
            size="sm"
            className="w-full h-6 text-[10px] font-semibold text-muted-foreground mt-1"
            onClick={() => navigate('/tests/review')}
          >
            查看全部 {reviews.due_count} 题
          </Button>
        )}
      </div>
    </div>
  );
};

// ── Exams: compact list ──
const ExamsList: React.FC<{ exams: DashboardData['exams']; highlighted?: boolean }> = ({ exams, highlighted }) => {
  const navigate = useNavigate();
  if (exams.length === 0) return null;

  return (
    <div className={cn(
      "rounded-xl border bg-card p-3 animate-in fade-in slide-in-from-bottom-2 duration-300",
      highlighted ? "border-emerald-300 shadow-md shadow-emerald-500/10" : "border-border"
    )} style={{ animationDelay: '200ms' }}>
      <SectionHead
        icon={<FileText className="h-3.5 w-3.5 text-emerald-500" />}
        title="考试记录"
        action={
          <Button
            variant="ghost"
            size="sm"
            className="h-6 text-[10px] font-semibold text-muted-foreground gap-0.5 px-1.5"
            onClick={() => navigate('/tests')}
          >
            更多 <ArrowRight className="h-2.5 w-2.5" />
          </Button>
        }
      />
      <div className="space-y-1">
        {exams.slice(0, 3).map(exam => (
          <div key={exam.id} className="flex items-center gap-2 py-1 px-1 rounded-lg hover:bg-muted/50 transition-colors">
            <div className={cn(
              "h-6 w-6 rounded-md flex items-center justify-center text-[10px] font-black shrink-0",
              exam.percentage >= 80 ? "bg-emerald-50 text-emerald-600" :
              exam.percentage >= 60 ? "bg-amber-50 text-amber-600" :
              "bg-red-50 text-red-600"
            )}>
              {exam.percentage}
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-[11px] font-medium">{exam.total_score}/{exam.max_score} 分</p>
            </div>
            {exam.elo_change !== 0 && (
              <span className={cn("text-[10px] font-bold shrink-0", exam.elo_change > 0 ? "text-emerald-500" : "text-red-500")}>
                {exam.elo_change > 0 ? '+' : ''}{exam.elo_change}
              </span>
            )}
          </div>
        ))}
      </div>
    </div>
  );
};

// ── Main ──
const SECTION_COMPONENTS: Record<string, React.FC<any>> = {
  plan: StudyPlanCard,
  stats: StatsInline,
  mastery: MasteryBars,
  reviews: ReviewsList,
  exams: ExamsList,
};

const DEFAULT_ORDER = ['plan', 'stats', 'mastery', 'reviews', 'exams'];

export const DashboardPanel: React.FC<DashboardPanelProps> = ({ data, onRefresh }) => {
  const handleTaskToggle = useCallback(async (planId: number, taskId: string, newStatus: string) => {
    try {
      await api.patch(`/ai/plans/${planId}/tasks/${taskId}/`, { status: newStatus });
      onRefresh();
    } catch {}
  }, [onRefresh]);

  if (!data) return <EmptyState />;
  if (data.stats.is_new_user && !data.plan) return <EmptyState />;

  const config = data.dashboard_config || { section_order: DEFAULT_ORDER, highlight: 'stats' };
  const order = config.section_order.length > 0 ? config.section_order : DEFAULT_ORDER;
  const highlight = config.highlight || 'stats';

  const sectionData: Record<string, any> = {
    plan: { plan: data.plan, onTaskToggle: handleTaskToggle },
    stats: { stats: data.stats },
    mastery: { mastery: data.mastery },
    reviews: { reviews: data.reviews },
    exams: { exams: data.exams },
  };

  return (
    <div className="h-full overflow-y-auto p-3 space-y-2.5">
      {order.map(section => {
        const Component = SECTION_COMPONENTS[section];
        if (!Component) return null;
        // Skip sections with no data
        if (section === 'plan' && !data.plan) return null;
        if (section === 'reviews' && data.reviews.due_count === 0) return null;
        if (section === 'exams' && data.exams.length === 0) return null;
        if (section === 'mastery' && Object.keys(data.mastery).length === 0) return null;
        return <Component key={section} {...sectionData[section]} highlighted={section === highlight} />;
      })}
    </div>
  );
};
