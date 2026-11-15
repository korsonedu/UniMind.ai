import { t, useLocale } from '@/i18n';
import React from 'react';
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover';
import { useAuthStore } from '@/store/useAuthStore';

export const EloPopover: React.FC = () => {
  useLocale();
  const user = useAuthStore(s => s.user);

  return (
    <Popover>
      <PopoverTrigger asChild>
        <button
          aria-label={t('ELO {0}，查看评分', { 0: user?.elo_score ?? t('暂无') })}
          className="um-app-elo"
        >
          <span className="um-app-elo-label">ELO</span>
          <span>{user?.elo_score ?? t('暂无')}</span>
        </button>
      </PopoverTrigger>
      <PopoverContent
        align="end"
        sideOffset={8}
        className="um-app-elo-panel w-[360px] p-0 border-border overflow-hidden"
      >
        <div className="px-5 pt-5 pb-3">
          <p className="text-xs font-medium text-muted-foreground">{t('ELO 评分')}</p>
          <p className="text-[26px] font-semibold text-foreground tabular-nums">{user?.elo_score}</p>
          <p className="text-xs text-muted-foreground leading-relaxed mt-2">
            {t('ELO 评分根据答题正确率、题目难度动态计算。')}</p>
        </div>
      </PopoverContent>
    </Popover>
  );
};
