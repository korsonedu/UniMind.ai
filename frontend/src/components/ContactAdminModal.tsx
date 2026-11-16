import { t, useLocale } from '@/i18n';
import { useEffect, useRef, useState } from 'react';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Envelope, Copy, Check } from '@phosphor-icons/react';
import { toast } from 'sonner';

interface ContactAdminModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  planLabel?: string;
}

const CONTACT_EMAIL = 'eular@unimind-ai.com';

export function ContactAdminModal({ open, onOpenChange, planLabel }: ContactAdminModalProps) {
  useLocale();
  const [copied, setCopied] = useState<string | null>(null);
  const copyTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => () => { if (copyTimer.current) clearTimeout(copyTimer.current); }, []);
  const copyText = (text: string, label: string) => {
    navigator.clipboard.writeText(text)
      .then(() => {
        setCopied(label);
        if (copyTimer.current) clearTimeout(copyTimer.current);
        copyTimer.current = setTimeout(() => setCopied(null), 2500);
        toast.success(t('{0} 已复制', { 0: t(label) }));
      })
      .catch(() => toast.error(t('复制{0}失败，请手动复制', { 0: t(label) })));
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[420px] rounded-[2rem] border-none shadow-2xl bg-card p-0 overflow-hidden">
        <DialogHeader className="px-8 pt-8 pb-2 text-left space-y-2">
          <DialogTitle className="text-xl font-black tracking-tight text-foreground">
            {planLabel ? t('咨询 {0}', { 0: planLabel }) : t('联系 UniMind.ai')}
          </DialogTitle>
          <DialogDescription className="text-[13px] font-medium text-muted-foreground leading-relaxed">
            {t('账号、学习服务或小宇使用问题，请通过邮箱联系我们。')}
          </DialogDescription>
        </DialogHeader>

        <div className="px-8 py-4 space-y-3">
          {/* Email */}
          <div className="flex items-center gap-4 p-4 rounded-2xl bg-unimind-bg-secondary">
            <div className="h-10 w-10 rounded-xl bg-primary/10 flex items-center justify-center shrink-0">
              <Envelope className="h-5 w-5 text-primary" />
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-[11px] font-bold text-muted-foreground uppercase tracking-wider">{t('邮箱')}</p>
              <p className="text-[14px] font-bold text-foreground truncate">{CONTACT_EMAIL}</p>
            </div>
            <Button
              variant="ghost"
              size="icon"
              className="h-8 w-8 rounded-lg shrink-0"
              aria-label={copied === '邮箱' ? t('邮箱已复制') : t('复制邮箱')}
              onClick={() => copyText(CONTACT_EMAIL, t('邮箱'))}
            >
              {copied === '邮箱' ? <Check className="h-3.5 w-3.5 text-emerald-600" /> : <Copy className="h-3.5 w-3.5" />}
            </Button>
          </div>
        </div>

        <div className="px-8 pb-8 pt-2">
          <Button
            variant="outline"
            className="w-full h-11 rounded-xl text-sm font-bold"
            onClick={() => onOpenChange(false)}
          >
            {t('我知道了')}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
