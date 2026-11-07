import { createContext, useContext, useEffect } from 'react';

export interface WorkspaceToolbarHost {
  host: HTMLDivElement | null;
  enabled: boolean;
}

export const WorkspaceToolbarHostContext = createContext<WorkspaceToolbarHost | null>(null);
export const WorkspaceActiveContext = createContext(true);
export const NotesSidebarContext = createContext<{ open: boolean; close: () => void; setAvailable: (available: boolean) => void }>({ open: false, close: () => {}, setAvailable: () => {} });

export function useNotesSidebarAvailability(available: boolean) {
  const { setAvailable } = useContext(NotesSidebarContext);
  useEffect(() => {
    setAvailable(available);
    return () => setAvailable(false);
  }, [available, setAvailable]);
}
