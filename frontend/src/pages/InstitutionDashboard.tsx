import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { useTranslation } from 'react-i18next';
import { useInstitutionStore, FEATURES } from '@/store/useInstitutionStore';
import { useAuthStore } from '@/store/useAuthStore';
import api from '@/lib/api';
import {
  Building2, Users, Crown, Calendar, ArrowRight, Loader2,
  Check, Minus, Eye, EyeOff, GraduationCap, TrendingUp, Sparkles,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { isAdminUser } from '@/lib/authz';

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
    top_weak_points: Array<{ label: string; weak_count: number }>;
  };
  features: string[];
  plan_matrix: Record<string, string[]>;
}

const PLAN_COLORS: Record<string, string> = {
  free: 'bg-[#AEAEB2]', solo: 'bg-[#0071E3]',
  plus: 'bg-[#34C759]', pro: 'bg-[#FF9500]',
};

const PLAN_NAMES: Record<string, string> = {
  free: 'Free', solo: 'Solo', plus: 'Plus', pro: 'Pro',
};

const FEATURE_LABELS: Record<string, string> = {
  'quiz.manual': '习题训练', 'quiz.exam': '模拟考试',
  'wrong.review': '错题复盘', 'basic.stats': '基础统计',
  'ai.generate': 'AI 生成题目', 'memorix.review': 'Memorix 记忆复习',
  'full.report': '完整学情报告', 'knowledge.graph': '交互式知识图谱',
  'ai.assistant': 'AI 学习助手', 'course.video': '视频课程',
  'video.outline': 'AI 智能大纲', 'faq.system': '在线答疑系统',
  'pdf.mock': 'PDF 模考', 'study.room': '实时自习室',
  'multi.teacher': '多教师协作', 'class.compare': '班级对比',
  'data.export': '数据导出', 'brand.custom': '品牌定制',
  'api.access': 'API 接入', 'student.payment': '学生端收费',
  'private.deploy': '私有化部署', 'i18n.custom': '多语言 · 国际化',
  'sso.saml': 'SSO · SAML', 'audit.log': '审计日志',
  'dedicated.support': '专属支持', 'sla.99.9': 'SLA 99.9%',
};

const ALL_FEATURES = [
  'quiz.manual', 'quiz.exam', 'wrong.review', 'basic.stats',
  'ai.generate', 'memorix.review', 'full.report', 'knowledge.graph', 'ai.assistant',
  'course.video', 'video.outline', 'faq.system', 'pdf.mock', 'study.room',
  'multi.teacher', 'class.compare', 'data.export',
  'brand.custom', 'api.access', 'student.payment',
  'private.deploy', 'i18n.custom', 'sso.saml', 'audit.log',
  'dedicated.support', 'sla.99.9',
];

export default function InstitutionDashboard() {
  const { t } = useTranslation('dashboard');
  const navigate = useNavigate();
  const { user } = useAuthStore();
  const { previewMode, previewInstitution, enterPreview, exitPreview } = useInstitutionStore();
  const [data, setData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);

  const isAdmin = isAdminUser(user);
  const isInstAdmin = user?.institution_role === 'admin' || user?.is_institution_admin;

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

  // Platform admin overview mode
  if (data.mode === 'platform_admin' && data.institutions) {
    return (
      <div className="max-w-5xl mx-auto space-y-6">
        {previewMode && previewInstitution && (
          <div className="flex items-center justify-between bg-[#0071E3] text-white px-4 py-2.5 rounded-xl">
            <div className="flex items-center gap-2 text-sm font-bold">
              <Eye className="h-4 w-4" />
              <span>{t('layout:previewMode', { name: previewInstitution.name, plan: previewInstitution.plan_label })}</span>
            </div>
            <Button size="sm" variant="ghost" className="text-white hover:bg-white/10 text-xs"
              onClick={exitPreview}>
              <EyeOff className="h-3.5 w-3.5 mr-1" /> {t('layout:exitPreview')}
            </Button>
          </div>
        )}

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
                <div className="flex items-center gap-2">
                  <Button variant="ghost" size="sm" className="h-8 text-xs"
                    onClick={async () => { await enterPreview(inst.id); }}>
                    <Eye className="h-3.5 w-3.5 mr-1" />{t('actions.preview')}
                  </Button>
                  <Button variant="ghost" size="sm" className="h-8 text-xs"
                    onClick={() => navigate('/admin/institutions')}>
                    {t('common:manage')}
                  </Button>
                </div>
              </div>
            </Card>
          ))}
        </div>

        {/* Plan matrix */}
        {data.plan_matrix && (
          <Card variant="apple" className="p-5">
            <h3 className="text-sm font-extrabold text-[#1D1D1F] mb-3">{t('featureMatrix')}</h3>
            <div className="grid grid-cols-4 gap-2 text-center">
              {['free', 'solo', 'plus', 'pro'].map(plan => (
                <div key={plan} className="space-y-1">
                  <p className="text-xs font-extrabold text-[#8E8E93]">{PLAN_NAMES[plan]}</p>
                  <p className="text-lg font-extrabold">{t('itemsCount', { count: ((data.plan_matrix[plan] || []) as string[]).length })}</p>
                </div>
              ))}
            </div>
          </Card>
        )}
      </div>
    );
  }

  // Institution admin mode
  const { institution: inst, features, plan_matrix } = data;
  if (!inst) {
    return (
      <div className="flex items-center justify-center h-64 text-sm text-muted-foreground">
        {t('noAccess')}
      </div>
    );
  }
  const currentTier = ['free', 'solo', 'plus', 'pro'].indexOf(inst.plan);

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      {/* Preview banner */}
      {previewMode && previewInstitution && (
        <div className="flex items-center justify-between bg-[#0071E3] text-white px-4 py-2.5 rounded-xl">
          <div className="flex items-center gap-2 text-sm font-bold">
            <Eye className="h-4 w-4" />
            <span>{t('layout:previewMode', { name: previewInstitution.name, plan: previewInstitution.plan_label })}</span>
            （{previewInstitution.plan_label}）{t('common:preview')}
          </div>
          <Button size="sm" variant="ghost" className="text-white hover:bg-white/10 text-xs"
            onClick={exitPreview}>
            <EyeOff className="h-3.5 w-3.5 mr-1" /> {t('layout:exitPreview')}
          </Button>
        </div>
      )}

      {/* Header */}
      <div>
        <h1 className="text-2xl font-extrabold text-[#1D1D1F] tracking-tight">{t('pageTitle')}</h1>
        <p className="text-sm text-[#8E8E93] mt-1">{inst.name} · {inst.plan_label}</p>
      </div>

      {/* Stats cards */}
      <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
        {[
          { label: t('stats.plan'), value: inst.plan_label, icon: Crown,
            color: 'text-[#FF9500]', bg: 'bg-[#FF9500]/6' },
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
          { label: t('stats.expires'), value: inst.plan_expires_at?.slice(0, 10) || t('stats.permanent'),
            icon: Calendar, color: 'text-[#8E8E93]', bg: 'bg-[#8E8E93]/6' },
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

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Feature list — current plan */}
        <Card variant="apple" className="p-5 lg:col-span-2">
          <h3 className="text-sm font-extrabold text-[#1D1D1F] mb-4">
            {t('features.title')}
            <Badge className={cn('ml-2 text-[10px] font-bold text-white', PLAN_COLORS[inst.plan] || 'bg-[#AEAEB2]')}>
              {inst.plan_label}
            </Badge>
          </h3>
          <div className="space-y-4">
            {/* 当前方案功能 */}
            <div>
              <p className="text-xs font-bold text-[#8E8E93] mb-2">{inst.plan_label} 方案包含</p>
              <div className="space-y-1">
                {ALL_FEATURES.filter(f => features.includes(f)).map(f => (
                  <div key={f} className="flex items-center gap-2.5 py-1">
                    <Check className="h-4 w-4 text-[#34C759] shrink-0" />
                    <span className="text-sm font-medium text-[#1D1D1F]">{FEATURE_LABELS[f] || f}</span>
                  </div>
                ))}
              </div>
            </div>
            {/* 升级功能 */}
            {(() => {
              const locked = ALL_FEATURES.filter(f => !features.includes(f));
              if (locked.length === 0) return null;
              const nextTier = ['solo', 'plus', 'pro'].find((_, i) => i + 1 > currentTier) || 'pro';
              return (
                <div>
                  <p className="text-xs font-bold text-[#FF9500] mb-2">
                    升级解锁 <Badge className="ml-1 text-[10px] font-bold text-white bg-[#FF9500]">{PLAN_NAMES[nextTier]}</Badge>
                  </p>
                  <div className="space-y-1">
                    {locked.map(f => (
                      <div key={f} className="flex items-center gap-2.5 py-1">
                        <div className="h-4 w-4 rounded-full bg-[#FF9500]/12 flex items-center justify-center shrink-0">
                          <div className="h-1.5 w-1.5 rounded-full bg-[#FF9500]" />
                        </div>
                        <span className="text-sm font-medium text-[#8E8E93]">{FEATURE_LABELS[f] || f}</span>
                      </div>
                    ))}
                  </div>
                </div>
              );
            })()}
          </div>
        </Card>

        {/* Plan comparison & actions */}
        <div className="space-y-4">
          {/* Plan tiers quick compare */}
          <Card variant="apple" className="p-5">
            <h3 className="text-sm font-extrabold text-[#1D1D1F] mb-3">{t('comparison.title')}</h3>
            <div className="space-y-2">
              {['free', 'solo', 'plus', 'pro'].map((plan, i) => {
                const isCurrent = plan === inst.plan;
                const isHigher = i > currentTier;
                return (
                  <div key={plan} className={cn(
                    'flex items-center justify-between px-3 py-2 rounded-lg',
                    isCurrent ? 'bg-[#0071E3]/6 border border-[#0071E3]/20' : 'bg-[#F5F5F7]',
                  )}>
                    <div className="flex items-center gap-2">
                      <span className={cn(
                        'text-xs font-extrabold',
                        isCurrent ? 'text-[#0071E3]' : 'text-[#8E8E93]',
                      )}>
                        {PLAN_NAMES[plan]}
                      </span>
                      {isCurrent && (
                        <Badge className="text-[10px] bg-[#0071E3] text-white font-bold">{t('current')}</Badge>
                      )}
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="text-xs font-bold text-[#AEAEB2]">
                        {t('featuresCount', { count: (plan_matrix[plan] || []).filter(f => f !== 'quiz.manual' && f !== 'quiz.exam' && f !== 'wrong.review' && f !== 'basic.stats').length })}
                      </span>
                      {isHigher && (
                        <ArrowRight className="h-3.5 w-3.5 text-[#AEAEB2]" />
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          </Card>

          {/* Actions */}
          <Card variant="apple" className="p-5 space-y-3">
            <Button variant="apple" className="w-full" size="sm"
              onClick={() => navigate('/institution/students')}>
              <Users className="h-4 w-4 mr-1.5" /> {t('actions.manageStudents')}
            </Button>

            {isAdmin && !previewMode && inst && (
              <Button variant="outline" size="sm" className="w-full"
                onClick={async () => {
                  await enterPreview(inst.id);
                }}>
                <Eye className="h-4 w-4 mr-1.5" /> {t('previewAs')}
              </Button>
            )}

            {!isAdmin && (
              <p className="text-xs text-[#AEAEB2] text-center pt-1">
                {t('contactAdminForUpgrade', '需要升级方案？请联系平台管理员')}
              </p>
            )}
          </Card>
        </div>
      </div>
    </div>
  );
}
