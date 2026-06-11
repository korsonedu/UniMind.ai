import { cn } from '@/lib/utils';
import { type Icon, Package } from '@phosphor-icons/react';

type EmptyStateProps = {
  icon?: Icon;
  title: string;
  description?: string;
  className?: string;
};

export const EmptyState: React.FC<EmptyStateProps> = ({
  icon: Icon = Package,
  title,
  description,
  className,
}) => (
  <div className={cn('flex flex-col items-center justify-center py-16 text-center', className)}>
    <Icon className="h-10 w-10 text-muted-foreground/25 mb-4" strokeWidth={1.5} />
    <p className="text-sm font-bold text-muted-foreground">{title}</p>
    {description && (
      <p className="text-xs text-muted-foreground/60 mt-1 max-w-xs">{description}</p>
    )}
  </div>
);
