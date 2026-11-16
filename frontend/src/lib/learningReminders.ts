import { spaceStorageKey } from '@/lib/activeWorkspace';
import { toast } from 'sonner';

const SETTINGS_KEY = spaceStorageKey('learning-reminder-settings');

export interface LearningReminderSettings {
  questionType: boolean;
  testResult: boolean;
}

const DEFAULT_SETTINGS: LearningReminderSettings = {
  questionType: true,
  testResult: true,
};

const readSettings = (): LearningReminderSettings => {
  if (typeof window === 'undefined') return DEFAULT_SETTINGS;
  try {
    const raw = window.localStorage.getItem(SETTINGS_KEY);
    if (!raw) return DEFAULT_SETTINGS;
    const parsed = JSON.parse(raw) as Partial<LearningReminderSettings>;
    return {
      questionType: parsed.questionType ?? true,
      testResult: parsed.testResult ?? true,
    };
  } catch {
    return DEFAULT_SETTINGS;
  }
};

const writeSettings = (settings: LearningReminderSettings) => {
  if (typeof window === 'undefined') return;
  window.localStorage.setItem(SETTINGS_KEY, JSON.stringify(settings));
};

export const getLearningReminderSettings = () => readSettings();

export const updateLearningReminderSetting = (
  key: keyof LearningReminderSettings,
  enabled: boolean
) => {
  const next = { ...readSettings(), [key]: enabled };
  writeSettings(next);
  return next;
};

export const isLearningReminderEnabled = (key: keyof LearningReminderSettings) => {
  return readSettings()[key];
};

const ensureNotificationPermission = async () => {
  if (typeof window === 'undefined' || !('Notification' in window)) return false;
  if (Notification.permission === 'granted') return true;
  if (Notification.permission === 'denied') return false;
  try {
    const permission = await Notification.requestPermission();
    return permission === 'granted';
  } catch {
    return false;
  }
};

export const sendLearningReminder = async (title: string, body: string) => {
  toast.info(body, { duration: 2800 });

  if (typeof navigator !== 'undefined' && typeof navigator.vibrate === 'function') {
    navigator.vibrate([140, 100, 140]);
  }

  const granted = await ensureNotificationPermission();
  if (!granted || typeof window === 'undefined' || !('Notification' in window)) return;

  new Notification(title, {
    body,
    icon: '/Unimind_logo.png',
  });
};
