import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';
import LanguageDetector from 'i18next-browser-languagedetector';

// ── 中文 ──
import zhCommon from '@/locales/zh/common.json';
import zhLanding from '@/locales/zh/landing.json';
import zhLayout from '@/locales/zh/layout.json';
import zhSettings from '@/locales/zh/settings.json';
import zhDashboard from '@/locales/zh/dashboard.json';
import zhPages from '@/locales/zh/pages.json';

// ── 英文 ──
import enCommon from '@/locales/en/common.json';
import enLanding from '@/locales/en/landing.json';
import enLayout from '@/locales/en/layout.json';
import enSettings from '@/locales/en/settings.json';
import enDashboard from '@/locales/en/dashboard.json';
import enPages from '@/locales/en/pages.json';

i18n
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    resources: {
      zh: { common: zhCommon, landing: zhLanding, layout: zhLayout, settings: zhSettings, dashboard: zhDashboard, pages: zhPages },
      en: { common: enCommon, landing: enLanding, layout: enLayout, settings: enSettings, dashboard: enDashboard, pages: enPages },
    },
    fallbackLng: 'zh',
    defaultNS: 'common',
    interpolation: { escapeValue: false },
    detection: {
      order: ['querystring', 'localStorage', 'navigator'],
      caches: ['localStorage'],
      lookupQuerystring: 'lang',
    },
  });

export default i18n;
