import { useEffect, useState } from 'react';
import { Card } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { useTranslation } from 'react-i18next';
import { useAuthStore } from '@/store/useAuthStore';
import api from '@/lib/api';
import {
  Building2, Users, Calendar, Loader2,
  Check, Minus, GraduationCap, TrendingUp, Sparkles,
} from 'lucide-react';
import { cn } from '@/lib/utils';

interface DashboardData {
  mode?: string;
  institutions?: Array<{
    id: number; name: string; plan: string; plan_label: string;
    plan_expires_at: string | null; is_active: boolean; is_plan_active: boolean;
    max_students: number; student_count: number;
  }>;
  institution?: {
    id: number; name: string; plan: string; plan_label: string;
    plan_expires_at: string | null; is_active: boolean; is_plan_active: boolean;
    max_students: number; student_count: number; admin_count: number;
  };
  stats?: {
    weekly_active_students: number;
    ai_usage: { used: number; limit: number | null };
  };
  features: string[];
}

const PLAN_COLORS: Record<string, string> = {
  free: 'bg-[#AEAEB2]', solo: 'bg-[#0071E3]',
  plus: 'bg-[#34C759]', pro: 'bg-[#FF9500]',
};


export default function InstitutionDashboard() {
  const { t } = useTranslation('dashboard');
  const { user } = useAuthStore();
  const FEATURE_KEYS = [
    'quiz.manual', 'quiz.exam', 'wrong.review', 'basic.stats',
    'ai.generate', 'memorix.review', 'full.report', 'knowledge.graph',
    'ai.assistant', 'course.video', 'video.outline', 'faq.system',
    'pdf.mock', 'study.room', 'multi.teacher', 'class.compare',
    'data.export', 'brand.custom', 'api.access', 'student.payment',
    'private.deploy', 'i18n.custom', 'sso.saml', 'audit.log',
    'dedicated.support', 'sla.99.9',
  ];
  const [data, setData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.get('/users/institution/me/')
      .then(res => { setData(res.data); })
      .catch(() => { /* redirect handled by RequireAuth */ })
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="flex justify-center py-20">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (!data) {
    return (
      <div className="flex items-center justify-center h-64 text-sm text-muted-foreground">
        {t('noPermission')}
      </div>
    );
  }

  // Platform admin: show institution overview list
  if (data.mode === 'platform_admin' && data.institutions) {
    return (
      <div className="max-w-5xl mx-auto space-y-6">
        <div>
          <h1 className="text-2xl font-extrabold text-[#1D1D1F] tracking-tight">{t('overviewTitle')}</h1>
          <p className="text-sm text-[#8E8E93] mt-1">{t('totalInstitutions', { count: data.institutions.length })}</p>
        </div>

        <div className="space-y-3">
          {data.institutions.map((inst: any) => (
            <Card key={inst.id} variant="apple" className="p-4">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <div className="h-9 w-9 rounded-lg bg-[#0071E3]/8 flex items-center justify-center">
                    <Building2 className="h-4 w-4 text-[#0071E3]" />
                  </div>
                  <div>
                    <p className="text-sm font-extrabold text-[#1D1D1F]">{inst.name}
                      <Badge className={cn('ml-2 text-[10px] font-bold text-white', PLAN_COLORS[inst.plan] || 'bg-[#AEAEB2]')}>{inst.plan_label}</Badge>
                      {!inst.is_active && <Badge variant="outline" className="ml-1 text-[10px] text-red-500">{t('common:disabled')}</Badge>}
                    </p>
                    <p className="text-xs text-[#AEAEB2] mt-0.5">
                      <Users className="h-3 w-3 inline mr-1" />{inst.student_count}/{inst.max_students} {t('stats.students')}
                      <span className="mx-2">·</span>
                      <Calendar className="h-3 w-3 inline mr-1" />{inst.plan_expires_at?.slice(0, 10) || t('stats.permanent')}
                    </p>
                  </div>
                </div>
              </div>
            </Card>
          ))}
        </div>
      </div>
    );
  }

  // Institution member mode
  const { institution: inst, features } = data;
  if (!inst) {
    return (
      <div className="flex items-center justify-center h-64 text-sm text-muted-foreground">
        {t('noAccess')}
      </div>
    );
  }

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-extrabold text-[#1D1D1F] tracking-tight">{inst.name}</h1>
        <div className="flex items-center gap-2 mt-1">
          <Badge className={cn('text-[10px] font-bold text-white', PLAN_COLORS[inst.plan] || 'bg-[#AEAEB2]')}>{inst.plan_label}</Badge>
          <span className="text-sm text-[#8E8E93]">{inst.plan_expires_at?.slice(0, 10) || t('stats.permanent')}</span>
        </div>
      </div>

      {/* Stats cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {[
          { label: t('stats.students'), value: `${inst.student_count} / ${inst.max_students}`,
            icon: Users, color: 'text-[#0071E3]', bg: 'bg-[#0071E3]/6' },
          { label: t('stats.admins'), value: inst.admin_count, icon: GraduationCap,
            color: 'text-[#34C759]', bg: 'bg-[#34C759]/6' },
          { label: t('stats.weeklyActive'), value: data.stats?.weekly_active_students ?? '—',
            icon: TrendingUp, color: 'text-[#0071E3]', bg: 'bg-[#0071E3]/6' },
          { label: t('stats.aiUsage'), value: data.stats?.ai_usage?.limit
            ? `${data.stats.ai_usage.used}/${data.stats.ai_usage.limit}`
            : (data.stats?.ai_usage?.limit === null ? t('common:unlimited') : '—'),
            icon: Sparkles, color: 'text-[#FF9500]', bg: 'bg-[#FF9500]/6' },
        ].map(s => (
          <Card key={s.label} variant="apple" className="p-4 space-y-1">
            <div className={cn('h-8 w-8 rounded-lg flex items-center justify-center', s.bg)}>
              <s.icon className={cn('h-4 w-4', s.color)} />
            </div>
            <p className="text-lg font-extrabold text-[#1D1D1F] tracking-tight">{s.value}</p>
            <p className="text-xs font-bold text-[#AEAEB2]">{s.label}</p>
          </Card>
        ))}
      </div>

      {/* Features */}
      <Card variant="apple" className="p-6">
        <h3 className="text-sm font-extrabold text-[#1D1D1F] mb-4">
          {t('features.title')}
          <Badge className={cn('ml-2 text-[10px] font-bold text-white', PLAN_COLORS[inst.plan] || 'bg-[#AEAEB2]')}>
            {inst.plan_label}
          </Badge>
        </h3>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-x-6 gap-y-1.5">
          {FEATURE_KEYS.map((key) => {
            const has = features.includes(key);
            return (
              <div key={key} className="flex items-center gap-2.5 py-1">
                {has ? (
                  <Check className="h-4 w-4 text-[#34C759] shrink-0" />
                ) : (
                  <Minus className="h-4 w-4 text-[#E5E5EA] shrink-0" />
                )}
                <span className={cn('text-sm font-medium', has ? 'text-[#1D1D1F]' : 'text-[#C7C7CC]')}>
                  {t(`features.labels.${key}` as any)}
                </span>
              </div>
            );
          })}
        </div>
      </Card>
    </div>
  );
}
