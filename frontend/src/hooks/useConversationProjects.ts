import { useCallback, useEffect, useState, type Dispatch, type SetStateAction } from 'react';
import { toast } from 'sonner';
import api from '@/lib/api';
import type { ConversationSession } from './useAgentConversation';

export interface ConversationProject { id: number; name: string; instructions: string; }
export interface ConversationProjectControls {
  projects: ConversationProject[];
  projectId: number | null;
  pending: boolean;
  error: boolean;
  reload: () => void;
  create: (name: string, instructions: string) => Promise<boolean>;
  update: (id: number, name: string, instructions: string) => Promise<boolean>;
  remove: (id: number) => Promise<boolean>;
}

export function useConversationProjects(enabled: boolean, projectId: number | null, setProjectId: Dispatch<SetStateAction<number | null>>, setSessions: Dispatch<SetStateAction<ConversationSession[]>>): ConversationProjectControls {
  const [projects, setProjects] = useState<ConversationProject[]>([]);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState(false);
  const reload = useCallback(async () => {
    try {
      const response = await api.get<ConversationProject[]>('/ai/projects/');
      setProjects(response.data);
      setError(false);
    } catch { setError(true); }
  }, []);
  useEffect(() => { if (enabled) void reload(); }, [enabled, reload]);

  const save = async (name: string, instructions: string, id?: number) => {
    if (pending || !name.trim()) return false;
    setPending(true);
    try {
      const response = id === undefined
        ? await api.post<ConversationProject>('/ai/projects/', { name: name.trim(), instructions: instructions.trim() })
        : await api.patch<ConversationProject>(`/ai/projects/${id}/`, { name: name.trim(), instructions: instructions.trim() });
      setProjects(previous => id === undefined ? [...previous, response.data] : previous.map(project => project.id === id ? response.data : project));
      return true;
    } catch { toast.error('项目保存失败，请重试'); return false; }
    finally { setPending(false); }
  };
  return {
    projects, projectId, pending, error, reload,
    create: (name, instructions) => save(name, instructions), update: (id, name, instructions) => save(name, instructions, id),
    remove: async id => {
      if (pending) return false;
      setPending(true);
      try {
        await api.delete(`/ai/projects/${id}/`);
        setProjects(previous => previous.filter(project => project.id !== id));
        setSessions(previous => previous.filter(session => session.projectId !== id));
        setProjectId(previous => previous === id ? null : previous);
        toast.success('项目及其中的对话已删除');
        return true;
      } catch { toast.error('项目删除失败，请重试'); return false; }
      finally { setPending(false); }
    },
  };
}
