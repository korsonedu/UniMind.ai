import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Envelope, ChatCircle, Copy } from '@phosphor-icons/react';
import { toast } from 'sonner';

interface ContactAdminModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  planLabel?: string;
}

const CONTACT_EMAIL = 'eular@unimind-ai.com';
const CONTACT_WECHAT = 'Korsonedu';

export function ContactAdminModal({ open, onOpenChange, planLabel }: ContactAdminModalProps) {
  const copyText = (text: string, label: string) => {
    navigator.clipboard.writeText(text);
    toast.success(`${label} 已复制`);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[420px] rounded-[2rem] border-none shadow-2xl bg-card p-0 overflow-hidden">
        <DialogHeader className="px-8 pt-8 pb-2 text-left space-y-2">
          <DialogTitle className="text-xl font-black tracking-tight text-foreground">
            {planLabel ? `升级至 ${planLabel} 方案` : '升级方案'}
          </DialogTitle>
          <DialogDescription className="text-[13px] font-medium text-muted-foreground leading-relaxed">
            目前暂未开放在线支付，请联系管理员完成方案升级。
          </DialogDescription>
        </DialogHeader>

        <div className="px-8 py-4 space-y-3">
          {/* Email */}
          <div className="flex items-center gap-4 p-4 rounded-2xl bg-unimind-bg-secondary">
            <div className="h-10 w-10 rounded-xl bg-primary/10 flex items-center justify-center shrink-0">
              <Envelope className="h-5 w-5 text-primary" />
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-[11px] font-bold text-muted-foreground uppercase tracking-wider">邮箱</p>
              <p className="text-[14px] font-bold text-foreground truncate">{CONTACT_EMAIL}</p>
            </div>
            <Button
              variant="ghost"
              size="icon"
              className="h-8 w-8 rounded-lg shrink-0"
              onClick={() => copyText(CONTACT_EMAIL, '邮箱')}
            >
              <Copy className="h-3.5 w-3.5" />
            </Button>
          </div>

          {/* WeChat */}
          <div className="flex items-center gap-4 p-4 rounded-2xl bg-unimind-bg-secondary">
            <div className="h-10 w-10 rounded-xl bg-emerald-500/10 flex items-center justify-center shrink-0">
              <ChatCircle className="h-5 w-5 text-emerald-500" />
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-[11px] font-bold text-muted-foreground uppercase tracking-wider">微信</p>
              <p className="text-[14px] font-bold text-foreground">{CONTACT_WECHAT}</p>
            </div>
            <Button
              variant="ghost"
              size="icon"
              className="h-8 w-8 rounded-lg shrink-0"
              onClick={() => copyText(CONTACT_WECHAT, '微信号')}
            >
              <Copy className="h-3.5 w-3.5" />
            </Button>
          </div>
        </div>

        <div className="px-8 pb-8 pt-2">
          <Button
            variant="outline"
            className="w-full h-11 rounded-xl text-sm font-bold"
            onClick={() => onOpenChange(false)}
          >
            我知道了
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
