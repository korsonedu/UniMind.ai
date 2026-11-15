import { getLocale, setLocale, t, useLocale, type Locale } from '@/i18n';
import { saveLanguagePreference } from '@/lib/languagePreference';
import { useAuthStore } from '@/store/useAuthStore';
import { toast } from 'sonner';

export function LanguageSelect() {
  useLocale();
  const change = (language: Locale) => {
    setLocale(language);
    const user = useAuthStore.getState().user;
    if (!user || user.preferred_language === undefined) return;
    void saveLanguagePreference(language, user.id).catch(() => toast.error(t('语言已在本机切换，账号同步失败。请联网后重新选择。')));
  };
  return <label className="inline-flex items-center gap-2 text-sm">
    <span>{t('语言')}</span>
    <select aria-label={t('语言')} value={getLocale()} onChange={event => change(event.target.value as Locale)}
      className="rounded-md border border-input bg-background px-2 py-1 text-foreground">
      <option value="zh-CN">简体中文</option>
      <option value="en">English</option>
    </select>
  </label>;
}
