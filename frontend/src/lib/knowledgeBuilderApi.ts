import api from '@/lib/api';
import type { BlockResourceItem, BlockResourcePayload, BlockResourcesResponse, BlockQuizMode, BlockAssessment } from '@/types/knowledgeBuilder';
import type { BuildArchetype, BuildSummary, KnowledgeTreeBuildDetail, IntakeRequestPayload, IntakeResponsePayload } from '@/types/knowledgeBuilder';
import type { AssetTrack, BlockResourceUpdatePayload, BlockResourceVotePayload, TreeAutoDiscoverResponse, TreePublicAssetImportPayload, TreePublicAssetsResponse } from '@/types/knowledgeBuilder';
import type { AtomDifficultyInfo, EnsureBlockProjectResponse, TreeAtomPoint } from '@/types/knowledgeBuilder';

export function inferAtomDifficultyTier(
  atom: Pick<TreeAtomPoint, 'goal_type' | 'cognitive_level' | 'granularity_minutes' | 'difficulty_tier' | 'difficulty_label'>
): AtomDifficultyInfo {
  if (atom.difficulty_tier === 'L3') {
    return { tier: 'L3', label: atom.difficulty_label || '硬核攻坚', shortLabel: '攻坚' };
  }
  if (atom.difficulty_tier === 'L1') {
    return { tier: 'L1', label: atom.difficulty_label || '基础速通', shortLabel: '基础' };
  }
  if (atom.difficulty_tier === 'L2') {
    return { tier: 'L2', label: atom.difficulty_label || '机制辨析', shortLabel: '辨析' };
  }
  const goalType = (atom.goal_type || '').trim();
  const cog = (atom.cognitive_level || '').trim();
  const mins = Number(atom.granularity_minutes || 4);
  if (
    goalType === '实操计算' ||
    goalType === '综合应用' ||
    cog === '评价' ||
    cog === '创造' ||
    (mins >= 6 && cog === '分析' && goalType !== '概念辨析')
  ) {
    return { tier: 'L3', label: '硬核攻坚', shortLabel: '攻坚' };
  }
  if ((cog === '记忆' || cog === '理解') && (!goalType || goalType === '概念辨析' || goalType === '概念')) {
    return { tier: 'L1', label: '基础速通', shortLabel: '基础' };
  }
  return { tier: 'L2', label: '机制辨析', shortLabel: '辨析' };
}

export function resolvePublicAssetLink(url: string, locator?: string): string | undefined {
  const internal = /^\/courses(?:\/|[?#]|$)/.test(url);
  if (!internal && !/^https:\/\//i.test(url)) return undefined;
  let link: URL;
  try {
    link = new URL(url, 'https://unimind.invalid');
  } catch {
    return undefined;
  }
  if (link.protocol !== 'https:' || (internal && !/^\/courses(?:\/|$)/.test(link.pathname))) return undefined;
  if (!locator?.trim()) return url;

  const host = link.hostname.toLowerCase();
  const bilibili = host === 'bilibili.com' || host.endsWith('.bilibili.com');
  const youtube = host === 'youtu.be' || host === 'youtube.com' || host.endsWith('.youtube.com');
  const episode = locator.match(/(?:\bP\s*|第\s*)(\d+)\s*(?:P|集|讲|章)?/i);
  const timestamp = locator.match(/(?:^|[^\d])(?:(\d+):)?(\d{1,2}):([0-5]\d)(?!\d)/);
  const anchor = locator.match(/#(.+)$/);
  if (bilibili && episode) link.searchParams.set('p', episode[1]);
  if ((bilibili || youtube) && timestamp) {
    const seconds = Number(timestamp[1] ?? 0) * 3600 + Number(timestamp[2]) * 60 + Number(timestamp[3]);
    link.searchParams.set('t', String(seconds));
  }
  if (anchor) link.hash = anchor[1];
  return internal ? `${link.pathname}${link.search}${link.hash}` : link.href;
}

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

export async function resumeKnowledgeBuild(buildId: string): Promise<BuildSummary> {
  const { data } = await api.post<BuildSummary>(`/knowledge-builder/${encodeURIComponent(buildId)}/resume/`);
  return data;
}

export async function inquireKnowledgeRequirements(payload: IntakeRequestPayload): Promise<IntakeResponsePayload> {
  const { data } = await api.post<IntakeResponsePayload>('/knowledge-builder/intake/', payload);
  return data;
}

const blockPath = (buildId: string, blockId: number) => `/knowledge-builder/${encodeURIComponent(buildId)}/blocks/${blockId}`;

export async function ensureBlockProject(
  buildId: string,
  blockId: number,
  payload?: { project_id?: number | null; atom_id?: number | null }
): Promise<EnsureBlockProjectResponse> {
  const { data } = await api.post<EnsureBlockProjectResponse>(`${blockPath(buildId, blockId)}/resources/`, {
    action: 'ensure_project',
    ...(payload?.project_id ? { project_id: payload.project_id } : {}),
    ...(payload?.atom_id ? { atom_id: payload.atom_id } : {}),
  });
  return data;
}

export async function getBlockResources(buildId: string, blockId: number, query?: string): Promise<BlockResourcesResponse> {
  const { data } = await api.get<BlockResourcesResponse>(`${blockPath(buildId, blockId)}/resources/`, { params: query === undefined ? {} : { query } });
  return data;
}
export async function getTreePublicAssets(buildId: string, signal?: AbortSignal): Promise<TreePublicAssetsResponse> {
  const { data } = await api.get<TreePublicAssetsResponse>(`/knowledge-builder/${encodeURIComponent(buildId)}/public-assets/`, { signal });
  return data;
}
export async function autoDiscoverTreePublicAssets(buildId: string): Promise<TreeAutoDiscoverResponse> {
  const { data } = await api.post<TreeAutoDiscoverResponse>(`/knowledge-builder/${encodeURIComponent(buildId)}/public-assets/`, { action: 'auto_discover' });
  return data;
}
export async function importTreePublicAsset(buildId: string, payload: TreePublicAssetImportPayload): Promise<{ mounted_count: number; asset_track: AssetTrack; resources: BlockResourceItem[] }> {
  const { data } = await api.post<{ mounted_count: number; asset_track: AssetTrack; resources: BlockResourceItem[] }>(`/knowledge-builder/${encodeURIComponent(buildId)}/public-assets/`, payload);
  return data;
}
export async function updateBlockResource(buildId: string, blockId: number, payload: BlockResourceUpdatePayload): Promise<BlockResourceItem> {
  const { data } = await api.patch<BlockResourceItem>(`${blockPath(buildId, blockId)}/resources/`, payload);
  return data;
}
export async function attachBlockResource(buildId: string, blockId: number, payload: BlockResourcePayload): Promise<BlockResourceItem> {
  const { data } = await api.post<BlockResourceItem>(`${blockPath(buildId, blockId)}/resources/`, payload);
  return data;
}
export async function voteBlockResource(buildId: string, blockId: number, resourceId: number, vote: 1 | -1 | 0, dismiss?: boolean): Promise<BlockResourceItem> {
  const payload: BlockResourceVotePayload = { action: 'vote', resource_id: resourceId, vote, ...(dismiss ? { dismiss: true } : {}) };
  const { data } = await api.post<BlockResourceItem>(`${blockPath(buildId, blockId)}/resources/`, payload);
  return data;
}
export async function deleteBlockResource(buildId: string, blockId: number, resourceId: number): Promise<void> {
  await api.delete(`${blockPath(buildId, blockId)}/resources/`, { data: { resource_id: resourceId } });
}
export async function blockAssessment(buildId: string, blockId: number, payload: { project_id: number; action: 'read' | 'generate'; mode?: BlockQuizMode; retest?: boolean }): Promise<{ assessment: BlockAssessment | null; preparation: { status: 'pending' | 'completed' | 'failed'; error: string } | null }> {
  const { data } = await api.post(`${blockPath(buildId, blockId)}/quiz/`, payload);
  return data;
}
export async function attachBlockResourceToProject(buildId: string, blockId: number, projectId: number, resourceId: number): Promise<{ notice: string }> {
  const { data } = await api.post(`${blockPath(buildId, blockId)}/resources/`, { action: 'attach_project', project_id: projectId, resource_id: resourceId });
  return data;
}
