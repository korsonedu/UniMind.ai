import { learningUrl } from './projectLearning';

export function companionProjectId(params: URLSearchParams) {
  const value = params.get('project');
  if (!value || !/^\d+$/.test(value)) return null;
  const id = Number(value);
  return Number.isSafeInteger(id) && id > 0 ? id : null;
}

export function companionSeconds(params: URLSearchParams) {
  const value = params.get('t');
  const seconds = value?.trim() ? Number(value) : Number.NaN;
  return Number.isFinite(seconds) && seconds >= 0 ? seconds : null;
}

export function companionReturnHref(projectId: number, conversationId?: string) {
  return learningUrl('/xiaoyu', projectId, conversationId);
}
