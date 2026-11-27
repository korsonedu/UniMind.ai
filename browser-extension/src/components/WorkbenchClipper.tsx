import { useEffect, useRef, useState } from 'react';
import { Archive, ArrowSquareOut, Spinner } from '@phosphor-icons/react';
import { throwApiError, type ApiClient } from '../lib/api';
import type { WorkbenchCaptureResult } from '../shared/types';

interface ImportResult {
  status: 'pending' | 'processing' | 'ready' | 'failed';
  error_message: string;
  unit_count: number;
}

export function WorkbenchClipper({ api, projectId, projectName, video, disabled, capture, onChooseProject }: {
  api: ApiClient;
  projectId: number | null;
  projectName?: string;
  video: boolean;
  disabled: boolean;
  capture: () => Promise<WorkbenchCaptureResult>;
  onChooseProject: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<{ text: string; href?: string; error?: boolean } | null>(null);
  const inFlight = useRef<AbortController | null>(null);
  useEffect(() => () => {
    inFlight.current?.abort();
    inFlight.current = null;
  }, []);

  async function clip() {
    if (inFlight.current) return;
    if (projectId === null) {
      setNotice({ text: '请先选择项目，或新建项目。' });
      onChooseProject();
      return;
    }
    const controller = new AbortController();
    inFlight.current = controller;
    setBusy(true);
    setNotice(null);
    try {
      const result = await capture();
      if (controller.signal.aborted) return;
      if ('error' in result) throw new Error(result.error);
      const response = await api.fetch(`/ai/projects/${projectId}/sources/import/`, {
        method: 'POST',
        headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
        body: JSON.stringify(result.source),
        signal: controller.signal,
      });
      if (!response.ok) await throwApiError(response);
      const imported: ImportResult = await response.json();
      if (imported.status === 'failed') throw new Error(imported.error_message || '资料解析失败，请重试。');
      if (controller.signal.aborted) return;
      const name = projectName ?? `项目 #${projectId}`;
      const title = response.status === 200 ? '已更新工作台中的资料' : `已收入「${name}」工作台`;
      const count = result.source.kind === 'external_video' ? result.source.segments.length : imported.unit_count;
      setNotice({
        text: imported.status === 'ready' ? `${title}（共 ${count} 段内容）` : `已提交到「${name}」工作台，正在解析。`,
        href: `${api.serverOrigin}/xiaoyu?project=${projectId}`,
      });
    } catch (error) {
      if (!controller.signal.aborted) setNotice({ text: error instanceof Error ? error.message : '收入工作台失败，请重试。', error: true });
    } finally {
      if (inFlight.current === controller) {
        inFlight.current = null;
        setBusy(false);
      }
    }
  }

  return <div className="workbench-clipper">
    <button type="button" className="workbench-clip-button" disabled={disabled || busy} onClick={() => void clip()}>
      {busy ? <Spinner size={16} className="spin" /> : <Archive size={16} weight="bold" />}
      {busy ? '正在收入工作台…' : `收入工作台 · ${video ? '视频讲稿' : '当前网页'}`}
    </button>
    {notice && <p className={notice.error ? 'inline-error' : 'workbench-clip-notice'} role={notice.error ? 'alert' : 'status'}>
      {notice.text}
      {notice.href && <a href={notice.href} target="_blank" rel="noreferrer">打开工作台 <ArrowSquareOut size={14} aria-hidden="true" /></a>}
    </p>}
  </div>;
}
