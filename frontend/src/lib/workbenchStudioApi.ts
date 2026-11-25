import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import api from './api';
import { queryKeys } from './queryKeys';
import type { FlashcardMastery, ProjectNote, StudioArtifact, StudioKind, StudioQuizAnswer, StudioQuizAttempt } from '@/types/workbench';

const studioUrl = (projectId: number) => `/ai/projects/${projectId}/studio/`;
const notesUrl = (projectId: number) => `/ai/projects/${projectId}/notes/`;
const aiWrite = { timeout: 180_000 };
type NoteDraft = Pick<ProjectNote, 'title' | 'content'>;

export function useWorkbenchStudio(projectId: number) {
  const client = useQueryClient();
  const key = queryKeys.workbench.studio(projectId);
  const url = studioUrl(projectId);
  const list = useQuery({
    queryKey: key,
    queryFn: async ({ signal }) => (await api.get<{ artifacts: StudioArtifact[] }>(url, { signal })).data.artifacts,
    refetchInterval: query => query.state.data?.some(artifact => artifact.status === 'generating') ? 2500 : false,
  });
  const update = async (change: (previous: StudioArtifact[]) => StudioArtifact[]) => {
    await client.cancelQueries({ queryKey: key, exact: true });
    client.setQueryData<StudioArtifact[]>(key, previous => change(previous ?? []));
    void client.invalidateQueries({ queryKey: key });
  };
  const upsert = (artifact: StudioArtifact) => update(previous => previous.some(row => row.id === artifact.id)
    ? previous.map(row => row.id === artifact.id ? artifact : row)
    : [artifact, ...previous]);

  const generate = useMutation({
    mutationFn: async ({ kind, sourceIds }: { kind: StudioKind; sourceIds: string[] }) =>
      (await api.post<StudioArtifact>(url, {
        kind, source_ids: sourceIds, ...(kind === 'quiz' ? { include_subjective: true } : {}),
      }, aiWrite)).data,
    onSuccess: upsert,
    onError: () => { void client.invalidateQueries({ queryKey: key }); },
  });
  const rate = useMutation({
    mutationFn: async ({ id, cardId, mastery }: { id: string; cardId: string; mastery: FlashcardMastery }) =>
      (await api.patch<StudioArtifact>(`${url}${id}/`, { flashcard_mastery: { [cardId]: mastery } })).data,
    onSuccess: upsert,
  });
  const submitQuiz = useMutation({
    mutationFn: async ({ id, answers }: { id: string; answers: StudioQuizAnswer[] }) =>
      (await api.post<StudioQuizAttempt>(`${url}${id}/submit-quiz/`, { answers }, aiWrite)).data,
    onSuccess: (attempt, { id }) => update(previous => previous.map(row =>
      row.id === id && row.status === 'ready' && row.kind === 'quiz'
        ? { ...row, structured_payload: { ...row.structured_payload, latest_attempt: attempt } } : row)),
  });
  const saveNote = useMutation({
    mutationFn: async (id: string) => (await api.post<ProjectNote>(`${url}${id}/save-note/`)).data,
    onSuccess: async (note, id) => {
      await update(previous => previous.map(row => row.id === id ? { ...row, linked_note: note.id } : row));
      void client.invalidateQueries({ queryKey: queryKeys.workbench.notes(projectId) });
    },
  });
  const remove = useMutation({
    mutationFn: (id: string) => api.delete(`${url}${id}/`),
    onSuccess: (_response, id) => update(previous => previous.filter(row => row.id !== id)),
  });
  return { list, generate, rate, submitQuiz, saveNote, remove };
}

export function useWorkbenchNotes(projectId: number) {
  const client = useQueryClient();
  const key = queryKeys.workbench.notes(projectId);
  const url = notesUrl(projectId);
  const list = useQuery({
    queryKey: key,
    queryFn: async ({ signal }) => (await api.get<{ notes: ProjectNote[] }>(url, { signal })).data.notes,
    refetchOnMount: 'always',
  });
  const save = useMutation({
    mutationFn: async ({ note, draft }: { note: ProjectNote | null; draft: NoteDraft }) => {
      if (!note) return (await api.post<ProjectNote>(url, draft)).data;
      const { data } = await api.patch<Pick<ProjectNote, 'id' | 'title' | 'content' | 'version' | 'updated_at'>>(
        `/notes/items/${note.id}/`, { ...draft, version: note.version });
      return { ...note, ...data };
    },
    onSuccess: async note => {
      await client.cancelQueries({ queryKey: key, exact: true });
      client.setQueryData<ProjectNote[]>(key, previous => [note, ...(previous ?? []).filter(row => row.id !== note.id)]);
      void client.invalidateQueries({ queryKey: key });
    },
  });
  return { list, save };
}
