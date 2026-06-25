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
};
