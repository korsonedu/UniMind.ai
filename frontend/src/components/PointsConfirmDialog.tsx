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
  const canAfford = balance >= cost;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[380px] rounded-2xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-base">
            <Coins className="h-5 w-5 text-amber-500" />
            {canAfford ? '确认消耗积分' : '积分不足'}
          </DialogTitle>
          <DialogDescription className="text-sm">
            {canAfford
              ? `即将消耗 ${cost} 积分用于「${featureName}」。确认继续？`
              : `「${featureName}」需要 ${cost} 积分，你当前只有 ${balance} 积分。刷几道题就能解锁啦！`
            }
          </DialogDescription>
        </DialogHeader>

        {canAfford && (
          <div className="flex items-center justify-between px-4 py-3 bg-muted/50 rounded-xl text-sm">
            <span className="text-muted-foreground">当前积分</span>
            <span className="font-black text-foreground">{balance}</span>
            <span className="text-muted-foreground text-xs">→</span>
            <span className="font-black text-amber-500">{balance - cost}</span>
          </div>
        )}

        <DialogFooter className="gap-2 sm:gap-2">
          <Button variant="outline" onClick={() => onOpenChange(false)} size="sm">
            取消
          </Button>
          {canAfford ? (
            <Button onClick={onConfirm} disabled={loading} size="sm">
              {loading ? '处理中...' : '确认消耗'}
            </Button>
          ) : (
            <Button
              onClick={() => {
                onOpenChange(false);
                window.location.href = '/test-ladder';
              }}
              size="sm"
            >
              去刷题赚积分
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};
