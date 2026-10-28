import { create } from 'zustand';
import { persist } from 'zustand/middleware';

type ThemeMode = 'light' | 'dark';

interface SystemState {
  theme: ThemeMode;
  primaryColor: string;
  pageTitle: string;
  pageSubtitle: string;
  setTheme: (theme: ThemeMode) => void;
  setPrimaryColor: (color: string) => void;
  setPageHeader: (title: string, subtitle: string) => void;
}

const STORAGE_KEY = 'system-storage';

const applyThemeClass = (theme: ThemeMode) => {
  if (typeof document === 'undefined') return;
  document.documentElement.classList.toggle('dark', theme === 'dark');
};

const applyPrimaryColorVar = (color: string) => {
  if (typeof document === 'undefined') return;
  document.documentElement.style.setProperty('--primary-override', color || '#4f5fa6');
};

const readPersistedSystemState = (): Partial<SystemState> | null => {
  if (typeof window === 'undefined') return null;
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (parsed && typeof parsed === 'object' && parsed.state && typeof parsed.state === 'object') {
      return parsed.state as Partial<SystemState>;
    }
    return parsed as Partial<SystemState>;
  } catch {
    return null;
  }
};

export const initializeSystemAppearance = () => {
  const persisted = readPersistedSystemState();
  const color = typeof persisted?.primaryColor === 'string' ? persisted.primaryColor : '#4f5fa6';
  applyThemeClass(persisted?.theme === 'dark' ? 'dark' : 'light');
  applyPrimaryColorVar(color);
};

export const useSystemStore = create<SystemState>()(
  persist(
    (set) => ({
      theme: 'light',
      primaryColor: '#4f5fa6',
      pageTitle: '',
      pageSubtitle: '',
      setTheme: (theme) => {
        applyThemeClass(theme);
        set({ theme });
      },
      setPrimaryColor: (color) => {
        applyPrimaryColorVar(color);
        set({ primaryColor: color });
      },
      setPageHeader: (title, subtitle) => set({ pageTitle: title, pageSubtitle: subtitle }),
    }),
    {
      name: STORAGE_KEY,
      onRehydrateStorage: () => (state) => {
        if (!state) return;
        applyThemeClass(state.theme === 'dark' ? 'dark' : 'light');
        applyPrimaryColorVar(state.primaryColor);
      },
    }
  )
);
