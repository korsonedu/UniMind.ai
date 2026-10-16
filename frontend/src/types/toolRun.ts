import type { GeneratedQuestion } from './api';


export type ToolTaskStatus = 'queued' | 'running' | 'succeeded' | 'failed';

export interface ToolTaskError {
  code: string;
  message: string;
}

export interface AgentStep {
  type?: 'step';
  run_id: string;
  call_id: string;
  round: number;
  name: string;
  label: string;
  status: ToolTaskStatus | 'batch_start';
  duration_ms?: number;
  args_summary?: string;
  result_summary?: string;
  retry_of?: string | null;
  error?: ToolTaskError | null;
  actions?: Array<{ label: string; route: string }>;
  visual?: { type: string; payload: unknown };
  questions?: (GeneratedQuestion & { index: number; answer_preview: string })[];
}

export interface TaskItem {
  id: string;
  run_id: string;
  round: number;
  name: string;
  label: string;
  status: ToolTaskStatus;
  duration_ms?: number;
  result_summary?: string;
  retry_of?: string | null;
  error?: ToolTaskError | null;
}

export interface TaskListData {
  run_id: string;
  items: TaskItem[];
  completed: boolean;
}

function isTerminalStatus(status: ToolTaskStatus): boolean {
  switch (status) {
    case 'queued':
    case 'running':
      return false;
    case 'succeeded':
    case 'failed':
      return true;
    default: {
      const exhaustive: never = status;
      return exhaustive;
    }
  }
}

function isToolTaskStatus(status: AgentStep['status']): status is ToolTaskStatus {
  return status === 'queued' || status === 'running' || status === 'succeeded' || status === 'failed';
}

function taskItemFromStep(event: AgentStep): TaskItem {
  if (event.status === 'batch_start') {
    throw new Error('Legacy batch_start cannot create a Tool Run task');
  }
  return {
    id: event.call_id,
    run_id: event.run_id,
    round: event.round,
    name: event.name,
    label: event.label,
    status: event.status,
    duration_ms: event.duration_ms,
    result_summary: event.result_summary,
    retry_of: event.retry_of,
    error: event.error,
  };
}

export function reduceToolRun(
  previous: TaskListData | null,
  event: AgentStep,
): TaskListData | null {
  if (!event.run_id || !event.call_id || !isToolTaskStatus(event.status)) return previous;

  const nextItem = taskItemFromStep(event);
  if (!previous || previous.run_id !== event.run_id) {
    return {
      run_id: event.run_id,
      items: [nextItem],
      completed: false,
    };
  }

  const existingIndex = previous.items.findIndex(item => item.id === event.call_id);
  if (existingIndex < 0) {
    return {
      ...previous,
      items: [...previous.items, nextItem],
    };
  }

  const existing = previous.items[existingIndex];
  const status = isTerminalStatus(existing.status) && !isTerminalStatus(nextItem.status)
    ? existing.status
    : nextItem.status;
  const items = [...previous.items];
  items[existingIndex] = { ...existing, ...nextItem, status };
  return { ...previous, items };
}

export function upsertToolStepMessage<T extends { toolStep?: AgentStep }>(
  messages: T[],
  event: AgentStep,
  createMessage: (event: AgentStep) => T,
): T[] {
  if (!event.run_id || !event.call_id || !isToolTaskStatus(event.status)) return messages;
  const existingIndex = messages.findIndex(message => message.toolStep?.call_id === event.call_id);
  if (existingIndex < 0) return [...messages, createMessage(event)];

  const updated = [...messages];
  updated[existingIndex] = { ...updated[existingIndex], toolStep: event };
  return updated;
}

export function shouldExpandToolRun(
  previousRunId: string,
  data: TaskListData,
): boolean {
  return previousRunId !== data.run_id || data.items.some(item => item.status === 'failed');
}

export function completeToolRun(
  previous: TaskListData | null,
  runId?: string,
): TaskListData | null {
  if (!previous || (runId && previous.run_id !== runId)) return previous;
  return { ...previous, completed: true };
}
