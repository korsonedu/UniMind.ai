import { create } from 'zustand';
import { persist } from 'zustand/middleware';

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
  membership_tier?: string;
  trial_ends_at?: string;
  membership_expires_at?: string;
  has_completed_initial_assessment: boolean;
  current_task?: string;
  current_timer_end?: string;
  today_focused_minutes?: number;
  today_completed_tasks?: any[];
  institution?: {
    id: number;
    name: string;
    slug: string;
    plan: string;
    plan_label: string;
    is_plan_active: boolean;
    max_students: number;
    student_count: number;
    invite_slug: string;
  } | null;
  institution_id?: number;
  institution_role?: string;
  is_admin?: boolean;
  is_institution_admin?: boolean;
  is_institution_owner?: boolean;
}

interface AuthState {
  user: User | null;
  token: string | null;
  setAuth: (user: User, token: string) => void;
  logout: () => void;
  updateUser: (user: Partial<User>) => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      user: null,
      token: null,
      setAuth: (user, token) => {
        set({ user, token });
      },
      logout: () => {
        set({ user: null, token: null });
      },
      updateUser: (updatedUser) => set((state) => ({
        user: state.user ? { ...state.user, ...updatedUser } : null
      })),
    }),
    {
      name: 'auth-storage',
      partialize: (state) => ({ token: state.token }),
    }
  )
);
