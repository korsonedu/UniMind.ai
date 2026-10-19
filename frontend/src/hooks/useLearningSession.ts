import { useEffect, type RefObject } from 'react';
import api from '@/lib/api';

type Options = {
  enabled: boolean;
  kind: 'video' | 'practice';
  courseId?: number;
  questionIds?: number[];
  videoRef?: RefObject<HTMLVideoElement | null>;
};

export function useLearningSession({ enabled, kind, courseId, questionIds, videoRef }: Options) {
  const questionKey = JSON.stringify(questionIds || []);

  useEffect(() => {
    if (!enabled) return;
    const video = videoRef?.current;
    if (kind === 'video' && !video) return;
    const url = `${api.defaults.baseURL?.replace(/\/$/, '') || ''}/users/me/learning-sessions/`;
    const isActive = () => kind === 'video'
      ? !!video && !video.paused && !video.seeking && !video.ended && video.readyState >= 3
      : document.visibilityState === 'visible';
    const isFocused = () => document.visibilityState === 'visible' && document.hasFocus();
    let lastTick = performance.now();
    let lastWallTime = Date.now();
    let wasActive = isActive();
    let wasFocused = isFocused();
    let session: { id: string; start: number; end: number; active: number; focused: number } | null = null;
    let lastSent = '';

    const flush = () => {
      if (!session || session.active < 1) return;
      const body = JSON.stringify({
        session_id: session.id, kind, course_id: courseId || null,
        question_ids: JSON.parse(questionKey),
        started_at: new Date(session.start).toISOString(),
        ended_at: new Date(session.end).toISOString(),
        active_seconds: Math.floor(session.active), focused_seconds: Math.floor(session.focused),
      });
      if (body === lastSent) return;
      lastSent = body;
      // keepalive 尽量保留切页和关闭页面前的最后一段；累计快照可安全重试。
      void fetch(url, { method: 'POST', credentials: 'include', keepalive: true,
        headers: { 'Content-Type': 'application/json' }, body,
      }).then(response => { if (!response.ok && lastSent === body) lastSent = ''; })
        .catch(() => { if (lastSent === body) lastSent = ''; });
    };

    const tick = () => {
      const now = performance.now();
      const wallTime = Date.now();
      const seconds = (now - lastTick) / 1000;
      // 浏览器挂起、休眠后的时间不补计。中断五分钟后视为新的一次学习。
      if (wasActive && seconds > 0 && seconds <= 5) {
        if (!session || wallTime - session.end >= 5 * 60 * 1000) {
          flush();
          session = { id: crypto.randomUUID(), start: lastWallTime, end: wallTime, active: 0, focused: 0 };
        }
        session.active += seconds;
        if (wasFocused) session.focused += seconds;
        session.end = wallTime;
      }
      lastTick = now;
      lastWallTime = wallTime;
      wasActive = isActive();
      wasFocused = isFocused();
    };
    const checkpoint = () => { tick(); flush(); };
    const onPageHide = () => { checkpoint(); wasActive = false; };
    const onPageShow = () => { lastTick = performance.now(); lastWallTime = Date.now(); wasActive = isActive(); wasFocused = isFocused(); };
    const videoEvents = ['play', 'playing', 'pause', 'waiting', 'seeking', 'seeked', 'ended'];
    videoEvents.forEach(event => video?.addEventListener(event, checkpoint));
    document.addEventListener('visibilitychange', checkpoint);
    window.addEventListener('focus', checkpoint);
    window.addEventListener('blur', checkpoint);
    window.addEventListener('pagehide', onPageHide);
    window.addEventListener('pageshow', onPageShow);
    const clock = window.setInterval(tick, 1000);
    const save = window.setInterval(checkpoint, 15000);
    return () => {
      window.clearInterval(clock);
      window.clearInterval(save);
      videoEvents.forEach(event => video?.removeEventListener(event, checkpoint));
      document.removeEventListener('visibilitychange', checkpoint);
      window.removeEventListener('focus', checkpoint);
      window.removeEventListener('blur', checkpoint);
      window.removeEventListener('pagehide', onPageHide);
      window.removeEventListener('pageshow', onPageShow);
      checkpoint();
    };
  }, [enabled, kind, courseId, questionKey, videoRef]);
}
