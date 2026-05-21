import React, { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { InterviewRadarChart } from './RadarChart';
import { toast } from 'sonner';
import { formatApiErrorToast } from '@/lib/apiError';
import api from '@/lib/api';
import { Send, StopCircle } from 'lucide-react';

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
  const { t } = useTranslation('interviews');
  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);
  const [streamingText, setStreamingText] = useState('');
  const [finishing, setFinishing] = useState(false);
  const [localCandidateTurn, setLocalCandidateTurn] = useState<{ text: string } | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  const turns = session.turns || [];
  const isCompleted = session.status === 'completed';
  const isAnalyzing = session.status === 'analyzing';
  const hasRadar = isCompleted && session.radar_scores && Object.keys(session.radar_scores).length > 0;

  useEffect(() => {
    if (localCandidateTurn && turns.some((t) => t.speaker === 'candidate' && t.content_text === localCandidateTurn.text)) {
      setLocalCandidateTurn(null);
    }
  }, [turns, localCandidateTurn]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [turns.length, streamingText, localCandidateTurn]);

  const sendTurn = async () => {
    if (!input.trim() || sending) return;
    const text = input.trim();
    setInput('');
    setSending(true);
    setStreamingText('');
    setLocalCandidateTurn({ text });

    try {
      const res = await fetch(`/api/interviews/sessions/${session.id}/text-turn/stream/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ text }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const reader = res.body?.getReader();
      if (!reader) throw new Error('stream not available');

      const decoder = new TextDecoder();
      let leftover = '';
      let streamCompleted = false;

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
            if (payload.done) { streamCompleted = true; }
            else if (payload.token) { setStreamingText((prev) => prev + payload.token); }
          } catch { /* skip */ }
        }
      }

      if (streamCompleted) {
        setStreamingText('');
        onRefresh();
      }
    } catch (e: any) {
      toast.error(formatApiErrorToast(e, t('sessionChat.sendFailed')));
      setStreamingText('');
      setLocalCandidateTurn(null);
    } finally {
      setSending(false);
    }
  };

  const finishSession = async () => {
    setFinishing(true);
    try {
      await api.post(`/interviews/sessions/${session.id}/finish/`, {});
      toast.success(t('sessionChat.reviewGenerated'));
      onRefresh();
    } catch (e) {
      toast.error(formatApiErrorToast(e, t('sessionChat.generateReviewFailed')));
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
    <div className="flex flex-col h-full">
      {/* Meta bar */}
      <div className="flex items-center justify-between pb-2.5 border-b border-neutral-200">
        <div className="flex items-baseline gap-3">
          <span className="text-[13px] font-semibold tabular-nums text-neutral-900">
            Session {session.id}
          </span>
          <span className="text-[11px] text-neutral-400">
            {{ resume: t('sessionChat.typeResume'), english: t('sessionChat.typeEnglish'), professional: t('sessionChat.typeProfessional'), mixed: t('sessionChat.typeMixed') }[session.session_type] || session.session_type}
          </span>
          <span className="text-[11px] text-neutral-400">
            {{ friendly: t('sessionChat.styleFriendly'), pressure: t('sessionChat.stylePressure') }[session.interviewer_style] || session.interviewer_style}
          </span>
        </div>
        {isAnalyzing && <span className="text-[11px] text-amber-600 font-medium animate-pulse">{t('sessionChat.analyzing')}</span>}
        {!isCompleted && !isAnalyzing && (
          <button
            className="text-[11px] font-medium text-neutral-400 hover:text-neutral-800 transition-colors flex items-center gap-1"
            onClick={finishSession}
            disabled={finishing}
          >
            <StopCircle className="h-3 w-3" />
            {finishing ? t('sessionChat.generating') : t('sessionChat.endInterview')}
          </button>
        )}
        {isCompleted && <span className="text-[11px] font-medium text-emerald-600">{t('sessionChat.completed')}</span>}
      </div>

      {/* Review header — shown only when completed */}
      {isCompleted && (
        <div className="border-b border-neutral-100 py-4">
          {hasRadar ? (
            <div className="flex items-start gap-5">
              <div className="w-44 shrink-0">
                <InterviewRadarChart scores={session.radar_scores} />
              </div>
              <div className="min-w-0">
                <p className="text-[10px] font-semibold uppercase tracking-widest text-neutral-400 mb-1.5">{t('sessionChat.overallFeedback')}</p>
                <p className="text-[13px] text-neutral-700 leading-relaxed">
                  {session.overall_feedback || t('sessionChat.noFeedback')}
                </p>
              </div>
            </div>
          ) : (
            <div>
              <p className="text-[10px] font-semibold uppercase tracking-widest text-neutral-400 mb-1.5">{t('sessionChat.overallFeedback')}</p>
              <p className="text-[13px] text-neutral-700 leading-relaxed">
                {session.overall_feedback || t('sessionChat.noFeedback')}
              </p>
            </div>
          )}
        </div>
      )}

      {/* Conversation transcript */}
      <div className="flex-1 overflow-y-auto py-4 space-y-4 pr-1 min-h-0">
        {turns.length === 0 && !localCandidateTurn && (
          <p className="text-[13px] text-neutral-400 text-center py-16">{t('sessionChat.waitingForInterviewer')}</p>
        )}

        {turns.map((turn) => (
          <div key={turn.id}>
            <p className={`text-[10px] font-semibold uppercase tracking-widest mb-1 ${
              turn.speaker === 'interviewer' ? 'text-stone-400' : 'text-neutral-400'
            }`}>
              {turn.speaker === 'interviewer' ? t('sessionChat.speakerInterviewer') : t('sessionChat.speakerCandidate')}
            </p>
            <div className={
              turn.speaker === 'interviewer'
                ? 'border-l-2 border-amber-400 pl-3 ml-0.5'
                : 'pl-3 ml-0.5'
            }>
              <p className={`text-[14px] leading-relaxed whitespace-pre-wrap ${
                turn.speaker === 'interviewer' ? 'font-serif text-neutral-900' : 'text-neutral-700'
              }`}>
                {turn.content_text}
              </p>
            </div>
            {turn.feedback_for_turn && (
              <p className="mt-1 pl-3 text-[11px] text-amber-600 italic leading-relaxed">
                {turn.feedback_for_turn}
              </p>
            )}
          </div>
        ))}

        {localCandidateTurn && (
          <div className="opacity-50">
            <p className="text-[10px] font-semibold uppercase tracking-widest mb-1 text-neutral-400">{t('sessionChat.speakerCandidate')}</p>
            <div className="pl-3 ml-0.5">
              <p className="text-[14px] text-neutral-700 whitespace-pre-wrap leading-relaxed">
                {localCandidateTurn.text}
              </p>
            </div>
          </div>
        )}

        {streamingText && (
          <div>
            <p className="text-[10px] font-semibold uppercase tracking-widest mb-1 text-stone-400">{t('sessionChat.speakerInterviewer')}</p>
            <div className="border-l-2 border-amber-400 pl-3 ml-0.5">
              <p className="text-[14px] font-serif text-neutral-900 whitespace-pre-wrap leading-relaxed">
                {streamingText}
                <span className="inline-block w-[2px] h-[1em] bg-amber-400 ml-0.5 animate-pulse align-text-bottom" />
              </p>
            </div>
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      {/* Input */}
      {!isCompleted && !isAnalyzing && (
        <div className="border-t border-neutral-200 pt-3 flex gap-2 items-end">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={t('sessionChat.inputPlaceholder')}
            rows={2}
            disabled={sending}
            aria-label={t('sessionChat.inputPlaceholder')}
            className="flex-1 resize-none text-[14px] leading-relaxed bg-transparent border-0 outline-none placeholder:text-neutral-300 text-neutral-900 py-1"
          />
          <button
            aria-label="Send message"
            className="shrink-0 h-9 w-9 rounded-full bg-neutral-900 text-white flex items-center justify-center hover:bg-neutral-800 transition-colors disabled:opacity-30"
            disabled={sending || !input.trim()}
            onClick={sendTurn}
          >
            <Send className="h-3.5 w-3.5" />
          </button>
        </div>
      )}
    </div>
  );
};
