import { useId, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';

export interface NoteDialogOptions {
  title: string;
  initialValue?: string;
  description?: string;
  confirmText?: string;
  destructive?: boolean;
  onConfirm: (value: string) => void;
}

export default function NoteDialog({ title, initialValue, description, confirmText = '确定', destructive, onConfirm, onClose }: NoteDialogOptions & { onClose: () => void }) {
  const [value, setValue] = useState(initialValue ?? '');
  const descriptionId = useId();
  return <Dialog open onOpenChange={open => { if (!open) onClose(); }}>
    <DialogContent className="max-w-sm" aria-describedby={description ? descriptionId : undefined}>
      <DialogHeader><DialogTitle className="text-lg">{title}</DialogTitle>{description && <DialogDescription id={descriptionId}>{description}</DialogDescription>}</DialogHeader>
      <form onSubmit={event => { event.preventDefault(); onClose(); onConfirm(value.trim()); }}>
        {initialValue !== undefined && <Input autoFocus aria-label={title} value={value} onChange={event => setValue(event.target.value)} className="mb-5" />}
        <DialogFooter><Button type="button" variant="outline" onClick={onClose}>取消</Button><Button type="submit" variant={destructive ? 'destructive' : 'default'} disabled={initialValue !== undefined && !value.trim()}>{confirmText}</Button></DialogFooter>
      </form>
    </DialogContent>
  </Dialog>;
}
