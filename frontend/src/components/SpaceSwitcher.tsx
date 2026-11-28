import { t, useLocale } from '@/i18n';
import { useState } from 'react';
import { Buildings, CaretDown, Check, User } from '@phosphor-icons/react';
import { toast } from 'sonner';
import api from '@/lib/api';
import { activeWorkspace, setActiveWorkspace } from '@/lib/activeWorkspace';
import { formatApiErrorToast } from '@/lib/apiError';
import { useWorkspace } from '@/lib/workspace';
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from './ui/dropdown-menu';

export function SpaceSwitcher() {
  useLocale();
  const [open, setOpen] = useState(false);
  const [switching, setSwitching] = useState(false);
  const { data: workspace, isPending } = useWorkspace();
  const inWorkspace = activeWorkspace() !== 'personal';
  const workspaceName = workspace?.workspace?.name || t('机构 Workspace');
  async function switchSpace(id: number | null) {
    if (switching || activeWorkspace() === String(id ?? 'personal')) return;
    setSwitching(true);
    try {
      await api.post('/users/workspace/select/', { workspace_id: id });
      setActiveWorkspace(id);
      window.location.assign('/xiaoyu');
    } catch (error) {
      toast.error(formatApiErrorToast(error, t('空间切换失败，请重试。')));
      setSwitching(false);
    }
  }

  return <DropdownMenu open={open} onOpenChange={setOpen} modal={false}>
    <DropdownMenuTrigger asChild><button type="button" className="um-space-switcher" disabled={switching} aria-label={t('切换空间，当前为{0}', { 0: inWorkspace ? workspaceName : t('个人空间') })}>
      <span>{switching ? t('正在切换…') : inWorkspace ? workspaceName : t('个人空间')}</span><CaretDown size={12} />
    </button></DropdownMenuTrigger>
    <DropdownMenuContent align="start" sideOffset={8} className="um-app-menu um-space-menu">
      <DropdownMenuItem disabled={switching} onSelect={() => void switchSpace(null)}>
        <User size={19} /><div><strong>{t('个人空间')}</strong></div>{!inWorkspace && <Check size={16} aria-label={t('当前空间')} />}
      </DropdownMenuItem>
      {workspace?.workspaces?.map(item => <DropdownMenuItem key={item.id} disabled={switching || isPending || !item.service_active} onSelect={() => void switchSpace(item.id)}>
        <Buildings size={19} /><div><strong>{item.name}</strong></div>{activeWorkspace() === String(item.id) && <Check size={16} aria-label={t('当前空间')} />}
      </DropdownMenuItem>)}
    </DropdownMenuContent>
  </DropdownMenu>;
}
