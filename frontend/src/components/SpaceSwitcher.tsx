import { t, useLocale } from '@/i18n';
import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Buildings, CaretDown, Check, User, Key } from '@phosphor-icons/react';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import api from '@/lib/api';
import { activeWorkspace, setActiveWorkspace } from '@/lib/activeWorkspace';
import { formatApiErrorToast } from '@/lib/apiError';
import { useWorkspace } from '@/lib/workspace';
import { useAuthStore } from '@/store/useAuthStore';
import type { LearningAccess } from '@/types/learning';
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger } from './ui/dropdown-menu';

export function SpaceSwitcher() {
  useLocale();
  const [open, setOpen] = useState(false);
  const [switching, setSwitching] = useState(false);
  const navigate = useNavigate();
  const userId = useAuthStore(state => state.user?.id);
  const { data: workspace, isPending, isError: workspaceError } = useWorkspace();
  const { data: access, isFetching, isError } = useQuery({
    queryKey: ['space-ai-usage', userId], enabled: open && !!userId, staleTime: 0,
    queryFn: ({ signal }) => api.get<LearningAccess>('/users/learning/access/', { signal }).then(response => response.data),
  });
  const inWorkspace = activeWorkspace() !== 'personal';
  const workspaceName = workspace?.workspace?.name || t('机构 Workspace');
  const usage = access?.ai_usage;
  const quota = isFetching ? t('正在读取 AI 额度…') : isError || !usage ? t('查看 AI 额度') : usage.unlimited ? t('AI 问答不限次') : !usage.configured && !usage.addon_remaining ? t('AI 基础额度待配置') : t('AI 剩余 {0} 次', { 0: usage.remaining });
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
      {inWorkspace ? <Buildings size={18} /> : <User size={18} />}<span>{switching ? t('正在切换…') : inWorkspace ? workspaceName : t('个人空间')}</span><CaretDown size={12} />
    </button></DropdownMenuTrigger>
    <DropdownMenuContent align="start" sideOffset={8} className="um-app-menu um-space-menu">
      <DropdownMenuLabel>{t('学习空间')}</DropdownMenuLabel>
      <DropdownMenuItem disabled={switching} onSelect={() => void switchSpace(null)}>
        <User size={19} /><div><strong>{t('个人空间')}</strong><span>{t('独立的个人学习、笔记与记录')}</span></div>{!inWorkspace && <Check size={16} aria-label={t('当前空间')} />}
      </DropdownMenuItem>
      {workspace?.workspaces?.length ? workspace.workspaces.map(item => <DropdownMenuItem key={item.id} disabled={switching || isPending || !item.service_active} onSelect={() => void switchSpace(item.id)}>
        <Buildings size={19} /><div><strong>{item.name}</strong><span>{item.service_active ? t('独立的机构学习、笔记与记录') : t('服务已暂停或到期')}</span></div>{activeWorkspace() === String(item.id) && <Check size={16} aria-label={t('当前空间')} />}
      </DropdownMenuItem>) : <DropdownMenuItem disabled={isPending || workspaceError} onSelect={() => navigate('/settings?section=institution')}>
        <Buildings size={19} /><div><strong>{workspaceName}</strong><span>{workspaceError ? t('暂时无法读取机构信息。') : t('查看或加入机构学习服务')}</span></div>
      </DropdownMenuItem>}
      <DropdownMenuItem disabled={isPending || switching} onSelect={() => navigate('/settings?section=institution')}>
        {workspace?.workspace ? <Buildings size={19} /> : <Key size={19} />}<div><strong>{workspaceError || workspace?.workspace ? t('机构与学习服务') : t('加入机构')}</strong><span>{workspace?.workspace ? t('查看机构信息、课程授权与服务期限') : t('输入机构邀请码，加入机构 Workspace')}</span></div>
      </DropdownMenuItem>
      <DropdownMenuSeparator />
      <DropdownMenuItem onSelect={() => navigate('/billing')}><div><strong>{quota}</strong><span>{t('两个空间仅共用账号 AI 额度')}</span></div></DropdownMenuItem>
    </DropdownMenuContent>
  </DropdownMenu>;
}
