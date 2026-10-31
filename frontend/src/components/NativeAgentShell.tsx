import { WorkspaceToolbar } from '@/components/WorkspaceToolbar';
import { useState, type CSSProperties, type ReactNode } from 'react';
import { SidebarSimple, Plus, X } from '@phosphor-icons/react';
import * as Dialog from '@radix-ui/react-dialog';
import { useDirectoryWidth } from '@/hooks/useDirectoryWidth';
import { DirectoryResizeHandle } from './DirectoryResizeHandle';
import { WorkspaceTrail } from './WorkspaceTrail';

interface Props { native?: boolean; sidebar?: ReactNode; onNew: () => void; children: ReactNode; title?: string; label?: string; }

/** Opt-in presentation; the existing Agent runtime and workbench keep their behavior. */
export function NativeAgentShell({ native, sidebar, onNew, children, title = '新对话', label = '小宇' }: Props) {
  const [open, setOpen] = useState(false);
  const directory = useDirectoryWidth();
  if (!native) return <div className="h-full flex animate-in fade-in duration-300">{sidebar}{children}</div>;
  return <div className="um-native-agent um-agent-workspace" data-directory-hidden={directory.collapsed} data-directory-animated={directory.animated || undefined}>
    <div className="um-agent-directory" style={{ width: directory.width, '--um-directory-content-width': `${directory.contentWidth}px` } as CSSProperties}>
      <div aria-hidden={directory.collapsed || undefined} inert={directory.collapsed} className="um-agent-directory-content um-directory-content">{sidebar}</div>
      <DirectoryResizeHandle width={directory.width} onChange={directory.previewWidth} onCommit={directory.changeWidth} label="调整历史对话宽度" />
    </div>
    <section className="um-agent-main" aria-label="小宇工作区">
      <WorkspaceToolbar className="um-agent-toolbar">
        <div>
          <button className="um-agent-icon-button um-agent-directory-toggle" onClick={directory.toggle} aria-label={!directory.collapsed ? '收起历史对话' : '展开历史对话'} title={!directory.collapsed ? '收起历史对话' : '展开历史对话'}><SidebarSimple size={18} /></button>
          <Dialog.Root open={open} onOpenChange={setOpen}>
            <Dialog.Trigger asChild><button className="um-agent-history-button" aria-label="打开历史对话"><SidebarSimple size={18} /></button></Dialog.Trigger>
            <Dialog.Portal><Dialog.Overlay className="um-agent-drawer-overlay" /><Dialog.Content className="um-native-agent um-agent-drawer">
              <Dialog.Title className="sr-only">历史对话</Dialog.Title>
              <Dialog.Description className="sr-only">搜索、切换或删除历史对话。</Dialog.Description>
              <Dialog.Close asChild><button className="um-agent-drawer-close" aria-label="关闭历史对话"><X size={18} /></button></Dialog.Close>
              <div onClick={event => { if ((event.target as HTMLElement).closest('[data-session-select], [data-session-new]')) setOpen(false); }}>{sidebar}</div>
            </Dialog.Content></Dialog.Portal>
          </Dialog.Root>
          <WorkspaceTrail title={title} crumbs={[{ label }]} />
        </div>
        <div className="um-agent-toolbar-actions"><button className="um-agent-icon-button um-agent-toolbar-new" onClick={onNew} aria-label="新对话" title="新对话"><Plus size={17} /></button></div>
      </WorkspaceToolbar>
      {children}
    </section>
  </div>;
}
