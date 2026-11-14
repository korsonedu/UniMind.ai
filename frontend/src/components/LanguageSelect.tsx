import { getLocale, setLocale, t, useLocale, type Locale } from '@/i18n';

export function LanguageSelect() {
  useLocale();
  return <label className="inline-flex items-center gap-2 text-sm">
    <span>{t('语言')}</span>
    <select aria-label={t('语言')} value={getLocale()} onChange={event => setLocale(event.target.value as Locale)}
      className="rounded-md border border-input bg-background px-2 py-1 text-foreground">
      <option value="zh-CN">简体中文</option>
      <option value="en">English</option>
    </select>
  </label>;
}
