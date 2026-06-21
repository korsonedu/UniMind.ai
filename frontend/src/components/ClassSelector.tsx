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
  institution_id: number;
}

export default function ClassSelector() {
  const { currentClassId, setCurrentClassId } = useInstitutionStore();
  const user = useAuthStore(s => s.user);
  const [classes, setClasses] = useState<ClassInfo[]>([]);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    api.get('/users/institution/me/classes/')
      .then(res => setClasses(res.data || []))
      .catch(() => setClasses([]));
  }, []);

  // 仅教师/机构主可见，学生不显示
  if (user?.role === 'student' || !user?.institution) return null;

  // 按 category 分组
  const grouped: Record<string, ClassInfo[]> = {};
  const uncategorized: ClassInfo[] = [];
  for (const c of classes) {
    if (c.category) {
      if (!grouped[c.category]) grouped[c.category] = [];
      grouped[c.category].push(c);
    } else {
      uncategorized.push(c);
    }
  }

  const handleValueChange = (val: string) => {
    if (val === 'all') {
      setCurrentClassId(null);
    } else {
      setCurrentClassId(Number(val));
    }
  };

  const selectedClass = classes.find(c => c.id === currentClassId);
  const displayValue = currentClassId && selectedClass
    ? selectedClass.name
    : '全部班级';

  return (
    <div className="shrink-0 px-4 py-2 border-b border-border/30 bg-background flex items-center gap-3">
      <Select
        value={currentClassId ? String(currentClassId) : 'all'}
        onValueChange={handleValueChange}
        open={open}
        onOpenChange={setOpen}
      >
        <SelectTrigger className="h-8 gap-1.5 border-0 bg-muted/50 hover:bg-muted px-2.5 text-xs font-medium w-auto min-w-0 max-w-[220px] data-[placeholder]:text-muted-foreground">
          <GraduationCap className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
          <SelectValue>
            <span className="text-foreground truncate">{displayValue}</span>
          </SelectValue>
        </SelectTrigger>
        <SelectContent align="start" className="min-w-[200px]">
          {/* 全部班级 */}
          <SelectItem value="all" className="text-xs">
            <span className="font-medium">全部班级</span>
            <span className="ml-auto text-muted-foreground text-[10px]">
              {classes.length} 个班级
            </span>
          </SelectItem>

          {/* 按分类分组 */}
          {Object.entries(grouped).map(([cat, items]) => (
            <div key={cat}>
              <div className="px-2 py-1 text-[10px] font-bold uppercase tracking-wider text-muted-foreground/60">
                {cat}
              </div>
              {items.map(c => (
                <SelectItem key={c.id} value={String(c.id)} className="text-xs">
                  <span className="truncate">{c.name}</span>
                  <span className="ml-auto text-muted-foreground text-[10px] shrink-0">
                    {c.student_count} 人
                  </span>
                </SelectItem>
              ))}
            </div>
          ))}

          {/* 未分类 */}
          {uncategorized.length > 0 && Object.keys(grouped).length > 0 && (
            <div>
              <div className="px-2 py-1 text-[10px] font-bold uppercase tracking-wider text-muted-foreground/60">
                未分类
              </div>
              {uncategorized.map(c => (
                <SelectItem key={c.id} value={String(c.id)} className="text-xs">
                  <span className="truncate">{c.name}</span>
                  <span className="ml-auto text-muted-foreground text-[10px] shrink-0">
                    {c.student_count} 人
                  </span>
                </SelectItem>
              ))}
            </div>
          )}

          {/* 无分类时直接列出 */}
          {Object.keys(grouped).length === 0 && uncategorized.map(c => (
            <SelectItem key={c.id} value={String(c.id)} className="text-xs">
              <span className="truncate">{c.name}</span>
              <span className="ml-auto text-muted-foreground text-[10px] shrink-0">
                {c.student_count} 人
              </span>
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      {/* 选中班级时的提示 */}
      {currentClassId && selectedClass && (
        <span className="text-[10px] text-muted-foreground/50 font-medium">
          {selectedClass.student_count} 名学员
        </span>
      )}
    </div>
  );
}
