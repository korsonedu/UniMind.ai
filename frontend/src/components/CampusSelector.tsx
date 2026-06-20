/**
 * 校区切换器 — 在顶栏显示下拉切换当前校区
 */
import { useEffect, useState } from 'react';
import {
  Buildings, CaretDown, ArrowsLeftRight,
} from '@phosphor-icons/react';
import { Button } from '@/components/ui/button';
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem,
  DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { useInstitutionStore } from '@/store/useInstitutionStore';
import api from '@/lib/api';
import { cn } from '@/lib/utils';

interface ChildCampus {
  id: number;
  name: string;
  is_active: boolean;
}

export function CampusSelector() {
  const store = useInstitutionStore();
  const [children, setChildren] = useState<ChildCampus[]>([]);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    // Only load if user is an institution admin
    if (!store.institution) return;
    api.get('/users/institution/me/children/')
      .then(({ data }) => {
        setChildren(Array.isArray(data) ? data : []);
        setLoaded(true);
      })
      .catch(() => setLoaded(true));
  }, [store.institution]);

  if (!loaded || children.length === 0) return null;

  const currentCampus = store.currentCampusId
    ? children.find(c => c.id === store.currentCampusId)
    : null;

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="sm" className="gap-1 text-muted-foreground">
          <Buildings className="h-4 w-4" />
          <span className="max-w-[120px] truncate">
            {currentCampus ? currentCampus.name : '总校视图'}
          </span>
          <CaretDown className="h-3 w-3" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-48">
        <DropdownMenuLabel>切换校区</DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuItem
          onClick={() => store.switchCampus(null)}
          className={cn(!store.currentCampusId && 'bg-accent')}
        >
          <ArrowsLeftRight className="mr-2 h-4 w-4" />
          总校（聚合视图）
        </DropdownMenuItem>
        {children.filter(c => c.is_active).map(c => (
          <DropdownMenuItem
            key={c.id}
            onClick={() => store.switchCampus(c.id)}
            className={cn(store.currentCampusId === c.id && 'bg-accent')}
          >
            <Buildings className="mr-2 h-4 w-4" />
            {c.name}
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
