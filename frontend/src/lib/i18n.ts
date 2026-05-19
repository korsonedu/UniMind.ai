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
import zhAuth from '@/locales/zh/auth.json';
import zhNotifications from '@/locales/zh/notifications.json';
import zhElo from '@/locales/zh/elo.json';
import zhOnboarding from '@/locales/zh/onboarding.json';
import zhTestLadder from '@/locales/zh/testLadder.json';
import zhStudyRoom from '@/locales/zh/studyRoom.json';
import zhKnowledgeMap from '@/locales/zh/knowledgeMap.json';
import zhAiAssistant from '@/locales/zh/aiAssistant.json';
import zhQaSystem from '@/locales/zh/qaSystem.json';
import zhPdfMockExam from '@/locales/zh/pdfMockExam.json';
import zhInterviews from '@/locales/zh/interviews.json';
import zhVideoLesson from '@/locales/zh/videoLesson.json';
import zhTestSession from '@/locales/zh/testSession.json';
import zhMaintenance from '@/locales/zh/maintenance.json';

// ── 英文 ──
import enCommon from '@/locales/en/common.json';
import enLanding from '@/locales/en/landing.json';
import enLayout from '@/locales/en/layout.json';
import enSettings from '@/locales/en/settings.json';
import enDashboard from '@/locales/en/dashboard.json';
import enPages from '@/locales/en/pages.json';
import enAuth from '@/locales/en/auth.json';
import enNotifications from '@/locales/en/notifications.json';
import enElo from '@/locales/en/elo.json';
import enOnboarding from '@/locales/en/onboarding.json';
import enTestLadder from '@/locales/en/testLadder.json';
import enStudyRoom from '@/locales/en/studyRoom.json';
import enKnowledgeMap from '@/locales/en/knowledgeMap.json';
import enAiAssistant from '@/locales/en/aiAssistant.json';
import enQaSystem from '@/locales/en/qaSystem.json';
import enPdfMockExam from '@/locales/en/pdfMockExam.json';
import enInterviews from '@/locales/en/interviews.json';
import enVideoLesson from '@/locales/en/videoLesson.json';
import enTestSession from '@/locales/en/testSession.json';
import enMaintenance from '@/locales/en/maintenance.json';

i18n
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    resources: {
      zh: {
        common: zhCommon,
        landing: zhLanding,
        layout: zhLayout,
        settings: zhSettings,
        dashboard: zhDashboard,
        pages: zhPages,
        auth: zhAuth,
        notifications: zhNotifications,
        elo: zhElo,
        onboarding: zhOnboarding,
        testLadder: zhTestLadder,
        studyRoom: zhStudyRoom,
        knowledgeMap: zhKnowledgeMap,
        aiAssistant: zhAiAssistant,
        qaSystem: zhQaSystem,
        pdfMockExam: zhPdfMockExam,
        interviews: zhInterviews,
        videoLesson: zhVideoLesson,
        testSession: zhTestSession,
        maintenance: zhMaintenance,
      },
      en: {
        common: enCommon,
        landing: enLanding,
        layout: enLayout,
        settings: enSettings,
        dashboard: enDashboard,
        pages: enPages,
        auth: enAuth,
        notifications: enNotifications,
        elo: enElo,
        onboarding: enOnboarding,
        testLadder: enTestLadder,
        studyRoom: enStudyRoom,
        knowledgeMap: enKnowledgeMap,
        aiAssistant: enAiAssistant,
        qaSystem: enQaSystem,
        pdfMockExam: enPdfMockExam,
        interviews: enInterviews,
        videoLesson: enVideoLesson,
        testSession: enTestSession,
        maintenance: enMaintenance,
      },
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
