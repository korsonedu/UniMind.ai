import { useEffect, useState } from 'react';
import { GraduationCap } from '@phosphor-icons/react';
import { useInstitutionStore } from '@/store/useInstitutionStore';
import { useAuthStore } from '@/store/useAuthStore';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import api from '@/lib/api';

interface ClassInfo {
  id: number;
  name: string;
  category: string;
  student_count: number;
}

export default function ClassSelector() {
  const { currentClassId, setCurrentClassId } = useInstitutionStore();
  const user = useAuthStore(s => s.user);
  const [classes, setClasses] = useState<ClassInfo[]>([]);

  useEffect(() => {
    api.get('/users/institution/me/classes/')
      .then(res => setClasses(res.data || []))
      .catch(() => {});
  }, []);

  if (user?.institution_role === 'student' || !user?.institution) return null;

  const grouped: Record<string, ClassInfo[]> = {};
  const uncategorized: ClassInfo[] = [];
  for (const c of classes) {
    if (c.category) {
      (grouped[c.category] ??= []).push(c);
    } else {
      uncategorized.push(c);
    }
  }

  const selectedClass = classes.find(c => c.id === currentClassId);

  return (
    <span className="inline-flex items-center gap-1">
      <Select
        value={currentClassId ? String(currentClassId) : 'all'}
        onValueChange={v => setCurrentClassId(v === 'all' ? null : Number(v))}
      >
        <SelectTrigger className="h-7 gap-1 border-0 bg-transparent hover:bg-muted/50 px-1.5 text-[11px] font-medium w-auto data-[placeholder]:text-muted-foreground/50">
          <GraduationCap className="h-3 w-3 text-muted-foreground/50 shrink-0" />
          <SelectValue>
            <span className="text-muted-foreground truncate max-w-[100px]">
              {currentClassId && selectedClass ? selectedClass.name : '全部班级'}
            </span>
          </SelectValue>
        </SelectTrigger>
        <SelectContent align="end" className="min-w-[180px]">
          <SelectItem value="all" className="text-xs">
            <span className="font-medium">全部班级</span>
            <span className="ml-auto text-muted-foreground text-[10px]">{classes.length} 班</span>
          </SelectItem>
          <div className="px-2 py-1 text-[10px] text-muted-foreground/50 border-b border-border/30 mb-0.5">
            选班级后，Agent 回答将针对该班
          </div>
          {Object.entries(grouped).map(([cat, items]) => (
            <div key={cat}>
              <div className="px-2 py-1 text-[10px] font-bold uppercase tracking-wider text-muted-foreground/50">
                {cat}
              </div>
              {items.map(c => (
                <SelectItem key={c.id} value={String(c.id)} className="text-xs">
                  <span className="truncate">{c.name}</span>
                  <span className="ml-auto text-muted-foreground text-[10px]">{c.student_count}人</span>
                </SelectItem>
              ))}
            </div>
          ))}
          {Object.keys(grouped).length === 0 && uncategorized.map(c => (
            <SelectItem key={c.id} value={String(c.id)} className="text-xs">
              <span className="truncate">{c.name}</span>
              <span className="ml-auto text-muted-foreground text-[10px]">{c.student_count}人</span>
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </span>
  );
}
