import { activeWorkspace } from './activeWorkspace';

export function isPersonalWorkspace() {
  return activeWorkspace() === 'personal';
}

export function personalWorkbenchProjectId(projectId: number | null) {
  return isPersonalWorkspace() ? projectId : null;
}
