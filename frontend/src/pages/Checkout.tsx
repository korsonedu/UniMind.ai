import { useEffect, useState, useRef } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import api from '@/lib/api';
import { Loader2, AlertCircle } from 'lucide-react';

export function Checkout() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const [error, setError] = useState('');
  const started = useRef(false);

  const plan = searchParams.get('plan') || 'starter';
  const cycle = searchParams.get('cycle') || 'annual';
  const gateway = searchParams.get('gateway') || 'stub';

  useEffect(() => {
    if (started.current) return;
    started.current = true;

    let cancelled = false;

    (async () => {
      try {
        const { data } = await api.post('/payments/create-session/', {
          plan,
          billing_cycle: cycle,
          gateway,
        });
        if (cancelled) return;
        if (data.checkout_url) {
          // Validate URL is from a known payment provider
          const url = new URL(data.checkout_url);
          const allowedHosts = ['checkout.stripe.com', 'pay.stripe.com', 'mapi.alipay.com', 'openapi.alipay.com', 'airwallex.com'];
          if (!allowedHosts.some(h => url.hostname === h || url.hostname.endsWith('.' + h))) {
            // Allow same-origin redirects and localhost for dev
            if (url.origin !== window.location.origin && url.hostname !== 'localhost') {
              setError('支付网关地址异常，请联系客服');
              return;
            }
          }
          window.location.href = data.checkout_url;
        } else {
          setError('支付网关未返回结算地址');
        }
      } catch (e: any) {
        if (cancelled) return;
        const msg =
          e?.response?.data?.error ||
          e?.response?.data?.detail ||
          e?.message ||
          '创建订单失败，请重试';
        setError(msg);
      }
    })();

    return () => { cancelled = true; };
  }, [plan, cycle, gateway]);

  return (
    <div className="flex min-h-screen items-center justify-center bg-unimind-bg-secondary">
      <div className="w-full max-w-sm mx-4 bg-card rounded-[2rem] border border-border shadow-dialog p-8 text-center">
        {error ? (
          <div className="space-y-5">
            <div className="mx-auto w-12 h-12 rounded-full bg-red-50 dark:bg-red-900/20 flex items-center justify-center">
              <AlertCircle className="h-6 w-6 text-red-500" />
            </div>
            <div>
              <h2 className="text-lg font-bold text-foreground">支付启动失败</h2>
              <p className="mt-1.5 text-sm text-muted-foreground">{error}</p>
            </div>
            <button
              onClick={() => navigate(-1)}
              className="text-sm font-bold text-primary hover:underline"
            >
              返回重试
            </button>
          </div>
        ) : (
          <div className="space-y-4">
            <Loader2 className="mx-auto h-8 w-8 animate-spin text-primary" />
            <div>
              <h2 className="text-lg font-bold text-foreground">正在创建订单…</h2>
              <p className="mt-1.5 text-sm text-muted-foreground">
                即将跳转至支付页面
              </p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
