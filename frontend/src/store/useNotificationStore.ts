import { create } from 'zustand';
import api from '@/lib/api';

interface Notification {
  id: number;
  ntype: string;
  title: string;
  content: string;
  link?: string;
  is_read: boolean;
  created_at: string;
}

interface NotificationState {
  notifications: Notification[];
  unreadCount: number;
  fetchNotifications: () => Promise<void>;
  fetchUnreadCount: () => Promise<void>;
  markAsRead: (id?: number) => Promise<void>;
  clearAll: () => Promise<void>;
}

export const useNotificationStore = create<NotificationState>((set, get) => ({
  notifications: [],
  unreadCount: 0,
  fetchNotifications: async () => {
    try {
      const res = await api.get('/notifications/');
      set({ notifications: res.data });
    } catch (e) { console.error('fetchNotifications failed', e); }
  },
  fetchUnreadCount: async () => {
    try {
      const res = await api.get('/notifications/unread-count/');
      set({ unreadCount: res.data.unread_count });
    } catch (e) { console.error('fetchUnreadCount failed', e); }
  },
  markAsRead: async (id) => {
    try {
      const url = id ? `/notifications/read/${id}/` : '/notifications/read/';
      await api.post(url);
      get().fetchUnreadCount();
      set({
        notifications: get().notifications.map(n =>
          (id ? n.id === id : true) ? { ...n, is_read: true } : n
        )
      });
    } catch (e) { console.error('markAsRead failed', e); }
  },
  clearAll: async () => {
    try {
      await api.delete('/notifications/clear/');
      set({ notifications: [], unreadCount: 0 });
    } catch (e) { console.error('clearAll failed', e); }
  },
}));
