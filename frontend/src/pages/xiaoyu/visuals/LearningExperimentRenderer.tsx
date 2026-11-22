import { t, useLocale } from '@/i18n';
import { useEffect, useRef, useState } from 'react';
import { ArrowUpRight, SlidersHorizontal } from '@phosphor-icons/react';
import api from '@/lib/api';
import { useAuthStore } from '@/store/useAuthStore';
import { useAgentReply } from './agentReplyContext';
import './LearningExperimentRenderer.css';

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
  useLocale();
  const { onReply } = useAgentReply();
  const frame = useRef<HTMLIFrameElement>(null);
  const [experiment, setExperiment] = useState<Experiment | null>(null);
  const [height, setHeight] = useState(360);
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
        if (active.current) setError(t('操作状态尚未保存，请重试。若实验已更新，请重新打开对话。'));
      } finally {
        inFlight.current = null;
        if (active.current) setSaving(false);
      }
    };
    inFlight.current = operation();
    return inFlight.current;
  };
  const persistRef = useRef(persist);
  useEffect(() => { persistRef.current = persist; });

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
    }).catch(() => { if (active.current) setError(t('实验暂时无法打开，请稍后重新打开对话。')); });
    const receive = (event: MessageEvent) => {
      if (!frame.current || event.source !== frame.current.contentWindow) return;
      const message = event.data;
      if (!message || message.channel !== 'unimind-experiment') return;
      if (message.type === 'height' && Number.isFinite(message.height)) {
        setHeight(Math.max(180, Math.min(560, message.height)));
      }
      if (message.type === 'error') setRuntimeError(String(message.message || t('实验运行出错')).slice(0, 500));
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
    const observation = runtimeError ? t('实验出现运行错误：{0}，请修正同一个实验。', { 0: runtimeError })
      : summary || t('当前参数：{0}', { 0: JSON.stringify(state.current).slice(0, 1200) });
    onReply(t('我操作了“{0}”（实验 ID：{1}，版本 {2}）。{3} 请读取实验当前状态后继续讲解。', { 0: experiment?.title || payload.title, 1: payload.experiment_id, 2: revision.current, 3: observation }));
    setSending(false);
  };

  return <div className="um-experiment">
    <header className="um-experiment-header">
      <SlidersHorizontal size={17} weight="duotone" className="um-experiment-icon" aria-hidden="true" />
      <h3 title={experiment?.title || payload.title}>{experiment?.title || payload.title}</h3>
      <span className="um-experiment-kind">{t('交互讲解')}</span>
    </header>
    {experiment && <iframe ref={frame} title={experiment.title} sandbox="allow-scripts" referrerPolicy="no-referrer"
      srcDoc={experiment.document} className="um-experiment-frame" style={{ height }} />}
    {!experiment && !error && <p className="um-experiment-status">{t('正在打开讲解…')}</p>}
    {runtimeError && <p role="alert" className="um-experiment-error">{t('讲解运行出错：')}{runtimeError}</p>}
    {error && <div role="alert" className="um-experiment-error">
      <span>{error}</span>{experiment && <button type="button" className="underline" onClick={() => void persistRef.current()}>{t('重试保存')}</button>}
    </div>}
    {experiment && <footer className="um-experiment-footer">
      <span className="um-experiment-save" role="status"><span aria-hidden="true" className={saving ? 'is-saving' : ''} />{saving ? t('保存中…') : t('参数自动保存')}</span>
      <button type="button" disabled={!onReply || sending || saving} onClick={() => void discuss()}
        className="um-experiment-discuss">
        {runtimeError ? t('请小宇修正') : t('继续讲解')}<ArrowUpRight size={14} aria-hidden="true" />
      </button>
    </footer>}
  </div>;
}
