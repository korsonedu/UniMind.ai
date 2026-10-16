import { useState, useEffect, useId } from 'react';
import { Check, Circle, Spinner, X, CaretRight } from '@phosphor-icons/react';
import { Collapse } from './ui/collapse';
import { cn } from '@/lib/utils';
import type { TaskListData } from '@/types/toolRun';

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
  const contentId = useId();
  const [completion, setCompletion] = useState(() => {
    const doneIds = new Set(data.items.filter(item => item.status === 'succeeded').map(item => item.id));
    return { items: data.items, doneIds, justCompleted: doneIds };
  });

  const activeCount = data.items.filter(item => item.status === 'queued' || item.status === 'running').length;
  const succeededCount = data.items.filter(item => item.status === 'succeeded').length;
  const failedCount = data.items.filter(item => item.status === 'failed').length;
  const terminalCount = succeededCount + failedCount;
  const allSucceeded = data.completed && activeCount === 0 && succeededCount > 0 && failedCount === 0;

  // Auto-collapse after all done for 3s
  useEffect(() => {
    if (allSucceeded) {
      const timer = setTimeout(() => {
        setCollapsed(true);
        onComplete?.();
      }, 3000);
      return () => clearTimeout(timer);
    }
  }, [allSucceeded, onComplete]);

  // Track newly completed items for animation
  const doneIds = new Set(data.items.filter(item => item.status === 'succeeded').map(item => item.id));
  if (completion.items !== data.items) {
    setCompletion({ items: data.items, doneIds, justCompleted: new Set([...doneIds].filter(id => !completion.doneIds.has(id))) });
  }
  const justCompleted = completion.justCompleted;

  const succeededItems = data.items.filter(item => item.status === 'succeeded');
  const failedItems = data.items.filter(item => item.status === 'failed');
  const activeItems = data.items.filter(item => item.status === 'queued' || item.status === 'running');

  return (
    <div className="my-3 rounded-xl border border-border/60 bg-card/50 overflow-hidden transition-all duration-300">
      {/* Header */}
      <button
        aria-expanded={!collapsed}
        aria-controls={contentId}
        onClick={() => setCollapsed(!collapsed)}
        className="w-full flex items-center gap-2 px-4 py-2.5 text-sm font-medium text-muted-foreground hover:bg-muted/30 transition-colors"
      >
        <CaretRight className="um-disclosure-chevron w-3.5 h-3.5" />
        <span>
          {allSucceeded
            ? `全部完成 · ${succeededCount} 项`
            : data.completed && failedCount > 0
              ? `已完成 · ${succeededCount} 成功 · ${failedCount} 失败`
              : `进行中 · ${terminalCount}/${data.items.length} 项`}
        </span>
      </button>

      {/* Items */}
      <Collapse open={!collapsed} id={contentId}>
        <div className="border-t border-border/30">
          {/* Active items first */}
          {activeItems.map(item => (
            <div
              key={item.id}
              className="flex items-center gap-3 px-4 py-2.5 text-sm border-b border-border/20 last:border-0"
            >
              {item.status === 'running'
                ? <Spinner className="w-4 h-4 text-primary animate-spin shrink-0" />
                : <Circle className="w-4 h-4 text-muted-foreground/50 shrink-0" />}
              <span className="flex-1 text-foreground">{item.label}</span>
              {item.duration_ms != null && (
                <span className="text-xs text-muted-foreground tabular-nums">
                  {formatDuration(item.duration_ms)}
                </span>
              )}
            </div>
          ))}

          {/* Succeeded items */}
          {succeededItems.map(item => {
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

          {/* Failed items */}
          {failedItems.map(item => (
            <div
              key={item.id}
              className="flex items-start gap-3 px-4 py-2.5 text-sm border-b border-border/20 last:border-0 bg-destructive/[0.04]"
            >
              <X className="w-4 h-4 mt-0.5 text-destructive shrink-0" />
              <div className="flex-1 min-w-0">
                <div className="text-foreground">{item.label}</div>
                {item.error?.message && (
                  <div className="text-xs text-destructive/80 mt-0.5 break-words">
                    {item.error.message}
                  </div>
                )}
              </div>
              {item.duration_ms != null && (
                <span className="text-xs text-muted-foreground/70 tabular-nums">
                  {formatDuration(item.duration_ms)}
                </span>
              )}
            </div>
          ))}
        </div>
      </Collapse>
    </div>
  );
}
