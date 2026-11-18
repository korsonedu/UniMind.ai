import * as React from 'react';
import * as DropdownMenuPrimitive from '@radix-ui/react-dropdown-menu';
import { CaretUpDown, Check } from '@phosphor-icons/react';
import { cn } from '@/lib/utils';

export interface AppleSelectOption {
  value: string;
  label: string;
  badge?: string;
  disabled?: boolean;
}

export interface AppleSelectFooterAction {
  label: string;
  icon?: React.ReactNode;
  onSelect: () => void;
}

export interface AppleSelectProps {
  value: string;
  options: AppleSelectOption[];
  onValueChange: (value: string) => void;
  onOpenChange?: (open: boolean) => void;
  footerActions?: AppleSelectFooterAction[];
  ariaLabel?: string;
  placeholder?: string;
  className?: string;
  id?: string;
  disabled?: boolean;
}

export function AppleSelect({
  value,
  options,
  onValueChange,
  onOpenChange,
  footerActions,
  ariaLabel,
  placeholder,
  className,
  id,
  disabled = false,
}: AppleSelectProps) {
  const selectedOption = React.useMemo(
    () => options.find(opt => opt.value === value) ?? options[0] ?? null,
    [options, value]
  );

  const displayLabel = selectedOption?.label ?? placeholder ?? '';
  const displayBadge = selectedOption?.badge;

  return (
    <DropdownMenuPrimitive.Root onOpenChange={onOpenChange}>
      <DropdownMenuPrimitive.Trigger asChild disabled={disabled}>
        <button
          type="button"
          id={id}
          aria-label={ariaLabel}
          disabled={disabled}
          className={cn(
            'kb-apple-select-trigger group inline-flex min-h-[36px] items-center justify-between gap-2.5 rounded-[10px] border border-black/10 bg-white/85 px-3 py-1.5 text-left text-[13.5px] font-medium text-foreground shadow-[0_1px_2px_rgba(0,0,0,0.04)] backdrop-blur-md transition-all duration-150 hover:border-black/20 hover:bg-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/35 disabled:pointer-events-none disabled:opacity-50 dark:border-white/15 dark:bg-zinc-900/80 dark:hover:border-white/25 dark:hover:bg-zinc-900',
            className
          )}
        >
          <span className="kb-apple-select-value flex min-w-0 flex-1 items-center gap-2">
            <span className="kb-apple-select-label truncate">{displayLabel}</span>
            {displayBadge && (
              <span className="kb-apple-select-badge shrink-0 rounded-full border border-black/[0.08] bg-black/[0.04] px-2 py-0.5 text-[11px] font-medium leading-none text-muted-foreground dark:border-white/[0.12] dark:bg-white/[0.08]">
                {displayBadge}
              </span>
            )}
          </span>
          <span
            className="kb-apple-select-chevron inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-md bg-black/[0.04] text-muted-foreground transition-colors group-hover:bg-black/[0.07] group-hover:text-foreground dark:bg-white/[0.08] dark:group-hover:bg-white/[0.14]"
            aria-hidden="true"
          >
            <CaretUpDown size={14} weight="bold" />
          </span>
        </button>
      </DropdownMenuPrimitive.Trigger>

      <DropdownMenuPrimitive.Portal>
        <DropdownMenuPrimitive.Content
          align="start"
          sideOffset={6}
          collisionPadding={12}
          className="kb-apple-select-content z-[110] max-h-[min(360px,68dvh)] min-w-[var(--radix-dropdown-menu-trigger-width)] max-w-[min(420px,calc(100vw-24px))] overflow-y-auto rounded-xl border border-black/[0.08] bg-white/90 p-1.5 text-foreground shadow-[0_12px_32px_-4px_rgba(0,0,0,0.14),0_4px_12px_-2px_rgba(0,0,0,0.06)] backdrop-blur-xl duration-150 ease-out data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0 data-[state=closed]:zoom-out-95 data-[state=open]:zoom-in-95 dark:border-white/[0.12] dark:bg-zinc-900/90"
        >
          {options.map(option => {
            const isSelected = option.value === value;
            return (
              <DropdownMenuPrimitive.Item
                key={option.value}
                disabled={option.disabled}
                data-selected={isSelected ? 'true' : 'false'}
                data-state={isSelected ? 'checked' : 'unchecked'}
                onSelect={() => {
                  if (!option.disabled) {
                    onValueChange(option.value);
                  }
                }}
                className={cn(
                  'kb-apple-select-item relative flex cursor-pointer select-none items-center gap-2 rounded-lg px-2.5 py-1.5 text-[13.5px] leading-snug outline-none transition-colors hover:bg-primary/10 focus:bg-primary/10 data-[disabled]:pointer-events-none data-[disabled]:opacity-45',
                  isSelected && 'bg-primary/[0.06] font-medium text-foreground'
                )}
              >
                <span
                  className={cn(
                    'kb-apple-select-check inline-flex h-4 w-4 shrink-0 items-center justify-center text-primary transition-opacity',
                    isSelected ? 'opacity-100' : 'opacity-0'
                  )}
                  aria-hidden="true"
                >
                  <Check size={14} weight="bold" />
                </span>
                <span className="kb-apple-select-label flex-1 truncate">{option.label}</span>
                {option.badge && (
                  <span className="kb-apple-select-badge ml-2 shrink-0 rounded-full border border-black/[0.08] bg-black/[0.04] px-2 py-0.5 text-[11px] font-medium leading-none text-muted-foreground dark:border-white/[0.12] dark:bg-white/[0.08]">
                    {option.badge}
                  </span>
                )}
              </DropdownMenuPrimitive.Item>
            );
          })}
          {footerActions && footerActions.length > 0 && (
            <>
              <DropdownMenuPrimitive.Separator className="kb-apple-select-divider my-1 h-px bg-black/[0.06] dark:bg-white/[0.1]" />
              {footerActions.map((action, idx) => (
                <DropdownMenuPrimitive.Item
                  key={`${action.label}-${idx}`}
                  onSelect={action.onSelect}
                  className="kb-apple-select-item kb-apple-select-action relative flex cursor-pointer select-none items-center gap-2 rounded-lg px-2.5 py-1.5 text-[13.5px] font-medium leading-snug text-primary outline-none transition-colors hover:bg-primary/10 focus:bg-primary/10"
                >
                  <span className="inline-flex h-4 w-4 shrink-0 items-center justify-center" aria-hidden="true">
                    {action.icon}
                  </span>
                  <span className="kb-apple-select-label flex-1 truncate">{action.label}</span>
                </DropdownMenuPrimitive.Item>
              ))}
            </>
          )}
        </DropdownMenuPrimitive.Content>
      </DropdownMenuPrimitive.Portal>
    </DropdownMenuPrimitive.Root>
  );
}

export default AppleSelect;
