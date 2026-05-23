import { useEffect, useState } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Loader2, Check, XCircle, ArrowRight, Home } from 'lucide-react';
import { cn } from '@/lib/utils';
import api from '@/lib/api';

export function PaymentResult() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const [status, setStatus] = useState<'checking' | 'paid' | 'failed'>('checking');
  const [mounted, setMounted] = useState(false);

  const redirectStatus = searchParams.get('redirect_status');
  const isStripeReturn = !!searchParams.get('payment_intent');

  useEffect(() => { requestAnimationFrame(() => setMounted(true)); }, []);

  useEffect(() => {
    const orderId = sessionStorage.getItem('last_order_id');
    if (!orderId) {
      if (redirectStatus === 'succeeded') { setStatus('paid'); }
      else { setStatus('failed'); }
      return;
    }

    let cancelled = false;
    let attempts = 0;

    const poll = async () => {
      while (attempts < 30 && !cancelled) {
        try {
          const { data } = await api.get(`/payments/orders/${orderId}/`);
          if (data.status === 'paid') {
            if (!cancelled) { setStatus('paid'); sessionStorage.removeItem('last_order_id'); }
            return;
          }
        } catch {}
        attempts++;
        await new Promise(r => setTimeout(r, 2000));
      }
      if (!cancelled) setStatus('failed');
    };

    poll();
    return () => { cancelled = true; };
  }, [redirectStatus]);

  return (
    <>
      <div className="fixed inset-0 pointer-events-none z-0 opacity-[0.015]"
        style={{ backgroundImage: `url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E")` }}
      />
      <div className="relative z-10 min-h-screen flex flex-col items-center justify-center px-4"
        style={{ background: 'radial-gradient(ellipse 60% 50% at 50% 50%, rgba(120,120,120,0.04) 0%, transparent 60%), #08080A' }}>

        <div className={cn(
          'w-full max-w-[320px] text-center space-y-6',
          'motion-safe:transition-all motion-safe:duration-700 motion-safe:ease-out',
          mounted ? 'translate-y-0 opacity-100' : 'translate-y-3 opacity-0',
        )}>

          {status === 'checking' && (
            <div className="space-y-5">
              <Loader2 className="h-8 w-8 animate-spin text-white/[0.10] mx-auto" />
              <div className="space-y-2">
                <h3 className="text-[15px] font-extrabold text-white/50 tracking-tight">确认支付状态</h3>
                <p className="text-[12px] text-white/15 font-semibold">正在查询支付结果&hellip;</p>
              </div>
            </div>
          )}

          {status === 'paid' && (
            <div className="space-y-5">
              <div className="relative mx-auto w-16 h-16">
                <div className="absolute inset-0 rounded-full bg-emerald-500/[0.06] scale-150" />
                <div className="absolute inset-0 rounded-full bg-emerald-500/[0.03] scale-[1.8] motion-safe:animate-pulse" />
                <div className="relative h-16 w-16 rounded-full bg-emerald-500/[0.08] flex items-center justify-center ring-1 ring-emerald-500/[0.08]">
                  <Check className="h-7 w-7 text-emerald-400/80" />
                </div>
              </div>
              <div className="space-y-1.5">
                <h3 className="text-[15px] font-extrabold text-white/80 tracking-tight">支付成功</h3>
                <p className="text-[12px] text-white/20 font-semibold">方案已升级，立即开始使用</p>
              </div>
              <Button variant="apple" className="h-10 px-6 rounded-xl text-[13px] font-extrabold gap-2 bg-white text-black hover:bg-white/90 shadow-lg shadow-white/5"
                onClick={() => navigate('/billing', { replace: true })}>
                查看方案与账单 <ArrowRight className="h-3.5 w-3.5" />
              </Button>
            </div>
          )}

          {status === 'failed' && (
            <div className="space-y-5">
              <div className="h-16 w-16 mx-auto rounded-full bg-amber-500/[0.06] flex items-center justify-center ring-1 ring-amber-500/[0.06]">
                <XCircle className="h-7 w-7 text-amber-400/40" />
              </div>
              <div className="space-y-1.5">
                <h3 className="text-[15px] font-extrabold text-white/50 tracking-tight">支付未完成</h3>
                <p className="text-[12px] text-white/15 font-semibold leading-relaxed">
                  {isStripeReturn ? '银行卡验证未通过或支付被取消' : '未能确认支付状态，请联系客服'}
                </p>
              </div>
              <div className="space-y-2">
                <Button variant="apple" className="w-full h-10 rounded-xl text-[13px] font-extrabold bg-white text-black hover:bg-white/90"
                  onClick={() => navigate('/billing', { replace: true })}>
                  返回方案与账单
                </Button>
                <Button variant="outline" className="w-full h-10 rounded-xl text-[13px] font-extrabold border-white/[0.06] text-white/30 hover:text-white/60 hover:bg-white/[0.03] gap-2"
                  onClick={() => navigate('/', { replace: true })}>
                  <Home className="h-3.5 w-3.5" /> 返回首页
                </Button>
              </div>
            </div>
          )}
        </div>
      </div>
    </>
  );
}
