import { create } from 'zustand';

export type SessionStatus = 'idle' | 'active' | 'paused' | 'ended';

export interface StudySession {
  status: SessionStatus;
  task_name: string;
  duration: number;
  time_left: number;
  timer_end_ts: number | null;
  total_focus: number;
}

export interface SessionEndedSummary {
  task_name: string;
  duration: number;
  total_focus_seconds: number;
}

interface StudyRoomState {
  // ── WS 连接状态 ──
  wsConnected: boolean;
  setWsConnected: (v: boolean) => void;

  // ── 会话状态 (来自服务器) ──
  session: StudySession | null;
  setSession: (s: StudySession | null) => void;

  // ── Timer ──
  timeLeft: number;
  setTimeLeft: (v: number) => void;
  isActive: boolean;

  // ── 上次结束的摘要 ──
  lastSummary: SessionEndedSummary | null;
  setLastSummary: (s: SessionEndedSummary | null) => void;

  // ── 督学事件 ──
  coachEvent: { event: string; [key: string]: any } | null;
  setCoachEvent: (e: { event: string; [key: string]: any } | null) => void;

  // ── 动作 ──
  sendWsMessage: ((msg: object) => void) | null;
  setSendWsMessage: (fn: ((msg: object) => void) | null) => void;

  // ── 便捷 actions ──
  startSession: (taskName: string, duration: number) => void;
  pauseSession: () => void;
  resumeSession: () => void;
  endSession: () => void;
  reset: () => void;
}

export const useStudyRoomStore = create<StudyRoomState>()((set, get) => ({
  wsConnected: false,
  setWsConnected: (v) => set({ wsConnected: v }),

  session: null,
  setSession: (s) => set({
    session: s,
    isActive: s?.status === 'active',
    timeLeft: s?.time_left ?? 0,
  }),

  timeLeft: 0,
  setTimeLeft: (v) => set({ timeLeft: v }),
  isActive: false,

  lastSummary: null,
  setLastSummary: (s) => set({ lastSummary: s }),

  coachEvent: null,
  setCoachEvent: (e) => set({ coachEvent: e }),

  sendWsMessage: null,
  setSendWsMessage: (fn) => set({ sendWsMessage: fn }),

  startSession: (taskName, duration) => {
    const { sendWsMessage } = get();
    sendWsMessage?.({ type: 'session.start', task_name: taskName, duration });
  },

  pauseSession: () => {
    const { sendWsMessage } = get();
    sendWsMessage?.({ type: 'session.pause' });
  },

  resumeSession: () => {
    const { sendWsMessage } = get();
    sendWsMessage?.({ type: 'session.resume' });
  },

  endSession: () => {
    const { sendWsMessage } = get();
    sendWsMessage?.({ type: 'session.end' });
  },

  reset: () => set({
    session: null,
    timeLeft: 0,
    isActive: false,
    lastSummary: null,
    coachEvent: null,
  }),
}));
