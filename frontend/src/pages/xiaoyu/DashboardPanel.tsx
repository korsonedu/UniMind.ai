import React, { useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { Checkbox } from '@/components/ui/checkbox';
import { Button } from '@/components/ui/button';
import { Progress } from '@/components/ui/progress';
import {
  CalendarCheck,
  BrainCircuit,
  Flame,
  Target,
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
  custom_cards: Array<{
    title: string;
    subtitle?: string;
    items: Array<{
      label: string;
      value: string;
      trend?: 'up' | 'down' | 'neutral';
      progress?: number;
      emphasis?: boolean;
      action_link?: string;
    }>;
    cta?: { label: string; link: string };
  }>;
}

interface DashboardPanelProps {
  data: DashboardData | null;
  onRefresh: () => void;
}

const EmptyState: React.FC = () => {
  const navigate = useNavigate();
  return (
    <div className="h-full flex flex-col items-center justify-center px-6 animate-in fade-in duration-500">
      <Sparkles className="h-5 w-5 text-muted-foreground/30 mb-2" />
      <h2 className="text-[13px] font-semibold mb-0.5">欢迎使用小宇</h2>
      <p className="text-[11px] text-muted-foreground mb-3 text-center max-w-[200px]">
        和我聊聊，我会为你生成个性化学习面板
      </p>
      <Button
        variant="ghost"
        size="sm"
        className="rounded-full gap-1 text-[11px] h-6 text-muted-foreground"
        onClick={() => navigate('/tests')}
      >
        <Target className="h-3 w-3" />
        开始诊断测试
      </Button>
    </div>
  );
};

const SectionHead: React.FC<{
  icon: React.ReactNode;
  title: string;
  action?: React.ReactNode;
}> = ({ icon, title, action }) => (
  <div className="flex items-center justify-between mb-1.5">
    <div className="flex items-center gap-1">
      {icon}
      <span className="text-[11px] font-semibold text-foreground/80">{title}</span>
    </div>
    {action}
  </div>
);

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
      "rounded-lg border border-border/60 bg-card overflow-hidden animate-in fade-in slide-in-from-bottom-2 duration-300",
      highlighted && "border-primary/15"
    )}>
      <div className="p-2.5">
        <SectionHead
          icon={<CalendarCheck className="h-3 w-3 text-primary/60" />}
          title={plan.title}
          action={
            <Button
              variant="ghost"
              size="sm"
              className="h-5 text-[10px] text-muted-foreground/60 gap-0.5 px-1"
              onClick={() => navigate('/plan')}
            >
              全部 <ArrowRight className="h-2.5 w-2.5" />
            </Button>
          }
        />

        <div className="mb-2">
          <div className="flex justify-between text-[10px] mb-0.5">
            <span className="text-muted-foreground/60">{plan.completed_tasks}/{plan.total_tasks}</span>
            <span className="font-semibold tabular-nums">{Math.round(plan.progress_pct)}%</span>
          </div>
          <Progress value={plan.progress_pct} className="h-1" />
        </div>

        {todayTasks.length > 0 && (
          <div className="space-y-0.5">
            {todayTasks.map(task => (
              <div
                key={task.id}
                className="flex items-center gap-2 py-0.5 px-1 rounded hover:bg-muted/40 transition-colors"
              >
                <Checkbox
                  checked={task.status === 'completed'}
                  onCheckedChange={() => onTaskToggle(plan.id, task.id, task.status === 'completed' ? 'pending' : 'completed')}
                  className="h-3 w-3"
                />
                <span className={cn(
                  "text-[11px] flex-1 truncate",
                  task.status === 'completed' && "line-through text-muted-foreground/50"
                )}>
                  {task.title}
                </span>
                {task.subject && (
                  <span className="text-[9px] text-muted-foreground/50 font-medium shrink-0">{task.subject}</span>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

const StatsInline: React.FC<{ stats: DashboardData['stats']; highlighted?: boolean }> = ({ stats, highlighted }) => {
  const navigate = useNavigate();
  if (stats.is_new_user) {
    return (
      <div className={cn(
        "rounded-lg border border-border/60 bg-card p-2.5 text-center animate-in fade-in slide-in-from-bottom-2 duration-300",
        highlighted && "border-primary/15"
      )}>
        <Target className="h-5 w-5 text-muted-foreground/30 mx-auto mb-1" />
        <p className="text-[11px] text-muted-foreground/60 mb-1">还没有学习数据</p>
        <Button variant="ghost" size="sm" className="rounded-full text-[10px] h-5 gap-0.5 text-muted-foreground/60" onClick={() => navigate('/tests')}>
          开始刷题 <ArrowRight className="h-2.5 w-2.5" />
        </Button>
      </div>
    );
  }

  const items = [
    { label: '正确率', value: `${stats.accuracy}%`, color: 'text-emerald-600' },
    { label: '连续', value: `${stats.streak_days}天`, color: 'text-orange-500' },
    { label: '已练习', value: stats.total_attempted, color: 'text-primary/70' },
    { label: '待复习', value: stats.wrong_count, color: 'text-amber-500' },
  ];

  return (
    <div className={cn(
      "grid grid-cols-4 gap-1.5 animate-in fade-in slide-in-from-bottom-2 duration-300",
      highlighted && "rounded-lg"
    )}>
      {items.map(item => (
        <div key={item.label} className="rounded-lg border border-border/40 bg-card p-2 text-center">
          <p className={cn("text-sm font-bold tabular-nums", item.color)}>{item.value}</p>
          <p className="text-[9px] text-muted-foreground/50 font-medium mt-0.5">{item.label}</p>
        </div>
      ))}
    </div>
  );
};

const MasteryBars: React.FC<{ mastery: DashboardData['mastery']; highlighted?: boolean }> = ({ mastery, highlighted }) => {
  const navigate = useNavigate();
  const subjects = Object.keys(mastery);
  if (subjects.length === 0) return null;

  return (
    <div className={cn(
      "rounded-lg border border-border/60 bg-card p-2.5 animate-in fade-in slide-in-from-bottom-2 duration-300",
      highlighted && "border-primary/15"
    )}>
      <SectionHead
        icon={<BrainCircuit className="h-3 w-3 text-primary/60" />}
        title="知识掌握度"
        action={
          <Button
            variant="ghost"
            size="sm"
            className="h-5 text-[10px] text-muted-foreground/60 gap-0.5 px-1"
            onClick={() => navigate('/knowledge-map')}
          >
            地图 <ArrowRight className="h-2.5 w-2.5" />
          </Button>
        }
      />
      <div className="space-y-2">
        {subjects.slice(0, 3).map(subj => {
          const kps = mastery[subj];
          const avg = kps.reduce((s, k) => s + k.mastery_score, 0) / kps.length;
          const weak = kps.filter(k => k.mastery_score < 0.4).length;
          return (
            <div key={subj} className="space-y-0.5">
              <div className="flex justify-between items-center">
                <span className="text-[11px] font-medium">{subj}</span>
                <div className="flex items-center gap-1.5">
                  <span className="text-[10px] text-muted-foreground/50 tabular-nums">{Math.round(avg * 100)}%</span>
                  {weak > 0 && (
                    <span className="text-[9px] text-orange-500/80 font-medium">{weak} 薄弱</span>
                  )}
                </div>
              </div>
              <div className="relative h-1 bg-muted/50 rounded-full overflow-hidden">
                <div
                  className={cn(
                    "absolute inset-y-0 left-0 rounded-full transition-all duration-500",
                    avg >= 0.7 ? "bg-emerald-400" : avg >= 0.4 ? "bg-amber-400" : "bg-red-400"
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

const ReviewsList: React.FC<{ reviews: DashboardData['reviews']; highlighted?: boolean }> = ({ reviews, highlighted }) => {
  const navigate = useNavigate();
  if (reviews.due_count === 0) return null;

  return (
    <div className={cn(
      "rounded-lg border border-border/60 bg-card p-2.5 animate-in fade-in slide-in-from-bottom-2 duration-300",
      highlighted && "border-primary/15"
    )}>
      <SectionHead
        icon={<CheckCircle2 className="h-3 w-3 text-primary/60" />}
        title="待复习"
        action={
          <span className="text-[10px] text-muted-foreground/50 font-medium tabular-nums">{reviews.due_count} 题</span>
        }
      />
      <div className="space-y-0.5">
        {reviews.items.slice(0, 3).map(item => (
          <div key={item.question_id} className="flex items-center gap-1.5 py-0.5 px-1 rounded hover:bg-muted/30 transition-colors">
            <div className="h-1 w-1 rounded-full bg-amber-400/60 shrink-0" />
            <p className="text-[11px] truncate text-foreground/80">{item.question_text}</p>
          </div>
        ))}
        {reviews.due_count > 3 && (
          <Button
            variant="ghost"
            size="sm"
            className="w-full h-5 text-[10px] text-muted-foreground/50 mt-0.5"
            onClick={() => navigate('/tests/review')}
          >
            查看全部 {reviews.due_count} 题
          </Button>
        )}
      </div>
    </div>
  );
};

const ExamsList: React.FC<{ exams: DashboardData['exams']; highlighted?: boolean }> = ({ exams, highlighted }) => {
  const navigate = useNavigate();
  if (exams.length === 0) return null;

  return (
    <div className={cn(
      "rounded-lg border border-border/60 bg-card p-2.5 animate-in fade-in slide-in-from-bottom-2 duration-300",
      highlighted && "border-primary/15"
    )}>
      <SectionHead
        icon={<FileText className="h-3 w-3 text-primary/60" />}
        title="考试记录"
        action={
          <Button
            variant="ghost"
            size="sm"
            className="h-5 text-[10px] text-muted-foreground/60 gap-0.5 px-1"
            onClick={() => navigate('/tests')}
          >
            更多 <ArrowRight className="h-2.5 w-2.5" />
          </Button>
        }
      />
      <div className="space-y-0.5">
        {exams.slice(0, 3).map(exam => (
          <div key={exam.id} className="flex items-center gap-2 py-0.5 px-1 rounded hover:bg-muted/30 transition-colors">
            <span className={cn(
              "text-[10px] font-bold tabular-nums shrink-0 w-7 text-center",
              exam.percentage >= 80 ? "text-emerald-500" :
              exam.percentage >= 60 ? "text-amber-500" :
              "text-red-400"
            )}>
              {exam.percentage}
            </span>
            <span className="text-[11px] text-foreground/70">{exam.total_score}/{exam.max_score}</span>
            {exam.elo_change !== 0 && (
              <span className={cn("text-[10px] font-medium tabular-nums shrink-0 ml-auto", exam.elo_change > 0 ? "text-emerald-500" : "text-red-400")}>
                {exam.elo_change > 0 ? '+' : ''}{exam.elo_change}
              </span>
            )}
          </div>
        ))}
      </div>
    </div>
  );
};

const CustomCards: React.FC<{
  cards: DashboardData['custom_cards'];
  highlighted?: boolean;
}> = ({ cards, highlighted }) => {
  const navigate = useNavigate();
  if (!cards || cards.length === 0) return null;

  const renderItem = (item: DashboardData['custom_cards'][0]['items'][0], ii: number) => {
    const clickable = !!item.action_link;
    const wrapperClass = cn(
      "w-full text-left transition-colors",
      clickable && "hover:bg-muted/40 rounded px-0.5 -mx-0.5 cursor-pointer"
    );
    const handleClick = clickable ? () => navigate(item.action_link!) : undefined;

    const content = item.progress != null ? (
      <div className="space-y-0.5">
        <div className="flex justify-between text-[11px]">
          <span className="text-muted-foreground/60 truncate">{item.label}</span>
          <span className="font-semibold tabular-nums">{item.value}</span>
        </div>
        <Progress value={item.progress} className="h-1" />
      </div>
    ) : item.emphasis ? (
      <div className="flex items-baseline gap-1.5">
        <span className="text-base font-bold tabular-nums text-foreground">{item.value}</span>
        <span className="text-[10px] text-muted-foreground/50">{item.label}</span>
      </div>
    ) : (
      <div className="flex items-center justify-between text-[11px]">
        <span className="text-muted-foreground/60 truncate">{item.label}</span>
        <span className={cn(
          "font-semibold tabular-nums shrink-0 ml-1",
          item.trend === 'up' && "text-emerald-500",
          item.trend === 'down' && "text-red-400",
        )}>
          {item.value}
          {item.trend === 'up' && ' ↑'}
          {item.trend === 'down' && ' ↓'}
        </span>
      </div>
    );

    return clickable ? (
      <button key={ii} className={wrapperClass} onClick={handleClick}>{content}</button>
    ) : (
      <div key={ii}>{content}</div>
    );
  };

  return (
    <div className={cn(
      "rounded-lg border border-border/60 bg-card p-2.5 animate-in fade-in slide-in-from-bottom-2 duration-300",
      highlighted && "border-primary/15"
    )}>
      <SectionHead icon={<BarChart3 className="h-3 w-3 text-primary/60" />} title="数据面板" />
      <div className="space-y-2">
        {cards.map((card, ci) => (
          <div key={ci} className="rounded-md border border-border/30 bg-muted/20 p-2 space-y-1.5">
            <div>
              <span className="text-[10px] font-semibold text-foreground/80">{card.title}</span>
              {card.subtitle && (
                <span className="text-[9px] text-muted-foreground/40 ml-1.5">{card.subtitle}</span>
              )}
            </div>
            <div className="space-y-1">
              {card.items?.map((item, ii) => renderItem(item, ii))}
            </div>
            {card.cta && (
              <Button
                variant="ghost"
                size="sm"
                className="w-full h-5 text-[10px] text-primary/70 gap-0.5 mt-1"
                onClick={() => navigate(card.cta!.link)}
              >
                {card.cta.label} <ArrowRight className="h-2.5 w-2.5" />
              </Button>
            )}
          </div>
        ))}
      </div>
    </div>
  );
};

const SECTION_COMPONENTS: Record<string, React.FC<any>> = {
  plan: StudyPlanCard,
  stats: StatsInline,
  mastery: MasteryBars,
  reviews: ReviewsList,
  exams: ExamsList,
  custom_cards: CustomCards,
};

const DEFAULT_ORDER = ['plan', 'stats', 'mastery', 'reviews', 'exams', 'custom_cards'];

export const DashboardPanel: React.FC<DashboardPanelProps> = ({ data, onRefresh }) => {
  const handleTaskToggle = useCallback(async (planId: number, taskId: string, newStatus: string) => {
    try {
      await api.patch(`/ai/plans/${planId}/tasks/${taskId}/`, { status: newStatus });
      onRefresh();
    } catch { console.error('Dashboard fetch failed'); }
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
    custom_cards: { cards: data.custom_cards || [] },
  };

  return (
    <div className="h-full overflow-y-auto p-2.5 space-y-2">
      {order.map(section => {
        const Component = SECTION_COMPONENTS[section];
        if (!Component) return null;
        if (section === 'plan' && !data.plan) return null;
        if (section === 'reviews' && data.reviews.due_count === 0) return null;
        if (section === 'exams' && data.exams.length === 0) return null;
        if (section === 'mastery' && Object.keys(data.mastery).length === 0) return null;
        if (section === 'custom_cards' && (!data.custom_cards || data.custom_cards.length === 0)) return null;
        return <Component key={section} {...sectionData[section]} highlighted={section === highlight} />;
      })}
    </div>
  );
};
