import { create } from 'zustand';
import { persist } from 'zustand/middleware';

export type ThemeMode = 'light' | 'dark' | 'system';

export interface ExperiencePreferences {
  readingSize: 'standard' | 'large' | 'larger';
  density: 'standard' | 'compact';
  reduceMotion: boolean;
  sendShortcut: 'enter' | 'modifier-enter';
  toolDetails: 'auto' | 'expanded';
  practiceCount: 'recommended' | '5' | '10' | '20';
  practicePreference: 'balanced' | 'new_first' | 'review_first';
  videoSpeed: 1 | 1.25 | 1.5 | 2;
  videoSubtitles: boolean;
  courseAssistantMode: 'floating' | 'sidebar';
}

export const DEFAULT_EXPERIENCE: ExperiencePreferences = {
  readingSize: 'standard', density: 'standard', reduceMotion: false,
  sendShortcut: 'enter', toolDetails: 'auto',
  practiceCount: 'recommended', practicePreference: 'balanced', videoSpeed: 1, videoSubtitles: false,
  courseAssistantMode: 'floating',
};

interface SystemState extends ExperiencePreferences {
  theme: ThemeMode;
  primaryColor: string;
  pageTitle: string;
  pageSubtitle: string;
  setTheme: (theme: ThemeMode) => void;
  setPrimaryColor: (color: string) => void;
  setPageHeader: (title: string, subtitle: string) => void;
  setExperience: (preferences: Partial<ExperiencePreferences>) => void;
}

const STORAGE_KEY = 'system-storage';

const applyThemeClass = (theme: ThemeMode) => {
  if (typeof document === 'undefined') return;
  const dark = theme === 'dark' || (theme === 'system' && window.matchMedia('(prefers-color-scheme: dark)').matches);
  document.documentElement.classList.toggle('dark', dark);
  document.documentElement.style.colorScheme = dark ? 'dark' : 'light';
};

const applyPrimaryColorVar = (color: string) => {
  if (typeof document === 'undefined') return;
  document.documentElement.style.setProperty('--primary-override', color || '#4f5fa6');
};

const applyExperience = (preferences: ExperiencePreferences) => {
  if (typeof document === 'undefined') return;
  const root = document.documentElement;
  root.dataset.readingSize = preferences.readingSize;
  root.dataset.density = preferences.density;
  root.dataset.reduceMotion = String(preferences.reduceMotion || window.matchMedia('(prefers-reduced-motion: reduce)').matches);
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
  applyThemeClass(persisted?.theme ?? 'system');
  applyPrimaryColorVar(color);
  applyExperience({ ...DEFAULT_EXPERIENCE, ...persisted });
  window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => {
    if (useSystemStore.getState().theme === 'system') applyThemeClass('system');
  });
  window.matchMedia('(prefers-reduced-motion: reduce)').addEventListener('change', () => {
    applyExperience(useSystemStore.getState());
  });
};

const readLegacyPracticePreference = (): ExperiencePreferences['practicePreference'] => {
  try {
    const value = window.localStorage.getItem('quiz_preference');
    return value === 'new_first' || value === 'review_first' ? value : 'balanced';
  } catch { return 'balanced'; }
};

export const useSystemStore = create<SystemState>()(
  persist(
    (set, get) => ({
      ...DEFAULT_EXPERIENCE,
      practicePreference: readLegacyPracticePreference(),
      theme: 'system',
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
      setExperience: (preferences) => {
        applyExperience({ ...get(), ...preferences });
        set(preferences);
      },
    }),
    {
      name: STORAGE_KEY,
      onRehydrateStorage: () => (state) => {
        if (!state) return;
        applyThemeClass(state.theme);
        applyPrimaryColorVar(state.primaryColor);
        applyExperience(state);
      },
    }
  )
);
