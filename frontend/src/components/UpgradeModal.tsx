import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { ArrowRight, Check } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { cn } from '@/lib/utils';

const PLAN_ORDER = ['free', 'solo', 'plus', 'pro'] as const;

const PLAN_META: Record<string, { label: string; price: string; color: string }> = {
  free: { label: 'Free', price: '免费', color: 'bg-[#AEAEB2]' },
  solo: { label: 'Solo', price: '¥299/月', color: 'bg-[#0071E3]' },
  plus: { label: 'Plus', price: '¥1,299/月', color: 'bg-[#34C759]' },
  pro:  { label: 'Pro', price: '¥3,999/月', color: 'bg-[#FF9500]' },
};

const PLAN_UNLOCK_SUMMARY: Record<string, string> = {
  solo: '解锁 AI 智能出题、记忆复习、知识图谱、完整学情报告等 6 项 AI 学习能力',
  plus: '解锁在线答疑、多教师协作、实时自习室、模拟考试、班级对比报表与数据导出等机构教学能力',
  pro:  '解锁品牌定制白标、私有化部署、API 接入、SSO 单点登录、审计日志等企业旗舰能力',
};

const PLAN_FEATURES: Record<string, string[]> = {
  solo: ['AI 出题无限制', 'Memorix 记忆复习', 'AI 学习助手 · 多 Bot', '交互式知识图谱', '完整学情报告', 'AI 智能大纲'],
  plus: ['在线答疑系统', '多教师协作 · 权限管理', '实时自习室 · 番茄钟', '模拟考试', '班级对比报表 · 数据导出'],
  pro:  [
    '品牌定制 · 白标部署', '私有化部署 · 数据主权', 'API 接入 · 系统集成',
    '多语言 · 国际化支持', 'SSO · SAML 单点登录', '审计日志 · 合规就绪',
    '专属客户成功经理', 'SLA 99.9% 保障', '学生端收费 · 自主定价',
    '学员数不限 · 教师数不限',
  ],
};

const FEATURE_REQUIRED_PLAN: Record<string, string> = {
  'memorix.review': 'solo', 'ai.assistant': 'solo',
  'full.report': 'solo', 'knowledge.graph': 'solo', 'video.outline': 'solo',
  'faq.system': 'plus', 'multi.teacher': 'plus', 'class.compare': 'plus',
  'data.export': 'plus', 'study.room': 'plus', 'pdf.mock': 'plus', 'interview.mock': 'plus',
  'brand.custom': 'pro', 'api.access': 'pro', 'student.payment': 'pro',
  'private.deploy': 'pro', 'i18n.custom': 'pro', 'sso.saml': 'pro',
  'audit.log': 'pro', 'dedicated.support': 'pro', 'sla.99.9': 'pro',
};

interface UpgradeModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  feature?: string;
  currentPlan?: string;
}

export function UpgradeModal({ open, onOpenChange, feature, currentPlan = 'free' }: UpgradeModalProps) {
  const navigate = useNavigate();

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
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[480px] rounded-apple-3xl border-none shadow-2xl bg-card p-0 overflow-hidden">
        {/* Header */}
        <div className="bg-gradient-to-br from-[#0071E3]/6 via-[#0071E3]/3 to-transparent px-8 pt-8 pb-4">
          <DialogHeader className="space-y-2 text-left">
            <Badge className={cn('text-[10px] font-bold text-white mb-1', meta.color)}>
              {meta.label}
            </Badge>
            <DialogTitle className="text-xl font-black tracking-tight">
              升级到 {meta.label} 方案
            </DialogTitle>
            <DialogDescription className="font-medium text-muted-foreground leading-relaxed text-sm">
              {unlockSummary}
            </DialogDescription>
          </DialogHeader>
        </div>

        {/* Features */}
        <div className="px-8 py-4 space-y-3">
          <p className="text-[11px] font-extrabold text-muted-foreground uppercase tracking-[0.2em]">
            {meta.label} 核心功能
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

        {/* Footer */}
        <div className="px-8 pb-8 pt-2 flex gap-3">
          <Button
            variant="outline"
            className="flex-1 h-11 rounded-xl text-sm font-bold"
            onClick={() => onOpenChange(false)}
          >
            稍后再说
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
            了解详情
            <ArrowRight className="ml-1.5 h-4 w-4" />
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
