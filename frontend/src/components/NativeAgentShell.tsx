import { useState, type ReactNode } from 'react';
import { List, Plus, X } from '@phosphor-icons/react';
import * as Dialog from '@radix-ui/react-dialog';

interface Props { native?: boolean; sidebar?: ReactNode; title: string; onNew: () => void; children: ReactNode; }

/** Opt-in presentation; the existing Agent runtime and workbench keep their behavior. */
export function NativeAgentShell({ native, sidebar, title, onNew, children }: Props) {
  const [open, setOpen] = useState(false);
  if (!native) return <div className="h-full flex animate-in fade-in duration-300">{sidebar}{children}</div>;
  return <div className="um-native-agent um-agent-workspace">
    <div className="um-agent-directory">{sidebar}</div>
    <section className="um-agent-main" aria-label="小宇工作区">
      <header className="um-agent-toolbar">
        <div>
          <Dialog.Root open={open} onOpenChange={setOpen}>
            <Dialog.Trigger asChild><button className="um-agent-history-button" aria-label="打开历史对话"><List size={18} /></button></Dialog.Trigger>
            <Dialog.Portal><Dialog.Overlay className="um-agent-drawer-overlay" /><Dialog.Content className="um-native-agent um-agent-drawer">
              <Dialog.Title className="sr-only">历史对话</Dialog.Title>
              <Dialog.Description className="sr-only">搜索、切换或删除历史对话。</Dialog.Description>
              <Dialog.Close asChild><button className="um-agent-drawer-close" aria-label="关闭历史对话"><X size={18} /></button></Dialog.Close>
              <div onClick={event => { if ((event.target as HTMLElement).closest('[data-session-select], [data-session-new]')) setOpen(false); }}>{sidebar}</div>
            </Dialog.Content></Dialog.Portal>
          </Dialog.Root>
          <h1>{title}</h1>
        </div>
        <button className="um-agent-button" onClick={onNew}><Plus size={16} />新对话</button>
      </header>
      {children}
    </section>
  </div>;
}
