import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { ArrowRight, Lock, Sparkles, Check } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { cn } from '@/lib/utils';

const FEATURE_REQUIRED_PLAN: Record<string, { plan: string; label: string; price: string }> = {
  'ai.generate':     { plan: 'Solo', label: 'AI 智能出题', price: '¥299/月' },
  'memorix.review':  { plan: 'Solo', label: 'Memorix 记忆复习', price: '¥299/月' },
  'ai.assistant':    { plan: 'Solo', label: 'AI 学习助手', price: '¥299/月' },
  'full.report':     { plan: 'Solo', label: '完整学情报告', price: '¥299/月' },
  'knowledge.graph': { plan: 'Solo', label: '知识图谱', price: '¥299/月' },
  'course.video':    { plan: 'Plus', label: '视频课程', price: '¥1,299/月' },
  'video.outline':   { plan: 'Plus', label: 'AI 智能大纲', price: '¥1,299/月' },
  'faq.system':      { plan: 'Plus', label: '在线答疑系统', price: '¥1,299/月' },
  'multi.teacher':   { plan: 'Plus', label: '多教师协作', price: '¥1,299/月' },
  'class.compare':   { plan: 'Plus', label: '班级对比报表', price: '¥1,299/月' },
  'data.export':     { plan: 'Plus', label: '数据导出', price: '¥1,299/月' },
  'study.room':      { plan: 'Plus', label: '实时自习室', price: '¥1,299/月' },
  'pdf.mock':        { plan: 'Plus', label: 'PDF 模考', price: '¥1,299/月' },
  'brand.custom':    { plan: 'Pro', label: '品牌定制 · 白标', price: '¥3,999/月' },
  'api.access':      { plan: 'Pro', label: 'API 接入', price: '¥3,999/月' },
  'student.payment': { plan: 'Pro', label: '学生端收费系统', price: '¥3,999/月' },
};

export function getRequiredPlan(feature: string): { plan: string; label: string; price: string } | null {
  return FEATURE_REQUIRED_PLAN[feature] ?? null;
}

const PLAN_FEATURES_BREAKDOWN: Record<string, string[]> = {
  Solo: ['AI 出题无限制', 'Memorix 记忆复习', 'AI 学习助手 · 多 Bot', '交互式知识图谱', '完整学情报告'],
  Plus: ['视频课程 + AI 智能大纲', '在线答疑系统', '多教师协作 · 权限管理', '实时自习室 · 番茄钟', 'PDF 个性化模考', '班级对比报表 · 数据导出'],
  Pro: ['品牌定制 · 白标部署', 'API 接入 · 数据私有化', '学生端收费系统（机构自主定价）', '学员数不限 · 教师数不限'],
};

interface UpgradeModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  feature: string | null;
}

export function UpgradeModal({ open, onOpenChange, feature }: UpgradeModalProps) {
  const { t } = useTranslation('layout');
  const navigate = useNavigate();
  const planInfo = feature ? getRequiredPlan(feature) : null;
  const targetPlan = planInfo?.plan ?? 'Solo';
  const targetLabel = planInfo?.label ?? t('thisFeature', '此功能');
  const features = PLAN_FEATURES_BREAKDOWN[targetPlan] ?? [];

  const planDesc: Record<string, string> = {
    Solo: t('upgradeModal.soloDesc', '每月仅 ¥299，解锁 AI 智能学习全部能力。'),
    Plus: t('upgradeModal.plusDesc', '每月 ¥1,299，解锁完整机构教学平台。'),
    Pro: t('upgradeModal.proDesc', '企业旗舰版，解锁品牌定制与 API 接入。'),
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[460px] rounded-apple-3xl border-none shadow-2xl bg-card p-8">
        <DialogHeader className="space-y-3">
          <div className="h-12 w-12 rounded-2xl bg-[#0071E3]/8 flex items-center justify-center mb-2">
            <Lock className="h-6 w-6 text-[#0071E3]" />
          </div>
          <DialogTitle className="text-xl font-black tracking-tight">
            {t('upgradeModal.title', { feature: targetLabel })}
          </DialogTitle>
          <DialogDescription className="font-medium text-muted-foreground leading-relaxed">
            {t('upgradeModal.requires', { feature: targetLabel, plan: targetPlan })}
            {planDesc[targetPlan]}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-3 my-4">
          <p className="text-[11px] font-extrabold text-muted-foreground uppercase tracking-[0.2em]">
            {t('upgradeModal.coreFeatures', { plan: targetPlan })}
          </p>
          <div className="bg-[#F5F5F7] rounded-2xl p-4 space-y-2">
            {features.map((f, i) => (
              <div key={i} className="flex items-start gap-2.5">
                <Check className="h-4 w-4 text-[#34C759] shrink-0 mt-0.5" />
                <span className="text-[13px] font-bold text-[#1D1D1F]">{f}</span>
              </div>
            ))}
          </div>
        </div>

        <div className="flex gap-3 pt-2">
          <Button
            variant="outline"
            className="flex-1 h-11 rounded-xl text-sm font-bold"
            onClick={() => onOpenChange(false)}
          >
            {t('common:cancel')}
          </Button>
          <Button
            variant="apple"
            className="flex-1 h-11 rounded-xl text-sm font-extrabold"
            onClick={() => {
              onOpenChange(false);
              navigate('/?upgrade=1');
              setTimeout(() => {
                document.querySelector('#pricing')?.scrollIntoView({ behavior: 'smooth' });
              }, 200);
            }}
          >
            {t('common:viewDetails')}
            <ArrowRight className="ml-1.5 h-4 w-4" />
          </Button>
        </div>

        <p className="text-center text-[10px] font-bold text-muted-foreground/50 mt-3">
          {t('upgradeModal.freeTrialNote', '所有方案均含 14 天免费试用')}
        </p>
      </DialogContent>
    </Dialog>
  );
}
