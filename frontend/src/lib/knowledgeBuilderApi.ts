import api from '@/lib/api';
import type { BlockResourceItem, BlockResourcePayload, BlockResourcesResponse, BlockQuizMode, BlockQuizQuestion, BlockQuizSubmitResult } from '@/types/knowledgeBuilder';
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

const blockPath = (buildId: string, blockId: number) => `/knowledge-builder/${encodeURIComponent(buildId)}/blocks/${blockId}`;

export async function getBlockResources(buildId: string, blockId: number, query?: string): Promise<BlockResourcesResponse> {
  const { data } = await api.get<BlockResourcesResponse>(`${blockPath(buildId, blockId)}/resources/`, { params: query === undefined ? {} : { query } });
  return data;
}
export async function attachBlockResource(buildId: string, blockId: number, payload: BlockResourcePayload): Promise<BlockResourceItem> {
  const { data } = await api.post<BlockResourceItem>(`${blockPath(buildId, blockId)}/resources/`, payload);
  return data;
}
export async function deleteBlockResource(buildId: string, blockId: number, resourceId: number): Promise<void> {
  await api.delete(`${blockPath(buildId, blockId)}/resources/`, { data: { resource_id: resourceId } });
}
export async function generateBlockQuiz(buildId: string, blockId: number, payload: { mode?: BlockQuizMode; retest?: boolean }): Promise<{ block_id: number; mode: BlockQuizMode; questions: BlockQuizQuestion[] }> {
  const { data } = await api.post(`${blockPath(buildId, blockId)}/quiz/`, { action: 'generate', ...payload });
  return data;
}
export async function submitBlockQuiz(buildId: string, blockId: number, payload: { questions: BlockQuizQuestion[]; answers: Record<string, string> }): Promise<BlockQuizSubmitResult> {
  const { data } = await api.post<BlockQuizSubmitResult>(`${blockPath(buildId, blockId)}/quiz/`, { action: 'submit', ...payload });
  return data;
}
