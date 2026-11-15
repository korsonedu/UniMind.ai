import en from '../src/i18n/en';

let language: 'zh-CN' | 'en' = 'zh-CN';
export const getNativeLanguage = () => language;
export function setNativeLanguage(value: string) {
  language = value.toLowerCase().startsWith('zh') ? 'zh-CN' : 'en';
}
export function nt(source: string, values: Record<string, string | number> = {}): string {
  const message = language === 'en' && Object.hasOwn(en, source) ? en[source] : source;
  return message.replace(/\{(\w+)\}/g, (match, key: string) => String(values[key] ?? match));
}
