import React, { useEffect, useRef, useState } from 'react';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { InterviewRadarChart } from './RadarChart';
import { toast } from 'sonner';
import { formatApiErrorToast } from '@/lib/apiError';
import api from '@/lib/api';

interface Turn {
  id: number;
  speaker: 'candidate' | 'interviewer';
  content_text: string;
  feedback_for_turn?: string;
}

interface SessionItem {
  id: number;
  session_type: string;
  interviewer_style: string;
  status: 'ongoing' | 'completed' | 'analyzing';
  radar_scores: Record<string, number>;
  overall_feedback: string;
  turns?: Turn[];
}

interface Props {
  session: SessionItem;
  onRefresh: () => void;
}

export const SessionChat: React.FC<Props> = ({ session, onRefresh }) => {
  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);
  const [streamingText, setStreamingText] = useState('');
  const [finishing, setFinishing] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  const turns = session.turns || [];
  const isCompleted = session.status === 'completed';
  const isAnalyzing = session.status === 'analyzing';

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [turns.length, streamingText]);

  const sendTurn = async () => {
    if (!input.trim() || sending) return;
    const text = input.trim();
    setInput('');
    setSending(true);
    setStreamingText('');

    try {
      const res = await fetch(`/api/interviews/sessions/${session.id}/text-turn/stream/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ text }),
      });

      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error((errData as any)?.error || `HTTP ${res.status}`);
      }

      const reader = res.body?.getReader();
      if (!reader) throw new Error('stream not available');

      const decoder = new TextDecoder();
      let leftover = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        leftover += decoder.decode(value, { stream: true });

        const lines = leftover.split('\n');
        leftover = lines.pop() || '';

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;
          try {
            const payload = JSON.parse(line.slice(6));
            if (payload.done) {
              onRefresh();
              setStreamingText('');
            } else if (payload.token) {
              setStreamingText((prev) => prev + payload.token);
            }
          } catch { /* skip malformed line */ }
        }
      }
    } catch (e: any) {
      toast.error(formatApiErrorToast(e, '发送失败'));
      setStreamingText('');
    } finally {
      setSending(false);
    }
  };

  const finishSession = async () => {
    setFinishing(true);
    try {
      await api.post(`/interviews/sessions/${session.id}/finish/`, {});
      toast.success('复盘已生成');
      onRefresh();
    } catch (e) {
      toast.error(formatApiErrorToast(e, '生成复盘失败'));
    } finally {
      setFinishing(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendTurn();
    }
  };

  return (
    <Card className="lg:col-span-2 p-4 rounded-2xl border border-border/60 flex flex-col min-h-[420px]">
      {/* Header */}
      <div className="flex items-center justify-between mb-3">
        <p className="text-sm font-black">Session #{session.id}</p>
        {!isCompleted && !isAnalyzing && (
          <Button size="sm" variant="outline" className="h-8 text-xs" onClick={finishSession} disabled={finishing}>
            {finishing ? '生成中...' : '结束并生成复盘'}
          </Button>
        )}
        {isAnalyzing && (
          <p className="text-xs font-bold text-amber-600">复盘分析中...</p>
        )}
      </div>

      {/* Radar chart for completed session */}
      {isCompleted && session.radar_scores && Object.keys(session.radar_scores).length > 0 && (
        <Card className="p-3 rounded-xl border border-emerald-200 bg-emerald-50/70 mb-3 space-y-2">
          <p className="text-xs font-black uppercase tracking-widest text-emerald-700">五维雷达图</p>
          <InterviewRadarChart scores={session.radar_scores} />
          {session.overall_feedback && (
            <p className="text-sm text-emerald-800">{session.overall_feedback}</p>
          )}
        </Card>
      )}

      {/* Conversation */}
      <div className="flex-1 max-h-[320px] overflow-y-auto space-y-2 pr-1 mb-3">
        {turns.length === 0 && !sending && (
          <p className="text-xs font-bold text-muted-foreground">还没有对话内容，先发送一句话开始模拟。</p>
        )}

        {turns.map((turn) => (
          <div
            key={turn.id}
            className={`rounded-xl px-3 py-2 border ${
              turn.speaker === 'candidate'
                ? 'bg-slate-50 border-slate-200'
                : 'bg-indigo-50 border-indigo-200'
            }`}
          >
            <p className="text-[11px] font-black uppercase">
              {turn.speaker === 'candidate' ? '你' : '面试官'}
            </p>
            <p className="text-sm mt-1 whitespace-pre-wrap">{turn.content_text}</p>
            {turn.feedback_for_turn && (
              <p className="text-xs text-amber-700 mt-2">逐句反馈：{turn.feedback_for_turn}</p>
            )}
          </div>
        ))}

        {/* Streaming bubble */}
        {streamingText && (
          <div className="rounded-xl px-3 py-2 border bg-indigo-50 border-indigo-200">
            <p className="text-[11px] font-black uppercase">面试官</p>
            <p className="text-sm mt-1 whitespace-pre-wrap">
              {streamingText}
              <span className="inline-block w-1.5 h-4 bg-indigo-400 ml-0.5 animate-pulse align-middle" />
            </p>
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      {/* Input area */}
      {!isCompleted && !isAnalyzing && (
        <div className="flex gap-2">
          <Input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="输入你的回答..."
            disabled={sending}
          />
          <Button
            className="rounded-xl text-xs font-bold bg-black text-white"
            disabled={sending || !input.trim()}
            onClick={sendTurn}
          >
            {sending ? '发送中...' : '发送'}
          </Button>
        </div>
      )}

      {/* Completed — just show feedback if no radar scores */}
      {isCompleted && (!session.radar_scores || Object.keys(session.radar_scores).length === 0) && (
        <Card className="p-3 rounded-xl border border-emerald-200 bg-emerald-50/70">
          <p className="text-xs font-black uppercase tracking-widest text-emerald-700">复盘结果</p>
          <p className="text-sm mt-1">{session.overall_feedback || '暂无反馈'}</p>
        </Card>
      )}
    </Card>
  );
};
