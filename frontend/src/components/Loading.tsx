import { Spinner } from '@phosphor-icons/react';
import { cn } from '@/lib/utils';

type LoadingProps = {
  message?: string;
  fullScreen?: boolean;
  size?: 'sm' | 'md' | 'lg';
  className?: string;
};

const sizeMap = { sm: 'h-5 w-5', md: 'h-8 w-8', lg: 'h-12 w-12' };

export const Loading: React.FC<LoadingProps> = ({
  message = 'Loading…',
  fullScreen = false,
  size = 'md',
  className,
}) => {
  const content = (
    <div
      className={cn(
        'flex flex-col items-center justify-center gap-3',
        fullScreen && 'h-dvh w-screen fixed inset-0 bg-background z-50',
        className
      )}
    >
      <Spinner className={cn('animate-spin text-muted-foreground/30', sizeMap[size])} />
      <p className="text-[10px] font-bold text-muted-foreground uppercase tracking-[0.2em]">{message}</p>
    </div>
  );

  return content;
};

export default Loading;
