import { useState } from 'react';
import { Copy, X } from '@phosphor-icons/react';
import { toast } from 'sonner';

interface InvitePopoverProps {
  inviteSlug: string;
  onClose: () => void;
}

export function InvitePopover({ inviteSlug, onClose }: InvitePopoverProps) {
  const [regenerating, setRegenerating] = useState(false);

  const inviteUrl = inviteSlug
    ? `${window.location.origin}/join/${inviteSlug}`
    : '';

  const copyLink = () => {
    if (!inviteUrl) return;
    navigator.clipboard.writeText(inviteUrl);
    toast.success('已复制');
  };

  const regenerate = async () => {
    setRegenerating(true);
    try {
      const { default: api } = await import('@/lib/api');
      const res = await api.post('/users/institution/me/regenerate-invite-slug/');
      toast.success('邀请链接已重置');
      onClose(); // close on regenerate since slug changed
    } catch {
      toast.error('重置失败');
    }
    setRegenerating(false);
  };

  return (
    <div className="w-80 bg-card rounded-2xl shadow-xl border border-border p-4 space-y-3"
      onClick={e => e.stopPropagation()}
    >
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-black tracking-tight">邀请学生</h3>
        <button onClick={onClose} className="p-1 rounded-md hover:bg-muted transition-colors">
          <X className="h-3.5 w-3.5 text-muted-foreground" />
        </button>
      </div>

      <p className="text-xs text-muted-foreground">
        学生通过此链接注册后自动加入机构。
      </p>

      <div className="rounded-lg border border-border bg-muted/30 p-2.5">
        <div className="text-[10px] text-muted-foreground mb-1 font-bold uppercase tracking-wider">邀请链接</div>
        <div className="text-xs font-mono text-foreground break-all select-all cursor-text leading-relaxed">
          {inviteUrl || '—'}
        </div>
      </div>

      <div className="flex gap-2">
        <button
          onClick={copyLink}
          disabled={!inviteUrl}
          className="flex-1 flex items-center justify-center gap-1.5 py-2 rounded-lg bg-primary text-primary-foreground text-xs font-bold hover:opacity-90 transition-opacity"
        >
          <Copy className="h-3.5 w-3.5" />
          点击复制
        </button>
        <button
          onClick={regenerate}
          disabled={regenerating}
          className="px-3 py-2 rounded-lg border border-border text-xs text-muted-foreground hover:text-foreground transition-colors"
        >
          {regenerating ? '...' : '重置'}
        </button>
      </div>
    </div>
  );
}
