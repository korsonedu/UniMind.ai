import { useState, useEffect } from 'react';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { PageWrapper } from '@/components/PageWrapper';
import { useAuthStore } from '@/store/useAuthStore';
import api from '@/lib/api';
import { toast } from 'sonner';
import { Check, Crown, CreditCard, Spinner, ArrowRight, Sparkle } from '@phosphor-icons/react';
import { cn } from '@/lib/utils';
import { ContactAdminModal } from '@/components/ContactAdminModal';

const PLAN: Record<string, { label: string; priceM: number; color: string; gradient: string }> = {
  free:       { label: 'Free', priceM: 0, color: 'bg-unimind-text-quaternary', gradient: 'from-neutral-400 to-neutral-500' },
  starter:    { label: 'Starter', priceM: 499, color: 'bg-primary', gradient: 'from-[#0071E3] to-[#0077ED]' },
  growth:     { label: 'Growth', priceM: 1299, color: 'bg-unimind-green', gradient: 'from-[#34C759] to-[#30D158]' },
  enterprise: { label: 'Enterprise', priceM: 3999, color: 'bg-amber-500', gradient: 'from-amber-500 to-amber-400' },
};

const PLAN_FEATURES: Record<string, string[]> = {
  starter: ['AI 出题无限制', 'Memorix 记忆复习', 'AI 学习助手', '交互式知识图谱', '完整学情报告', 'AI 智能大纲'],
  growth: ['答疑系统', '多教师协作', '实时自习室', '模拟考试', '班级对比报表', '数据导出'],
  enterprise: ['品牌定制 · 白标部署', '私有化部署', 'API 接入', 'SSO 单点登录', '审计日志', '学生端收费', 'SLA 99.9%'],
};

const fmtDate = (d: Date) =>
  new Intl.DateTimeFormat('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit' }).format(d);

const STATUS_LABEL: Record<string, string> = {
  paid: '已支付', pending: '待支付', expired: '已过期',
  refunded: '已退款', cancelled: '已取消',
};

export function BillingPage() {
  const { user } = useAuthStore();
  const [orders, setOrders] = useState<any[]>([]);
  const [loadingOrders, setLoadingOrders] = useState(false);
  const [contactOpen, setContactOpen] = useState(false);
  const [contactPlan, setContactPlan] = useState('');

  const currentTier = user?.institution?.plan || user?.membership_tier || 'free';
  const isTrial = user?.is_member && user?.membership_source === 'trial';
  const membershipEnd = user?.membership_expires_at ? new Date(user?.membership_expires_at) : null;
  const daysLeft = membershipEnd
    ? Math.max(0, Math.ceil((membershipEnd.getTime() - Date.now()) / (1000 * 60 * 60 * 24)))
    : 0;

  useEffect(() => { fetchOrders(); }, []);

  const fetchOrders = async () => {
    setLoadingOrders(true);
    try { const { data } = await api.get('/payments/orders/'); setOrders(data); }
    catch { toast.error('加载订单失败'); }
    finally { setLoadingOrders(false); }
  };

  const currentMeta = PLAN[currentTier] || PLAN.free;

  return (
    <PageWrapper>
      <div className="h-full w-full px-4 py-4 md:py-6 overflow-y-auto">
        <div className="max-w-4xl mx-auto space-y-5">

          {/* Header */}
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-[22px] font-black tracking-tight text-foreground">方案与账单</h2>
              <p className="text-[13px] text-muted-foreground font-semibold mt-0.5">管理会员方案和支付记录</p>
            </div>
          </div>

          {/* Current plan */}
          <Card className="border border-black/[0.04] shadow-none rounded-2xl p-5 bg-card space-y-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className={cn(
                  'h-10 w-10 rounded-xl flex items-center justify-center bg-gradient-to-br', currentMeta.gradient,
                )}>
                  <Crown className="h-5 w-5 text-white" />
                </div>
                <div className="leading-tight">
                  <div className="flex items-center gap-2">
                    <h3 className="font-extrabold text-[16px] text-foreground">{currentMeta.label} 方案</h3>
                    {isTrial && (
                      <Badge variant="outline" className="text-[10px] font-extrabold border-amber-200 text-amber-600 bg-amber-50">
                        试用中
                      </Badge>
                    )}
                  </div>
                  <p className="text-[12px] text-muted-foreground font-semibold">
                    {isTrial
                      ? `试用还剩 ${daysLeft} 天`
                      : membershipEnd
                        ? `到期时间：${fmtDate(membershipEnd)}`
                        : '免费方案 · 功能受限'}
                  </p>
                </div>
              </div>
              {currentTier !== 'enterprise' && (
                <Button variant="apple" className="h-9 px-4 rounded-xl text-[12px] font-extrabold gap-1.5"
                  onClick={() => { setContactPlan('Starter'); setContactOpen(true); }}>
                  <Sparkle className="h-3.5 w-3.5" /> 升级方案
                </Button>
              )}
            </div>
            {currentTier !== 'free' && PLAN_FEATURES[currentTier] && (
              <div className="bg-unimind-bg-secondary rounded-xl p-4">
                <p className="text-[10px] font-extrabold text-muted-foreground/40 uppercase tracking-[0.25em] mb-3">当前功能</p>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-1">
                  {PLAN_FEATURES[currentTier]?.map((f, i) => (
                    <div key={i} className="flex items-center gap-2 text-[12px] font-semibold text-foreground/55 py-0.5">
                      <Check className="h-3.5 w-3.5 text-unimind-green shrink-0" />
                      {f}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </Card>

          {/* Upgrade options */}
          {currentTier !== 'enterprise' && (
            <div>
              <p className="text-[11px] font-extrabold text-muted-foreground/40 uppercase tracking-[0.25em] mb-3 ml-1">可升级方案</p>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                {(Object.keys(PLAN) as string[])
                  .filter(k => k !== 'free' && PLAN[k].priceM > (PLAN[currentTier]?.priceM || 0))
                  .map((k) => {
                    const p = PLAN[k];
                    const feats = PLAN_FEATURES[k] || [];
                    return (
                      <Card key={k} className="border border-black/[0.04] shadow-none rounded-2xl p-4 space-y-3 text-center bg-card">
                        <Badge className={cn('text-[10px] font-extrabold text-white bg-gradient-to-br', p.gradient, 'border-none')}>
                          {p.label}
                        </Badge>
                        <div>
                          <span className="text-[26px] font-black text-foreground tabular-nums tracking-tight">¥{p.priceM}</span>
                          <span className="text-[11px] text-muted-foreground font-semibold ml-0.5">/月</span>
                        </div>
                        <ul className="text-left space-y-0.5">
                          {feats.slice(0, 4).map((f, i) => (
                            <li key={i} className="flex items-center gap-1.5 text-[11px] font-semibold text-foreground/50">
                              <Check className="h-3 w-3 text-unimind-green shrink-0" /> {f}
                            </li>
                          ))}
                        </ul>
                        <Button variant="outline" size="sm"
                          className="w-full h-9 rounded-xl text-[11px] font-extrabold border border-black/[0.06] hover:bg-unimind-bg-secondary gap-1"
                          onClick={() => { setContactPlan(p.label); setContactOpen(true); }}>
                          升级至 {p.label} <ArrowRight className="h-3 w-3" />
                        </Button>
                      </Card>
                    );
                  })}
              </div>
            </div>
          )}

          {/* Order history */}
          <Card className="border border-black/[0.04] shadow-none rounded-2xl p-5 space-y-4 bg-card">
            <div className="flex items-center gap-2">
              <CreditCard className="h-4.5 w-4.5 text-muted-foreground/50" />
              <h3 className="font-extrabold text-[13px] text-foreground">支付记录</h3>
            </div>

            {loadingOrders ? (
              <div className="flex items-center justify-center py-14">
                <Spinner className="h-5 w-5 animate-spin text-muted-foreground/25" />
              </div>
            ) : orders.length === 0 ? (
              <div className="py-14 text-center space-y-1">
                <p className="text-[13px] font-semibold text-muted-foreground">暂无支付记录</p>
                <p className="text-[11px] text-muted-foreground/50 font-medium">升级方案后将在此显示</p>
              </div>
            ) : (
              <div className="divide-y divide-border/40">
                {orders.map((o: any) => (
                  <div key={o.id} className="flex items-center justify-between py-3 first:pt-0 last:pb-0">
                    <div>
                      <p className="text-[13px] font-bold text-foreground capitalize">
                        {o.plan} · {o.billing_cycle === 'annual' ? '年付' : '月付'}
                      </p>
                      <p className="text-[11px] text-muted-foreground font-semibold mt-0.5">
                        {fmtDate(new Date(o.created_at))} · {o.gateway}
                      </p>
                    </div>
                    <div className="text-right">
                      <p className="text-[14px] font-extrabold text-foreground tabular-nums">¥{(o.amount_cents / 100).toFixed(0)}</p>
                      <Badge variant={o.status === 'paid' ? 'default' : 'secondary'}
                        className={cn('text-[9px] font-extrabold mt-0.5',
                          o.status === 'paid' && 'bg-emerald-50 text-emerald-700 border-emerald-200',
                        )}>
                        {STATUS_LABEL[o.status] || o.status}
                      </Badge>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </Card>
        </div>
      </div>
      <ContactAdminModal open={contactOpen} onOpenChange={setContactOpen} planLabel={contactPlan} />
    </PageWrapper>
  );
}
