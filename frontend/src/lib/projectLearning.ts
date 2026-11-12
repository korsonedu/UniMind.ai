import type { LearningKnowledge } from '@/components/LearningKnowledgePanel';
import { useQuery } from '@tanstack/react-query';
import api from '@/lib/api';
import { useAuthStore } from '@/store/useAuthStore';

export interface LearningStage { id: string; title: string; outcome: string; task: string; prerequisites: string[]; sources: string[]; }
export interface LearningPlan { goal: string; deadline: string | null; weekly_minutes: number; stages: LearningStage[]; }
export interface LearningResource { source_kind?: string; domain?: string; topic?: string; level?: string; edition?: string; library_revision?: number; id: string; title: string; url: string; excerpt: string; read_at: string; }
export interface LearningEvent { id: number; kind: string; content: Record<string, unknown>; delivery: { saved: boolean; read: boolean | null; responded: boolean } | null; source: { id: number; text: string; conversation_id: string } | null; created_at: string; }
export interface TeachingGuidance {
  status: 'inactive' | 'start' | 'awaiting' | 'retry' | 'remediate' | 'recheck' | 'continue' | 'review';
  feedback: string; next_action: string; task_id: string | null; stage_id: string; reason: string; stalled: boolean;
}
export interface ProjectLearning {
  planning_enabled: boolean; reminders_enabled: boolean;
  teaching_guidance?: TeachingGuidance;
  knowledge?: LearningKnowledge;
  task_progress?: { completed: number; total: number; feedback: string; next_action: string; next_task_id: string | null };
  project_id: number; name: string; instructions: string; status: 'preparing' | 'active' | 'paused' | 'completed';
  plan: Partial<LearningPlan>; resources: LearningResource[]; current_stage: string; feedback: string; next_action: string;
  pending_plan: { plan?: LearningPlan; reason?: string; knowledge?: { title: string; revision: number; targets: string[]; depth: 'apply' | 'transfer' } }; revision: number; conversation_id: string | null;
  followup_at: string | null; followup_text: string; resume_at: string | null; events: LearningEvent[];
}
export const learningKey = (userId: number | undefined, projectId: number | null) => ['project-learning', userId, projectId];
export function useProjectLearning(projectId: number | null) {
  const userId = useAuthStore(s => s.user?.id);
  return useQuery({ queryKey: learningKey(userId, projectId), enabled: !!userId && !!projectId,
    queryFn: ({ signal }) => api.get<ProjectLearning>(`/ai/projects/${projectId}/learning/`, { signal }).then(r => r.data), staleTime: 5000 });
}
export function learningUrl(path: string, projectId: number | null, conversationId?: string) {
  if (!projectId) return path;
  const url = new URL(path, 'https://unimind.invalid');
  url.searchParams.set('project', String(projectId));
  if (conversationId) url.searchParams.set('conversation', conversationId);
  return url.pathname + url.search + url.hash;
}
