import { t, useLocale } from '@/i18n';
import { WorkspaceToolbar } from '@/components/WorkspaceToolbar';
import { useContext, useEffect, useState, type CSSProperties, type ReactNode } from 'react';
import { SidebarSimple, Plus, X } from '@phosphor-icons/react';
import * as Dialog from '@radix-ui/react-dialog';
import { useDirectoryWidth } from '@/hooks/useDirectoryWidth';
import { DirectoryResizeHandle } from './DirectoryResizeHandle';
import { WorkspaceTrail } from './WorkspaceTrail';
import { WorkspaceActiveContext } from './WorkspaceContext';

export interface AgentWorkspace { active: boolean; header: ReactNode; activity: ReactNode; chatContext?: ReactNode; }

interface Props { workspace?: AgentWorkspace; native?: boolean; sidebar?: ReactNode; onNew: () => void; children: ReactNode; title?: string; label?: string; action?: ReactNode; }

/** Opt-in presentation; the existing Agent runtime and workbench keep their behavior. */
export function NativeAgentShell({ native, sidebar, onNew, children, title = t('新对话'), label = t('小宇'), action, workspace }: Props) {
  useLocale();
  const [open, setOpen] = useState(false);
  const [mobileChat, setMobileChat] = useState(false);
  const workspaceActive = useContext(WorkspaceActiveContext);
  const [narrow, setNarrow] = useState(() => window.matchMedia('(max-width:1100px)').matches);
  useEffect(() => {
    const media = window.matchMedia('(max-width:1100px)');
    const update = () => setNarrow(media.matches);
    media.addEventListener('change', update);
    return () => media.removeEventListener('change', update);
  }, []);
  const directory = useDirectoryWidth();
  if (!native) return <div className="h-full flex um-motion-surface animate-in fade-in duration-[180ms] ease-out">{sidebar}{children}</div>;
  return <div className="um-native-agent um-agent-workspace" data-directory-hidden={directory.collapsed} data-directory-animated={directory.animated || undefined}>
    <div className="um-agent-directory" style={{ width: directory.width, '--um-directory-content-width': `${directory.contentWidth}px` } as CSSProperties}>
      <div aria-hidden={directory.collapsed || undefined} inert={directory.collapsed} className="um-agent-directory-content um-directory-content">{sidebar}</div>
      <DirectoryResizeHandle width={directory.width} onChange={directory.previewWidth} onCommit={directory.changeWidth} label={t('调整历史对话宽度')} />
    </div>
    <section className="um-agent-main" aria-label={t('小宇工作区')}>
      <WorkspaceToolbar className="um-agent-toolbar">
        <div>
          <button className="um-agent-icon-button um-agent-directory-toggle" onClick={directory.toggle} aria-label={!directory.collapsed ? t('收起历史对话') : t('展开历史对话')} title={!directory.collapsed ? t('收起历史对话') : t('展开历史对话')}><SidebarSimple size={18} /></button>
          <Dialog.Root open={open} onOpenChange={setOpen}>
            <Dialog.Trigger asChild><button className="um-agent-history-button" aria-label={t('打开历史对话')}><SidebarSimple size={18} /></button></Dialog.Trigger>
            <Dialog.Portal><Dialog.Overlay className="um-agent-drawer-overlay" /><Dialog.Content className="um-native-agent um-agent-drawer">
              <Dialog.Title className="sr-only">{t('历史对话')}</Dialog.Title>
              <Dialog.Description className="sr-only">{t('搜索、切换或删除历史对话。')}</Dialog.Description>
              <Dialog.Close asChild><button className="um-agent-drawer-close" aria-label={t('关闭历史对话')}><X size={18} /></button></Dialog.Close>
              <div onClick={event => { if ((event.target as HTMLElement).closest('[data-session-select], [data-session-new]')) setOpen(false); }}>{sidebar}</div>
            </Dialog.Content></Dialog.Portal>
          </Dialog.Root>
          <WorkspaceTrail title={title} crumbs={[{ label }]} />
        </div>
        <div className="um-agent-toolbar-actions">{action}<button className="um-agent-icon-button um-agent-toolbar-new" onClick={onNew} aria-label={t('新对话')} title={t('新对话')}><Plus size={17} /></button></div>
      </WorkspaceToolbar>
      {workspace?.header}
      <div className="um-agent-work-panels" data-activity={!!workspace?.active} data-mobile-chat={mobileChat}>
        <section className="um-agent-activity" aria-label={t('当前学习活动')} hidden={!workspace?.active}><WorkspaceActiveContext.Provider value={workspaceActive && !!workspace?.active && (!narrow || !mobileChat)}>{workspace?.activity}</WorkspaceActiveContext.Provider></section>
        <div className="um-agent-conversation" aria-label={t('小宇对话')}><WorkspaceActiveContext.Provider value={workspaceActive && (!workspace?.active || !narrow || mobileChat)}>{workspace?.chatContext}{children}</WorkspaceActiveContext.Provider></div>
      </div>
      {workspace?.active && <button className="um-work-mobile-chat um-agent-button" onClick={() => setMobileChat(value => !value)}>{mobileChat ? t('回到学习活动') : t('与小宇对话')}</button>}
    </section>
  </div>;
}
