import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Trophy } from '@phosphor-icons/react';
import { cn } from '@/lib/utils';
import api from '@/lib/api';

export const AchievementPill: React.FC = () => {
  const navigate = useNavigate();
  const [count, setCount] = useState<number | null>(null);

  useEffect(() => {
    api.get('/users/me/achievements/')
      .then(res => setCount(res.data?.length || 0))
      .catch(() => {});
  }, []);

  if (count === null || count === 0) return null;

  return (
    <button
      aria-label={`成就 ${count} 个已解锁`}
      onClick={() => navigate('/achievements')}
      className={cn(
        "flex items-center gap-1.5 px-3 py-1.5 rounded-full border border-border",
        "bg-card shadow-sm hover:bg-muted hover:border-amber-300 transition-colors duration-200 cursor-pointer",
        "focus-visible:ring-2 focus-visible:ring-primary/20 focus-visible:outline-none",
      )}
    >
      <Trophy className="h-3.5 w-3.5 text-amber-500" weight="fill" />
      <span className="text-xs font-bold text-foreground tabular-nums">{count}</span>
    </button>
  );
};
