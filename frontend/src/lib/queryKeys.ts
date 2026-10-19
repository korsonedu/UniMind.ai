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
    status: (id: number) => ['exams', 'status', id] as const,
    detail: (id: number) => ['exams', 'detail', id] as const,
    history: ['exams', 'history'] as const,
  },
};
