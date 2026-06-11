import { WarningCircle, ArrowsClockwise } from '@phosphor-icons/react';
import { cn } from '@/lib/utils';

type InlineErrorProps = {
  message: string;
  onRetry?: () => void;
  className?: string;
};

export const InlineError: React.FC<InlineErrorProps> = ({ message, onRetry, className }) => (
  <div className={cn('flex flex-col items-center justify-center gap-3 py-12 text-center', className)}>
    <WarningCircle className="h-8 w-8 text-destructive/40" strokeWidth={1.5} />
    <p className="text-sm font-medium text-muted-foreground">{message}</p>
    {onRetry && (
      <button
        onClick={onRetry}
        className="inline-flex items-center gap-1.5 text-xs font-semibold text-primary hover:underline"
      >
        <ArrowsClockwise className="h-3 w-3" />
        Retry
      </button>
    )}
  </div>
);
