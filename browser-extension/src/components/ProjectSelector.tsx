import { useEffect, useRef, useState } from 'react';
import { FolderSimple, Plus, X } from '@phosphor-icons/react';
import type { ApiClient } from '../lib/api';
import type { WorkbenchCaptureResult } from '../shared/types';
import { WorkbenchClipper } from './WorkbenchClipper';

export interface ProjectItem { id: number; name: string }

export function ProjectSelector({ api, value, onChange, disabled = false, clipPage }: {
  api: ApiClient;
  value: number | null;
  onChange: (projectId: number | null) => Promise<void> | void;
  disabled?: boolean;
  clipPage: { video: boolean; capture: () => Promise<WorkbenchCaptureResult> };
}) {
  const [projects, setProjects] = useState<ProjectItem[]>([]);
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [revision, setRevision] = useState(0);
  const picker = useRef<HTMLSelectElement>(null);
  useEffect(() => {
    const controller = new AbortController();
    setProjects([]);
    setError('');
    async function load() {
      const items: ProjectItem[] = [];
      const visited = new Set<string>();
      let path: string | null = '/api/ai/projects/';
      while (path && !visited.has(path)) {
        visited.add(path);
        const data: ProjectItem[] | { results: ProjectItem[]; next?: string | null } = await api.request(path, { signal: controller.signal });
        if (Array.isArray(data)) { items.push(...data); break; }
        items.push(...data.results);
        path = data.next ?? null;
      }
      if (!controller.signal.aborted) setProjects(items);
    }
    void load()
      .catch(failure => { if (!controller.signal.aborted) setError(failure instanceof Error ? failure.message : '项目暂时无法加载。'); });
    return () => controller.abort();
  }, [api, revision]);

  async function select(projectId: number | null) {
    setBusy(true);
    setError('');
    try { await onChange(projectId); }
    catch (failure) { setError(failure instanceof Error ? failure.message : '项目切换失败，请重试。'); }
    finally { setBusy(false); }
  }
  async function create() {
    if (!name.trim() || busy) return;
    setBusy(true);
    setError('');
    try {
      const project = await api.request<ProjectItem>('/api/ai/projects/', { method: 'POST', body: { name: name.trim() } });
      setProjects(previous => [...previous, project]);
      await onChange(project.id);
      setName('');
      setCreating(false);
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : '项目创建失败，请重试。');
    } finally { setBusy(false); }
  }
  return <div className="project-selector">
    <div className="project-select-row">
      <FolderSimple size={16} aria-hidden="true" />
      <select ref={picker} aria-label="当前对话所属项目" value={value ?? ''} disabled={disabled || busy}
        onChange={event => void select(event.target.value ? Number(event.target.value) : null)}>
        <option value="">未归属项目</option>
        {value !== null && !projects.some(project => project.id === value) && <option value={value}>当前项目 #{value}</option>}
        {projects.map(project => <option value={project.id} key={project.id}>{project.name}</option>)}
      </select>
      <button type="button" className="project-create-toggle" title={creating ? '取消新建项目' : '新建项目'}
        disabled={disabled || busy} onClick={() => setCreating(previous => !previous)}>
        {creating ? <><X size={14} />取消</> : <><Plus size={14} />新建项目</>}
      </button>
    </div>
    {creating && <form className="project-create" onSubmit={event => { event.preventDefault(); void create(); }}>
      <input autoFocus aria-label="新项目名称" placeholder="项目名称" maxLength={60} value={name} onChange={event => setName(event.target.value)} disabled={busy} />
      <button type="submit" className="small-button" disabled={busy || !name.trim()}>{busy ? '保存中' : '创建'}</button>
    </form>}
    {error && <p className="inline-error" role="alert">{error} <button type="button" className="text-button" onClick={() => setRevision(count => count + 1)}>重新加载</button></p>}
    <WorkbenchClipper api={api} projectId={value} projectName={projects.find(project => project.id === value)?.name}
      disabled={disabled || busy} video={clipPage.video} capture={clipPage.capture} onChooseProject={() => {
        if (projects.length) picker.current?.focus();
        else setCreating(true);
      }} />
  </div>;
}
