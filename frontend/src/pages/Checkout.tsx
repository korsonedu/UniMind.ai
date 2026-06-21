import { useEffect, useState, useCallback } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import api from '@/lib/api';
import { Spinner, WarningCircle, Ticket } from '@phosphor-icons/react';
import { Button } from '@/components/ui/button';

const PLAN_LABELS: Record<string, string> = {
  starter: 'Starter',
  growth: 'Growth',
  enterprise: 'Enterprise',
};

export function Checkout() {
  const { t } = useTranslation('common');
  const [searchParams] = useSearchParams();
  const [error, setError] = useState('');
  const [paying, setPaying] = useState(false);

  const plan = searchParams.get('plan') || 'starter';
  const cycle = searchParams.get('cycle') || 'annual';
  const gateway = searchParams.get('gateway') || 'stub';

  // Promo code
  const [couponCode, setCouponCode] = useState('');
  const [couponResult, setCouponResult] = useState<any>(null);
  const [validatingCoupon, setValidatingCoupon] = useState(false);

  const validateCoupon = useCallback(async (code: string) => {
    if (!code.trim()) { setCouponResult(null); return; }
    setValidatingCoupon(true);
    try {
      const { data } = await api.post('/payments/coupons/validate/', {
        code: code.trim(),
        plan: plan,
        billing_cycle: cycle,
      });
      setCouponResult(data);
    } catch (err: any) {
      setCouponResult({ valid: false, error: err.response?.data?.error || t('checkoutCouponError') });
    } finally { setValidatingCoupon(false); }
  }, [plan, cycle, t]);

  useEffect(() => {
    const timer = setTimeout(() => validateCoupon(couponCode), 500);
    return () => clearTimeout(timer);
  }, [couponCode, validateCoupon]);

  const handlePay = async () => {
    setPaying(true);
    setError('');
    try {
      const payload: any = { plan, billing_cycle: cycle, gateway };
      if (couponCode.trim() && couponResult?.valid) {
        payload.coupon_code = couponCode.trim();
      }
      const { data } = await api.post('/payments/create-session/', payload);
      if (data.checkout_url) {
        const url = new URL(data.checkout_url);
        const allowedHosts = ['checkout.stripe.com', 'pay.stripe.com', 'mapi.alipay.com', 'openapi.alipay.com', 'airwallex.com'];
        if (!allowedHosts.some(h => url.hostname === h || url.hostname.endsWith('.' + h))) {
          if (url.origin !== window.location.origin && url.hostname !== 'localhost') {
            setError(t('checkoutGatewayError'));
            setPaying(false);
            return;
          }
        }
        window.location.href = data.checkout_url;
      } else {
        setError(t('checkoutNoUrl'));
        setPaying(false);
      }
    } catch (e: any) {
      const msg =
        e?.response?.data?.error ||
        e?.response?.data?.detail ||
        e?.message ||
        t('checkoutFailed');
      setError(msg);
      setPaying(false);
    }
  };

  const planLabel = PLAN_LABELS[plan] || plan;
  const cycleLabel = cycle === 'annual' ? t('billingAnnual') : cycle === 'monthly' ? t('billingMonthly') : cycle;

  return (
    <div className="flex min-h-screen items-center justify-center bg-unimind-bg-secondary">
      <div className="w-full max-w-sm mx-4 bg-card rounded-[2rem] border border-border shadow-dialog p-8 text-center space-y-5">
        {error ? (
          <div className="space-y-5">
            <div className="mx-auto w-12 h-12 rounded-full bg-red-50 dark:bg-red-900/20 flex items-center justify-center">
              <WarningCircle className="h-6 w-6 text-red-500" />
            </div>
            <div>
              <h2 className="text-lg font-bold text-foreground">{t('checkoutFailedTitle')}</h2>
              <p className="mt-1.5 text-sm text-muted-foreground">{error}</p>
            </div>
            <button
              onClick={() => {
                setError('');
                setPaying(false);
              }}
              className="text-sm font-bold text-primary hover:underline"
            >
              {t('retry')}
            </button>
          </div>
        ) : (
          <>
            {/* Plan Summary */}
            <div>
              <h2 className="text-lg font-extrabold text-foreground">{t('checkoutConfirmTitle')}</h2>
              <p className="mt-1 text-sm text-muted-foreground">
                {planLabel} · {cycleLabel}
              </p>
            </div>

            {/* Promo Code */}
            <div className="space-y-2 text-left">
              <div className="relative">
                <Ticket className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                <input
                  type="text"
                  placeholder={t('checkoutCouponPlaceholder')}
                  value={couponCode}
                  onChange={e => setCouponCode(e.target.value)}
                  className="w-full h-10 pl-9 pr-3 rounded-xl border border-border bg-background text-sm font-medium placeholder:text-muted-foreground/50 focus:outline-none focus:ring-2 focus:ring-primary/20"
                />
                {validatingCoupon && (
                  <Spinner className="absolute right-3 top-1/2 -translate-y-1/2 h-4 w-4 animate-spin text-muted-foreground" />
                )}
              </div>

              {couponResult?.valid && (
                <div className="flex items-center gap-2 px-1">
                  <span className="inline-flex items-center gap-1 text-xs font-bold text-emerald-600 bg-emerald-50 dark:bg-emerald-900/20 px-2 py-0.5 rounded-full">
                    {'\u2713'} {t('checkoutCouponSaved', { amount: (couponResult.discount / 100).toFixed(2) })}
                  </span>
                  {couponResult.original_amount != null && (
                    <span className="text-xs text-muted-foreground line-through">
                      ¥{(couponResult.original_amount / 100).toFixed(2)}
                    </span>
                  )}
                  {couponResult.final_amount != null && (
                    <span className="text-xs font-bold text-foreground">
                      ¥{(couponResult.final_amount / 100).toFixed(2)}
                    </span>
                  )}
                </div>
              )}

              {couponResult?.valid === false && (
                <p className="text-xs text-red-500 px-1">{couponResult.error}</p>
              )}
            </div>

            {/* Pay Button */}
            <Button
              variant="apple"
              className="w-full h-12 rounded-xl font-bold text-sm"
              onClick={handlePay}
              disabled={paying}
            >
              {paying ? (
                <>
                  <Spinner className="h-4 w-4 animate-spin mr-2" />
                  {t('checkoutCreatingOrder')}
                </>
              ) : (
                t('checkoutPayNow')
              )}
            </Button>
          </>
        )}
      </div>
    </div>
  );
}
