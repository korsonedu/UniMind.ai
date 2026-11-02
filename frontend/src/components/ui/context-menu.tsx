import * as React from 'react';
import * as ContextMenuPrimitive from '@radix-ui/react-context-menu';
import { CaretRight } from '@phosphor-icons/react';
import { cn } from '@/lib/utils';

export const ContextMenu = ContextMenuPrimitive.Root;
export const ContextMenuSub = ContextMenuPrimitive.Sub;

export function ContextMenuTrigger({ onKeyDown, ...props }: React.ComponentPropsWithoutRef<typeof ContextMenuPrimitive.Trigger>) {
  return <ContextMenuPrimitive.Trigger {...props} onKeyDown={event => {
    onKeyDown?.(event);
    if (!event.defaultPrevented && (event.key === 'ContextMenu' || (event.shiftKey && event.key === 'F10'))) {
      event.preventDefault();
      const rect = event.currentTarget.getBoundingClientRect();
      event.currentTarget.dispatchEvent(new MouseEvent('contextmenu', { bubbles: true, cancelable: true, clientX: rect.left + 8, clientY: rect.bottom }));
    }
  }} />;
}

const contentClass = 'z-50 min-w-[8rem] overflow-hidden rounded-md border bg-popover p-1 text-popover-foreground shadow-md um-motion-surface duration-[180ms] ease-out data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=open]:fade-in-0 data-[state=closed]:fade-out-0';
const itemClass = 'relative flex cursor-default select-none items-center gap-2 rounded-sm px-2 py-1.5 text-sm outline-none focus:bg-accent focus:text-accent-foreground data-[disabled]:pointer-events-none data-[disabled]:opacity-50';

export function ContextMenuContent({ className, ...props }: React.ComponentPropsWithoutRef<typeof ContextMenuPrimitive.Content>) {
  return <ContextMenuPrimitive.Portal><ContextMenuPrimitive.Content className={cn(contentClass, className)} {...props} /></ContextMenuPrimitive.Portal>;
}

export function ContextMenuItem({ className, ...props }: React.ComponentPropsWithoutRef<typeof ContextMenuPrimitive.Item>) {
  return <ContextMenuPrimitive.Item className={cn(itemClass, className)} {...props} />;
}

export function ContextMenuSeparator(props: React.ComponentPropsWithoutRef<typeof ContextMenuPrimitive.Separator>) {
  return <ContextMenuPrimitive.Separator {...props} className={cn('-mx-1 my-1 h-px bg-muted', props.className)} />;
}

export function ContextMenuSubTrigger({ className, children, ...props }: React.ComponentPropsWithoutRef<typeof ContextMenuPrimitive.SubTrigger>) {
  return <ContextMenuPrimitive.SubTrigger className={cn(itemClass, 'data-[state=open]:bg-accent', className)} {...props}>{children}<CaretRight className="ml-auto h-4 w-4" /></ContextMenuPrimitive.SubTrigger>;
}

export function ContextMenuSubContent({ className, ...props }: React.ComponentPropsWithoutRef<typeof ContextMenuPrimitive.SubContent>) {
  return <ContextMenuPrimitive.Portal><ContextMenuPrimitive.SubContent className={cn(contentClass, className)} {...props} /></ContextMenuPrimitive.Portal>;
}
