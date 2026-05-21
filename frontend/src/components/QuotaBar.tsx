import { cn } from '@/lib/utils';
import { ArrowUpRight } from 'lucide-react';
import type { QuotaItem } from '@/store/useInstitutionStore';
import { quotaLabel } from '@/store/useInstitutionStore';

interface QuotaBarProps {
  resourceKey: string;
  quota: QuotaItem;
  onUpgrade?: () => void;
  compact?: boolean;
  className?: string;
}

const STATUS_STYLES = {
  normal: 'bg-emerald-500',
  warning: 'bg-amber-500',
  exhausted: 'bg-red-500',
} as const;

const STATUS_TRACK_STYLES = {
  normal: 'bg-emerald-100',
  warning: 'bg-amber-100',
  exhausted: 'bg-red-100',
} as const;

export function QuotaBar({ resourceKey, quota, onUpgrade, compact, className }: QuotaBarProps) {
  const { limit, used, pct, status } = quota;
  const unlimited = limit === null;
  const label = quotaLabel(resourceKey);

  if (compact) {
    return (
      <div className={cn('flex items-center gap-2', className)}>
        <div className={cn('h-1.5 flex-1 rounded-full', unlimited ? 'bg-emerald-100' : STATUS_TRACK_STYLES[status])}>
          <div
            className={cn('h-full rounded-full transition-all', unlimited ? 'bg-emerald-500' : STATUS_STYLES[status])}
            style={{ width: `${unlimited ? 100 : pct}%` }}
          />
        </div>
        <span className="text-[11px] font-medium text-muted-foreground whitespace-nowrap">
          {unlimited ? '∞' : `${used}/${limit}`}
        </span>
      </div>
    );
  }

  return (
    <div className={cn('space-y-1.5', className)}>
      <div className="flex items-center justify-between">
        <span className="text-[13px] font-bold text-foreground">{label}</span>
        <span className="text-[12px] font-medium text-muted-foreground">
          {unlimited ? '无限制' : `${used} / ${limit}`}
        </span>
      </div>
      <div className={cn('h-2 rounded-full', unlimited ? 'bg-emerald-100' : STATUS_TRACK_STYLES[status])}>
        <div
          className={cn('h-full rounded-full transition-all', unlimited ? 'bg-emerald-500' : STATUS_STYLES[status])}
          style={{ width: `${unlimited ? 100 : Math.max(pct, 4)}%` }}
        />
      </div>
      {status === 'warning' && (
        <p className="text-[11px] font-medium text-amber-600">
          即将用完，建议升级方案
        </p>
      )}
      {status === 'exhausted' && (
        <div className="flex items-center gap-2 pt-0.5">
          <p className="text-[11px] font-bold text-red-600">已用完</p>
          {onUpgrade && (
            <button
              onClick={onUpgrade}
              className="inline-flex items-center gap-1 text-[11px] font-extrabold text-primary hover:underline"
            >
              升级解锁更多 <ArrowUpRight className="h-3 w-3" />
            </button>
          )}
        </div>
      )}
    </div>
  );
}
