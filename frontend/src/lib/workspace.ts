import { useQuery } from '@tanstack/react-query';
import axios from 'axios';
import api from '@/lib/api';
import { useAuthStore } from '@/store/useAuthStore';

export interface WorkspaceCourse {
  id: number; title: string; module: string; duration: string; filename: string;
  status: 'published' | 'draft' | 'processing' | 'failed';
  processing_status?: 'pending' | 'processing' | 'completed' | 'failed'; error_message?: string;
  transcript: string; knowledge: { name: string; children: string[] }[];
}
export interface WorkspaceInvite {
  id: number; code: string; name: string; courses: number[]; expires_at: string;
  service_ends_at: string; max_uses: number; used_count: number; active: boolean; enabled?: boolean; state_label?: string;
}
export interface WorkspaceMember {
  id: number; name: string; joined_at: string; service_ends_at: string;
  courses: number[]; active: boolean;
}
export interface WorkspaceSnapshot {
  available: boolean; demo?: boolean; role: 'admin' | 'student' | null;
  workspace: { name: string; description: string; joined_at: string; service_ends_at: string; service_active?: boolean } | null;
  courses: WorkspaceCourse[]; members: WorkspaceMember[]; invites: WorkspaceInvite[];
  usage: { label: string; used: number; limit: number | null; unit: string }[];
}
export interface InvitePreview { name: string; service: string; courses: string[]; service_ends_at: string }
export const workspacePath = '/users/workspace/';
export const emptyWorkspace: WorkspaceSnapshot = { available: false, role: null, workspace: null, courses: [], members: [], invites: [], usage: [] };
export function useWorkspace() {
  const userId = useAuthStore(state => state.user?.id);
  return useQuery({ queryKey: ['workspace', userId], enabled: userId !== undefined, retry: false,
    refetchInterval: query => query.state.data?.courses.some(course => course.status === 'processing') ? 5000 : false,
    queryFn: async (): Promise<WorkspaceSnapshot> => {
      try { return (await api.get(workspacePath)).data; }
      catch (error) {
        if (axios.isAxiosError(error) && [404, 410].includes(error.response?.status || 0)) return emptyWorkspace;
        throw error;
      }
    },
  });
}
export const serviceDate = (date: string) => date ? new Intl.DateTimeFormat('zh-CN', { year: 'numeric', month: 'long', day: 'numeric' }).format(new Date(date)) : '未设置';
