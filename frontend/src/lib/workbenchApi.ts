import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import api from './api';
import { queryKeys } from './queryKeys';
import type {
  ProjectSourceCounts, ProjectSourceDetail, ProjectSourceList, ProjectSourceSummary, WorkbenchOverview,
} from '@/types/workbench';

const sourcesUrl = (projectId: number) => `/ai/projects/${projectId}/sources/`;
const sourceUrl = (projectId: number, sourceId: string) => `${sourcesUrl(projectId)}${sourceId}/`;
const overviewUrl = (projectId: number) => `/ai/projects/${projectId}/workbench-overview/`;

type SourceImport = { kind: 'web_url'; url: string } | { kind: 'course'; course_id: number };
export async function importWorkbenchSource(projectId: number, input: SourceImport) {
  return (await api.post<ProjectSourceSummary>(`${sourcesUrl(projectId)}import/`, input)).data;
}

type SourcePatch = { title: string } | { is_selected: boolean } | { action: 'retry' };
export type SourceChange =
  | { type: 'upload'; files: File[]; onProgress: (percent: number) => void }
  | { type: 'import'; input: SourceImport }
  | { type: 'patch'; sourceId: string; patch: SourcePatch }
  | { type: 'selectAll'; selected: boolean }
  | { type: 'delete'; sourceId: string };

export function sourceIsProcessing(source: ProjectSourceSummary) {
  return source.status === 'pending' || source.status === 'processing';
}

export function selectedReadySources(sources: ProjectSourceSummary[]) {
  return sources.filter(source => source.is_selected && source.status === 'ready');
}

export function useWorkbenchSources(projectId: number) {
  return useQuery({
    queryKey: queryKeys.workbench.sources(projectId),
    queryFn: async ({ signal }) => (await api.get<ProjectSourceList>(sourcesUrl(projectId), { signal })).data,
    refetchInterval: query => query.state.data?.sources.some(sourceIsProcessing) ? 2500 : false,
  });
}

export function useWorkbenchSourceDetail(projectId: number, sourceId: string, summary?: ProjectSourceSummary) {
  return useQuery({
    queryKey: queryKeys.workbench.source(projectId, sourceId, summary?.status, summary?.updated_at),
    queryFn: async ({ signal }) => (await api.get<ProjectSourceDetail>(sourceUrl(projectId, sourceId), { signal })).data,
    refetchInterval: query => query.state.data && sourceIsProcessing(query.state.data) ? 2500 : false,
  });
}

export function useWorkbenchSourceActions(projectId: number) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async (change: SourceChange): Promise<ProjectSourceSummary[]> => {
      const url = sourcesUrl(projectId);
      switch (change.type) {
        case 'upload': {
          const form = new FormData();
          change.files.forEach(file => form.append('files', file));
          const { data } = await api.post<{ sources: ProjectSourceSummary[] }>(`${url}upload/`, form, {
            timeout: 30 * 60_000,
            onUploadProgress: ({ progress }) => {
              if (progress !== undefined) change.onProgress(Math.round(progress * 100));
            },
          });
          return data.sources;
        }
        case 'import':
          return [await importWorkbenchSource(projectId, change.input)];
        case 'patch':
          return [(await api.patch<ProjectSourceSummary>(sourceUrl(projectId, change.sourceId), change.patch)).data];
        case 'selectAll':
          await api.post<ProjectSourceCounts>(`${url}batch-select/`, { select_all: true, is_selected: change.selected });
          return [];
        case 'delete':
          await api.delete(sourceUrl(projectId, change.sourceId));
          return [];
      }
    },
    onSuccess: async (updated, change) => {
      const key = queryKeys.workbench.sources(projectId);
      if (change.type === 'selectAll') {
        await client.invalidateQueries({ queryKey: key });
        return;
      }
      await client.cancelQueries({ queryKey: key, exact: true });
      client.setQueryData<ProjectSourceList>(key, previous => {
        if (!previous) return previous;
        let sources = previous.sources;
        const updatedById = new Map(updated.map(source => [source.id, source]));
        sources = change.type === 'delete'
          ? sources.filter(source => source.id !== change.sourceId)
          : [...updated.filter(source => !sources.some(row => row.id === source.id)),
            ...sources.map(source => updatedById.get(source.id) ?? source)];
        return {
          sources, project_id: projectId,
          total_count: sources.length,
          selected_count: sources.filter(source => source.is_selected).length,
          ready_count: sources.filter(source => source.status === 'ready').length,
        };
      });
      await client.invalidateQueries({ queryKey: key });
    },
  });
}

export function useWorkbenchOverview(projectId: number, sources: ProjectSourceSummary[]) {
  const selection = sources.map(source => [source.id, source.updated_at]).sort(([a], [b]) => a.localeCompare(b));
  const query = (generate: boolean) => ({
    queryKey: queryKeys.workbench.overview(projectId, selection, generate),
    queryFn: async () => (generate
      ? await api.post<WorkbenchOverview>(overviewUrl(projectId), undefined, { timeout: 90_000 })
      : await api.get<WorkbenchOverview>(overviewUrl(projectId))).data,
    enabled: sources.length > 0,
    staleTime: Infinity,
    retry: false as const,
  });
  const extract = useQuery(query(false));
  const synthesis = useQuery(query(true));
  return { overview: synthesis.data ?? extract.data, pending: synthesis.isPending, error: synthesis.isError, regenerate: synthesis.refetch };
}

interface CoursePage {
  items: { id: number; title: string }[];
  page: number;
  total_pages: number;
}

export function useWorkbenchCourses(projectId: number, search: string, enabled: boolean) {
  return useInfiniteQuery({
    queryKey: queryKeys.workbench.courses(projectId, search),
    queryFn: async ({ pageParam, signal }) => (await api.get<CoursePage>('/courses/', {
      params: { workbench_project: projectId, search, page: pageParam, page_size: 20 }, signal,
    })).data,
    initialPageParam: 1,
    getNextPageParam: last => last.page < last.total_pages ? last.page + 1 : undefined,
    enabled,
  });
}
