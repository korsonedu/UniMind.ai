import { create } from 'zustand';
import api from '@/lib/api';

interface InstitutionInfo {
  id: number;
  name: string;
  slug: string;
  plan: 'free' | 'solo' | 'plus' | 'pro';
  plan_label: string;
  plan_expires_at: string | null;
  is_active: boolean;
  is_plan_active: boolean;
  max_students: number;
  student_count: number;
  invite_code: string;
  invite_slug: string;
}

interface UsageInfo {
  used: number;
  limit: number | null;
}

interface InstitutionState {
  isPlatformAdmin: boolean;
  institution: InstitutionInfo | null;
  features: string[];
  usage: UsageInfo | null;
  loading: boolean;

  // Preview mode: platform admin previews another institution's perspective
  previewMode: boolean;
  previewInstitution: InstitutionInfo | null;
  enterPreview: (institutionId: number) => Promise<void>;
  exitPreview: () => Promise<void>;

  fetchFeatures: () => Promise<void>;
  hasFeature: (feature: string) => boolean;
  clear: () => void;
}

export const useInstitutionStore = create<InstitutionState>((set, get) => ({
  isPlatformAdmin: false,
  institution: null,
  features: [],
  usage: null,
  loading: false,
  previewMode: false,
  previewInstitution: null,

  fetchFeatures: async () => {
    const state = get();
    if (state.previewMode) return; // preview mode takes precedence
    const isInitial = state.features.length === 0 && !state.isPlatformAdmin;
    if (isInitial) {
      set({ loading: true });
    }
    try {
      const { data } = await api.get('/users/institution/me/features/');
      set({
        isPlatformAdmin: data.is_platform_admin,
        institution: data.institution,
        features: data.features || [],
        usage: data.usage || null,
        loading: false,
      });
    } catch {
      if (isInitial) {
        set({ loading: false, features: [] });
      }
    }
  },

  enterPreview: async (institutionId: number) => {
    try {
      const { data } = await api.get(`/users/institutions/${institutionId}/preview/`);
      set({
        previewMode: true,
        previewInstitution: data.institution,
        isPlatformAdmin: false,
        institution: data.institution,
        features: data.features,
        usage: data.usage || null,
        loading: false,
      });
    } catch { /* silently fail */ }
  },

  exitPreview: async () => {
    set({ previewMode: false, previewInstitution: null, loading: true });
    // Re-fetch real features
    try {
      const { data } = await api.get('/users/institution/me/features/');
      set({
        isPlatformAdmin: data.is_platform_admin,
        institution: data.institution,
        features: data.features || [],
        usage: data.usage || null,
        loading: false,
      });
    } catch {
      set({ loading: false, features: [] });
    }
  },

  hasFeature: (feature: string) => {
    const { isPlatformAdmin, institution, features } = get();
    // Platform admin without institution → all features unlocked
    if (isPlatformAdmin && !institution) return true;
    // Otherwise check against institution plan features
    return features.includes(feature);
  },

  clear: () => set({
    isPlatformAdmin: false,
    institution: null,
    features: [],
    loading: false,
    previewMode: false,
    previewInstitution: null,
  }),
}));

// Feature flag constants matching backend PLAN_FEATURES
export const FEATURES = {
  AI_GENERATE: 'ai.generate',
  QUIZ_MANUAL: 'quiz.manual',
  QUIZ_EXAM: 'quiz.exam',
  MEMORIX_REVIEW: 'memorix.review',
  WRONG_REVIEW: 'wrong.review',
  BASIC_STATS: 'basic.stats',
  FULL_REPORT: 'full.report',
  COURSE_VIDEO: 'course.video',
  VIDEO_OUTLINE: 'video.outline',
  KNOWLEDGE_GRAPH: 'knowledge.graph',
  FAQ_SYSTEM: 'faq.system',
  MULTI_TEACHER: 'multi.teacher',
  CLASS_COMPARE: 'class.compare',
  DATA_EXPORT: 'data.export',
  STUDY_ROOM: 'study.room',
  AI_ASSISTANT: 'ai.assistant',
  PDF_MOCK: 'pdf.mock',
  BRAND_CUSTOM: 'brand.custom',
  API_ACCESS: 'api.access',
  STUDENT_PAYMENT: 'student.payment',
  PRIVATE_DEPLOY: 'private.deploy',
  I18N_CUSTOM: 'i18n.custom',
  SSO_SAML: 'sso.saml',
  AUDIT_LOG: 'audit.log',
  DEDICATED_SUPPORT: 'dedicated.support',
  SLA_99_9: 'sla.99.9',
} as const;
