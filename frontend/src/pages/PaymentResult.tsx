import { useEffect, useState } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Loader2, Check, XCircle, ArrowRight } from 'lucide-react';
import api from '@/lib/api';

export function PaymentResult() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const [status, setStatus] = useState<'checking' | 'paid' | 'failed'>('checking');

  const redirectStatus = searchParams.get('redirect_status');
  const isStripeReturn = !!searchParams.get('payment_intent');

  useEffect(() => {
    const orderId = sessionStorage.getItem('last_order_id');
    if (!orderId) {
      if (redirectStatus === 'succeeded') {
        setStatus('paid');
      } else {
        setStatus('failed');
      }
      return;
    }

    let cancelled = false;
    let attempts = 0;

    const poll = async () => {
      while (attempts < 30 && !cancelled) {
        try {
          const { data } = await api.get(`/payments/orders/${orderId}/`);
          if (data.status === 'paid') {
            if (!cancelled) setStatus('paid');
            sessionStorage.removeItem('last_order_id');
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
    <div className="min-h-screen flex items-center justify-center bg-unimind-bg p-4">
      <Card className="max-w-sm w-full rounded-3xl border-none shadow-2xl p-8 text-center space-y-6">
        {status === 'checking' && (
          <>
            <Loader2 className="h-10 w-10 animate-spin text-muted-foreground mx-auto" />
            <div>
              <h3 className="text-lg font-extrabold text-foreground">确认支付状态</h3>
              <p className="text-sm text-muted-foreground mt-1">正在查询支付结果...</p>
            </div>
          </>
        )}

        {status === 'paid' && (
          <>
            <div className="h-16 w-16 mx-auto rounded-full bg-unimind-green/10 flex items-center justify-center">
              <Check className="h-8 w-8 text-unimind-green" />
            </div>
            <div>
              <h3 className="text-lg font-extrabold text-foreground">支付成功</h3>
              <p className="text-sm text-muted-foreground mt-1">您的方案已升级，开始使用吧。</p>
            </div>
            <Button variant="apple" className="w-full h-11 rounded-xl font-extrabold gap-2"
              onClick={() => navigate('/billing', { replace: true })}>
              查看方案与账单 <ArrowRight className="h-4 w-4" />
            </Button>
          </>
        )}

        {status === 'failed' && (
          <>
            <div className="h-16 w-16 mx-auto rounded-full bg-amber-500/10 flex items-center justify-center">
              <XCircle className="h-8 w-8 text-amber-500" />
            </div>
            <div>
              <h3 className="text-lg font-extrabold text-foreground">支付未完成</h3>
              <p className="text-sm text-muted-foreground mt-1">
                {isStripeReturn ? '银行卡验证未通过或支付被取消。' : '未能确认支付状态，请联系客服。'}
              </p>
            </div>
            <div className="space-y-2">
              <Button variant="apple" className="w-full h-11 rounded-xl font-extrabold"
                onClick={() => navigate('/billing', { replace: true })}>
                返回方案与账单
              </Button>
              <Button variant="outline" className="w-full h-11 rounded-xl font-bold"
                onClick={() => navigate('/', { replace: true })}>
                返回首页
              </Button>
            </div>
          </>
        )}
      </Card>
    </div>
  );
}
