import { useState } from 'react';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Check, Loader2, ArrowLeft, ExternalLink } from 'lucide-react';
import { StripeCheckout } from '@/components/StripeCheckout';
import { cn } from '@/lib/utils';
import api from '@/lib/api';
import { toast } from 'sonner';

type PlanKey = 'solo' | 'plus' | 'pro';
type BillingCycle = 'monthly' | 'annual';
type Gateway = 'stripe' | 'wechat' | 'alipay';
type Step = 'plan' | 'pay' | 'result';

const PLAN_META: Record<PlanKey, { label: string; priceM: number; priceA: number; color: string }> = {
  solo: { label: 'Solo', priceM: 299, priceA: 199, color: 'bg-primary' },
  plus: { label: 'Plus', priceM: 1299, priceA: 999, color: 'bg-unimind-green' },
  pro:  { label: 'Pro', priceM: 3999, priceA: 2999, color: 'bg-amber-500' },
};

const PLAN_FEATURES: Record<PlanKey, string[]> = {
  solo: ['AI 出题无限制', 'Memorix 记忆复习', 'AI 学习助手', '知识图谱', '完整学情报告', 'AI 智能大纲'],
  plus: ['答疑系统', '多教师协作', '自习室', '模拟考试', '班级报表', '数据导出'],
  pro: ['品牌定制', '私有化部署', 'API 接入', 'SSO 单点登录', '审计日志', '专属客户成功经理', 'SLA 99.9%'],
};

interface CheckoutModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  preselectedPlan?: string;
  currentPlan?: string;
}

export function CheckoutModal({ open, onOpenChange, preselectedPlan, currentPlan = 'free' }: CheckoutModalProps) {
  const [step, setStep] = useState<Step>('plan');
  const [plan, setPlan] = useState<PlanKey>((preselectedPlan as PlanKey) || 'solo');
  const [billingCycle, setBillingCycle] = useState<BillingCycle>('annual');
  const [gateway, setGateway] = useState<Gateway | null>(null);
  const [qrUrl, setQrUrl] = useState<string>('');
  const [payUrl, setPayUrl] = useState<string>('');
  const [stripeClientSecret, setStripeClientSecret] = useState<string>('');
  const [orderId, setOrderId] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);
  const [polling, setPolling] = useState(false);
  const [success, setSuccess] = useState(false);

  const meta = PLAN_META[plan];
  const price = billingCycle === 'annual' ? meta.priceA : meta.priceM;

  const handleCreateOrder = async (gw: Gateway) => {
    setGateway(gw);
    setLoading(true);
    try {
      const { data } = await api.post('/payments/orders/create/', { plan, billing_cycle: billingCycle, gateway: gw });
      setOrderId(data.order_id);
      if (gw === 'stripe') {
        setStripeClientSecret(data.clientSecret || '');
        setLoading(false);
        setStep('pay');
      } else if (gw === 'wechat') {
        setQrUrl(data.code_url);
        setLoading(false);
        setStep('pay');
        startPolling(data.order_id);
      } else if (gw === 'alipay') {
        setPayUrl(data.pay_url);
        setLoading(false);
        setStep('pay');
      }
    } catch (e: any) {
      toast.error(e?.response?.data?.error || '创建订单失败');
      setLoading(false);
    }
  };

  const startPolling = (oid: number) => {
    setPolling(true);
    const iv = setInterval(async () => {
      try {
        const { data } = await api.get(`/payments/orders/${oid}/`);
        if (data.status === 'paid') {
          clearInterval(iv);
          setPolling(false);
          setSuccess(true);
          setStep('result');
        }
      } catch {}
    }, 2000);
    // Stop after 5 minutes
    setTimeout(() => { clearInterval(iv); setPolling(false); }, 300000);
  };

  const handleReset = () => {
    setStep('plan');
    setPlan('solo');
    setGateway(null);
    setQrUrl('');
    setPayUrl('');
    setStripeClientSecret('');
    setOrderId(null);
    setSuccess(false);
  };

  const handleClose = () => {
    handleReset();
    onOpenChange(false);
  };

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="sm:max-w-[520px] rounded-3xl border-none shadow-2xl bg-card p-0 overflow-hidden">
        {step === 'plan' && (
          <>
            <DialogHeader className="px-8 pt-8 pb-2 text-left">
              <DialogTitle className="text-xl font-black tracking-tight">升级方案</DialogTitle>
              <DialogDescription className="font-medium text-muted-foreground text-sm">
                选择合适的方案和周期，开始支付。
              </DialogDescription>
            </DialogHeader>

            <div className="px-8 pb-2 space-y-4">
              {/* Plan selector */}
              <div className="grid grid-cols-3 gap-2">
                {(Object.keys(PLAN_META) as PlanKey[]).map((k) => (
                  <button
                    key={k}
                    onClick={() => setPlan(k)}
                    className={cn(
                      'p-3 rounded-2xl border-2 text-left transition-all',
                      plan === k ? 'border-primary bg-primary/5' : 'border-border hover:border-border/80'
                    )}
                  >
                    <p className={cn('text-[10px] font-extrabold uppercase tracking-widest mb-0.5',
                      plan === k ? 'text-primary' : 'text-muted-foreground')}>
                      {PLAN_META[k].label}
                    </p>
                    <p className="text-lg font-extrabold text-foreground">
                      ¥{billingCycle === 'annual' ? PLAN_META[k].priceA : PLAN_META[k].priceM}
                    </p>
                    <p className="text-[10px] text-muted-foreground font-medium">/月</p>
                  </button>
                ))}
              </div>

              {/* Billing toggle */}
              <div className="flex items-center gap-2">
                <Button
                  variant={billingCycle === 'monthly' ? 'default' : 'outline'}
                  size="sm"
                  onClick={() => setBillingCycle('monthly')}
                  className="flex-1 h-9 rounded-xl text-xs font-bold"
                >
                  月付
                </Button>
                <Button
                  variant={billingCycle === 'annual' ? 'default' : 'outline'}
                  size="sm"
                  onClick={() => setBillingCycle('annual')}
                  className="flex-1 h-9 rounded-xl text-xs font-bold"
                >
                  年付 <Badge variant="outline" className="ml-1 text-[9px] px-1 py-0">省23-33%</Badge>
                </Button>
              </div>

              {/* Plan features */}
              <div className="bg-unimind-bg-secondary rounded-2xl p-4 space-y-1.5">
                <p className="text-[10px] font-extrabold text-muted-foreground uppercase tracking-[0.2em] mb-2">
                  {meta.label} 功能
                </p>
                {PLAN_FEATURES[plan]?.map((f, i) => (
                  <div key={i} className="flex items-start gap-2">
                    <Check className="h-3.5 w-3.5 text-unimind-green shrink-0 mt-0.5" />
                    <span className="text-[12px] font-medium text-foreground/70">{f}</span>
                  </div>
                ))}
              </div>
            </div>

            {/* Total + pay buttons */}
            <div className="px-8 pb-8 space-y-3">
              <div className="flex items-center justify-between py-2">
                <span className="text-sm font-bold text-muted-foreground">
                  {meta.label} · {billingCycle === 'annual' ? '年付' : '月付'}
                </span>
                <span className="text-2xl font-extrabold text-foreground">¥{price}<span className="text-sm font-medium text-muted-foreground">/月</span></span>
              </div>

              <div className="grid grid-cols-3 gap-2">
                <Button onClick={() => handleCreateOrder('stripe')} disabled={loading}
                  className="h-11 rounded-xl text-xs font-bold">信用卡</Button>
                <Button onClick={() => handleCreateOrder('wechat')} disabled={loading}
                  className="h-11 rounded-xl text-xs font-bold bg-unimind-green hover:bg-unimind-green/90">微信</Button>
                <Button onClick={() => handleCreateOrder('alipay')} disabled={loading}
                  className="h-11 rounded-xl text-xs font-bold bg-blue-500 hover:bg-blue-600">支付宝</Button>
              </div>
              {loading && (
                <div className="flex items-center justify-center gap-2 text-sm text-muted-foreground">
                  <Loader2 className="h-4 w-4 animate-spin" /> 创建订单中...
                </div>
              )}
            </div>
          </>
        )}

        {step === 'pay' && (
          <div className="px-8 py-8 space-y-6 text-center">
            <button onClick={() => setStep('plan')} className="flex items-center gap-1 text-sm font-medium text-muted-foreground hover:text-foreground">
              <ArrowLeft className="h-4 w-4" /> 返回
            </button>

            <div className="space-y-4">
              <h3 className="text-lg font-extrabold text-foreground">
                {gateway === 'stripe' ? '输入卡号' : gateway === 'wechat' ? '微信扫码支付' : '支付宝支付'}
              </h3>
              <p className="text-2xl font-extrabold">¥{price}</p>

              {gateway === 'wechat' && qrUrl && (
                <div className="space-y-4">
                  <div className="w-48 h-48 mx-auto bg-white rounded-2xl border p-4">
                    <img src={`https://api.qrserver.com/v1/create-qr-code/?size=160x160&data=${encodeURIComponent(qrUrl)}`}
                      alt="微信支付二维码" className="w-full h-full" />
                  </div>
                  {polling && (
                    <div className="flex items-center justify-center gap-2 text-sm text-muted-foreground">
                      <Loader2 className="h-4 w-4 animate-spin" /> 等待支付确认...
                    </div>
                  )}
                </div>
              )}

              {gateway === 'alipay' && payUrl && (
                <div className="space-y-4">
                  <Button onClick={() => window.open(payUrl, '_blank')} className="gap-2">
                    前往支付宝支付 <ExternalLink className="h-4 w-4" />
                  </Button>
                  <p className="text-xs text-muted-foreground">支付完成后会自动返回</p>
                </div>
              )}

              {gateway === 'stripe' && stripeClientSecret && (
                <StripeCheckout
                  clientSecret={stripeClientSecret}
                  orderId={orderId!}
                  onSuccess={() => startPolling(orderId!)}
                  onBack={() => setStep('plan')}
                />
              )}
              {gateway === 'stripe' && !stripeClientSecret && (
                <p className="text-sm text-muted-foreground">创建支付订单中...</p>
              )}
            </div>
          </div>
        )}

        {step === 'result' && (
          <div className="px-8 py-12 text-center space-y-6">
            {success ? (
              <>
                <div className="h-16 w-16 mx-auto rounded-full bg-unimind-green/10 flex items-center justify-center">
                  <Check className="h-8 w-8 text-unimind-green" />
                </div>
                <div>
                  <h3 className="text-xl font-extrabold text-foreground">支付成功</h3>
                  <p className="text-sm text-muted-foreground mt-1">您的方案已升级至 {meta.label}</p>
                </div>
                <Button onClick={handleClose} variant="apple" className="h-11 px-8 rounded-xl font-extrabold">
                  开始使用
                </Button>
              </>
            ) : (
              <>
                <h3 className="text-lg font-extrabold text-foreground">支付未确认</h3>
                <p className="text-sm text-muted-foreground">请检查支付是否完成，或联系客服。</p>
                <div className="flex gap-2 justify-center">
                  <Button variant="outline" onClick={() => { if (orderId) startPolling(orderId); }} className="rounded-xl">
                    重新检查
                  </Button>
                  <Button variant="outline" onClick={handleClose} className="rounded-xl">关闭</Button>
                </div>
              </>
            )}
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
