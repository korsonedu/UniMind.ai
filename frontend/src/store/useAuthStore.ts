import { create } from 'zustand';

interface User {
  id: number;
  username: string;
  nickname: string;
  role: 'student' | 'admin';
  elo_score: number;
  avatar_url: string;
  avatar_style: string;
  avatar_seed: string;
  bio: string;
  allow_broadcast: boolean;
  show_others_broadcast: boolean;
  is_member: boolean;
  has_completed_initial_assessment: boolean;
  elo_reset_count: number;
  current_task?: string;
  current_timer_end?: string;
  today_focused_minutes?: number;
  today_completed_tasks?: any[];
  institution_id?: number;
  institution_role?: string;
  is_admin?: boolean;
  is_institution_admin?: boolean;
}

interface AuthState {
  user: User | null;
  token: string | null;
  setAuth: (user: User, token: string) => void;
  logout: () => void;
  updateUser: (user: Partial<User>) => void;
}

export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  token: localStorage.getItem('token'),
  setAuth: (user, token) => {
    localStorage.setItem('token', token);
    set({ user, token });
  },
  logout: () => {
    localStorage.removeItem('token');
    set({ user: null, token: null });
  },
  updateUser: (updatedUser) => set((state) => ({
    user: state.user ? { ...state.user, ...updatedUser } : null
  })),
}));
