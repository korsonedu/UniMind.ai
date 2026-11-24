import { useRef, useState } from 'react';
import { Check, Exam, NotePencil, Sparkle, Spinner } from '@phosphor-icons/react';
import type { ApiClient } from '../lib/api';
import { parseSeekSeconds } from '../shared/bridge';
import type { ActiveVideoDescriptor } from '../shared/types';

export const QUIZ_PROMPT = '请基于当前视频刚讲到的核心内容出 2 道随堂检验题考考我';
export const SUMMARY_PROMPT = '请帮我用精炼要点梳理当前这段视频的核心逻辑与易错点，并附上时间戳';

export interface QuickActionsBarProps {
  api: ApiClient;
  onAsk: (prompt: string) => void | Promise<void>;
  latestAnswer?: string;
  video?: ActiveVideoDescriptor | null;
  videoSeconds?: number;
  disabled?: boolean;
}

function formatTime(seconds: number): string {
  const value = Math.floor(seconds);
  const hours = Math.floor(value / 3600);
  const minutes = Math.floor((value % 3600) / 60).toString().padStart(2, '0');
  const remainder = (value % 60).toString().padStart(2, '0');
  return hours ? `${hours}:${minutes}:${remainder}` : `${minutes}:${remainder}`;
}

function videoTimeUrl(video: ActiveVideoDescriptor, seconds: number): string {
  const url = new URL(video.url);
  url.searchParams.set('t', `${Math.floor(seconds)}`);
  return url.href;
}

export function QuickActionsBar({ api, onAsk, latestAnswer, video, videoSeconds, disabled }: QuickActionsBarProps) {
  const [saving, setSaving] = useState(false);
  const [notice, setNotice] = useState('');
  const [failed, setFailed] = useState(false);
  const inFlight = useRef(false);

  const saveNote = async () => {
    if (inFlight.current || !latestAnswer?.trim()) return;
    inFlight.current = true;
    setSaving(true);
    setNotice('');
    setFailed(false);
    try {
      const timestamps = new Set<number>();
      if (typeof videoSeconds === 'number' && Number.isFinite(videoSeconds) && videoSeconds >= 0) timestamps.add(videoSeconds);
      for (const match of latestAnswer.matchAll(/#seek:\d+(?:\.\d+)?|\[(?:\d+:)?\d+:\d{2}\]/g)) {
        const seconds = parseSeekSeconds(match[0]);
        if (seconds !== null) timestamps.add(seconds);
      }
      const source = video ? `\n\n---\n视频来源：${video.title}${video.part > 1 ? `（P${video.part}）` : ''}\n\n原链接：${video.url}`
        + (timestamps.size ? `\n\n时间戳来源：${Array.from(timestamps).map(seconds => `[${formatTime(seconds)}](${videoTimeUrl(video, seconds)})`).join(' · ')}` : '') : '';
      const heading = latestAnswer.split('\n').map(line => line.replace(/^\s{0,3}#{1,6}\s+/, '').trim()).find(Boolean) || '小宇伴学笔记';
      await api.request<{ id: number }>('/api/notes/', {
        method: 'POST', body: { title: (video ? `${video.title} · 伴学笔记` : heading).slice(0, 300), content: latestAnswer + source },
      });
      setNotice('已存为个人笔记');
    } catch (error) {
      setFailed(true);
      setNotice(error instanceof Error ? error.message : '保存失败，请重试。');
    } finally {
      inFlight.current = false;
      setSaving(false);
    }
  };

  const ask = (prompt: string) => {
    setNotice('');
    void Promise.resolve().then(() => onAsk(prompt)).catch(error => {
      setFailed(true);
      setNotice(error instanceof Error ? error.message : '暂时无法发送，请重试。');
    });
  };

  return <div className="um-quick-actions">
    <div className="quick-actions-list" aria-label="快捷学习动作">
      <button type="button" disabled={disabled} onClick={() => ask(QUIZ_PROMPT)}><Exam size={14} />考我 2 题</button>
      <button type="button" disabled={disabled} onClick={() => ask(SUMMARY_PROMPT)}><Sparkle size={14} />梳理本段</button>
      <button type="button" disabled={disabled || saving || !latestAnswer?.trim()} onClick={() => void saveNote()}>{saving ? <Spinner size={14} className="spin" /> : <NotePencil size={14} />}存为笔记</button>
    </div>
    {notice && <p className={`quick-actions-notice ${failed ? 'inline-error' : 'inline-success'}`} role={failed ? 'alert' : 'status'}>{!failed && <Check size={14} />}{notice}</p>}
  </div>;
}
