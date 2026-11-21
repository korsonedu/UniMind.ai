import { useLocale, type Locale } from '@/i18n';
import type { LearningKnowledge } from '@/components/LearningKnowledgePanel';
import type { PracticePayload } from '@/pages/xiaoyu/visuals/PracticeQuizCard';
import { useQuery } from '@tanstack/react-query';
import api from '@/lib/api';
import { useAuthStore } from '@/store/useAuthStore';

export interface LearningStage { knowledge_nodes?: string[]; id: string; title: string; outcome: string; task: string; prerequisites: string[]; sources: string[]; }
export interface LearningTask {
  is_current?: boolean; stage_id: string;
  id: string; title: string; instructions: string; node_id: string; version_id: number | null;
  purpose?: 'diagnostic' | 'practice' | 'recheck'; source_task_id?: string | null;
  response_type?: 'objective' | 'explanation' | 'calculation' | 'reasoning' | 'case' | 'code'; criteria?: string[]; sources?: string[];
  status: 'ready' | 'processing' | 'completed' | 'partial' | 'failed' | 'unavailable';
  exam_id: number | null; assistance: string; review_due_at: string | null;
  summary: { total_score: number; max_score: number; graded_count: number; total_questions: number; label_source?: string } | null;
  payload: PracticePayload;
}
export type LearningStudyRequest = (text: string, activity?: { task_id?: string; stage_id?: string }) => void;

export function passedLearningTask(task: LearningTask) {
  const score = task.summary;
  return task.status === 'completed' && !!score?.max_score && score.total_score / score.max_score >= 0.6;
}

export function failedLearningTask(task: LearningTask) {
  return task.status === 'completed' && task.purpose !== 'diagnostic' && !passedLearningTask(task);
}

export function playableLearningTask(task: LearningTask) {
  return task.is_current !== false && ['ready', 'processing', 'partial', 'failed'].includes(task.status);
}

export function findRemedialTask(tasks: LearningTask[], failedTask: LearningTask) {
  // The task list API orders attempts from oldest to newest.
  return tasks.slice(tasks.findIndex(task => task.id === failedTask.id) + 1).reverse().find(task =>
    task.purpose !== 'diagnostic' && playableLearningTask(task) &&
    (task.source_task_id === failedTask.id || task.stage_id === failedTask.stage_id));
}

export interface LearningPlan { knowledge_path?: { version_id: number; targets: string[]; depth: 'apply' | 'transfer' }; goal: string; deadline: string | null; weekly_minutes: number; stages: LearningStage[]; }
export interface LearningResource { source_kind?: string; domain?: string; topic?: string; level?: string; edition?: string; library_revision?: number; id: string; title: string; url: string; excerpt: string; read_at: string; }
export interface LearningEvent { id: number; kind: string; content: Record<string, unknown>; delivery: { saved: boolean; read: boolean | null; responded: boolean } | null; source: { id: number; text: string; conversation_id: string } | null; created_at: string; }
export interface TeachingGuidance {
  status: 'inactive' | 'start' | 'awaiting' | 'retry' | 'remediate' | 'recheck' | 'continue' | 'review';
  feedback: string; next_action: string; task_id: string | null; stage_id: string; reason: string; stalled: boolean;
}
export interface ProjectLearning {
  revision: number; conversation_id: string | null; server_time: string;
  focus_task_id?: string | null; planning_enabled: boolean; reminders_enabled: boolean;
  teaching_guidance?: TeachingGuidance;
  knowledge?: LearningKnowledge;
  task_progress?: { completed: number; total: number; feedback: string; next_action: string; next_task_id: string | null };
  project_id: number; name: string; instructions: string; status: 'preparing' | 'active' | 'paused' | 'completed';
  plan: Partial<LearningPlan>; resources: LearningResource[]; current_stage: string; feedback: string; next_action: string;
  pending_plan: { base_revision?: number; plan?: LearningPlan; reason?: string; knowledge?: { title: string; revision: number; targets: string[]; depth: 'apply' | 'transfer' } };
  followup_at: string | null; followup_text: string; resume_at: string | null; events: LearningEvent[];
}
export const learningKey = (userId: number | undefined, projectId: number | null, locale?: Locale) =>
  locale ? ['project-learning', userId, projectId, locale] : ['project-learning', userId, projectId];
export function useProjectLearning(projectId: number | null) {
  const locale = useLocale();
  const userId = useAuthStore(s => s.user?.id);
  return useQuery({ queryKey: learningKey(userId, projectId, locale), enabled: !!userId && !!projectId,
    queryFn: ({ signal }) => api.get<ProjectLearning>(`/ai/projects/${projectId}/learning/`, { signal, headers: { 'Accept-Language': locale } }).then(r => r.data), staleTime: 5000 });
}
export function learningUrl(path: string, projectId: number | null, conversationId?: string) {
  if (!projectId) return path;
  const url = new URL(path, 'https://unimind.invalid');
  url.searchParams.set('project', String(projectId));
  if (conversationId) url.searchParams.set('conversation', conversationId);
  return url.pathname + url.search + url.hash;
}
