import { useState, useRef, useCallback, useEffect } from 'react';
import {
  completeToolRun,
  reduceToolRun,
  type AgentStep,
  type TaskListData,
} from '@/types/toolRun';

export type { AgentStep } from '@/types/toolRun';

type AgentEvent =
  | { type: 'step' } & AgentStep
  | { type: 'text_delta'; delta: string }
  | { type: 'message'; content: string }
  | { type: 'done'; full_content: string; has_intermediate?: boolean; run_id?: string }
  | { type: 'error'; message: string }
  | { type: 'ping' };

const WS_BASE = import.meta.env.VITE_WS_URL || (
  window.location.protocol === 'https:' ? 'wss://' : 'ws://'
) + window.location.host;

export function useAgentChat(botId: number) {
  const [steps, setSteps] = useState<AgentStep[]>([]);
  const [streamingText, setStreamingText] = useState('');
  const [messages, setMessages] = useState<string[]>([]);
  const [isDone, setIsDone] = useState(false);
  const [isConnected, setIsConnected] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [taskList, setTaskList] = useState<TaskListData | null>(null);
  const wsRef = useRef<WebSocket | null>(null);

  // Cleanup WebSocket on unmount
  useEffect(() => {
    return () => {
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  }, []);

  const upsertStep = useCallback((prev: AgentStep[], event: AgentStep): AgentStep[] => {
    const idx = prev.findIndex(s => s.call_id === event.call_id);
    if (idx >= 0) {
      const updated = [...prev];
      updated[idx] = { ...updated[idx], ...event };
      return updated;
    }
    return [...prev, event];
  }, []);

  const reset = useCallback(() => {
    setSteps([]);
    setStreamingText('');
    setMessages([]);
    setIsDone(false);
    setError(null);
    setIsConnected(false);
    setTaskList(null);
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
  }, []);

  const sendMessage = useCallback((message: string) => {
    reset();
    setIsConnected(true);

    const ws = new WebSocket(`${WS_BASE}/ws/ai/chat/${botId}/`);
    wsRef.current = ws;

    ws.onopen = () => {
      ws.send(JSON.stringify({ message }));
    };

    ws.onmessage = (e) => {
      try {
        const event: AgentEvent = JSON.parse(e.data);
        switch (event.type) {
          case 'step': {
            const stepEvent = event as AgentStep;
            setTaskList(prev => reduceToolRun(prev, stepEvent));
            if (stepEvent.status === 'batch_start') break;
            setSteps(prev => upsertStep(prev, stepEvent));
            break;
          }
          case 'ping':
            break;
          case 'text_delta':
            setStreamingText(prev => prev + (event as { type: 'text_delta'; delta: string }).delta);
            break;
          case 'message': {
            const msg = event as { type: 'message'; content: string };
            if (msg.content) {
              setMessages(prev => [...prev, msg.content]);
            }
            break;
          }
          case 'done': {
            const done = event as { type: 'done'; full_content: string; run_id?: string };
            setStreamingText(done.full_content);
            setTaskList(prev => completeToolRun(prev, done.run_id));
            setIsDone(true);
            setIsConnected(false);
            break;
          }
          case 'error': {
            const err = event as { type: 'error'; message: string };
            setError(err.message);
            setIsConnected(false);
            break;
          }
        }
      } catch (err) {
        console.error('Failed to parse WS message:', err);
      }
    };

    ws.onerror = () => {
      setError('WebSocket 连接失败');
      setIsConnected(false);
    };

    const currentWs = ws;
    ws.onclose = (e) => {
      setIsConnected(false);
      // If closed abnormally and this socket is still the active one, ensure UI unblocks
      if (e.code !== 1000 && wsRef.current === currentWs) {
        setIsDone(true);
      }
    };
  }, [botId, upsertStep, reset]);



  return {
    steps,
    streamingText,
    messages,
    isDone,
    isConnected,
    error,
    sendMessage,
    reset,
    taskList,
  };
}
