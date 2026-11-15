import { useSyncExternalStore } from 'react';
import en from './en';

export type Locale = 'zh-CN' | 'en';
const STORAGE_KEY = 'unimind-language';
const listeners = new Set<() => void>();

function initialLocale(): Locale {
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved === 'zh-CN' || saved === 'en') return saved;
  } catch { /* Language switching also works without browser storage. */ }
  return navigator.language.toLowerCase().startsWith('zh') ? 'zh-CN' : 'en';
}

let locale = initialLocale();
export const getLocale = () => locale;

function applyLocale(value: Locale) {
  locale = value;
  document.documentElement.lang = value;
  void window.unimindDesktop?.updatePreferences({ language: value }).catch(() => { /* Older clients keep their native language. */ });
  listeners.forEach(listener => listener());
}

export function setLocale(value: Locale) {
  try { localStorage.setItem(STORAGE_KEY, value); } catch { /* Keep the in-memory preference. */ }
  applyLocale(value);
}

applyLocale(locale);
window.addEventListener('storage', event => {
  if (event.key === STORAGE_KEY) applyLocale(initialLocale());
});

export function useLocale() {
  return useSyncExternalStore(listener => {
    listeners.add(listener);
    return () => { listeners.delete(listener); };
  }, getLocale);
}

// Chinese source strings remain the fallback while screens are migrated.
export function t(source = '', values: Record<string, string | number | null | undefined> = {}): string {
  const translated = Object.hasOwn(en, source) ? en[source]
    : Object.hasOwn(en, source.trim()) ? source.replace(source.trim(), en[source.trim()]) : source;
  const message = locale === 'en' ? translated ?? source : source;
  return message.replace(/\{(\w+)\}/g, (match, key: string) => String(values[key] ?? match));
}
