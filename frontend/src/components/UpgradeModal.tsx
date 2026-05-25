import { useState } from 'react';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { ArrowRight, Check } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useTranslation } from 'react-i18next';
import { CheckoutModal } from './CheckoutModal';

const PLAN_ORDER = ['free', 'starter', 'growth', 'enterprise'] as const;

const PLAN_META: Record<string, { label: string; price: string; color: string }> = {
  free:       { label: 'Free', price: '免费', color: 'bg-unimind-text-quaternary' },
  starter:    { label: 'Starter', price: '¥499/月', color: 'bg-primary' },
  growth:     { label: 'Growth', price: '¥1,299/月', color: 'bg-unimind-green' },
  enterprise: { label: 'Enterprise', price: '¥3,999/月', color: 'bg-amber-500' },
};

const PLAN_UNLOCK_SUMMARY: Record<string, string> = {
  starter:    '解锁 AI 智能出题、记忆复习、知识图谱、完整学情报告等 6 项 AI 学习能力',
  growth:     '解锁在线答疑、多教师协作、实时自习室、模拟考试、班级对比报表与数据导出等机构教学能力',
  enterprise: '解锁品牌定制白标、私有化部署、API 接入、SSO 单点登录、审计日志等企业旗舰能力',
};

const PLAN_FEATURES: Record<string, string[]> = {
  starter: ['AI 出题无限制', 'Memorix 记忆复习', 'AI 学习助手 · 多 Bot', '交互式知识图谱', '完整学情报告', 'AI 智能大纲'],
  growth: ['在线答疑系统', '多教师协作 · 权限管理', '实时自习室 · 番茄钟', '模拟考试', '班级对比报表 · 数据导出'],
  enterprise: [
    '品牌定制 · 白标部署', '私有化部署 · 数据主权', 'API 接入 · 系统集成',
    '多语言 · 国际化支持', 'SSO · SAML 单点登录', '审计日志 · 合规就绪',
    '专属客户成功经理', 'SLA 99.9% 保障', '学生端收费 · 自主定价',
    '学员数不限 · 教师数不限',
  ],
};

const FEATURE_REQUIRED_PLAN: Record<string, string> = {
  'memorix.review': 'starter', 'ai.assistant': 'starter',
  'full.report': 'starter', 'knowledge.graph': 'starter', 'video.outline': 'starter',
  'faq.system': 'growth', 'multi.teacher': 'growth', 'class.compare': 'growth',
  'data.export': 'growth', 'study.room': 'growth', 'pdf.mock': 'growth', 'interview.mock': 'growth',
  'brand.custom': 'enterprise', 'api.access': 'enterprise', 'student.payment': 'enterprise',
  'private.deploy': 'enterprise', 'i18n.custom': 'enterprise', 'sso.saml': 'enterprise',
  'audit.log': 'enterprise', 'dedicated.support': 'enterprise', 'sla.99.9': 'enterprise',
};

interface UpgradeModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  feature?: string;
  currentPlan?: string;
}

export function UpgradeModal({ open, onOpenChange, feature, currentPlan = 'free' }: UpgradeModalProps) {
  const [checkoutOpen, setCheckoutOpen] = useState(false);
  const { t } = useTranslation('layout');

  // Determine target plan
  const requiredPlan = feature ? FEATURE_REQUIRED_PLAN[feature] : null;
  const currentIdx = PLAN_ORDER.indexOf(currentPlan as any);
  const nextIdx = requiredPlan
    ? PLAN_ORDER.indexOf(requiredPlan as any)
    : Math.min(currentIdx + 1, PLAN_ORDER.length - 1);
  const targetPlan = PLAN_ORDER[Math.max(nextIdx, 1)]; // at least solo
  const meta = PLAN_META[targetPlan];
  const features = PLAN_FEATURES[targetPlan] || [];
  const unlockSummary = PLAN_UNLOCK_SUMMARY[targetPlan] || '';

  return (
    <>
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent className="sm:max-w-[480px] rounded-apple-3xl border-none shadow-2xl bg-card p-0 overflow-hidden">
          {/* Header */}
          <div className="bg-card px-8 pt-8 pb-4">
            <DialogHeader className="space-y-2 text-left">
              <Badge className={cn('text-[10px] font-bold text-white mb-1', meta.color)}>
                {meta.label}
              </Badge>
              <DialogTitle className="text-xl font-black tracking-tight">
                {t('upgradeModal.upgradeTo', { plan: meta.label })}
              </DialogTitle>
              <DialogDescription className="font-medium text-muted-foreground leading-relaxed text-sm">
                {unlockSummary}
              </DialogDescription>
            </DialogHeader>
          </div>

          {/* Features */}
          <div className="px-8 py-4 space-y-3">
            <p className="text-[11px] font-extrabold text-muted-foreground uppercase tracking-[0.2em]">
              {t('upgradeModal.coreFeatures', { plan: meta.label })}
            </p>
            <div className="bg-unimind-bg-secondary rounded-2xl p-4 space-y-2">
              {features.map((f, i) => (
                <div key={i} className="flex items-start gap-2.5">
                  <Check className="h-4 w-4 text-unimind-green shrink-0 mt-0.5" />
                  <span className="text-[13px] font-bold text-foreground">{f}</span>
                </div>
              ))}
            </div>

          </div>

          {/* Footer */}
          <div className="px-8 pb-8 pt-2 flex gap-3">
            <Button
              variant="outline"
              className="flex-1 h-11 rounded-xl text-sm font-bold"
              onClick={() => onOpenChange(false)}
            >
              {t('upgradeModal.later')}
            </Button>
            <Button
              variant="apple"
              className="flex-1 h-11 rounded-xl text-sm font-extrabold"
              onClick={() => {
                onOpenChange(false);
                setCheckoutOpen(true);
              }}
            >
              {t('upgradeModal.learnMore')}
              <ArrowRight className="ml-1.5 h-4 w-4" />
            </Button>
          </div>
        </DialogContent>
      </Dialog>
      <CheckoutModal open={checkoutOpen} onOpenChange={setCheckoutOpen} preselectedPlan={targetPlan} currentPlan={currentPlan} />
    </>
  );
}
