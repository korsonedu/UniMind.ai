import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { PageWrapper } from '@/components/PageWrapper';
import { useFetch } from '@/lib/useFetch';
import { toast } from 'sonner';
import api from '@/lib/api';
import { formatApiErrorToast } from '@/lib/apiError';
import { InterviewLobby } from '@/components/interviews/InterviewLobby';
import { SessionList } from '@/components/interviews/SessionList';
import { SessionChat } from '@/components/interviews/SessionChat';
import { InlineError } from '@/components/InlineError';

interface Turn {
  id: number;
  speaker: 'candidate' | 'interviewer';
  content_text: string;
  feedback_for_turn?: string;
}

interface SessionItem {
  id: number;
  session_type: 'resume' | 'english' | 'professional' | 'mixed';
  interviewer_style: 'friendly' | 'pressure';
  status: 'ongoing' | 'completed' | 'analyzing';
  radar_scores: Record<string, number>;
  overall_feedback: string;
  started_at: string;
  turns?: Turn[];
}

export const Interviews: React.FC = () => {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const activeSessionId = Number(searchParams.get('session_id') || 0);
  const [activeTab, setActiveTab] = useState<'lobby' | 'history'>('lobby');
  const [style, setStyle] = useState<'friendly' | 'pressure'>('friendly');
  const [detailTurns, setDetailTurns] = useState<Record<number, Turn[]>>({});

  const {
    data: sessions,
    loading: historyLoading,
    error: historyFailed,
    refetch,
  } = useFetch<SessionItem[]>((signal) =>
    api.get('/interviews/sessions/', { signal }).then((r) => (r.data?.results || []) as SessionItem[]),
  );

  const activeSession = useMemo(() => {
    const s = (sessions || []).find((s) => s.id === activeSessionId) || null;
    if (s && detailTurns[activeSessionId]) {
      return { ...s, turns: detailTurns[activeSessionId] };
    }
    return s;
  }, [sessions, activeSessionId, detailTurns]);

  const loadDetail = useCallback(async (sid: number) => {
    try {
      const res = await api.get(`/interviews/sessions/${sid}/`);
      const detail = res.data as SessionItem;
      if (detail.turns) {
        setDetailTurns((prev) => ({ ...prev, [sid]: detail.turns! }));
      }
      refetch();
    } catch (e) {
      toast.error(formatApiErrorToast(e, '加载会话详情失败'));
    }
  }, [refetch]);

  useEffect(() => {
    if (activeSessionId > 0) {
      loadDetail(activeSessionId);
    }
  }, [activeSessionId, loadDetail]);

  const handleSessionCreated = useCallback((sessionId: number) => {
    refetch();
    setActiveTab('history');
    navigate(`/interviews?session_id=${sessionId}`);
    loadDetail(sessionId);
  }, [refetch, navigate, loadDetail]);

  const handleSessionSelect = (id: number) => {
    navigate(`/interviews?session_id=${id}`);
  };

  const handleRefresh = useCallback(() => {
    if (activeSessionId > 0) {
      loadDetail(activeSessionId);
    } else {
      refetch();
    }
  }, [activeSessionId, loadDetail, refetch]);

  const tabClass = (active: boolean) =>
    `text-[13px] font-semibold pb-2 border-b-2 transition-colors ${
      active ? 'border-neutral-900 text-neutral-900' : 'border-transparent text-neutral-400 hover:text-neutral-600'
    }`;

  return (
    <PageWrapper title="模拟面试" subtitle="简历调优、实时追问、逐轮反馈与五维复盘雷达。">
      <div className="max-w-6xl mx-auto space-y-5 pb-20">
        {/* Tab bar */}
        <div className="flex items-center gap-5 border-b border-neutral-200">
          <button onClick={() => setActiveTab('lobby')} className={tabClass(activeTab === 'lobby')}>
            面试大厅
          </button>
          <button onClick={() => setActiveTab('history')} className={tabClass(activeTab === 'history')}>
            会话与复盘
          </button>
        </div>

        {activeTab === 'lobby' ? (
          <InterviewLobby style={style} onStyleChange={setStyle} onSessionCreated={handleSessionCreated} />
        ) : historyLoading && (!sessions || sessions.length === 0) ? (
          <div className="flex items-center justify-center py-20">
            <p className="text-[13px] text-neutral-400">加载中...</p>
          </div>
        ) : historyFailed ? (
          <div className="py-10">
            <InlineError message={historyFailed} onRetry={refetch} />
          </div>
        ) : !sessions || sessions.length === 0 ? (
          <div className="flex items-center justify-center py-20">
            <p className="text-[13px] text-neutral-400">暂无面试记录，去面试大厅开始一场模拟面试</p>
          </div>
        ) : (
          <div className="grid grid-cols-[200px_1fr] gap-0 border border-neutral-200 rounded-lg overflow-hidden" style={{ height: '580px' }}>
            {/* Sidebar */}
            <div className="border-r border-neutral-200 bg-neutral-50/50 p-3 overflow-y-auto">
              <p className="text-[10px] font-semibold uppercase tracking-widest text-neutral-400 mb-2 px-3">会话</p>
              <SessionList sessions={sessions} activeId={activeSessionId} onSelect={handleSessionSelect} />
            </div>
            {/* Main content */}
            <div className="p-4 bg-white overflow-hidden">
              {!activeSessionId ? (
                <div className="flex items-center justify-center h-full min-h-[480px]">
                  <p className="text-[13px] text-neutral-400">选择左侧会话查看详情</p>
                </div>
              ) : !activeSession ? (
                <div className="flex items-center justify-center h-full min-h-[480px]">
                  <p className="text-[13px] text-neutral-400">会话不存在或无权限</p>
                </div>
              ) : (
                <SessionChat session={activeSession} onRefresh={handleRefresh} />
              )}
            </div>
          </div>
        )}
      </div>
    </PageWrapper>
  );
};
