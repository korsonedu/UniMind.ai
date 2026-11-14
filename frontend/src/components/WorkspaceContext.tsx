import { createContext, useContext, useEffect } from 'react';

export interface WorkspaceToolbarHost {
  host: HTMLDivElement | null;
  enabled: boolean;
}

export const WorkspaceToolbarHostContext = createContext<WorkspaceToolbarHost | null>(null);
export const WorkspaceActiveContext = createContext(true);
export const NotesSidebarContext = createContext<{ open: boolean; close: () => void; setAvailable: (available: boolean) => void }>({ open: false, close: () => {}, setAvailable: () => {} });

export type SidebarView = 'home' | 'chat' | 'outline' | 'materials' | 'notes';
export interface SidebarRecentItem { key: string; view: 'chat' | 'notes'; title: string; courseId?: number; conversationId?: string; noteId?: number }
export const CourseSidebarContext = createContext<{
  host: HTMLDivElement | null;
  view: SidebarView;
  visible: boolean;
  recordRecent: (item: SidebarRecentItem) => void;
  setAvailable: (available: boolean) => void;
}>({ host: null, view: 'home', visible: false, recordRecent: () => {}, setAvailable: () => {} });

export function useNotesSidebarAvailability(available: boolean) {
  const { setAvailable } = useContext(NotesSidebarContext);
  useEffect(() => {
    setAvailable(available);
    return () => setAvailable(false);
  }, [available, setAvailable]);
}
