import { useEffect, useRef, useState } from 'react';
import api from '@/lib/api';
import { useAuthStore } from '@/store/useAuthStore';
import { useAgentReply } from './agentReplyContext';

interface ExperimentPayload {
  title: string;
  conversation_id: string;
  experiment_id: string;
}
interface Experiment {
  title: string;
  revision: number;
  state_version: number;
  state: Record<string, unknown>;
  document: string;
}

export function LearningExperimentRenderer({ payload }: { payload: ExperimentPayload }) {
  const userId = useAuthStore(state => state.user?.id);
  return <ExperimentFrame key={`${userId}:${payload.conversation_id}:${payload.experiment_id}`} payload={payload} />;
}

function ExperimentFrame({ payload }: { payload: ExperimentPayload }) {
  const { onReply } = useAgentReply();
  const frame = useRef<HTMLIFrameElement>(null);
  const [experiment, setExperiment] = useState<Experiment | null>(null);
  const [height, setHeight] = useState(480);
  const [error, setError] = useState('');
  const [runtimeError, setRuntimeError] = useState('');
  const [summary, setSummary] = useState('');
  const [saving, setSaving] = useState(false);
  const [sending, setSending] = useState(false);
  const state = useRef<Record<string, unknown>>({});
  const version = useRef(0);
  const revision = useRef(0);
  const pending = useRef<Record<string, unknown> | null>(null);
  const active = useRef(false);
  const inFlight = useRef<Promise<void> | null>(null);
  const abort = useRef<AbortController | null>(null);
  const endpoint = `/ai/learning-experiments/${encodeURIComponent(payload.conversation_id)}/${encodeURIComponent(payload.experiment_id)}/`;

  const persist = (): Promise<void> => {
    if (inFlight.current) return inFlight.current;
    if (!pending.current || !active.current) return Promise.resolve();
    const operation = async () => {
      setSaving(true);
      try {
        while (pending.current && active.current) {
          const snapshot = pending.current;
          const { data } = await api.patch(endpoint, {
            revision: revision.current, state_version: version.current, state: snapshot,
          }, { signal: abort.current?.signal });
          if (!active.current) return;
          version.current = data.state_version;
          if (pending.current === snapshot) pending.current = null;
        }
        if (active.current) setError('');
      } catch {
        if (active.current) setError('操作状态尚未保存，请重试。若实验已更新，请重新打开对话。');
      } finally {
        inFlight.current = null;
        if (active.current) setSaving(false);
      }
    };
    inFlight.current = operation();
    return inFlight.current;
  };
  const persistRef = useRef(persist);
  persistRef.current = persist;

  useEffect(() => {
    const controller = new AbortController();
    abort.current = controller;
    active.current = true;
    void api.get<Experiment>(endpoint, { signal: controller.signal }).then(({ data }) => {
      if (!active.current) return;
      state.current = data.state;
      version.current = data.state_version;
      revision.current = data.revision;
      setExperiment(data);
    }).catch(() => { if (active.current) setError('实验暂时无法打开，请稍后重新打开对话。'); });
    const receive = (event: MessageEvent) => {
      if (!frame.current || event.source !== frame.current.contentWindow) return;
      const message = event.data;
      if (!message || message.channel !== 'unimind-experiment') return;
      if (message.type === 'height' && Number.isFinite(message.height)) {
        setHeight(Math.max(240, Math.min(800, message.height + 16)));
      }
      if (message.type === 'error') setRuntimeError(String(message.message || '实验运行出错').slice(0, 500));
      if (message.type === 'state' || message.type === 'report') {
        try {
          const value = message.state;
          if (!value || typeof value !== 'object' || Array.isArray(value) || new TextEncoder().encode(JSON.stringify(value)).length > 4096) return;
          state.current = value;
          pending.current = value;
          void persistRef.current();
          if (message.type === 'report') setSummary(String(message.summary || '').slice(0, 1200));
        } catch { /* Only serializable state can cross the experiment boundary. */ }
      }
    };
    window.addEventListener('message', receive);
    return () => {
      active.current = false;
      controller.abort();
      window.removeEventListener('message', receive);
    };
  }, [endpoint]);

  const discuss = async () => {
    if (!onReply || sending) return;
    setSending(true);
    await persistRef.current();
    if (!active.current) return;
    if (pending.current) { setSending(false); return; }
    const observation = runtimeError ? `实验出现运行错误：${runtimeError}，请修正同一个实验。`
      : summary || `当前参数：${JSON.stringify(state.current).slice(0, 1200)}`;
    onReply(`我操作了“${experiment?.title || payload.title}”（实验 ID：${payload.experiment_id}，版本 ${revision.current}）。${observation} 请读取实验当前状态后继续。`);
    setSending(false);
  };

  return <div className="space-y-3">
    <header className="flex flex-wrap items-center justify-between gap-2">
      <h3 className="text-sm font-medium">{experiment?.title || payload.title}</h3>
      <span className="text-xs text-muted-foreground">交互实验{experiment ? ` · v${experiment.revision}` : ''}</span>
    </header>
    {experiment && <iframe ref={frame} title={experiment.title} sandbox="allow-scripts" referrerPolicy="no-referrer"
      srcDoc={experiment.document} className="w-full rounded-md border border-border bg-white" style={{ height }} />}
    {!experiment && !error && <p className="text-sm text-muted-foreground">正在打开实验…</p>}
    {runtimeError && <p role="alert" className="text-sm text-destructive">实验运行出错：{runtimeError}</p>}
    {summary && <p className="text-sm">{summary}</p>}
    {error && <div role="alert" className="flex flex-wrap items-center gap-2 text-sm text-destructive">
      <span>{error}</span>{experiment && <button type="button" className="underline" onClick={() => void persistRef.current()}>重试保存</button>}
    </div>}
    {experiment && <footer className="flex flex-wrap items-center justify-between gap-2">
      <span className="text-xs text-muted-foreground">{saving ? '正在保存操作…' : '实验结果仅用于本次对话讨论'}</span>
      <button type="button" disabled={!onReply || sending || saving} onClick={() => void discuss()}
        className="rounded-md border border-border px-3 py-2 text-sm hover:bg-accent disabled:opacity-50">
        {runtimeError ? '请小宇修正实验' : '把当前结果发给小宇'}
      </button>
    </footer>}
  </div>;
}
