import { useState, useEffect } from 'react';
import { Copy, Check, X } from '@phosphor-icons/react';
import { toast } from 'sonner';
import api from '@/lib/api';

interface InviteLinkDrawerProps {
  open: boolean;
  onClose: () => void;
}

export function InviteLinkDrawer({ open, onClose }: InviteLinkDrawerProps) {
  const [inviteSlug, setInviteSlug] = useState('');
  const [regenerating, setRegenerating] = useState(false);

  useEffect(() => {
    if (!open) return;
    api.get('/users/institution/me/')
      .then(res => {
        setInviteSlug(res.data?.institution?.invite_slug || '');
      })
      .catch(() => {});
  }, [open]);

  if (!open) return null;

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
      const res = await api.post('/users/institution/me/regenerate-invite-slug/');
      const newSlug = res.data?.invite_slug || '';
      setInviteSlug(newSlug);
      toast.success('邀请链接已重置');
    } catch {
      toast.error('重置失败');
    }
    setRegenerating(false);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center"
      onClick={onClose}
    >
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/20" />

      {/* Drawer */}
      <div className="relative w-full sm:max-w-md bg-card rounded-t-2xl sm:rounded-2xl shadow-2xl p-6 space-y-4 animate-in slide-in-from-bottom duration-200"
        onClick={e => e.stopPropagation()}
      >
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-black tracking-tight">邀请学生</h3>
          <button onClick={onClose} className="p-1 rounded-md hover:bg-muted transition-colors">
            <X className="h-4 w-4 text-muted-foreground" />
          </button>
        </div>

        <p className="text-xs text-muted-foreground">
          学生通过此链接注册后自动加入你的机构。
        </p>

        {/* URL display */}
        <div className="rounded-lg border border-border bg-muted/30 p-3">
          <div className="text-xs text-muted-foreground mb-1 font-bold uppercase tracking-wider">邀请链接</div>
          <div
            className="text-sm font-mono text-foreground break-all select-all cursor-text"
          >
            {inviteUrl || '加载中...'}
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
            {regenerating ? '重置中...' : '重置链接'}
          </button>
        </div>

        <p className="text-[10px] text-muted-foreground text-center">
          也可以直接选中上方链接手动复制
        </p>
      </div>
    </div>
  );
}
