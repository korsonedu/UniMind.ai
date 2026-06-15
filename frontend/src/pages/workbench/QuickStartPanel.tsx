import { useState, useEffect, useCallback } from 'react';
import { CheckCircle, Circle, ArrowRight, CaretDown, CaretRight } from '@phosphor-icons/react';
import { toast } from 'sonner';
import api from '@/lib/api';
import { cn } from '@/lib/utils';
import { useNavigate } from 'react-router-dom';

interface Task {
  id: string;
  label: string;
  description: string;
  done: boolean;
  action: { label: string; onClick: () => void };
}

interface Props { studentCount: number; }

export function QuickStartPanel({ studentCount }: Props) {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [loading, setLoading] = useState(true);
  const [collapsed, setCollapsed] = useState(false);
  const [inviteDone, setInviteDone] = useState(
    () => localStorage.getItem('qs_invite_done') === '1'
  );

  const markInviteDone = useCallback(() => {
    setInviteDone(true);
    localStorage.setItem('qs_invite_done', '1');
  }, []);
  const navigate = useNavigate();

  const pulse = useCallback((sel: string, ms = 3000) => {
    const el = document.querySelector(sel) as HTMLElement | null;
    if (!el) return;
    el.scrollIntoView({ behavior: 'smooth', block: 'center' });
    el.style.transition = 'box-shadow 0.3s';
    el.style.boxShadow = '0 0 0 4px hsl(var(--primary))';
    setTimeout(() => { el.style.boxShadow = ''; }, ms);
  }, []);

  const startGuide = useCallback(() => {
    pulse('#avatar-btn');
    toast('点击右上角头像', { description: '然后选择「邀请学员」', duration: 4000 });

    // Step 2: detect avatar click
    const onAvatarClick = () => {
      setTimeout(() => {
        toast('点击「邀请学员」', { description: '复制链接发给学生即可', duration: 4000 });
      }, 300);
      document.querySelector('#avatar-btn')?.removeEventListener('click', onAvatarClick);

      // Step 3: detect menu item click
      const check = setInterval(() => {
        const el = document.querySelector('#invite-menu-item');
        if (el) {
          clearInterval(check);
          el.addEventListener('click', () => {
            markInviteDone();
          }, { once: true });
        }
      }, 200);
      setTimeout(() => clearInterval(check), 6000);
    };

    document.querySelector('#avatar-btn')?.addEventListener('click', onAvatarClick, { once: true });
  }, [pulse]);

  useEffect(() => {
    api.get('/users/institution/me/bulk-init/')
      .then(bulkRes => {
        const bulk = bulkRes.data || {};
        const kpCount = bulk.kp_count ?? 0;
        const hasUsedBulk = bulk.has_used ?? false;
        const list: Task[] = [];

        list.push({
          id: 'invite', label: '邀请学生',
          description: '点击右上角头像 → 邀请学员',
          done: inviteDone,
          action: { label: '去看看', onClick: startGuide },
        });

        if (kpCount === 0) list.push({
          id: 'knowledge_tree', label: '建立知识树',
          description: '选择学科导入或自定义知识点体系', done: false,
          action: { label: '去设置', onClick: () => navigate('/knowledge-tree') },
        });

        if (!hasUsedBulk && kpCount > 0) list.push({
          id: 'bulk_init', label: '初始化题库',
          description: 'AI 为 ' + kpCount + ' 个知识点批量生成题目', done: false,
          action: { label: '去生成', onClick: () => document.getElementById('bulk-init-card')?.scrollIntoView({ behavior: 'smooth' }) },
        });

        setTasks(list);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [studentCount, inviteDone, navigate, startGuide]);

  if (loading) return null;
  const doneCount = tasks.filter(t => t.done).length;
  if (tasks.length > 0 && doneCount === tasks.length) return null;
  if (tasks.length === 0) return null;

  return (
    <div className="rounded-xl border border-primary/15 bg-primary/[0.02] overflow-hidden">
      <button onClick={() => setCollapsed(!collapsed)} className="w-full flex items-center gap-2 px-4 py-3 hover:bg-primary/[0.04] transition-colors">
        <span className="text-sm font-black tracking-tight">快速启动</span>
        <span className="text-[10px] font-bold text-muted-foreground bg-muted/50 px-1.5 py-0.5 rounded">{doneCount}/{tasks.length}</span>
        <span className="ml-auto text-muted-foreground/50">{collapsed ? <CaretRight className="h-3.5 w-3.5" /> : <CaretDown className="h-3.5 w-3.5" />}</span>
      </button>
      {!collapsed && (
        <div className="px-3 pb-3 space-y-1">
          {tasks.map(task => (
            <div key={task.id} className={cn("flex items-center gap-2.5 px-3 py-2 rounded-lg transition-colors", task.done ? "bg-emerald-50/50 text-emerald-700" : "hover:bg-muted/50 text-muted-foreground hover:text-foreground")}>
              {task.done ? <CheckCircle className="h-4 w-4 text-emerald-500 shrink-0" weight="fill" /> : <Circle className="h-4 w-4 shrink-0" />}
              <div className="flex-1 min-w-0">
                <span className="text-xs font-bold">{task.label}</span>
                {!task.done && <span className="text-[10px] text-muted-foreground ml-1.5">{task.description}</span>}
              </div>
              {!task.done && (
                <button onClick={task.action.onClick} className="shrink-0 text-[10px] font-bold text-primary hover:text-primary/80 transition-colors flex items-center gap-0.5">
                  {task.action.label}<ArrowRight className="h-3 w-3" />
                </button>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
