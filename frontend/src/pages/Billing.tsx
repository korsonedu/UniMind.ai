import { useState, useEffect } from 'react';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { PageWrapper } from '@/components/PageWrapper';
import { useAuthStore } from '@/store/useAuthStore';
import { useTranslation } from 'react-i18next';
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

const fmtDate = (d: Date) =>
  new Intl.DateTimeFormat(navigator.language || 'en', { year: 'numeric', month: '2-digit', day: '2-digit' }).format(d);


export function BillingPage() {
  const user = useAuthStore(s => s.user);
  const { t } = useTranslation('common');
  const [orders, setOrders] = useState<any[]>([]);
  const [loadingOrders, setLoadingOrders] = useState(false);
  const [contactOpen, setContactOpen] = useState(false);
  const [contactPlan, setContactPlan] = useState('');

  const currentTier = (user?.institution?.plan || user?.personal_plan || user?.membership_tier || 'free') as string;
  const isTrial = user?.is_member && user?.membership_source === 'trial';
  const membershipEnd = user?.membership_expires_at ? new Date(user?.membership_expires_at) : null;
  const daysLeft = membershipEnd
    ? Math.max(0, Math.ceil((membershipEnd.getTime() - Date.now()) / (1000 * 60 * 60 * 24)))
    : 0;

  useEffect(() => { fetchOrders(); }, []);

  const fetchOrders = async () => {
    setLoadingOrders(true);
    try { const { data } = await api.get('/payments/orders/'); setOrders(data); }
    catch { toast.error(t('billingLoadFailed')); }
    finally { setLoadingOrders(false); }
  };

  const currentMeta = PLAN[currentTier] || PLAN.free;

  const planFeatures = {
    starter: t('billingFeaturesStarter', { returnObjects: true }) as string[],
    growth: t('billingFeaturesGrowth', { returnObjects: true }) as string[],
    enterprise: t('billingFeaturesEnterprise', { returnObjects: true }) as string[],
  };

  const statusLabels: Record<string, string> = {
    paid: t('billingStatusPaid'),
    pending: t('billingStatusPending'),
    expired: t('billingStatusExpired'),
    refunded: t('billingStatusRefunded'),
    cancelled: t('billingStatusCancelled'),
  };

  return (
    <PageWrapper>
      <div className="h-full w-full px-4 py-4 md:py-6 overflow-y-auto">
        <div className="max-w-4xl mx-auto space-y-5">

          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-[22px] font-black tracking-tight text-foreground">{t('billingTitle')}</h2>
              <p className="text-[13px] text-muted-foreground font-semibold mt-0.5">{t('billingSubtitle')}</p>
            </div>
          </div>


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
                    <h3 className="font-extrabold text-[16px] text-foreground">{t('billingPlanSuffix', { plan: currentMeta.label })}</h3>
                    {isTrial && (
                      <Badge variant="outline" className="text-[10px] font-extrabold border-amber-200 dark:border-amber-800/40 text-amber-600 dark:text-amber-400 bg-amber-50 dark:bg-amber-950/30">
                        {t('billingTrial')}
                      </Badge>
                    )}
                  </div>
                  <p className="text-[12px] text-muted-foreground font-semibold">
                    {isTrial
                      ? t('billingTrialDaysLeft', { days: daysLeft })
                      : membershipEnd
                        ? t('billingExpiresAt', { date: fmtDate(membershipEnd) })
                        : t('billingFreeLimited')}
                  </p>
                </div>
              </div>
              {currentTier !== 'enterprise' && (
                <Button variant="apple" className="h-9 px-4 rounded-xl text-[12px] font-extrabold gap-1.5"
                  onClick={() => { setContactPlan('Starter'); setContactOpen(true); }}>
                  <Sparkle className="h-3.5 w-3.5" /> {t('upgrade')}
                </Button>
              )}
            </div>
            {currentTier !== 'free' && (planFeatures as Record<string, string[]>)[currentTier] && (
              <div className="bg-unimind-bg-secondary rounded-xl p-4">
                <p className="text-[10px] font-extrabold text-muted-foreground/40 uppercase tracking-[0.25em] mb-3">{t('billingCurrentFeatures')}</p>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-1">
                  {(planFeatures as Record<string, string[]>)[currentTier]?.map((f: string, i: number) => (
                    <div key={i} className="flex items-center gap-2 text-[12px] font-semibold text-foreground/55 py-0.5">
                      <Check className="h-3.5 w-3.5 text-unimind-green shrink-0" />
                      {f}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </Card>


          {currentTier !== 'enterprise' && (
            <div>
              <p className="text-[11px] font-extrabold text-muted-foreground/40 uppercase tracking-[0.25em] mb-3 ml-1">{t('billingAvailablePlans')}</p>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                {(Object.keys(PLAN) as string[])
                  .filter(k => k !== 'free' && PLAN[k].priceM > (PLAN[currentTier]?.priceM || 0))
                  .map((k) => {
                    const p = PLAN[k];
                    const feats = (planFeatures as Record<string, string[]>)[k] || [];
                    return (
                      <Card key={k} className="border border-black/[0.04] shadow-none rounded-2xl p-4 space-y-3 text-center bg-card">
                        <Badge className={cn('text-[10px] font-extrabold text-white bg-gradient-to-br', p.gradient, 'border-none')}>
                          {p.label}
                        </Badge>
                        <div>
                          <span className="text-[26px] font-black text-foreground tabular-nums tracking-tight">¥{p.priceM}</span>
                          <span className="text-[11px] text-muted-foreground font-semibold ml-0.5">{t('billingPerMonth')}</span>
                        </div>
                        <ul className="text-left space-y-0.5">
                          {feats.slice(0, 4).map((f: string, i: number) => (
                            <li key={i} className="flex items-center gap-1.5 text-[11px] font-semibold text-foreground/50">
                              <Check className="h-3 w-3 text-unimind-green shrink-0" /> {f}
                            </li>
                          ))}
                        </ul>
                        <Button variant="outline" size="sm"
                          className="w-full h-9 rounded-xl text-[11px] font-extrabold border border-black/[0.06] hover:bg-unimind-bg-secondary gap-1"
                          onClick={() => { setContactPlan(p.label); setContactOpen(true); }}>
                          {t('billingUpgradeTo', { plan: p.label })} <ArrowRight className="h-3 w-3" />
                        </Button>
                      </Card>
                    );
                  })}
              </div>
            </div>
          )}


          <Card className="border border-black/[0.04] shadow-none rounded-2xl p-5 space-y-4 bg-card">
            <div className="flex items-center gap-2">
              <CreditCard className="h-4.5 w-4.5 text-muted-foreground/50" />
              <h3 className="font-extrabold text-[13px] text-foreground">{t('billingPaymentHistory')}</h3>
            </div>

            {loadingOrders ? (
              <div className="flex items-center justify-center py-14">
                <Spinner className="h-5 w-5 animate-spin text-muted-foreground/25" />
              </div>
            ) : orders.length === 0 ? (
              <div className="py-14 text-center space-y-1">
                <p className="text-[13px] font-semibold text-muted-foreground">{t('billingNoOrders')}</p>
                <p className="text-[11px] text-muted-foreground/50 font-medium">{t('billingNoOrdersHint')}</p>
              </div>
            ) : (
              <div className="divide-y divide-border/40">
                {orders.map((o: any) => (
                  <div key={o.id} className="flex items-center justify-between py-3 first:pt-0 last:pb-0">
                    <div>
                      <p className="text-[13px] font-bold text-foreground capitalize">
                        {o.plan} · {o.billing_cycle === 'annual' ? t('billingAnnual') : t('billingMonthly')}
                      </p>
                      <p className="text-[11px] text-muted-foreground font-semibold mt-0.5">
                        {fmtDate(new Date(o.created_at))} · {o.gateway}
                      </p>
                    </div>
                    <div className="text-right">
                      <p className="text-[14px] font-extrabold text-foreground tabular-nums">¥{(o.amount_cents / 100).toFixed(0)}</p>
                      <Badge variant={o.status === 'paid' ? 'default' : 'secondary'}
                        className={cn('text-[9px] font-extrabold mt-0.5',
                          o.status === 'paid' && 'bg-emerald-50 dark:bg-emerald-950/30 text-emerald-700 dark:text-emerald-400 border-emerald-200 dark:border-emerald-800/40',
                        )}>
                        {statusLabels[o.status] || o.status}
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
