import { useTranslation } from 'react-i18next';
import { Globe } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';

interface LanguageSwitcherProps {
  variant?: 'compact' | 'full';
  className?: string;
}

export function LanguageSwitcher({ variant = 'compact', className }: LanguageSwitcherProps) {
  const { i18n } = useTranslation();
  const isZh = i18n.language?.startsWith('zh');

  const toggle = () => {
    i18n.changeLanguage(isZh ? 'en' : 'zh');
  };

  if (variant === 'compact') {
    return (
      <Button
        variant="ghost"
        size="sm"
        onClick={toggle}
        className={cn("h-8 rounded-full px-2.5 text-[11px] font-bold gap-1.5", className)}
      >
        <Globe className="h-3.5 w-3.5" />
        {isZh ? 'EN' : '中'}
      </Button>
    );
  }

  return (
    <button
      onClick={toggle}
      className={cn(
        "flex items-center gap-1.5 text-[13px] font-medium text-[#6E6E73] hover:text-[#1D1D1F] transition-colors",
        className
      )}
    >
      <Globe className="h-4 w-4" />
      {isZh ? 'English' : '中文'}
    </button>
  );
}
