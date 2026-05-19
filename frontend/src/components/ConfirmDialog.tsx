import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { useTranslation } from 'react-i18next';

interface ConfirmDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description: string;
  onConfirm: () => void;
  confirmLabel?: string;
  variant?: 'default' | 'destructive';
}

export function ConfirmDialog({
  open,
  onOpenChange,
  title,
  description,
  onConfirm,
  confirmLabel,
  variant = 'destructive',
}: ConfirmDialogProps) {
  const { t } = useTranslation('common');
  const resolvedConfirmLabel = confirmLabel || t('confirm');
  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent className="rounded-apple-3xl border-none shadow-2xl bg-card">
        <AlertDialogHeader>
          <AlertDialogTitle className="text-xl font-bold text-foreground">{title}</AlertDialogTitle>
          <AlertDialogDescription className="font-medium text-muted-foreground">{description}</AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel className="rounded-xl font-bold border-border text-foreground hover:bg-muted">{t('cancel')}</AlertDialogCancel>
          <AlertDialogAction
            onClick={onConfirm}
            className={`rounded-xl font-bold hover:opacity-90 ${variant === 'destructive' ? 'bg-destructive text-destructive-foreground' : 'bg-primary text-primary-foreground'}`}
          >
            {resolvedConfirmLabel}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
