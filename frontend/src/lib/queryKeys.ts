export const queryKeys = {
  user: {
    me: ['users', 'me'] as const,
  },
  institution: {
    members: (instId: number) => ['institution', instId, 'members'] as const,
    features: ['institution', 'features'] as const,
  },
  notifications: {
    unreadCount: ['notifications', 'unread-count'] as const,
  },
  knowledgePoints: {
    subjects: ['knowledge-points', 'subjects'] as const,
  },
  courses: {
    list: (params: string) => ['courses', 'list', params] as const,
  },
  exams: {
    submission: (userId: number | undefined, id: string) => ['exams', 'submission', userId, id] as const,
    status: (id: number) => ['exams', 'status', id] as const,
    detail: (id: number) => ['exams', 'detail', id] as const,
    history: ['exams', 'history'] as const,
  },
  workbench: {
    sources: (projectId: number) => ['workbench', projectId, 'sources'] as const,
    courses: (projectId: number, search: string) => ['workbench', projectId, 'courses', search] as const,
    source: (projectId: number, sourceId: string, status?: string, updatedAt?: string) =>
      ['workbench', projectId, 'source', sourceId, status, updatedAt] as const,
    overview: (projectId: number, selection: string[][], generate: boolean) =>
      ['workbench', projectId, 'overview', selection, generate] as const,
  },
  knowledgeBuilder: {
    list: (userId: number | undefined) => ['knowledge-builder', 'list', userId] as const,
    detail: (buildId: string) => ['knowledge-builder', 'detail', buildId] as const,
    status: (buildId: string) => ['knowledge-builder', 'status', buildId] as const,
  },
};
