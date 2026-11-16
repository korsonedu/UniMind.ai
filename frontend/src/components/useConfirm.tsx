import { t, useLocale } from '@/i18n';
import { useState, useCallback } from 'react';
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel,
  AlertDialogContent, AlertDialogDescription, AlertDialogFooter,
  AlertDialogHeader, AlertDialogTitle,
} from '@/components/ui/alert-dialog';

interface ConfirmOptions {
  title?: string;
  description: string;
  confirmText?: string;
  cancelText?: string;
  variant?: 'default' | 'destructive';
}

export function useConfirm() {
  useLocale();
  const [state, setState] = useState<{
    open: boolean;
    options: ConfirmOptions;
    resolve: (value: boolean) => void;
  } | null>(null);

  const confirm = useCallback((description: string, opts?: Partial<Omit<ConfirmOptions, 'description'>>): Promise<boolean> => {
    return new Promise((resolve) => {
      setState({
        open: true,
        options: {
          description,
          title: opts?.title,
          confirmText: opts?.confirmText,
          cancelText: opts?.cancelText,
          variant: opts?.variant ?? 'destructive',
        },
        resolve,
      });
    });
  }, []);

  const handleConfirm = useCallback(() => {
    state?.resolve(true);
    setState(null);
  }, [state]);

  const handleCancel = useCallback(() => {
    state?.resolve(false);
    setState(null);
  }, [state]);

  const Dialog = state ? (
    <AlertDialog open={state.open} onOpenChange={(open) => { if (!open) handleCancel(); }}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{state.options.title ?? t('确认操作')}</AlertDialogTitle>
          <AlertDialogDescription>{state.options.description}</AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel onClick={handleCancel}>
            {state.options.cancelText ?? t('取消')}
          </AlertDialogCancel>
          <AlertDialogAction
            onClick={handleConfirm}
            className={state.options.variant === 'destructive' ? 'bg-red-500 hover:bg-red-600' : ''}
          >
            {state.options.confirmText ?? t('确认')}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  ) : null;

  return { confirm, Dialog };
}
