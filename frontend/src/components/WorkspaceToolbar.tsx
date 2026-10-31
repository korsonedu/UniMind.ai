import { useContext, type ReactNode } from 'react';
import { createPortal } from 'react-dom';
import { useOutletContext } from 'react-router-dom';
import { WorkspaceToolbarHostContext } from './WorkspaceContext';

export function WorkspaceToolbar({ children, className }: { children: ReactNode; className: string }) {
  const override = useContext(WorkspaceToolbarHostContext);
  const outlet = useOutletContext<{ toolbarHost?: HTMLDivElement | null }>() ?? {};
  const host = override ? override.host : outlet.toolbarHost ?? null;
  const enabled = override ? override.enabled : true;
  return enabled && host ? createPortal(<header className={className}>{children}</header>, host) : null;
}
