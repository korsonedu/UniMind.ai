import { t, useLocale } from '@/i18n';
import { useState, useEffect, useId, useRef } from 'react';
import { CaretRight, Check, CheckCircle, Circle, ListChecks, Spinner, X, XCircle } from '@phosphor-icons/react';
import { Collapse } from './ui/collapse';
import { shouldExpandToolRun, type TaskListData, type ToolTaskStatus } from '@/types/toolRun';
import { useSystemStore } from '@/store/useSystemStore';
import './task-list.css';

interface TaskListProps {
  data: TaskListData;
  onComplete?: () => void;
}

const taskStatus = {
  queued: { Icon: Circle, label: '等待中' },
  running: { Icon: Spinner, label: '进行中' },
  succeeded: { Icon: Check, label: '已完成' },
  failed: { Icon: X, label: '失败' },
} satisfies Record<ToolTaskStatus, { Icon: typeof Circle; label: string }>;

function formatDuration(ms: number): string {
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

export function TaskList({ data, onComplete }: TaskListProps) {
  useLocale();
  const toolDetails = useSystemStore(state => state.toolDetails);
  const [collapsed, setCollapsed] = useState(false);
  const [previousToolDetails, setPreviousToolDetails] = useState(toolDetails);
  if (previousToolDetails !== toolDetails) {
    setPreviousToolDetails(toolDetails);
    if (toolDetails === 'expanded') setCollapsed(false);
  }
  const previousRunId = useRef(data.run_id);
  const contentId = useId();
  const activeItems = data.items.filter(item => item.status === 'queued' || item.status === 'running');
  const succeededItems = data.items.filter(item => item.status === 'succeeded');
  const failedItems = data.items.filter(item => item.status === 'failed');
  const succeededCount = succeededItems.length;
  const failedCount = failedItems.length;
  const terminalCount = succeededCount + failedCount;
  const allSucceeded = data.completed && !data.failed && activeItems.length === 0 && succeededCount > 0 && failedCount === 0;
  const runFailed = data.completed && (data.failed || failedCount > 0);
  const SummaryIcon = allSucceeded ? CheckCircle : runFailed ? XCircle : ListChecks;

  useEffect(() => {
    if (shouldExpandToolRun(previousRunId.current, data)) {
      setCollapsed(false);
    }
    previousRunId.current = data.run_id;
  }, [data]);

  // Auto-collapse after all done for 3s
  useEffect(() => {
    if (allSucceeded) {
      const timer = setTimeout(() => {
        if (toolDetails === 'auto') setCollapsed(true);
        onComplete?.();
      }, 3000);
      return () => clearTimeout(timer);
    }
  }, [allSucceeded, onComplete, toolDetails]);

  return (
    <div className="um-chat-tasks">
      <div className="min-h-0 overflow-hidden">
        <div className="um-chat-tasks-panel">
          <button
            type="button"
            aria-expanded={!collapsed}
            aria-controls={contentId}
            onClick={() => setCollapsed(value => !value)}
            className="um-chat-tasks-summary"
          >
            <SummaryIcon size={16} aria-hidden="true" />
            <span className="flex-1">
              {allSucceeded
                ? t('全部完成 · {0} 项', { 0: succeededCount })
                : runFailed
                  ? t('本轮未完成 · {0} 成功 · {1} 失败', { 0: succeededCount, 1: failedCount })
                  : t('进行中 · {0}/{1} 项', { 0: terminalCount, 1: data.items.length })}
            </span>
            <CaretRight size={14} className="um-disclosure-chevron" aria-hidden="true" />
          </button>

          <Collapse open={!collapsed} id={contentId}>
            <ul className="um-chat-tasks-items" role="list">
              {[...activeItems, ...succeededItems, ...failedItems].map(item => {
                const { Icon, label } = taskStatus[item.status];
                return (
                  <li key={item.id} data-status={item.status} className="um-chat-task">
                    <Icon size={14} role="img" aria-label={t(label)} className="um-chat-task-status" />
                    <div className="min-w-0 flex-1 break-words">
                      {t(item.label)}
                      {item.status === 'failed' && item.error?.message && (
                        <p className="um-chat-task-error">{item.error.message}</p>
                      )}
                    </div>
                    {item.duration_ms != null && (
                      <span className="um-chat-task-duration">{formatDuration(item.duration_ms)}</span>
                    )}
                  </li>
                );
              })}
            </ul>
          </Collapse>
        </div>
      </div>
    </div>
  );
}
