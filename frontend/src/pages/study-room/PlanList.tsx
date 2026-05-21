import React, { useState } from 'react';
import { Card, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  CheckCircle2, Circle, ListTodo, Plus, Trash2
} from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { cn } from '@/lib/utils';
import api from '@/lib/api';
import { toast } from 'sonner';
import { formatApiErrorToast } from '@/lib/apiError';

interface PlanListProps {
  plans: Array<{ id: number; content: string; is_completed: boolean }>;
  allowBroadcast: boolean;
  onRefresh: () => void;
  onStartPlan: (content: string, planId: number) => void;
  onPlanCompleted: (planId: number) => void;
  onPlanDeleted: (planId: number) => void;
}

const PlanList: React.FC<PlanListProps> = (props) => {
  const { plans, allowBroadcast, onRefresh, onStartPlan, onPlanCompleted, onPlanDeleted } = props;
  const [newPlan, setNewPlan] = useState('');
  const { t } = useTranslation('studyRoom');

  return (
    <Card className="border-none shadow-sm rounded-2xl md:rounded-3xl bg-card overflow-hidden p-4 md:p-6 md:flex-1 min-h-0 flex flex-col border border-border">
      <header className="mb-4 flex items-center justify-between border-b border-border pb-4"><CardTitle className="text-[13px] font-bold uppercase tracking-widest text-muted-foreground">{t('planList.title')}</CardTitle><ListTodo className="h-4 w-4 text-muted-foreground opacity-20" /></header>
      <div className="flex-1 overflow-y-auto space-y-1.5 pr-2 scrollbar-none">
        {plans.map(p => (
          <div key={p.id} className={cn("group flex items-center gap-3 p-2 rounded-2xl transition-all border border-transparent", p.is_completed ? "bg-muted/30 opacity-60" : "hover:bg-muted hover:border-border")}>
            <button
              disabled={p.is_completed}
              className={cn("transition-colors", p.is_completed ? "cursor-not-allowed" : "cursor-pointer")}
              onClick={async () => {
                if (p.is_completed) return;
                try {
                  await api.patch(`/users/plans/${p.id}/`, { is_completed: true });
                  onRefresh();
                  if (allowBroadcast) {
                    await api.post('/study/messages/', {
                      content: t('planCompleted', { emoji: '✅', plan: p.content }),
                      related_plan_id: p.id
                    });
                  }
                  onPlanCompleted(p.id);
                } catch (e) { toast.error('标记完成失败，请稍后重试'); }
              }}
            >
              {p.is_completed ? <CheckCircle2 className="h-4 w-4 text-emerald-500" /> : <Circle className="h-4 w-4 text-muted-foreground/20 group-hover:text-emerald-500" />}
            </button>
            <span onClick={() => { if(!p.is_completed) { onStartPlan(p.content, p.id); } }} className={cn("text-xs font-bold truncate flex-1", p.is_completed ? "line-through text-muted-foreground cursor-default" : "text-foreground cursor-pointer")}>{p.content}</span>

            <button
              onClick={async (e) => {
                e.stopPropagation();
                try {
                  await api.delete(`/users/plans/${p.id}/`);
                  onRefresh();
                  toast.success(t('planList.planDeleted'));
                  onPlanDeleted(p.id);
                } catch (e) { toast.error(formatApiErrorToast(e, t('planList.deleteFailed'))); }
              }}
              className="opacity-0 group-hover:opacity-100 transition-all p-1.5 hover:bg-red-100 rounded-lg text-muted-foreground/50 hover:text-red-500 cursor-pointer"
              title={t('planList.deletePlan')}
            >
              <Trash2 className="h-3.5 w-3.5" />
            </button>
          </div>
        ))}
      </div>
      <div className="mt-4 flex gap-2">
        <Input
          value={newPlan}
          onChange={e => setNewPlan(e.target.value)}
          onKeyDown={async (e) => {
            if (e.key === 'Enter' && !(e.nativeEvent as any).isComposing) {
              if (!newPlan.trim()) return;
              const res = await api.post('/users/plans/', { content: newPlan });
              if (allowBroadcast) {
                await api.post('/study/messages/', {
                  content: t('planList.planCreated', { emoji: '📅', plan: newPlan }),
                  related_plan_id: res.data.id
                });
              }
              onRefresh();
              setNewPlan('');
            }
          }}
          placeholder={t('planList.addTarget')}
          className="bg-muted border-none h-8 rounded-lg text-[11px] font-bold px-3 text-foreground focus-visible:ring-1 focus-visible:ring-primary/20"
        />
        <Button
          onClick={async () => {
            if (!newPlan.trim()) return;
            const res = await api.post('/users/plans/', { content: newPlan });
            if (allowBroadcast) {
              await api.post('/study/messages/', {
                content: t('planList.planCreated', { emoji: '📅', plan: newPlan }),
                related_plan_id: res.data.id
              });
            }
            onRefresh();
            setNewPlan('');
          }}
          size="icon"
          className="h-8 w-8 bg-primary text-primary-foreground rounded-lg shrink-0 hover:opacity-90 active:scale-95 transition-all"
        >
          <Plus className="h-3.5 w-3.5"/>
        </Button>
      </div>
    </Card>
  );
};

export { PlanList };
