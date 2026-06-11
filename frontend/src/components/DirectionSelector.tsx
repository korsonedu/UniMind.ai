import { useState } from 'react';
import { GraduationCap, Briefcase, Wrench, Check, BookOpen, Pen } from '@phosphor-icons/react';
import { cn } from '@/lib/utils';
import { Input } from '@/components/ui/input';

const CATEGORY_ICONS: Record<string, React.ElementType> = {
  '高中学科': BookOpen,
  '考研专业课': GraduationCap,
  '职业资格证': Briefcase,
};

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
  const [customName, setCustomName] = useState('');
  const [customOpen, setCustomOpen] = useState(false);

  const isPreset = categories.some(c => c.subjects.some(s => s.subject === selected[0]));
  const isCustomActive = selected.length === 1 && selected[0] !== '' && !isPreset;

  const handleCustomInputChange = (value: string) => {
    setCustomName(value);
    if (value.trim()) {
      onSelectionChange([value.trim()]);
    } else {
      onSelectionChange([]);
    }
  };

  const openCustom = () => {
    setCustomOpen(true);
    if (customName.trim()) {
      onSelectionChange([customName.trim()]);
    }
  };

  const toggle = (subjectKey: string) => {
    if (selected.includes(subjectKey)) {
      onSelectionChange([]);
    } else {
      setCustomOpen(false);
      setCustomName('');
      onSelectionChange([subjectKey]);
    }
  };

  const atLimit = selected.length >= maxSelections;

  return (
    <div className={cn('select-none space-y-4', className)}>
      {/* Custom — button → input */}
      {!customOpen ? (
        <button
          type="button"
          onClick={openCustom}
          className={cn(
            'w-full flex items-center gap-3 px-4 py-3.5 rounded-xl text-sm font-semibold transition-all duration-200',
            'border-2 border-dashed border-muted-foreground/25 hover:border-primary/40 hover:bg-accent/40 active:scale-[0.99]',
          )}
        >
          <div className="w-7 h-7 rounded-lg bg-muted flex items-center justify-center">
            <Pen className="h-3.5 w-3.5 text-muted-foreground" strokeWidth={2.5} />
          </div>
          <span>自定义学科</span>
        </button>
      ) : (
        <div
          className={cn(
            'rounded-xl border-2 p-4 transition-all duration-200',
            isCustomActive
              ? 'border-primary bg-primary/5 shadow-sm'
              : 'border-primary/30',
          )}
        >
          <div className="flex items-center gap-2.5 mb-3">
            <div
              className={cn(
                'w-7 h-7 rounded-lg flex items-center justify-center transition-colors',
                isCustomActive ? 'bg-primary text-primary-foreground' : 'bg-muted text-muted-foreground',
              )}
            >
              <Pen className="h-3.5 w-3.5" strokeWidth={2.5} />
            </div>
            <span className="text-sm font-extrabold">自定义学科</span>
          </div>
          <Input
            placeholder="输入你的学科名称，如：AP物理、雅思、高中化学…"
            value={customName}
            onChange={e => handleCustomInputChange(e.target.value)}
            autoFocus
            className="h-10 rounded-lg"
          />
        </div>
      )}

      {/* Divider */}
      <div className="relative py-1">
        <div className="absolute inset-0 flex items-center">
          <div className="w-full border-t border-border/60" />
        </div>
        <div className="relative flex justify-center">
          <span className="bg-card px-3 text-[10px] font-bold text-muted-foreground uppercase tracking-widest">
            或使用我们已配置好的预设学科
          </span>
        </div>
      </div>

      {/* Preset categories */}
      {categories.map((cat) => {
        const Icon = CATEGORY_ICONS[cat.name] || GraduationCap;

        return (
          <div key={cat.name}>
            <div className="flex items-center gap-2 mb-2.5">
              <div className="w-6 h-6 rounded-md flex items-center justify-center bg-muted">
                <Icon className="h-3.5 w-3.5 text-foreground/70" strokeWidth={2} />
              </div>
              <span className="text-[11px] font-extrabold text-muted-foreground tracking-widest uppercase">
                {cat.name}
              </span>
            </div>

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
    </div>
  );
}
