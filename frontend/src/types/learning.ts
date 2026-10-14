export interface LearningProduct {
  id: number;
  name: string;
  description: string;
  price_cents: number;
  duration_days: number;
  monthly_ai_calls: number;
  modules: number[];
  module_names: string[];
  is_active: boolean;
  sort_order: number;
}

export interface LearningGrant {
  id: number;
  email: string;
  product: number;
  snapshot: { name: string; duration_days: number; monthly_ai_calls: number; modules: number[] };
  source: 'payment' | 'course' | 'admin';
  starts_at: string;
  expires_at: string;
  revoked: boolean;
}

export interface LearningCatalog {
  free_ai_calls: number;
  payment_methods: string[];
  products: LearningProduct[];
}

export const learningPrice = (cents: number) => new Intl.NumberFormat('zh-CN', { style: 'currency', currency: 'CNY' }).format(cents / 100);
export const learningDate = (value: string) => new Intl.DateTimeFormat('zh-CN', { timeZone: 'Asia/Shanghai', dateStyle: 'medium' }).format(new Date(value));
