export interface AIAddonProduct {
  id: number;
  name: string;
  description: string;
  price_cents: number;
  ai_calls: number;
  validity_days: number;
  is_active: boolean;
  configured: boolean;
  sort_order: number;
}

export interface AIUsage {
  used: number;
  limit: number | null;
  remaining: number | null;
  base_remaining: number | null;
  addon_remaining: number;
  resets_at: string;
  configured: boolean;
  unlimited: boolean;
}

export interface LearningAccess {
  is_course_student: boolean;
  ai_usage: AIUsage;
  addons: { id: number; name: string; ai_calls: number; used_calls: number; expires_at: string }[];
}

export interface LearningCatalog {
  experience_weekly_calls: number | null;
  course_weekly_calls: number | null;
  payment_methods: string[];
  products: AIAddonProduct[];
}

export const learningPrice = (cents: number) => new Intl.NumberFormat('zh-CN', { style: 'currency', currency: 'CNY' }).format(cents / 100);
export const learningDate = (value: string) => new Intl.DateTimeFormat('zh-CN', { timeZone: 'Asia/Shanghai', dateStyle: 'medium' }).format(new Date(value));
export const learningReset = (value: string) => new Intl.DateTimeFormat('zh-CN', { timeZone: 'Asia/Shanghai', dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value));
