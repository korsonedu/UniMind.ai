import type { ReactNode } from 'react';
import { createPortal } from 'react-dom';
import { useOutletContext } from 'react-router-dom';

export function WorkspaceToolbar({ children, className }: { children: ReactNode; className: string }) {
  const { toolbarHost } = useOutletContext<{ toolbarHost: HTMLDivElement | null }>();
  return toolbarHost ? createPortal(<header className={className}>{children}</header>, toolbarHost) : null;
}
