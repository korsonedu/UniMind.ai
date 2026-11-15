import { setLocale, t, useLocale, type Locale } from '@/i18n';
import { saveLanguagePreference } from '@/lib/languagePreference';
import { useAuthStore } from '@/store/useAuthStore';
import { toast } from 'sonner';

export function LanguageSelect() {
  const locale = useLocale();
  const next = locale === 'en' ? 'zh-CN' : 'en';
  const label = t('切换语言：{0}', { 0: next === 'en' ? 'English' : '简体中文' });
  const change = (language: Locale) => {
    setLocale(language);
    const user = useAuthStore.getState().user;
    if (!user || user.preferred_language === undefined) return;
    void saveLanguagePreference(language, user.id).catch(() => toast.error(t('语言已在本机切换，账号同步失败。请联网后重新选择。')));
  };
  return <button type="button" aria-label={label} title={label} onClick={() => change(next)}
    className="inline-flex min-w-10 items-center justify-center rounded-md border border-input bg-background px-2 py-1 text-sm font-medium text-foreground hover:bg-accent focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring">
    {next === 'en' ? 'EN' : '中文'}
  </button>;
}
