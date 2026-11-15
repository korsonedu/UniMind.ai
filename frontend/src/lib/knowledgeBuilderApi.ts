import api from '@/lib/api';
import type { BuildArchetype, BuildSummary, KnowledgeTreeBuildDetail, IntakeRequestPayload, IntakeResponsePayload } from '@/types/knowledgeBuilder';

export async function listKnowledgeBuilds(signal?: AbortSignal): Promise<BuildSummary[]> {
  const { data } = await api.get<BuildSummary[]>('/knowledge-builder/', { signal });
  return data;
}

export async function getKnowledgeBuildDetail(buildId: string, signal?: AbortSignal): Promise<KnowledgeTreeBuildDetail> {
  const { data } = await api.get<KnowledgeTreeBuildDetail>(`/knowledge-builder/${encodeURIComponent(buildId)}/`, { signal });
  return data;
}

export async function getKnowledgeBuildStatus(buildId: string, signal?: AbortSignal): Promise<BuildSummary> {
  const { data } = await api.get<BuildSummary>(`/knowledge-builder/${encodeURIComponent(buildId)}/status/`, { signal });
  return data;
}

export async function createKnowledgeBuild(payload: { subject: string; archetype?: BuildArchetype; requirements?: Record<string, unknown> }): Promise<BuildSummary> {
  const { data } = await api.post<BuildSummary>('/knowledge-builder/', payload);
  return data;
}

export async function inquireKnowledgeRequirements(payload: IntakeRequestPayload): Promise<IntakeResponsePayload> {
  const { data } = await api.post<IntakeResponsePayload>('/knowledge-builder/intake/', payload);
  return data;
}
