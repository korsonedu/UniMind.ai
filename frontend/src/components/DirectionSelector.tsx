import { useRef } from 'react';
import { GraduationCap, Briefcase, Wrench, Check, BookOpen } from 'lucide-react';
import { cn } from '@/lib/utils';

const CATEGORY_ICONS: Record<string, React.ElementType> = {
  '高中学科': BookOpen,
  '考研专业课': GraduationCap,
  '职业资格证': Briefcase,
};

const CATEGORY_COLORS: Record<string, string> = {};

interface Subject {
  subject: string;
  label: string;
  topics?: number;
}

interface SubjectCategory {
  name: string;
  subjects: Subject[];
}

interface DirectionSelectorProps {
  categories: SubjectCategory[];
  selected: string[];
  onSelectionChange: (selected: string[]) => void;
  maxSelections: number;
  className?: string;
}

export function DirectionSelector({
  categories,
  selected,
  onSelectionChange,
  maxSelections,
  className,
}: DirectionSelectorProps) {
  const SCROLL_DEBOUNCE = useRef(false);

  const toggle = (subjectKey: string) => {
    if (selected.includes(subjectKey)) {
      onSelectionChange(selected.filter(s => s !== subjectKey));
    } else if (selected.length < maxSelections) {
      onSelectionChange([...selected, subjectKey]);
    }
  };

  const toggleCustom = () => {
    if (selected.includes('custom')) {
      onSelectionChange([]);
    } else {
      onSelectionChange(['custom']);
    }
  };

  const atLimit = selected.length >= maxSelections;
  const hasCustom = selected.includes('custom');

  return (
    <div className={cn('select-none', className)}>
      {/* Counter */}
      {maxSelections < 999 && (
        <div className="flex items-center gap-2 mb-4 px-1">
          <div className="flex-1 h-1.5 rounded-full bg-muted overflow-hidden">
            <div
              className="h-full rounded-full bg-primary transition-[width] duration-300 ease-out"
              style={{ width: `${(selected.length / maxSelections) * 100}%` }}
            />
          </div>
          <span className="text-[10px] font-bold text-muted-foreground tabular-nums">
            {selected.length}/{maxSelections}
          </span>
        </div>
      )}

      <div className="space-y-4">
        {categories.map((cat) => {
          const Icon = CATEGORY_ICONS[cat.name] || GraduationCap;
          const colorClass = CATEGORY_COLORS[cat.name] || '';

          return (
            <div key={cat.name}>
              {/* Category header */}
              <div className="flex items-center gap-2 mb-2.5">
                <div
                  className={cn(
                    'w-6 h-6 rounded-md flex items-center justify-center bg-muted',
                    colorClass || 'border-muted',
                  )}
                >
                  <Icon className="h-3.5 w-3.5 text-foreground/70" strokeWidth={2} />
                </div>
                <span className="text-[11px] font-extrabold text-muted-foreground tracking-widest uppercase">
                  {cat.name}
                </span>
              </div>

              {/* Subject grid */}
              <div className="grid grid-cols-2 gap-1.5">
                {cat.subjects.map((sub) => {
                  const isSelected = selected.includes(sub.subject);
                  const disabled = atLimit && !isSelected;

                  return (
                    <button
                      key={sub.subject}
                      type="button"
                      disabled={disabled}
                      onClick={() => toggle(sub.subject)}
                      className={cn(
                        'group relative flex items-center gap-2.5 px-3 py-2.5 rounded-xl text-sm font-semibold transition-[color,background,border,box-shadow,transform] duration-200',
                        'border bg-card',
                        isSelected
                          ? 'border-primary/80 bg-primary/5 text-primary shadow-sm'
                          : disabled
                            ? 'border-border/50 bg-muted/30 text-muted-foreground/40 cursor-not-allowed'
                            : 'border-border hover:border-primary/25 hover:bg-accent/50 hover:shadow-sm active:scale-[0.98]',
                      )}
                    >
                      {/* Selection indicator */}
                      <div
                        className={cn(
                          'shrink-0 w-4 h-4 rounded-md border-2 flex items-center justify-center transition-[color,background,border,transform] duration-200',
                          isSelected
                            ? 'border-primary bg-primary scale-100'
                            : 'border-muted-foreground/25 group-hover:border-muted-foreground/40',
                        )}
                      >
                        {isSelected && <Check className="h-2.5 w-2.5 text-primary-foreground" strokeWidth={3} />}
                      </div>
                      <span className="truncate min-w-0">{sub.label}</span>
                    </button>
                  );
                })}
              </div>
            </div>
          );
        })}

        {/* Divider */}
        <div className="relative py-1">
          <div className="absolute inset-0 flex items-center">
            <div className="w-full border-t border-border/60" />
          </div>
          <div className="relative flex justify-center">
            <span className="bg-card px-3 text-[9px] font-bold text-muted-foreground uppercase tracking-widest">
              或
            </span>
          </div>
        </div>

        {/* Custom option */}
        <button
          type="button"
          onClick={toggleCustom}
          className={cn(
            'w-full flex items-center gap-3 px-4 py-3 rounded-xl text-sm font-semibold transition-all duration-200',
            'border bg-card',
            hasCustom
              ? 'border-primary/80 bg-primary/5 text-primary shadow-sm'
              : 'border-dashed border-muted-foreground/25 hover:border-primary/30 hover:bg-accent/40 active:scale-[0.99] text-muted-foreground',
          )}
        >
          <div
            className={cn(
              'shrink-0 w-8 h-8 rounded-lg flex items-center justify-center transition-colors',
              hasCustom ? 'bg-primary text-primary-foreground' : 'bg-muted',
            )}
          >
            <Wrench className="h-4 w-4" strokeWidth={2} />
          </div>
          <div className="text-left">
            <div className={cn(hasCustom ? 'text-primary' : 'text-foreground')}>自定义知识体系</div>
            <div className="text-[10px] font-normal text-muted-foreground mt-0.5">
              自行搭建和管理知识点结构
            </div>
          </div>
        </button>
      </div>
    </div>
  );
}
