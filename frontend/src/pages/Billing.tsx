import { useState, useEffect } from 'react';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { PageWrapper } from '@/components/PageWrapper';
import { CheckoutModal } from '@/components/CheckoutModal';
import { useAuthStore } from '@/store/useAuthStore';
import api from '@/lib/api';
import { Check, Crown, Calendar, CreditCard, FileText, Loader2 } from 'lucide-react';
import { cn } from '@/lib/utils';
import { toast } from 'sonner';

const PLAN_META: Record<string, { label: string; priceM: number; color: string }> = {
  free: { label: 'Free', priceM: 0, color: 'bg-unimind-text-quaternary' },
  solo: { label: 'Solo', priceM: 299, color: 'bg-primary' },
  plus: { label: 'Plus', priceM: 1299, color: 'bg-unimind-green' },
  pro:  { label: 'Pro', priceM: 3999, color: 'bg-amber-500' },
};

const PLAN_FEATURES: Record<string, string[]> = {
  solo: ['AI 出题无限制', 'Memorix 记忆复习', 'AI 学习助手', '交互式知识图谱', '完整学情报告', 'AI 智能大纲'],
  plus: ['答疑系统', '多教师协作', '实时自习室', '模拟考试', '班级对比报表', '数据导出'],
  pro: ['品牌定制 · 白标部署', '私有化部署', 'API 接入', 'SSO 单点登录', '审计日志', '学生端收费', 'SLA 99.9%'],
};

export function BillingPage() {
  const { user } = useAuthStore();
  const [checkoutOpen, setCheckoutOpen] = useState(false);
  const [orders, setOrders] = useState<any[]>([]);
  const [loadingOrders, setLoadingOrders] = useState(false);

  // 机构用户以 institution.plan 为准，个人用户 fallback 到 membership_tier
  const currentTier = user?.institution?.plan || user?.membership_tier || 'free';
  const isTrial = user?.is_member && currentTier === 'free';
  const trialEnd = user?.trial_ends_at ? new Date(user?.trial_ends_at) : null;
  const daysLeft = trialEnd
    ? Math.max(0, Math.ceil((trialEnd.getTime() - Date.now()) / (1000 * 60 * 60 * 24)))
    : 0;
  const membershipEnd = user?.membership_expires_at ? new Date(user?.membership_expires_at) : null;

  useEffect(() => {
    fetchOrders();
  }, []);

  const fetchOrders = async () => {
    setLoadingOrders(true);
    try {
      const { data } = await api.get('/payments/orders/');
      setOrders(data);
    } catch {
      // orders optional — not critical
    } finally {
      setLoadingOrders(false);
    }
  };

  const currentMeta = PLAN_META[currentTier] || PLAN_META.free;

  return (
    <PageWrapper>
      <div className="h-full w-full px-4 py-4 md:py-6 overflow-y-auto">
        <div className="max-w-4xl mx-auto space-y-6">
          {/* Header */}
          <div>
            <h2 className="text-2xl font-extrabold tracking-tight text-foreground">方案与账单</h2>
            <p className="text-sm text-muted-foreground font-medium mt-1">管理您的会员方案和支付记录</p>
          </div>

          {/* Current plan card */}
          <Card className="border-none shadow-sm rounded-2xl p-6 bg-card space-y-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className={cn('h-10 w-10 rounded-xl flex items-center justify-center', currentMeta.color)}>
                  <Crown className="h-5 w-5 text-white" />
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <h3 className="font-extrabold text-lg text-foreground">{currentMeta.label} 方案</h3>
                    {isTrial && (
                      <Badge variant="outline" className="text-[10px] font-extrabold border-amber-200 text-amber-700">
                        试用中
                      </Badge>
                    )}
                  </div>
                  <p className="text-[13px] text-muted-foreground font-medium">
                    {isTrial
                      ? `试用还剩 ${daysLeft} 天`
                      : membershipEnd
                        ? `到期时间: ${membershipEnd.toLocaleDateString('zh-CN')}`
                        : '免费方案'}
                  </p>
                </div>
              </div>
              {currentTier !== 'pro' && (
                <Button variant="apple" className="h-10 rounded-xl text-sm font-extrabold"
                  onClick={() => setCheckoutOpen(true)}>
                  升级方案
                </Button>
              )}
            </div>

            {/* Current plan features */}
            {currentTier !== 'free' && PLAN_FEATURES[currentTier] && (
              <div className="bg-unimind-bg-secondary rounded-2xl p-4">
                <p className="text-[10px] font-extrabold text-muted-foreground uppercase tracking-[0.2em] mb-3">当前功能</p>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-1.5">
                  {PLAN_FEATURES[currentTier]?.map((f, i) => (
                    <div key={i} className="flex items-center gap-2 text-[12px] font-medium text-foreground/70">
                      <Check className="h-3.5 w-3.5 text-unimind-green shrink-0" />
                      {f}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </Card>

          {/* Upgrade to... */}
          {currentTier !== 'pro' && (
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              {(Object.keys(PLAN_META) as string[])
                .filter(k => k !== 'free' && PLAN_META[k].priceM > (PLAN_META[currentTier]?.priceM || 0))
                .map((k) => {
                  const p = PLAN_META[k];
                  return (
                    <Card key={k} className="border-none shadow-sm rounded-2xl p-5 space-y-3 text-center">
                      <Badge className={cn('text-[10px] font-bold text-white', p.color)}>{p.label}</Badge>
                      <div>
                        <span className="text-2xl font-extrabold text-foreground">¥{p.priceM}</span>
                        <span className="text-xs text-muted-foreground font-medium">/月</span>
                      </div>
                      <ul className="text-left space-y-1">
                        {(PLAN_FEATURES[k] || []).slice(0, 4).map((f, i) => (
                          <li key={i} className="flex items-center gap-1.5 text-[11px] font-medium text-foreground/60">
                            <Check className="h-3 w-3 text-unimind-green shrink-0" /> {f}
                          </li>
                        ))}
                      </ul>
                      <Button variant="outline" size="sm" className="w-full h-9 rounded-xl text-xs font-bold"
                        onClick={() => setCheckoutOpen(true)}>
                        升级至 {p.label}
                      </Button>
                    </Card>
                  );
                })}
            </div>
          )}

          {/* Order history */}
          <Card className="border-none shadow-sm rounded-2xl p-6 space-y-4">
            <div className="flex items-center gap-2">
              <CreditCard className="h-5 w-5 text-muted-foreground" />
              <h3 className="font-extrabold text-sm text-foreground">支付记录</h3>
            </div>

            {loadingOrders ? (
              <div className="flex items-center justify-center py-12">
                <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
              </div>
            ) : orders.length === 0 ? (
              <div className="py-12 text-center">
                <p className="text-[13px] font-medium text-muted-foreground">暂无支付记录</p>
              </div>
            ) : (
              <div className="space-y-2">
                {orders.map((o: any) => (
                  <div key={o.id} className="flex items-center justify-between py-3 px-4 rounded-xl bg-unimind-bg-secondary/50">
                    <div>
                      <p className="text-[13px] font-bold text-foreground">
                        {o.plan} · {o.billing_cycle === 'annual' ? '年付' : '月付'}
                      </p>
                      <p className="text-[11px] text-muted-foreground font-medium">
                        {new Date(o.created_at).toLocaleDateString('zh-CN')} · {o.gateway}
                      </p>
                    </div>
                    <div className="text-right">
                      <p className="text-sm font-extrabold text-foreground">¥{(o.amount_cents / 100).toFixed(0)}</p>
                      <Badge variant={o.status === 'paid' ? 'default' : 'secondary'} className="text-[9px]">
                        {o.status === 'paid' ? '已支付' : o.status === 'pending' ? '待支付' : o.status}
                      </Badge>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </Card>
        </div>
      </div>

      <CheckoutModal open={checkoutOpen} onOpenChange={setCheckoutOpen} currentPlan={currentTier} />
    </PageWrapper>
  );
}
