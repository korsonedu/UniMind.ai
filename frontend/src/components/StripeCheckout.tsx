import { useState } from 'react';
import { loadStripe } from '@stripe/stripe-js';
import { Elements, PaymentElement, useStripe, useElements } from '@stripe/react-stripe-js';
import { Button } from '@/components/ui/button';
import { Loader2 } from 'lucide-react';

const stripePk = import.meta.env.VITE_STRIPE_PUBLISHABLE_KEY || '';
const stripePromise = stripePk ? loadStripe(stripePk) : null;

function CardForm({ orderId, onSuccess, onError }: {
  orderId: number;
  onSuccess: () => void;
  onError: (msg: string) => void;
}) {
  const stripe = useStripe();
  const elements = useElements();

  const handlePay = async () => {
    if (!stripe || !elements) return;
    sessionStorage.setItem('last_order_id', String(orderId));
    const { error } = await stripe.confirmPayment({
      elements,
      confirmParams: {
        return_url: `${window.location.origin}/payments/result`,
      },
      redirect: 'if_required',
    });
    if (error) {
      onError(error.message || '支付失败');
    } else {
      onSuccess();
    }
  };

  return (
    <div className="space-y-5">
      <PaymentElement />
      <Button
        onClick={handlePay}
        disabled={!stripe || !elements}
        className="w-full h-12 rounded-xl text-sm font-extrabold bg-zinc-900 hover:bg-zinc-800 text-white"
      >
        确认支付
      </Button>
    </div>
  );
}

function CardFormWrapper({ onSuccess, onBack }: {
  clientSecret: string;
  orderId: number;
  onSuccess: () => void;
  onBack: () => void;
}) {
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSuccess = () => {
    setLoading(false);
    onSuccess();
  };

  const handleError = (msg: string) => {
    setError(msg);
    setLoading(false);
  };

  return (
    <div className="space-y-5">
      <button
        onClick={onBack}
        className="flex items-center gap-1.5 text-sm font-semibold text-muted-foreground hover:text-foreground transition-colors mx-auto"
      >
        ← 返回选择方案
      </button>

      <CardForm orderId={orderId} onSuccess={handleSuccess} onError={handleError} />

      {loading && (
        <div className="flex items-center justify-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" /> 处理中...
        </div>
      )}

      {error && (
        <p className="text-sm text-red-500 font-medium text-center">{error}</p>
      )}
    </div>
  );
}

export function StripeCheckout({
  clientSecret,
  orderId,
  onSuccess,
  onBack,
}: {
  clientSecret: string;
  orderId: number;
  onSuccess: () => void;
  onBack: () => void;
}) {
  if (!stripePromise) {
    return (
      <div className="py-8 text-center">
        <p className="text-sm text-muted-foreground font-medium">Stripe 未配置</p>
        <p className="text-xs text-muted-foreground/60 mt-1">请联系管理员配置支付通道</p>
      </div>
    );
  }

  return (
    <Elements stripe={stripePromise} options={{ clientSecret }}>
      <CardFormWrapper clientSecret={clientSecret} orderId={orderId} onSuccess={onSuccess} onBack={onBack} />
    </Elements>
  );
}
