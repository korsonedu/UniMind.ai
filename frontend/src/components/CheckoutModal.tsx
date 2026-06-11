import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Check, Sparkle } from '@phosphor-icons/react';
import { cn } from '@/lib/utils';

type PlanKey = 'starter' | 'growth' | 'enterprise';
type BillingCycle = 'monthly' | 'annual';

const PLAN: Record<PlanKey, {
  label: string; priceM: number; priceA: number;
  color: string; gradient: string; ring: string;
  features: string[];
}> = {
  starter: {
    label: 'Starter', priceM: 499, priceA: 416,
    color: 'text-primary', gradient: 'from-[#0071E3] to-[#0077ED]', ring: 'ring-primary',
    features: ['AI 出题无限制', 'Memorix 记忆复习', 'AI 学习助手', '知识图谱', '完整学情报告', 'AI 智能大纲'],
  },
  growth: {
    label: 'Growth', priceM: 1299, priceA: 1083,
    color: 'text-unimind-green', gradient: 'from-[#34C759] to-[#30D158]', ring: 'ring-unimind-green',
    features: ['答疑系统', '多教师协作', '自习室', '模拟考试', '班级报表', '数据导出'],
  },
  enterprise: {
    label: 'Enterprise', priceM: 3999, priceA: 3333,
    color: 'text-amber-500', gradient: 'from-amber-500 to-amber-400', ring: 'ring-amber-500',
    features: ['品牌定制', '私有化部署', 'API 接入', 'SSO 单点登录', '审计日志', '专属客户成功经理', 'SLA 99.9%'],
  },
};

interface CheckoutModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  preselectedPlan?: string;
  currentPlan?: string;
}

export function CheckoutModal({ open, onOpenChange, preselectedPlan }: CheckoutModalProps) {
  const navigate = useNavigate();
  const [plan, setPlan] = useState<PlanKey>((preselectedPlan as PlanKey) || 'starter');
  const [billingCycle, setBillingCycle] = useState<BillingCycle>('annual');

  const meta = PLAN[plan];
  const price = billingCycle === 'annual' ? meta.priceA : meta.priceM;

  const handlePay = () => {
    onOpenChange(false);
    navigate(`/checkout?plan=${plan}&cycle=${billingCycle}&gateway=stub`);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[480px] rounded-[2rem] border-none shadow-2xl bg-card p-0 overflow-hidden">
        {/* Header */}
        <DialogHeader className="px-7 pt-7 pb-0 text-left space-y-1">
          <div className="flex items-center gap-2 mb-1">
            <Sparkle className="h-4 w-4 text-amber-400/60" />
            <span className="text-[10px] font-extrabold text-muted-foreground uppercase tracking-[0.25em]">升级方案</span>
          </div>
          <DialogTitle className="text-xl font-black tracking-tight text-foreground">
            选择您的方案
          </DialogTitle>
          <DialogDescription className="text-[13px] font-medium text-muted-foreground leading-relaxed">
            所有方案均包含 14 天免费试用，随时可取消。
          </DialogDescription>
        </DialogHeader>

        <div className="px-7 space-y-4 pt-5 pb-2">
          {/* Plan selector */}
          <div className="grid grid-cols-3 gap-2">
            {(Object.keys(PLAN) as PlanKey[]).map((k) => {
              const p = PLAN[k];
              const isActive = plan === k;
              return (
                <button
                  key={k}
                  onClick={() => setPlan(k)}
                  className={cn(
                    'relative p-3.5 rounded-2xl border-2 text-left',
                    'motion-safe:transition-all motion-safe:duration-200',
                    'focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none',
                    isActive
                      ? `${p.ring} border-current bg-accent/30 shadow-sm`
                      : 'border-border hover:border-muted-foreground/20',
                  )}
                >
                  <p className={cn(
                    'text-[10px] font-extrabold uppercase tracking-[0.15em] mb-1',
                    isActive ? p.color : 'text-muted-foreground',
                  )}>
                    {p.label}
                  </p>
                  <p className="text-[17px] font-extrabold text-foreground tabular-nums tracking-tight leading-none">
                    ¥{billingCycle === 'annual' ? p.priceA : p.priceM}
                  </p>
                  <p className="text-[10px] text-muted-foreground font-semibold mt-0.5">/月</p>
                  {isActive && (
                    <div className={cn('absolute top-2 right-2 h-4 w-4 rounded-full bg-gradient-to-br', p.gradient, 'flex items-center justify-center')}>
                      <Check className="h-2.5 w-2.5 text-white" strokeWidth={3} />
                    </div>
                  )}
                </button>
              );
            })}
          </div>

          {/* Billing toggle */}
          <div className="flex bg-unimind-bg-secondary rounded-2xl p-1 gap-1">
            <button
              onClick={() => setBillingCycle('monthly')}
              className={cn(
                'flex-1 h-9 rounded-xl text-[12px] font-extrabold motion-safe:transition-all motion-safe:duration-200',
                billingCycle === 'monthly'
                  ? 'bg-background text-foreground shadow-sm'
                  : 'text-muted-foreground hover:text-foreground',
              )}
            >
              月付
            </button>
            <button
              onClick={() => setBillingCycle('annual')}
              className={cn(
                'flex-1 h-9 rounded-xl text-[12px] font-extrabold motion-safe:transition-all motion-safe:duration-200 flex items-center justify-center gap-1.5',
                billingCycle === 'annual'
                  ? 'bg-background text-foreground shadow-sm'
                  : 'text-muted-foreground hover:text-foreground',
              )}
            >
              年付
              <Badge variant="outline" className="text-[9px] px-1 py-0 font-extrabold border-emerald-200 text-emerald-700 bg-emerald-50">
                省 33%
              </Badge>
            </button>
          </div>

          {/* Features */}
          <div className="bg-unimind-bg-secondary rounded-2xl p-4 space-y-1.5">
            <p className="text-[10px] font-extrabold text-muted-foreground/50 uppercase tracking-[0.2em] mb-2">
              {meta.label} 方案功能
            </p>
            {meta.features.map((f, i) => (
              <div key={i} className="flex items-start gap-2">
                <Check className="h-3.5 w-3.5 text-unimind-green shrink-0 mt-0.5" />
                <span className="text-[12px] font-semibold text-foreground/65">{f}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Footer */}
        <div className="px-7 pb-7 pt-3 space-y-3">
          <div className="flex items-center justify-between py-1">
            <span className="text-[13px] font-bold text-muted-foreground">
              {meta.label} · {billingCycle === 'annual' ? '年付' : '月付'}
            </span>
            <span className="text-2xl font-extrabold text-foreground tabular-nums tracking-tight">
              ¥{price}<span className="text-[13px] font-semibold text-muted-foreground">/月</span>
            </span>
          </div>

          <Button onClick={handlePay}
            className="w-full h-12 rounded-xl text-[13px] font-extrabold bg-gradient-to-r from-[#0071E3] to-[#0077ED] hover:from-[#0071E3]/90 hover:to-[#0077ED]/90 text-white shadow-lg shadow-[#0071E3]/15 gap-2">
            <Sparkle className="h-4 w-4" />
            立即支付
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
