import { create } from 'zustand';
import api, { setPreviewInstitutionId, setCampusContextId } from '@/lib/api';

interface InstitutionInfo {
  id: number;
  name: string;
  slug: string;
  plan: 'free' | 'starter' | 'growth' | 'enterprise';
  plan_label: string;
  plan_expires_at: string | null;
  is_active: boolean;
  is_plan_active: boolean;
  max_students: number;
  student_count: number;
  invite_slug: string;
  business_type: string;
}

export interface QuotaItem {
  used: number;
  limit: number | null; // null = 无限制
  pct: number;          // 0-100
  status: 'normal' | 'warning' | 'exhausted';
}

export interface UsageInfo {
  course: QuotaItem;
  question: QuotaItem;
  knowledge_point: QuotaItem;
  article: QuotaItem;
  ai_question: QuotaItem;
  ai_call_total: QuotaItem;
  pdf_export: QuotaItem;
  interview: QuotaItem;
  custom_bot: QuotaItem;
  // backward compat
  used: number;
  limit: number | null;
}

export const QUOTA_LABELS: Record<string, string> = {
  course: '课程数',
  question: '题目总数',
  knowledge_point: '知识图谱节点',
  article: '文章数',
  ai_question: 'AI 出题次数',
  ai_call_total: 'AI 调用总次数',
  pdf_export: '模拟考试 PDF',
  interview: '面试场次',
  custom_bot: '自定义机器人数',
};

export function quotaStatus(resource: QuotaItem): 'normal' | 'warning' | 'exhausted' {
  if (resource.limit === null) return 'normal';
  if (resource.used >= resource.limit) return 'exhausted';
  if (resource.pct >= 80) return 'warning';
  return 'normal';
}

export function quotaLabel(key: string): string {
  return QUOTA_LABELS[key] || key;
}

export interface CampusInfo {
  id: number;
  name: string;
  slug: string;
  plan: string;
  inherit_plan: boolean;
  is_active: boolean;
  student_count: number;
  staff_count: number;
}

interface InstitutionState {
  isPlatformAdmin: boolean;
  institution: InstitutionInfo | null;
  features: string[];
  usage: UsageInfo | null;
  loading: boolean;
  featuresError: boolean;

  // Preview mode: platform admin previews another institution's perspective
  previewMode: boolean;
  previewInstitution: InstitutionInfo | null;
  enterPreview: (institutionId: number) => Promise<void>;
  exitPreview: () => Promise<void>;

  // Campus / sub-institution
  currentCampusId: number | null;
  children: CampusInfo[];
  fetchChildren: () => Promise<void>;
  switchCampus: (campusId: number | null) => Promise<void>;

  // Class selector
  currentClassId: number | null;
  setCurrentClassId: (id: number | null) => void;

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
  featuresError: false,
  previewMode: false,
  previewInstitution: null,

  // Campus / sub-institution
  currentCampusId: null,
  children: [],
  fetchChildren: async () => {
    try {
      const { data } = await api.get('/users/institution/me/children/');
      set({ children: Array.isArray(data) ? data : [] });
    } catch {
      set({ children: [] });
    }
  },
  switchCampus: async (campusId: number | null) => {
    setCampusContextId(campusId);
    set({ currentCampusId: campusId });
    // Re-fetch features to reflect the new campus context
    if (campusId !== null) {
      get().fetchFeatures();
    }
  },

  // Class selector
  currentClassId: null,
  setCurrentClassId: (id: number | null) => set({ currentClassId: id }),

  fetchFeatures: async () => {
    const state = get();
    if (state.previewMode) return;
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
        featuresError: false,
      });
    } catch {
      console.error('Fetch institution features failed');
      if (isInitial) {
        set({ loading: false, features: [], featuresError: true });
      }
    }
  },

  enterPreview: async (institutionId: number) => {
    try {
      const { data } = await api.get(`/users/institutions/${institutionId}/preview/`);
      setPreviewInstitutionId(institutionId);
      set({
        previewMode: true,
        previewInstitution: data.institution,
        isPlatformAdmin: false,
        institution: data.institution,
        features: data.features,
        usage: data.usage || null,
        loading: false,
      });
    } catch {
      console.error('Enter preview failed');
    }
  },

  exitPreview: async () => {
    setPreviewInstitutionId(null);
    set({ previewMode: false, previewInstitution: null, loading: true });
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
      console.error('Exit preview failed');
      set({ loading: false, features: [] });
    }
  },

  hasFeature: (feature: string) => {
    const { isPlatformAdmin, institution, features } = get();
    if (isPlatformAdmin && !institution) return true;
    return features.includes(feature);
  },

  clear: () => {
    setPreviewInstitutionId(null);
    setCampusContextId(null);
    set({
      isPlatformAdmin: false,
      institution: null,
      features: [],
      loading: false,
      previewMode: false,
      previewInstitution: null,
      currentCampusId: null,
      currentClassId: null,
      children: [],
    });
  },
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
  INTERVIEW_MOCK: 'interview.mock',
  AI_BOT_CUSTOM: 'ai.bot.custom',
  BRAND_CUSTOM: 'brand.custom',
  API_ACCESS: 'api.access',
  STUDENT_PAYMENT: 'student.payment',
  PRIVATE_DEPLOY: 'private.deploy',
  I18N_CUSTOM: 'i18n.custom',
  SSO_SAML: 'sso.saml',
  AUDIT_LOG: 'audit.log',
  DEDICATED_SUPPORT: 'dedicated.support',
  SLA_99_9: 'sla.99.9',
  TEACHING_PLANS: 'teaching_plans',
} as const;
