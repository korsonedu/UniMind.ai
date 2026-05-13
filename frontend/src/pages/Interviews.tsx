import React, { useMemo, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { PageWrapper } from '@/components/PageWrapper';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Bot, FileText, Globe, GraduationCap, Mic, Sparkles } from 'lucide-react';
import { EmptyState } from '@/components/EmptyState';
import { InlineError } from '@/components/InlineError';
import { useFetch } from '@/lib/useFetch';
import { toast } from 'sonner';
import api from '@/lib/api';
import { formatApiErrorToast } from '@/lib/apiError';

type SessionItem = {
  id: number;
  session_type: 'resume' | 'english' | 'professional' | 'mixed';
  interviewer_style: 'friendly' | 'pressure';
  status: 'ongoing' | 'completed' | 'analyzing';
  radar_scores: Record<string, number>;
  overall_feedback: string;
  started_at: string;
  turns?: Array<{ id: number; speaker: 'candidate' | 'interviewer'; content_text: string; feedback_for_turn?: string; latency_ms?: number }>;
};

export const Interviews: React.FC = () => {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const activeSessionId = Number(searchParams.get('session_id') || 0);
  const [activeTab, setActiveTab] = useState<'lobby' | 'history'>('lobby');
  const [style, setStyle] = useState<'friendly' | 'pressure'>('friendly');
  const [startingType, setStartingType] = useState<string | null>(null);
  const { data: sessions, loading: historyLoading, error: historyFailed, refetch } = useFetch<SessionItem[]>(
    (signal) => api.get('/interviews/sessions/', { signal }).then(r => (r.data?.results || []) as SessionItem[])
  );
  const [chatLoading, setChatLoading] = useState(false);
  const [chatSending, setChatSending] = useState(false);
  const [chatInput, setChatInput] = useState('');
  const [finishing, setFinishing] = useState(false);
  const [resumeText, setResumeText] = useState('');
  const [resumeFile, setResumeFile] = useState<File | null>(null);
  const [resumeSaving, setResumeSaving] = useState(false);

  const activeSession = useMemo(() => (sessions || []).find((s) => s.id === activeSessionId) || null, [sessions, activeSessionId]);

  const loadSessionDetail = async (sessionId: number) => {
    if (!sessionId) return;
    setChatLoading(true);
    try {
      const res = await api.get(`/interviews/sessions/${sessionId}/`);
      const detail = res.data as SessionItem;
      refetch();
      setActiveTab('history');
    } catch (e) {
      toast.error(formatApiErrorToast(e, '加载会话详情失败'));
    } finally {
      setChatLoading(false);
    }
  };

  useEffect(() => {
    if (activeSessionId > 0) {
      loadSessionDetail(activeSessionId);
    }
  }, [activeSessionId]);

  const startInterview = async (type: string) => {
    setStartingType(type);
    try {
      const res = await api.post('/interviews/sessions/', {
        session_type: type,
        interviewer_style: style,
      });
      const sessionId = Number(res.data?.id || 0);
      if (!sessionId) throw new Error('missing_session_id');
      toast.success(`面试会话 #${sessionId} 已创建`);
      navigate(`/interviews?session_id=${sessionId}`);
      refetch();
    } catch (e) {
      toast.error(formatApiErrorToast(e, '创建面试会话失败'));
    } finally {
      setStartingType(null);
    }
  };

  const sendTextTurn = async () => {
    if (!activeSessionId || !chatInput.trim()) return;
    setChatSending(true);
    try {
      await api.post(`/interviews/sessions/${activeSessionId}/text-turn/`, { text: chatInput.trim() });
      setChatInput('');
      await loadSessionDetail(activeSessionId);
    } catch (e) {
      toast.error(formatApiErrorToast(e, '发送失败'));
    } finally {
      setChatSending(false);
    }
  };

  const finishSession = async () => {
    if (!activeSessionId) return;
    setFinishing(true);
    try {
      await api.post(`/interviews/sessions/${activeSessionId}/finish/`, {});
      toast.success('复盘已生成');
      await loadSessionDetail(activeSessionId);
      refetch();
    } catch (e) {
      toast.error(formatApiErrorToast(e, '生成复盘失败'));
    } finally {
      setFinishing(false);
    }
  };

  const submitResume = async () => {
    if (!resumeText.trim() && !resumeFile) {
      toast.error('请填写简历文本或上传文件');
      return;
    }
    setResumeSaving(true);
    try {
      const fd = new FormData();
      if (resumeText.trim()) fd.append('resume_text', resumeText.trim());
      if (resumeFile) fd.append('file', resumeFile);
      const res = await api.post('/interviews/resume/tune/', fd);
      toast.success(`简历调优已完成（记录 #${res.data?.record_id || '--'}）`);
    } catch (e) {
      toast.error(formatApiErrorToast(e, '简历调优失败'));
    } finally {
      setResumeSaving(false);
    }
  };

  const interviewTypes = [
    { id: 'resume', icon: FileText, title: '简历深挖', desc: '结合你的经历生成针对性追问。' },
    { id: 'english', icon: Globe, title: '英语口语', desc: '模拟英文问答并给出流畅度反馈。' },
    { id: 'professional', icon: GraduationCap, title: '专业课(431)', desc: '围绕 431 核心考点做高压追问。' },
  ];

  return (
    <PageWrapper title="综合复试模块" subtitle="简历调优、实时追问、逐轮反馈与五维复盘雷达。">
      <div className="max-w-6xl mx-auto space-y-6 pb-20">
        <div className="flex items-center gap-4 border-b border-border pb-3">
          <button onClick={() => setActiveTab('lobby')} className={`text-sm font-bold pb-2 border-b-2 ${activeTab === 'lobby' ? 'border-indigo-600' : 'border-transparent text-muted-foreground'}`}>面试大厅</button>
          <button onClick={() => setActiveTab('history')} className={`text-sm font-bold pb-2 border-b-2 ${activeTab === 'history' ? 'border-indigo-600' : 'border-transparent text-muted-foreground'}`}>会话与复盘</button>
        </div>

        {activeTab === 'lobby' ? (
          <div className="space-y-4">
            <Card className="p-6 rounded-3xl bg-gradient-to-r from-indigo-500/10 to-emerald-500/10 border-indigo-200/60">
              <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-indigo-500/15 text-indigo-700 text-xs font-bold">
                <Sparkles className="w-4 h-4" /> 多阶段复试训练
              </div>
              <h2 className="text-2xl font-black mt-3">从简历到专业面试的一体化闭环</h2>
              <p className="text-sm text-muted-foreground mt-2">支持风格选择、实时追问、逐句反馈和结束后雷达报告。</p>
            </Card>

            <Card className="p-5 rounded-2xl border border-border/60 space-y-3">
              <p className="text-xs font-black uppercase tracking-widest text-muted-foreground">导师风格</p>
              <div className="flex gap-2">
                <Button size="sm" variant={style === 'friendly' ? 'default' : 'outline'} className="h-8 text-xs" onClick={() => setStyle('friendly')}>和蔼引导</Button>
                <Button size="sm" variant={style === 'pressure' ? 'default' : 'outline'} className="h-8 text-xs" onClick={() => setStyle('pressure')}>高压追问</Button>
              </div>
            </Card>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              {interviewTypes.map((type) => (
                <Card key={type.id} className="p-5 rounded-2xl border border-border/60">
                  <type.icon className="w-7 h-7 text-indigo-600" />
                  <h4 className="text-lg font-bold mt-3">{type.title}</h4>
                  <p className="text-sm text-muted-foreground mt-2 min-h-10">{type.desc}</p>
                  <Button className="w-full mt-4 rounded-xl bg-slate-900 text-white text-xs font-bold" onClick={() => startInterview(type.id)} disabled={startingType === type.id}>
                    {startingType === type.id ? '创建中...' : '进入会话'}
                  </Button>
                </Card>
              ))}
            </div>

            <Card className="p-5 rounded-2xl border border-border/60 space-y-3">
              <p className="text-xs font-black uppercase tracking-widest text-muted-foreground">简历调优</p>
              <textarea
                value={resumeText}
                onChange={(e) => setResumeText(e.target.value)}
                className="w-full min-h-[120px] rounded-xl border border-border/60 p-3 text-sm"
                placeholder="粘贴简历文本，或上传 PDF/DOCX/TXT..."
              />
              <Input type="file" accept=".pdf,.doc,.docx,.txt" onChange={(e) => setResumeFile(e.target.files?.[0] || null)} />
              <Button className="rounded-xl text-xs font-bold bg-black text-white" onClick={submitResume} disabled={resumeSaving}>
                {resumeSaving ? '分析中...' : '提交简历调优'}
              </Button>
            </Card>
          </div>
        ) : (
          <div className="space-y-4">
            {historyLoading && (!sessions || sessions.length === 0) ? (
              <Card className="p-10 rounded-2xl border border-border/60 text-center text-sm font-bold text-muted-foreground">正在加载面试记录...</Card>
            ) : historyFailed ? (
              <Card className="p-6 rounded-2xl border border-border/60"><InlineError message={historyFailed} onRetry={refetch} /></Card>
            ) : !sessions || sessions.length === 0 ? (
              <Card className="p-10 rounded-2xl border border-border/60">
                <EmptyState icon={Bot} title="暂无面试记录" className="py-0" />
              </Card>
            ) : (
              <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
                <Card className="lg:col-span-1 p-3 rounded-2xl border border-border/60 space-y-2">
                  {(sessions || []).map((s) => (
                    <button key={s.id} onClick={() => navigate(`/interviews?session_id=${s.id}`)} className={`w-full text-left rounded-xl border px-3 py-2 ${s.id === activeSessionId ? 'border-indigo-400 bg-indigo-50/70' : 'border-border/60'}`}>
                      <p className="text-sm font-black">Session #{s.id}</p>
                      <p className="text-xs text-muted-foreground mt-1">{s.session_type} · {s.interviewer_style} · {s.status}</p>
                    </button>
                  ))}
                </Card>

                <Card className="lg:col-span-2 p-4 rounded-2xl border border-border/60 min-h-[420px]">
                  {!activeSessionId ? (
                    <p className="text-sm font-bold text-muted-foreground">请选择一个会话查看详情。</p>
                  ) : chatLoading ? (
                    <p className="text-sm font-bold text-muted-foreground">加载会话中...</p>
                  ) : !activeSession ? (
                    <p className="text-sm font-bold text-muted-foreground">会话不存在或无权限。</p>
                  ) : (
                    <div className="space-y-3">
                      <div className="flex items-center justify-between">
                        <p className="text-sm font-black">Session #{activeSession.id}</p>
                        <Button size="sm" variant="outline" className="h-8 text-xs" onClick={finishSession} disabled={finishing || activeSession.status !== 'ongoing'}>
                          {finishing ? '生成中...' : '结束并生成复盘'}
                        </Button>
                      </div>
                      <div className="max-h-[280px] overflow-y-auto space-y-2 pr-1">
                        {(activeSession.turns || []).length === 0 ? (
                          <p className="text-xs font-bold text-muted-foreground">还没有对话内容，先发送一句话开始模拟。</p>
                        ) : (
                          (activeSession.turns || []).map((turn) => (
                            <div key={turn.id} className={`rounded-xl px-3 py-2 border ${turn.speaker === 'candidate' ? 'bg-slate-50 border-slate-200' : 'bg-indigo-50 border-indigo-200'}`}>
                              <p className="text-[11px] font-black uppercase">{turn.speaker === 'candidate' ? '你' : '面试官'}</p>
                              <p className="text-sm mt-1">{turn.content_text}</p>
                              {turn.feedback_for_turn ? <p className="text-xs text-amber-700 mt-2">逐句反馈：{turn.feedback_for_turn}</p> : null}
                            </div>
                          ))
                        )}
                      </div>
                      {activeSession.status === 'completed' ? (
                        <Card className="p-3 rounded-xl border border-emerald-200 bg-emerald-50/70">
                          <p className="text-xs font-black uppercase tracking-widest text-emerald-700">复盘结果</p>
                          <p className="text-sm mt-1">{activeSession.overall_feedback || '暂无反馈'}</p>
                        </Card>
                      ) : (
                        <div className="flex gap-2">
                          <Input value={chatInput} onChange={(e) => setChatInput(e.target.value)} placeholder="输入你的回答..." />
                          <Button className="rounded-xl text-xs font-bold bg-black text-white" disabled={chatSending} onClick={sendTextTurn}>
                            {chatSending ? '发送中...' : '发送'}
                          </Button>
                        </div>
                      )}
                    </div>
                  )}
                </Card>
              </div>
            )}
          </div>
        )}
      </div>
    </PageWrapper>
  );
};
