import React, { useEffect, useMemo, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { PageWrapper } from '@/components/PageWrapper';
import { Card } from '@/components/ui/card';
import { Bot } from 'lucide-react';
import { EmptyState } from '@/components/EmptyState';
import { InlineError } from '@/components/InlineError';
import { useFetch } from '@/lib/useFetch';
import { toast } from 'sonner';
import api from '@/lib/api';
import { formatApiErrorToast } from '@/lib/apiError';
import { InterviewLobby } from '@/components/interviews/InterviewLobby';
import { SessionList } from '@/components/interviews/SessionList';
import { SessionChat } from '@/components/interviews/SessionChat';

type SessionItem = {
  id: number;
  session_type: 'resume' | 'english' | 'professional' | 'mixed';
  interviewer_style: 'friendly' | 'pressure';
  status: 'ongoing' | 'completed' | 'analyzing';
  radar_scores: Record<string, number>;
  overall_feedback: string;
  started_at: string;
  turns?: Array<{
    id: number;
    speaker: 'candidate' | 'interviewer';
    content_text: string;
    feedback_for_turn?: string;
  }>;
};

export const Interviews: React.FC = () => {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const activeSessionId = Number(searchParams.get('session_id') || 0);
  const [activeTab, setActiveTab] = useState<'lobby' | 'history'>('lobby');
  const [style, setStyle] = useState<'friendly' | 'pressure'>('friendly');

  const {
    data: sessions,
    loading: historyLoading,
    error: historyFailed,
    refetch,
  } = useFetch<SessionItem[]>((signal) =>
    api.get('/interviews/sessions/', { signal }).then((r) => (r.data?.results || []) as SessionItem[]),
  );

  const activeSession = useMemo(
    () => (sessions || []).find((s) => s.id === activeSessionId) || null,
    [sessions, activeSessionId],
  );

  // Load session detail when navigating via URL param
  useEffect(() => {
    if (activeSessionId > 0 && activeSession?.turns === undefined) {
      api
        .get(`/interviews/sessions/${activeSessionId}/`)
        .then(() => refetch())
        .catch((e) => toast.error(formatApiErrorToast(e, '加载会话详情失败')));
    }
  }, [activeSessionId]);

  const handleSessionCreated = (sessionId: number) => {
    refetch(); setActiveTab('history'); navigate(`/interviews?session_id=${sessionId}`);
  };

  const handleSessionSelect = (id: number) => {
    navigate(`/interviews?session_id=${id}`);
  };

  return (
    <PageWrapper title="模拟面试" subtitle="简历调优、实时追问、逐轮反馈与五维复盘雷达。">
      <div className="max-w-6xl mx-auto space-y-6 pb-20">
        {/* Tab bar */}
        <div className="flex items-center gap-4 border-b border-border pb-3">
          <button
            onClick={() => setActiveTab('lobby')}
            className={`text-sm font-bold pb-2 border-b-2 ${
              activeTab === 'lobby' ? 'border-indigo-600' : 'border-transparent text-muted-foreground'
            }`}
          >
            面试大厅
          </button>
          <button
            onClick={() => setActiveTab('history')}
            className={`text-sm font-bold pb-2 border-b-2 ${
              activeTab === 'history' ? 'border-indigo-600' : 'border-transparent text-muted-foreground'
            }`}
          >
            会话与复盘
          </button>
        </div>

        {activeTab === 'lobby' ? (
          <InterviewLobby style={style} onStyleChange={setStyle} onSessionCreated={handleSessionCreated} />
        ) : historyLoading && (!sessions || sessions.length === 0) ? (
          <Card className="p-10 rounded-2xl border border-border/60 text-center text-sm font-bold text-muted-foreground">
            正在加载面试记录...
          </Card>
        ) : historyFailed ? (
          <Card className="p-6 rounded-2xl border border-border/60">
            <InlineError message={historyFailed} onRetry={refetch} />
          </Card>
        ) : !sessions || sessions.length === 0 ? (
          <Card className="p-10 rounded-2xl border border-border/60">
            <EmptyState icon={Bot} title="暂无面试记录" className="py-0" />
          </Card>
        ) : (
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
            <SessionList sessions={sessions} activeId={activeSessionId} onSelect={handleSessionSelect} />
            {!activeSessionId ? (
              <Card className="lg:col-span-2 p-4 rounded-2xl border border-border/60 min-h-[420px] flex items-center justify-center">
                <p className="text-sm font-bold text-muted-foreground">请选择一个会话查看详情。</p>
              </Card>
            ) : !activeSession ? (
              <Card className="lg:col-span-2 p-4 rounded-2xl border border-border/60 min-h-[420px] flex items-center justify-center">
                <p className="text-sm font-bold text-muted-foreground">会话不存在或无权限。</p>
              </Card>
            ) : (
              <SessionChat session={activeSession} onRefresh={refetch} />
            )}
          </div>
        )}
      </div>
    </PageWrapper>
  );
};
