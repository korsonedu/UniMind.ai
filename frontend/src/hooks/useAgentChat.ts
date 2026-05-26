import { useState, useRef, useCallback } from 'react';

export interface AgentStep {
  call_id: string;
  step: number;
  status: 'calling' | 'done';
  name: string;
  label: string;
  args_summary?: string;
  result_summary?: string;
}

type AgentEvent =
  | { type: 'step' } & AgentStep
  | { type: 'text_delta'; delta: string }
  | { type: 'done'; full_content: string }
  | { type: 'error'; message: string };

const WS_BASE = import.meta.env.VITE_WS_URL || (
  window.location.protocol === 'https:' ? 'wss://' : 'ws://'
) + window.location.host;

export function useAgentChat(botId: number) {
  const [steps, setSteps] = useState<AgentStep[]>([]);
  const [streamingText, setStreamingText] = useState('');
  const [isDone, setIsDone] = useState(false);
  const [isConnected, setIsConnected] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const wsRef = useRef<WebSocket | null>(null);

  const upsertStep = useCallback((prev: AgentStep[], event: AgentStep): AgentStep[] => {
    const idx = prev.findIndex(s => s.call_id === event.call_id);
    if (idx >= 0) {
      const updated = [...prev];
      updated[idx] = { ...updated[idx], ...event };
      return updated;
    }
    return [...prev, event];
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
          case 'step':
            setSteps(prev => upsertStep(prev, event as AgentStep));
            break;
          case 'text_delta':
            setStreamingText(prev => prev + (event as any).delta);
            break;
          case 'done':
            setStreamingText((event as any).full_content);
            setIsDone(true);
            setIsConnected(false);
            break;
          case 'error':
            setError((event as any).message);
            setIsConnected(false);
            break;
        }
      } catch (err) {
        console.error('Failed to parse WS message:', err);
      }
    };

    ws.onerror = () => {
      setError('WebSocket 连接失败');
      setIsConnected(false);
    };

    ws.onclose = () => {
      setIsConnected(false);
    };
  }, [botId, upsertStep]);

  const reset = useCallback(() => {
    setSteps([]);
    setStreamingText('');
    setIsDone(false);
    setError(null);
    setIsConnected(false);
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
  }, []);

  return {
    steps,
    streamingText,
    isDone,
    isConnected,
    error,
    sendMessage,
    reset,
  };
}
