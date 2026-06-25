import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { useAuthStore } from '@/store/useAuthStore';
import { CheckoutModal } from './CheckoutModal';
import { X } from '@phosphor-icons/react';

export function TrialBanner() {
  const user = useAuthStore(s => s.user);
  const [show, setShow] = useState(true);
  const [checkoutOpen, setCheckoutOpen] = useState(false);

  if (!user?.is_member || user?.membership_source !== 'trial') return null;

  const expiresAt = user.membership_expires_at ? new Date(user.membership_expires_at) : null;
  if (!expiresAt) return null;

  const now = new Date();
  const daysLeft = Math.max(0, Math.ceil((expiresAt.getTime() - now.getTime()) / (1000 * 60 * 60 * 24)));

  if (daysLeft === 0) {
    return (
      <>
        <div className="bg-amber-50 border-b border-amber-200 px-4 py-2.5 flex items-center justify-between gap-3">
          <p className="text-[13px] font-bold text-amber-800">
            试用已到期，已降级为 Free 方案。升级即可恢复全部功能。
          </p>
          <div className="flex items-center gap-2 shrink-0">
            <Button size="sm" variant="apple" className="h-8 rounded-lg text-[11px] font-extrabold"
              onClick={() => setCheckoutOpen(true)}>
              立即升级
            </Button>
          </div>
        </div>
        <CheckoutModal open={checkoutOpen} onOpenChange={setCheckoutOpen} />
      </>
    );
  }

  if (!show) return null;

  const urgency = daysLeft <= 3 ? 'bg-amber-50 border-amber-200' : 'bg-primary/5 border-primary/10';

  return (
    <>
      <div className={cn('border-b px-4 py-2.5 flex items-center justify-between gap-3', urgency)}>
        <p className="text-[13px] font-bold text-foreground/80">
          试用期还剩 <span className="text-primary font-extrabold">{daysLeft}</span> 天 ·
          升级方案即可永久使用全部功能
        </p>
        <div className="flex items-center gap-2 shrink-0">
          <Button size="sm" variant="apple" className="h-8 rounded-lg text-[11px] font-extrabold"
            onClick={() => setCheckoutOpen(true)}>
            升级
          </Button>
          {daysLeft > 3 && (
            <button onClick={() => setShow(false)} className="text-muted-foreground hover:text-foreground">
              <X className="h-4 w-4" />
            </button>
          )}
        </div>
      </div>
      <CheckoutModal open={checkoutOpen} onOpenChange={setCheckoutOpen} />
    </>
  );
}
