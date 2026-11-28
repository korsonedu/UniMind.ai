import { useState } from 'react';
import * as AlertDialog from '@radix-ui/react-alert-dialog';
import * as Dialog from '@radix-ui/react-dialog';
import { DotsThree, PencilSimple, Plus, Spinner, Trash, UploadSimple } from '@phosphor-icons/react';
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from '@/components/ui/dropdown-menu';
import { ContextMenu, ContextMenuTrigger, ContextMenuContent, ContextMenuItem } from '@/components/ui/context-menu';
import { t } from '@/i18n';
import { formatApiErrorToast } from '@/lib/apiError';
import { sourceIsProcessing, useWorkbenchSourceActions, type SourceChange, type useWorkbenchSources } from '@/lib/workbenchApi';
import type { ProjectSourceSummary, SourceAnchor } from '@/types/workbench';
import { AddSourceDialog } from './AddSourceDialog';
import { SourceInspectorDrawer } from './SourceInspectorDrawer';
import { sourceTypeLabel, sourceUnitLabel } from './workbenchSourcePresentation';

export function WorkbenchSourcesPane({ projectId, query, activeAnchor, onSelect, onBack, conversationId }: {
  projectId: number;
  query: ReturnType<typeof useWorkbenchSources>;
  activeAnchor: SourceAnchor | null;
  onSelect: (anchor: SourceAnchor) => void;
  onBack: () => void;
  conversationId: string;
}) {
  const sources = query.data?.sources ?? [];
  const selectedCount = sources.filter(source => source.is_selected).length;
  const allSelected = sources.length > 0 && selectedCount === sources.length;
  const [addOpen, setAddOpen] = useState(false);
  const [editing, setEditing] = useState<{ source: ProjectSourceSummary; title: string } | null>(null);
  const [deleting, setDeleting] = useState<ProjectSourceSummary | null>(null);
  const [error, setError] = useState('');
  const [uploading, setUploading] = useState<number | null>(null);
  const actions = useWorkbenchSourceActions(projectId);
  const pending = actions.isPending;

  async function change(action: SourceChange) {
    setError('');
    try {
      await actions.mutateAsync(action);
      return true;
    } catch (exception) {
      setError(formatApiErrorToast(exception, '资料操作失败，请重试。'));
      return false;
    }
  }

  const setAdd = (open: boolean) => { setError(''); setAddOpen(open); };
  async function add(action: SourceChange) {
    if (pending) return;
    if (await change(action)) setAdd(false);
  }
  async function upload(files: File[]) {
    if (pending) return;
    setAdd(true);
    setUploading(0);
    try {
      await add({ type: 'upload', files, onProgress: setUploading });
    } finally {
      setUploading(null);
    }
  }
  const openRename = (source: ProjectSourceSummary) => { setError(''); setEditing({ source, title: source.title }); };
  const openDelete = (source: ProjectSourceSummary) => { setError(''); setDeleting(source); };

  return <>
    {activeAnchor ? <SourceInspectorDrawer key={activeAnchor.sourceId}
      projectId={projectId} activeAnchor={activeAnchor} onBack={onBack} conversationId={conversationId}
      summary={sources.find(source => source.id === activeAnchor.sourceId)} />
    : <>
      <header className="um-wb-pane-header">
        <h2>{t('资料源')}</h2>
        <button className="um-agent-button um-wb-add" type="button" onClick={() => setAdd(true)} disabled={pending}>
          <Plus size={15} />{t('添加')}
        </button>
      </header>
      <div className="um-wb-source-body">
        <button type="button" className="um-wb-dropzone um-wb-dropzone-small" onClick={() => setAdd(true)} disabled={pending}
          onDragOver={event => { if (event.dataTransfer.types.includes('Files')) event.preventDefault(); }}
          onDrop={event => { event.preventDefault(); if (event.dataTransfer.files.length) void upload(Array.from(event.dataTransfer.files)); }}>
          <UploadSimple size={18} />
          <span>{t('拖放文件到这里上传')}</span>
        </button>
        {query.isPending && <p className="um-wb-muted" role="status">{t('正在加载资料…')}</p>}
        {query.isError && <button className="um-agent-button" onClick={() => void query.refetch()}>{t('资料列表加载失败，重试')}</button>}
        {!!sources.length && <label className="um-wb-select-all">
          <input type="checkbox" checked={allSelected} disabled={pending}
            ref={input => { if (input) input.indeterminate = selectedCount > 0 && !allSelected; }}
            onChange={() => void change({ type: 'selectAll', selected: !allSelected })} />
          <span>{t('全选')}</span><small>{t('已选 {0}/{1}', { 0: selectedCount, 1: sources.length })}</small>
        </label>}
        {error && !addOpen && !editing && !deleting && <p className="um-wb-error" role="alert">{error}</p>}
        <ul className="um-wb-sources">
          {sources.map(source => {
            const actionItems = (MenuItem: typeof DropdownMenuItem | typeof ContextMenuItem) => <>
              <MenuItem disabled={pending} onSelect={() => openRename(source)}><PencilSimple size={15} />{t('重命名')}</MenuItem>
              <MenuItem className="um-agent-menu-danger" disabled={pending} onSelect={() => openDelete(source)}><Trash size={15} />{t('删除资料')}</MenuItem>
            </>;
            return <ContextMenu key={source.id}>
              <ContextMenuTrigger asChild>
                <li className="um-wb-source" data-selected={source.is_selected}>
                  <input type="checkbox" checked={source.is_selected} disabled={pending}
                    aria-label={t('选择资料：{0}', { 0: source.title })}
                    onChange={event => void change({ type: 'patch', sourceId: source.id, patch: { is_selected: event.target.checked } })} />
                  <div className="um-wb-source-info">
                    <button type="button" className="um-wb-source-title" title={source.title} onClick={() => onSelect({ sourceId: source.id })}>{source.title}</button>
                    <div className="um-wb-source-meta">
                      <span className="um-wb-file-type" data-type={source.source_type}>{sourceTypeLabel(source)}</span>
                      {sourceIsProcessing(source) ? <span role="status"><Spinner size={13} className="um-wb-spin" />{t('解析中…')}</span>
                        : source.status === 'failed'
                          ? <button className="um-wb-retry" title={source.error_message} disabled={pending}
                            onClick={() => void change({ type: 'patch', sourceId: source.id, patch: { action: 'retry' } })}>{t('失败 · 重试')}</button>
                          : <span>{sourceUnitLabel(source)}</span>}
                    </div>
                  </div>
                  <DropdownMenu>
                    <DropdownMenuTrigger asChild><button className="um-agent-icon-button" aria-label={t('资料菜单：{0}', { 0: source.title })}><DotsThree size={18} /></button></DropdownMenuTrigger>
                    <DropdownMenuContent align="end" className="um-native-menu">{actionItems(DropdownMenuItem)}</DropdownMenuContent>
                  </DropdownMenu>
                </li>
              </ContextMenuTrigger>
              <ContextMenuContent className="um-native-menu">{actionItems(ContextMenuItem)}</ContextMenuContent>
            </ContextMenu>;
          })}
        </ul>
      </div>
    </>}
    <AddSourceDialog projectId={projectId} open={addOpen} setOpen={setAdd} uploading={uploading} pending={pending} error={error}
      courseIds={new Set(sources.map(source => source.course_id))}
      onUpload={files => void upload(files)} onUrl={url => void add({ type: 'import', input: { kind: 'web_url', url } })}
      onCourse={course_id => void add({ type: 'import', input: { kind: 'course', course_id } })} />
    <Dialog.Root open={!!editing} onOpenChange={open => { if (!open && !pending) setEditing(null); }}>
      <Dialog.Portal>
        <Dialog.Overlay className="um-agent-project-overlay" />
        <Dialog.Content className="um-native-agent um-agent-project-dialog">
          <Dialog.Title>{t('重命名资料')}</Dialog.Title>
          <Dialog.Description className="sr-only">{t('修改这份资料在项目中的显示名称。')}</Dialog.Description>
          {editing && <form onSubmit={async event => {
            event.preventDefault();
            if (await change({ type: 'patch', sourceId: editing.source.id, patch: { title: editing.title.trim() } })) setEditing(null);
          }}>
            <label>{t('资料名称')}<input autoFocus required maxLength={240} value={editing.title} disabled={pending}
              onChange={event => setEditing({ ...editing, title: event.target.value })} /></label>
            {error && <p className="um-wb-error" role="alert">{error}</p>}
            <footer>
              <Dialog.Close asChild><button type="button" className="um-agent-button" disabled={pending}>{t('取消')}</button></Dialog.Close>
              <button className="um-agent-button um-agent-button-primary" disabled={pending || !editing.title.trim()}>{t('保存')}</button>
            </footer>
          </form>}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
    <AlertDialog.Root open={!!deleting} onOpenChange={open => { if (!open && !pending) setDeleting(null); }}>
      <AlertDialog.Portal>
        <AlertDialog.Overlay className="um-agent-project-overlay" />
        <AlertDialog.Content className="um-native-agent um-agent-project-dialog">
          <AlertDialog.Title>{t('删除资料')}</AlertDialog.Title>
          <AlertDialog.Description>{t('确定从项目中删除「{0}」？', { 0: deleting?.title ?? '' })}</AlertDialog.Description>
          {error && <p className="um-wb-error" role="alert">{error}</p>}
          <footer>
            <AlertDialog.Cancel className="um-agent-button" disabled={pending}>{t('取消')}</AlertDialog.Cancel>
            <button type="button" className="um-agent-button um-agent-button-danger" disabled={pending} onClick={async () => {
              if (deleting && await change({ type: 'delete', sourceId: deleting.id })) setDeleting(null);
            }}>{t('删除')}</button>
          </footer>
        </AlertDialog.Content>
      </AlertDialog.Portal>
    </AlertDialog.Root>
  </>;
}
