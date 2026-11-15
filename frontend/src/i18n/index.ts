import { useSyncExternalStore } from 'react';
import en from './en';

export type Locale = 'zh-CN' | 'en';
const STORAGE_KEY = 'unimind-language';
const listeners = new Set<() => void>();
const metadata = [...document.querySelectorAll<HTMLMetaElement>('meta[name="description"], meta[name="keywords"], meta[property="og:title"], meta[property="og:description"], meta[name="twitter:title"], meta[name="twitter:description"]')].map(element => ({ element, source: element.content }));
const structuredData = [...document.querySelectorAll<HTMLScriptElement>('script[type="application/ld+json"]')].map(element => ({ element, source: JSON.parse(element.textContent || '{}') }));

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
  try { document.cookie = `${STORAGE_KEY}=${value}; Path=/; Max-Age=31536000; SameSite=Lax${location.protocol === 'https:' ? '; Secure' : ''}`; } catch { /* Cookie access may be restricted. */ }
  document.documentElement.lang = value;
  document.title = t('UniMind.ai 智能学习平台');
  metadata.forEach(({ element, source }) => { element.content = t(source); });
  structuredData.forEach(({ element, source }) => { element.textContent = JSON.stringify({ ...source, description: t(source.description), ...(source.inLanguage ? { inLanguage: value } : {}), ...(source.offers ? { offers: { ...source.offers, description: t(source.offers.description) } } : {}) }); });
  document.querySelector('meta[property="og:locale"]')?.setAttribute('content', value === 'en' ? 'en_US' : 'zh_CN');
  const manifest = document.querySelector<HTMLLinkElement>('link[rel="manifest"]');
  if (manifest) manifest.href = value === 'en' ? '/manifest-en.webmanifest' : '/manifest.webmanifest';
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
