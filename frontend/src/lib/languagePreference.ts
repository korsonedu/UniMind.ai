import { getLocale, type Locale } from '@/i18n';
import api from '@/lib/api';
import { useAuthStore } from '@/store/useAuthStore';

let pending = Promise.resolve();

export function saveLanguagePreference(language: Locale, userId: number) {
  pending = pending.catch(() => {}).then(async () => {
    if (useAuthStore.getState().user?.id !== userId || getLocale() !== language) return;
    await api.patch('/users/me/update/', { preferred_language: language });
    if (useAuthStore.getState().user?.id === userId && getLocale() === language) useAuthStore.getState().updateUser({ preferred_language: language });
  });
  return pending;
}
