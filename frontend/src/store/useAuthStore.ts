import { setActiveWorkspace, spaceStorageKey } from '@/lib/activeWorkspace';
import { setLocale, t, type Locale } from '@/i18n';
import { toast } from 'sonner';
import { create } from 'zustand';
import { Preferences } from '@capacitor/preferences';
import { useDesktopStore } from '@/lib/desktop';
import { clearConversationRecovery } from '@/lib/conversationRecovery';
import { persist } from 'zustand/middleware';
import { useInstitutionStore } from './useInstitutionStore';
import { useExamActivityStore } from './useExamActivityStore';
import { useChatUnreadStore } from './useChatUnreadStore';
import { resetOfflineCache } from '@/lib/offlineData';
import { isNativePlatform, registerAuthTokenAccessor } from '@/lib/serverConfig';

import { DEMO_USER, isOfflineDemo, setOfflineDemo } from '@/lib/offlineSession';
const DEMO_KEY = 'unimind_offline_demo';
const localizedDemoUser = () => ({ ...DEMO_USER, nickname: t(DEMO_USER.nickname), bio: t(DEMO_USER.bio) });
let realUserBeforeDemo: User | null = null;
const NATIVE_TOKEN_KEY = 'unimind_native_auth_token';
let authEpoch = 0;

let nativeTokenWrite: Promise<void> = Promise.resolve();
export function flushNativeToken(): Promise<void> { return nativeTokenWrite; }
function syncNativeToken(token: string | null): void {
  if (!isNativePlatform()) return;
  nativeTokenWrite = nativeTokenWrite.catch(() => {}).then(() => token
    ? Preferences.set({ key: NATIVE_TOKEN_KEY, value: token })
    : Preferences.remove({ key: NATIVE_TOKEN_KEY }));
  void nativeTokenWrite.catch(() => { toast.error(t('无法保存登录状态，重启后请重新登录')); });
}

interface User {
  id: number;
  account_id?: number;
  workspace_id?: number | null;
  username: string;
  email?: string;
  nickname: string;
  role: 'student' | 'admin';
  elo_score: number;
  avatar_url: string;
  avatar_style: string;
  avatar_seed: string;
  bio: string;
  preferred_language?: Locale | '';
  allow_broadcast: boolean;
  show_others_broadcast: boolean;
  is_member: boolean;
  membership_tier?: string;
  personal_plan?: string;
  membership_expires_at?: string;
  membership_source?: string;
  has_completed_initial_assessment: boolean;
  current_task?: string;
  current_timer_end?: string;
  today_focused_minutes?: number;
  today_completed_tasks?: unknown[];
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
  is_institution_teacher?: boolean;
  tour_dismissed_at?: string | null;
  tour_panel_dismissed_at?: string | null;
}

let languageUserId: number | null = null;

interface AuthState {
  user: User | null;
  token: string | null;
  tokenHydrated: boolean;
  demoActive: boolean;
  enterDemo: () => Promise<void>;
  exitDemo: () => Promise<void>;
  setAuth: (user: User, token?: string | null) => void;
  logout: (options?: { preserveDesktop?: boolean }) => void;
  updateUser: (user: Partial<User>) => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      demoActive: false,
      enterDemo: async () => {
        if (!isNativePlatform()) return;
        authEpoch += 1;
        await Preferences.set({ key: DEMO_KEY, value: 'true' });
        if (!get().demoActive) realUserBeforeDemo = get().user;
        setOfflineDemo(true);
        resetOfflineCache();
        set({ user: localizedDemoUser(), token: null, demoActive: true, tokenHydrated: true });
        useInstitutionStore.setState({ features: ['ai.assistant','quiz.exam','knowledge.graph','full.report'], loading: false, featuresError: false });
      },
      exitDemo: async () => {
        authEpoch += 1;
        await Preferences.remove({ key: DEMO_KEY });
        setOfflineDemo(false);
        set({ user: null, token: null, demoActive: false });
        useInstitutionStore.getState().clear();
        resetOfflineCache();
      },
      user: null,
      token: null,
      tokenHydrated: !isNativePlatform(),
      setAuth: (user, token) => {
        if (isOfflineDemo()) { setOfflineDemo(false); void Preferences.remove({ key: DEMO_KEY }); }
        const previousId = get().user?.id;
        if (languageUserId !== user.id) {
          languageUserId = user.id;
          if (user.preferred_language === 'en' || user.preferred_language === 'zh-CN') setLocale(user.preferred_language);
        }
        const nextToken = token === undefined ? get().token : (token || null);
        if (token !== undefined) {
          authEpoch += 1;
          syncNativeToken(nextToken);
        }
        set({ user, token: nextToken, tokenHydrated: true, demoActive: false });
        if (previousId !== user.id) {
          useChatUnreadStore.getState().reset();
          resetOfflineCache();
        }
      },
      logout: (options) => {
        setActiveWorkspace(null);
        languageUserId = null;
        if (isOfflineDemo()) { void get().exitDemo(); return; }
        authEpoch += 1;
        syncNativeToken(null);
        useDesktopStore.setState({ state: null, error: null });
        if (!options?.preserveDesktop) {
          const userId = get().user?.id;
          if (userId) clearConversationRecovery(userId);
          void window.unimindDesktop?.logout().catch(() => {});
        }
        set({ user: null, token: null, tokenHydrated: true });
        useInstitutionStore.getState().clear();
        useExamActivityStore.getState().clear();
        useChatUnreadStore.getState().reset();
        resetOfflineCache();
      },
      updateUser: (updatedUser) => set((state) => ({
        user: state.user ? { ...state.user, ...updatedUser } : null
      })),
    }),
    {
      name: spaceStorageKey('auth-storage'),
      partialize: (state) => ({ user: state.demoActive ? realUserBeforeDemo : state.user }),
    }
  )
);

let nativeHydrationPromise: Promise<void> | null = null;

/**
 * Hydrates the native Capacitor token stored in SharedPreferences into memory
 * without ever writing tokens to web localStorage.
 */
export function hydrateNativeAuth(): Promise<void> {
  if (!isNativePlatform()) {
    if (!useAuthStore.getState().tokenHydrated) {
      useAuthStore.setState({ tokenHydrated: true });
    }
    return Promise.resolve();
  }
  if (!nativeHydrationPromise) {
    const startEpoch = authEpoch;
    nativeHydrationPromise = Promise.all([Preferences.get({ key: NATIVE_TOKEN_KEY }), Preferences.get({ key: DEMO_KEY })])
      .then(([{ value }, demo]) => {
        if (startEpoch !== authEpoch) {
          useAuthStore.setState({ tokenHydrated: true });
          return;
        }
        if (demo.value === 'true') {
          realUserBeforeDemo = useAuthStore.getState().user;
          setOfflineDemo(true);
          useAuthStore.setState({ user: localizedDemoUser(), token: null, demoActive: true, tokenHydrated: true });
          return;
        }
        useAuthStore.setState((state) => ({
          token: state.token ?? (value || null),
          tokenHydrated: true,
        }));
      })
      .catch(() => {
        useAuthStore.setState({ user: null, token: null, tokenHydrated: true });
        toast.error(t('无法读取已保存的登录状态，请重新登录'));
      });
  }
  return nativeHydrationPromise;
}

registerAuthTokenAccessor(() => useAuthStore.getState().token);
void hydrateNativeAuth();

// Clear in-memory state when 401 interceptor fires
window.addEventListener('auth:logout', () => {
  if (!isOfflineDemo()) useAuthStore.getState().logout({ preserveDesktop: true });
});
