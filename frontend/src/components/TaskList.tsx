import { useState, useEffect, useRef } from 'react';
import { Check, Spinner, CaretDown, CaretRight } from '@phosphor-icons/react';
import { cn } from '@/lib/utils';

export interface TaskItem {
  id: string;
  label: string;
  status: 'running' | 'done';
  duration_ms?: number;
}

export interface TaskListData {
  task_id: string;
  items: TaskItem[];
}

interface TaskListProps {
  data: TaskListData;
  onComplete?: () => void;
}

function formatDuration(ms: number): string {
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

export function TaskList({ data, onComplete }: TaskListProps) {
  const [collapsed, setCollapsed] = useState(false);
  const prevDoneRef = useRef<Set<string>>(new Set());

  const runningCount = data.items.filter(i => i.status === 'running').length;
  const doneCount = data.items.filter(i => i.status === 'done').length;
  const allDone = runningCount === 0 && doneCount > 0;

  // Auto-collapse after all done for 3s
  useEffect(() => {
    if (allDone) {
      const timer = setTimeout(() => {
        setCollapsed(true);
        onComplete?.();
      }, 3000);
      return () => clearTimeout(timer);
    }
  }, [allDone, onComplete]);

  // Track newly completed items for animation
  const doneIds = new Set(data.items.filter(i => i.status === 'done').map(i => i.id));
  const justCompleted = new Set([...doneIds].filter(id => !prevDoneRef.current.has(id)));
  prevDoneRef.current = doneIds;

  const doneItems = data.items.filter(i => i.status === 'done');
  const activeItems = data.items.filter(i => i.status === 'running');

  return (
    <div className="my-3 rounded-xl border border-border/60 bg-card/50 overflow-hidden transition-all duration-300">
      {/* Header */}
      <button
        onClick={() => setCollapsed(!collapsed)}
        className="w-full flex items-center gap-2 px-4 py-2.5 text-sm font-medium text-muted-foreground hover:bg-muted/30 transition-colors"
      >
        {collapsed ? <CaretRight className="w-3.5 h-3.5" /> : <CaretDown className="w-3.5 h-3.5" />}
        <span>
          {allDone
            ? `全部完成 · ${doneCount} 项`
            : `进行中 · ${doneCount}/${data.items.length} 项`}
        </span>
      </button>

      {/* Items */}
      {!collapsed && (
        <div className="border-t border-border/30">
          {/* Active items first */}
          {activeItems.map(item => (
            <div
              key={item.id}
              className="flex items-center gap-3 px-4 py-2.5 text-sm border-b border-border/20 last:border-0"
            >
              <Spinner className="w-4 h-4 text-primary animate-spin shrink-0" />
              <span className="flex-1 text-foreground">{item.label}</span>
              {item.duration_ms != null && (
                <span className="text-xs text-muted-foreground tabular-nums">
                  {formatDuration(item.duration_ms)}
                </span>
              )}
            </div>
          ))}

          {/* Done items */}
          {doneItems.map(item => {
            const isNew = justCompleted.has(item.id);
            return (
              <div
                key={item.id}
                className={cn(
                  'flex items-center gap-3 px-4 py-2 text-sm border-b border-border/20 last:border-0 transition-all duration-500',
                  isNew && 'bg-emerald-50/50 dark:bg-emerald-950/20',
                )}
              >
                <Check className="w-4 h-4 text-emerald-500 shrink-0" />
                <span className="flex-1 text-muted-foreground line-through decoration-muted-foreground/30">
                  {item.label}
                </span>
                {item.duration_ms != null && (
                  <span className="text-xs text-muted-foreground/70 tabular-nums">
                    {formatDuration(item.duration_ms)}
                  </span>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
