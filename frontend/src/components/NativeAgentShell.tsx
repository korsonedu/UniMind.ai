import { t, useLocale } from '@/i18n';
import { WorkspaceToolbar } from '@/components/WorkspaceToolbar';
import { useContext, useEffect, useState, type CSSProperties, type ReactNode } from 'react';
import { SidebarSimple, Plus, NotePencil, X } from '@phosphor-icons/react';
import * as Dialog from '@radix-ui/react-dialog';
import { useDirectoryWidth } from '@/hooks/useDirectoryWidth';
import { DirectoryResizeHandle } from './DirectoryResizeHandle';
import { WorkspaceTrail } from './WorkspaceTrail';
import { createPortal } from 'react-dom';
import { useOutletContext } from 'react-router-dom';
import { SpaceSwitcher } from './SpaceSwitcher';
import { MobileMenuIcon, type MobileNavigationSlot } from './MobileNavPrimitives';
import { ProjectChatSidebarContext, RightSidebarLayoutContext, WorkspaceActiveContext } from './WorkspaceContext';

export interface AgentWorkspace { active: boolean; header: ReactNode; activity: ReactNode; chatContext?: ReactNode; }

interface Props { directoryInitiallyCollapsed?: boolean; workspace?: AgentWorkspace; native?: boolean; sidebar?: ReactNode; onNew: () => void; children: ReactNode; composer?: ReactNode; mobileHeaderTitle?: ReactNode; title?: string; label?: string; action?: ReactNode; }

/** Opt-in presentation; the existing Agent runtime and workbench keep their behavior. */
export function NativeAgentShell({ native, sidebar, onNew, children, composer, mobileHeaderTitle, title = t('新对话'), label = t('小宇'), action, workspace, directoryInitiallyCollapsed }: Props) {
  useLocale();
  const [open, setOpen] = useState(false);
  const { mobileNavigation } = useOutletContext<{ mobileNavigation?: MobileNavigationSlot }>() ?? {};
  const drawerTitle = mobileNavigation ? t('应用导航') : t('历史对话');
  const workspaceActive = useContext(WorkspaceActiveContext);
  const { fullscreen: rightSidebarFullscreen, exitFullscreen } = useContext(RightSidebarLayoutContext);
  const { host: chatHost, visible: chatVisible, open: openChat, close: closeChat, setAvailable } = useContext(ProjectChatSidebarContext);
  const activityOpen = !!workspace?.active;
  useEffect(() => {
    setAvailable(workspaceActive && activityOpen);
    if (workspaceActive && activityOpen) openChat();
    return () => setAvailable(false);
  }, [workspaceActive, activityOpen, setAvailable, openChat]);
  const conversation = <div className="um-agent-conversation" aria-label={t('小宇对话')} onKeyDown={event => { if (activityOpen && event.key === 'Escape' && !event.defaultPrevented) { event.preventDefault(); closeChat(); } }}><WorkspaceActiveContext.Provider value={workspaceActive && (!activityOpen || chatVisible)}>{workspace?.chatContext}{children}{composer}</WorkspaceActiveContext.Provider></div>;
  const directory = useDirectoryWidth(undefined, directoryInitiallyCollapsed);
  const directoryHidden = directory.collapsed || rightSidebarFullscreen;
  if (!native) return <div className="h-full flex um-motion-surface animate-in fade-in duration-[180ms] ease-out">{sidebar}{children}</div>;
  return <div className="um-native-agent um-agent-workspace" data-directory-hidden={directory.collapsed} data-directory-animated={directory.animated || undefined}>
    <div className="um-agent-directory" style={{ width: directory.width, '--um-directory-content-width': `${directory.contentWidth}px` } as CSSProperties}>
      <div aria-hidden={directory.collapsed || undefined} inert={directory.collapsed} className="um-agent-directory-content um-directory-content">{sidebar}</div>
      <DirectoryResizeHandle width={directory.width} onChange={directory.previewWidth} onCommit={directory.changeWidth} label={t('调整历史对话宽度')} />
    </div>
    <section className="um-agent-main" aria-label={t('小宇工作区')}>
      <WorkspaceToolbar className="um-agent-toolbar">
        <div>
          <button className="um-agent-icon-button um-agent-directory-toggle" onClick={() => {
            if (rightSidebarFullscreen) {
              exitFullscreen();
              if (directory.collapsed) directory.expand();
            } else directory.toggle();
          }} aria-label={directoryHidden ? t('展开历史对话') : t('收起历史对话')} title={directoryHidden ? t('展开历史对话') : t('收起历史对话')} aria-expanded={!directoryHidden}><SidebarSimple size={18} /></button>
          <Dialog.Root open={open} onOpenChange={value => { if (value) mobileNavigation?.onOpen(); setOpen(value); }}>
            <Dialog.Trigger asChild><button className={mobileNavigation ? 'um-agent-history-button um-mobile-menu-trigger' : 'um-agent-history-button'} aria-label={mobileNavigation ? drawerTitle : t('打开历史对话')}>{mobileNavigation ? <MobileMenuIcon size={20} /> : <SidebarSimple size={18} />}</button></Dialog.Trigger>
            <Dialog.Portal><Dialog.Overlay className="um-agent-drawer-overlay" data-mobile-menu={!!mobileNavigation} /><Dialog.Content className="um-native-agent um-agent-drawer" data-mobile-menu={!!mobileNavigation}>
              <Dialog.Title className="sr-only">{drawerTitle}</Dialog.Title>
              <Dialog.Description className="sr-only">{t('搜索、切换或删除历史对话。')}</Dialog.Description>
              {mobileNavigation ? <>
                <div className="um-m-drawer-head">
                  <SpaceSwitcher />
                  <Dialog.Close asChild><button type="button" className="um-m-drawer-close" aria-label={t('关闭侧栏')}><X size={18} /></button></Dialog.Close>
                </div>
                <div onClick={event => { if ((event.target as HTMLElement).closest('a')) setOpen(false); }}>
                  {mobileNavigation.links}
                </div>
              </> : <Dialog.Close asChild><button className="um-agent-drawer-close" aria-label={t('关闭历史对话')}><X size={18} /></button></Dialog.Close>}
              <div className={mobileNavigation ? 'um-agent-drawer-history um-m-drawer-body' : 'um-agent-drawer-history'} onClick={event => { if ((event.target as HTMLElement).closest('[data-session-select], [data-session-new], [data-session-open]')) setOpen(false); }}>{sidebar}</div>
              {mobileNavigation?.account && <div className="um-m-drawer-footer" onClick={event => { if ((event.target as HTMLElement).closest('a')) setOpen(false); }}>{mobileNavigation.account}</div>}
            </Dialog.Content></Dialog.Portal>
          </Dialog.Root>
          {mobileNavigation ? (mobileHeaderTitle ?? <span className="um-mobile-header-title um-agent-mobile-title">{label}</span>) : <WorkspaceTrail title={title} crumbs={[{ label }]} />}
        </div>
        <div className="um-agent-toolbar-actions">{action}<button className="um-agent-icon-button um-agent-toolbar-new" onClick={() => { if (rightSidebarFullscreen) exitFullscreen(); onNew(); }} aria-label={t('新对话')} title={t('新对话')}>{mobileNavigation ? <NotePencil size={19} /> : <Plus size={17} />}</button></div>
      </WorkspaceToolbar>
      {workspace?.header}
      <div className="um-agent-work-panels">
        <section className="um-agent-activity" aria-label={t('当前学习活动')} hidden={!activityOpen}><WorkspaceActiveContext.Provider value={workspaceActive && activityOpen}>{workspace?.activity}</WorkspaceActiveContext.Provider></section>
        {activityOpen && chatHost ? createPortal(conversation, chatHost) : conversation}
      </div>
    </section>
  </div>;
}
