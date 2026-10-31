import { createContext } from 'react';

export interface WorkspaceToolbarHost {
  host: HTMLDivElement | null;
  enabled: boolean;
}

export const WorkspaceToolbarHostContext = createContext<WorkspaceToolbarHost | null>(null);
export const WorkspaceActiveContext = createContext(true);
