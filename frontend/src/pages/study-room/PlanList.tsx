import React, { useState } from 'react';
import { Card, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { CheckCircle, Circle, ListChecks, Plus, Trash } from '@phosphor-icons/react';
import { cn } from '@/lib/utils';
import api from '@/lib/api';
import { toast } from 'sonner';
import { formatApiErrorToast } from '@/lib/apiError';
import { useConfirm } from '@/components/useConfirm';

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
  const { confirm, Dialog } = useConfirm();

  return (
    <Card className="um-study-plans border-0 shadow-none rounded-none bg-transparent overflow-hidden p-4 md:flex-1 min-h-0 flex flex-col">
      <header className="um-study-section-header mb-3 flex items-center justify-between"><CardTitle className="text-[13px] font-semibold text-foreground">计划清单</CardTitle><ListChecks className="h-4 w-4 text-muted-foreground" /></header>
      <div className="flex-1 overflow-y-auto space-y-1.5 pr-2 scrollbar-none">
        {plans.map(p => (
          <div key={p.id} className={cn("um-study-plan group flex items-center gap-3 p-2 rounded-lg transition-colors", p.is_completed && "is-complete")}>
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
                      content: `✅ 完成了计划：${p.content}`,
                      related_plan_id: p.id
                    });
                  }
                  onPlanCompleted(p.id);
                } catch (e) { toast.error('标记完成失败，请稍后重试'); }
              }}
            >
              {p.is_completed ? <CheckCircle className="h-4 w-4 text-emerald-500" /> : <Circle className="h-4 w-4 text-muted-foreground/20 group-hover:text-emerald-500" />}
            </button>
            <span onClick={() => { if(!p.is_completed) { onStartPlan(p.content, p.id); } }} className={cn("text-[13px] font-normal truncate flex-1", p.is_completed ? "line-through text-muted-foreground cursor-default" : "text-foreground cursor-pointer")}>{p.content}</span>

            <button
              onClick={async (e) => {
                e.stopPropagation();
                if (!(await confirm('确定删除此计划？'))) return;
                try {
                  await api.delete(`/users/plans/${p.id}/`);
                  onRefresh();
                  toast.success('计划已删除');
                  onPlanDeleted(p.id);
                } catch (e) { toast.error(formatApiErrorToast(e, '删除失败')); }
              }}
              className="opacity-100 transition-all p-1.5 hover:bg-red-100 rounded-lg text-muted-foreground/50 hover:text-red-500 cursor-pointer"
              title="删除计划"
            >
              <Trash className="h-3.5 w-3.5" />
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
                  content: `📅 制定了计划：${newPlan}`,
                  related_plan_id: res.data.id
                });
              }
              onRefresh();
              setNewPlan('');
            }
          }}
          placeholder="添加学习计划…"
          className="um-study-plan-input h-9 rounded-lg text-[13px] px-3 text-foreground"
        />
        <Button
          onClick={async () => {
            if (!newPlan.trim()) return;
            const res = await api.post('/users/plans/', { content: newPlan });
            if (allowBroadcast) {
              await api.post('/study/messages/', {
                content: `📅 制定了计划：${newPlan}`,
                related_plan_id: res.data.id
              });
            }
            onRefresh();
            setNewPlan('');
          }}
          size="icon"
          className="um-study-plan-add h-9 w-9 bg-primary text-primary-foreground rounded-lg shrink-0 transition-colors"
          aria-label="添加学习计划"
        >
          <Plus className="h-3.5 w-3.5"/>
        </Button>
      </div>
      {Dialog}
    </Card>
  );
};

export { PlanList };
