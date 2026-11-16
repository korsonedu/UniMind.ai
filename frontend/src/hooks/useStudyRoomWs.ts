import { activeWorkspace } from '@/lib/activeWorkspace';
import { useEffect, useRef, useCallback } from 'react';
import { useStudyRoomStore } from '@/store/useStudyRoomStore';

import api from '@/lib/api';
import { getWsBaseUrl, isNativePlatform } from '@/lib/serverConfig';
import { toast } from 'sonner';
import { t } from '@/i18n';

const RECONNECT_DELAY_MS = 2000;
const MAX_RECONNECT_DELAY_MS = 30000;
const HEARTBEAT_INTERVAL_MS = 30000;

/**
 * App 级 WebSocket hook — 自习室会话持久化。
 * 挂载在 App.tsx，路由切换不断开。
 * 仅在已认证用户且需自习室功能时激活。
 */
export function useStudyRoomWs(enabled: boolean) {
  const setWsConnected = useStudyRoomStore(s => s.setWsConnected);
  const setSession = useStudyRoomStore(s => s.setSession);
  const setTimeLeft = useStudyRoomStore(s => s.setTimeLeft);
  const setLastSummary = useStudyRoomStore(s => s.setLastSummary);
  const setCoachEvent = useStudyRoomStore(s => s.setCoachEvent);
  const setSendWsMessage = useStudyRoomStore(s => s.setSendWsMessage);

  const wsRef = useRef<WebSocket | null>(null);
  const reconnectDelayRef = useRef(RECONNECT_DELAY_MS);
  const reconnectTimerRef = useRef<number | null>(null);
  const heartbeatTimerRef = useRef<number | null>(null);
  const mountedRef = useRef(true);
  const generationRef = useRef(0);

  // ── Send helper ──
  const send = useCallback((msg: object) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(msg));
    }
  }, []);

  // Register send function in store so pages can call it
  useEffect(() => {
    setSendWsMessage(send);
    return () => setSendWsMessage(null);
  }, [send, setSendWsMessage]);

  // ── Connect ──
  const connect = useCallback(async function connectSocket() {
    const generation = ++generationRef.current;
    if (!mountedRef.current || !enabled) return;

    // Clean up existing connection
    if (wsRef.current) {
      wsRef.current.onclose = null;
      wsRef.current.close();
      wsRef.current = null;
    }

    let url = `${getWsBaseUrl()}/ws/study-room/?space=${encodeURIComponent(activeWorkspace())}`;
    try {
      if (isNativePlatform()) {
        const { data } = await api.post('/ws-ticket/');
        url += `&ticket=${encodeURIComponent(data.ticket)}`;
      }
    } catch {
      if (!mountedRef.current || generation !== generationRef.current) return;
      setWsConnected(false);
      toast.error(t('自习室连接中断，正在重新连接'), { id: 'study-ws-reconnect' });
      const delay = reconnectDelayRef.current;
      reconnectDelayRef.current = Math.min(delay * 1.5, MAX_RECONNECT_DELAY_MS);
      reconnectTimerRef.current = window.setTimeout(() => { void connectSocket(); }, delay);
      return;
    }
    if (!mountedRef.current || generation !== generationRef.current) return;
    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => {
      if (!mountedRef.current) { ws.close(); return; }
      setWsConnected(true);
      reconnectDelayRef.current = RECONNECT_DELAY_MS;

      // Start heartbeat
      if (heartbeatTimerRef.current) clearInterval(heartbeatTimerRef.current);
      heartbeatTimerRef.current = window.setInterval(() => {
        send({ type: 'ping' });
      }, HEARTBEAT_INTERVAL_MS);
    };

    ws.onmessage = (e) => {
      if (!mountedRef.current) return;
      try {
        const event = JSON.parse(e.data);
        switch (event.type) {
          case 'session.sync':
            setSession(event.session);
            break;
          case 'timer.tick':
            setTimeLeft(event.time_left);
            break;
          case 'timer.expired':
            setSession({
              status: 'ended',
              task_name: event.task_name || '',
              duration: event.duration || 25,
              time_left: 0,
              timer_end_ts: null,
              total_focus: event.total_focus ?? 0,
            });
            // 转发为 coachEvent 以便 StudyRoom 显示 toast + 广播
            setCoachEvent({
              event: 'timer_expired',
              task_name: event.task_name,
              duration: event.duration,
              total_focus: event.total_focus ?? 0,
            });
            break;
          case 'session.ended':
            setLastSummary(event.summary);
            setSession(null);
            break;
          case 'coach.event':
            setCoachEvent(event);
            break;
          case 'pong':
            break;
          case 'error':
            console.warn('[StudyRoom WS]', event.message);
            break;
        }
      } catch (err) {
        console.error('[StudyRoom WS] parse error:', err);
      }
    };

    ws.onerror = () => {
      setWsConnected(false);
    };

    ws.onclose = () => {
      if (!mountedRef.current) return;
      setWsConnected(false);
      if (heartbeatTimerRef.current) {
        clearInterval(heartbeatTimerRef.current);
        heartbeatTimerRef.current = null;
      }

      // Exponential backoff reconnect
      const delay = reconnectDelayRef.current;
      reconnectDelayRef.current = Math.min(delay * 1.5, MAX_RECONNECT_DELAY_MS);
      reconnectTimerRef.current = window.setTimeout(() => {
        connectSocket();
      }, delay);
    };
  }, [enabled, setWsConnected, setSession, setTimeLeft, setLastSummary, setCoachEvent, send]);

  // ── Connect on mount / disconnect on unmount ──
  useEffect(() => {
    mountedRef.current = true;
    if (enabled) {
      connect();
    }
    return () => {
      mountedRef.current = false;
      generationRef.current += 1;
      if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current);
      if (heartbeatTimerRef.current) clearInterval(heartbeatTimerRef.current);
      if (wsRef.current) {
        wsRef.current.onclose = null; // prevent reconnect on intentional close
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  }, [enabled, connect]);

  return { send, connected: useStudyRoomStore(s => s.wsConnected) };
}
