import React from 'react';
import { Coins } from 'lucide-react';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { useTranslation } from 'react-i18next';

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  cost: number;
  featureName: string;
  balance: number;
  onConfirm: () => void;
  loading?: boolean;
}

export const PointsConfirmDialog: React.FC<Props> = ({
  open, onOpenChange, cost, featureName, balance, onConfirm, loading,
}) => {
  const { t } = useTranslation('common');
  const canAfford = balance >= cost;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[380px] rounded-2xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-base">
            <Coins className="h-5 w-5 text-amber-500" />
            {canAfford ? t('pointsConfirmTitle') : t('pointsInsufficientTitle')}
          </DialogTitle>
          <DialogDescription className="text-sm">
            {canAfford
              ? t('pointsConfirmDesc', { cost, featureName })
              : t('pointsInsufficientDesc', { cost, featureName, balance })
            }
          </DialogDescription>
        </DialogHeader>

        {canAfford && (
          <div className="flex items-center justify-between px-4 py-3 bg-muted/50 rounded-xl text-sm">
            <span className="text-muted-foreground">{t('pointsBalance')}</span>
            <span className="font-black text-foreground">{balance}</span>
            <span className="text-muted-foreground text-xs">→</span>
            <span className="font-black text-amber-500">{balance - cost}</span>
          </div>
        )}

        <DialogFooter className="gap-2 sm:gap-2">
          <Button variant="outline" onClick={() => onOpenChange(false)} size="sm">
            {t('cancel')}
          </Button>
          {canAfford ? (
            <Button onClick={onConfirm} disabled={loading} size="sm">
              {loading ? t('processing') : t('pointsConfirm')}
            </Button>
          ) : (
            <Button
              onClick={() => {
                onOpenChange(false);
                window.location.href = '/test-ladder';
              }}
              size="sm"
            >
              {t('pointsEarnMore')}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};
