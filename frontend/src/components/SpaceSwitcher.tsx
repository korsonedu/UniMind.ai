import { t, useLocale } from '@/i18n';
import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Buildings, CaretDown, Check, User, Key } from '@phosphor-icons/react';
import { useLocation, useNavigate } from 'react-router-dom';
import api from '@/lib/api';
import { useWorkspace, syncWorkspace, workspacePath } from '@/lib/workspace';
import { formatApiErrorToast } from '@/lib/apiError';
import { toast } from 'sonner';
import { useAuthStore } from '@/store/useAuthStore';
import { useInstitutionStore } from '@/store/useInstitutionStore';
import type { LearningAccess } from '@/types/learning';
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger } from './ui/dropdown-menu';

export function SpaceSwitcher({ personalPath }: { personalPath: string }) {
  useLocale();
  const [open, setOpen] = useState(false);
  const [switching, setSwitching] = useState(false);
  const { pathname, search } = useLocation();
  const navigate = useNavigate();
  const userId = useAuthStore(state => state.user?.id);
  const hasCourseCatalog = useInstitutionStore(state => state.hasCourseCatalog);
  const featuresLoading = useInstitutionStore(state => state.loading);
  const { data: workspace, isPending: workspaceLoading, isError: workspaceError } = useWorkspace();
  const { data: access, isFetching, isError } = useQuery({
    queryKey: ['space-ai-usage', userId], enabled: open && !!userId, staleTime: 0,
    queryFn: ({ signal }) => api.get<LearningAccess>('/users/learning/access/', { signal }).then(response => response.data),
  });
  const institutionSettings = pathname === '/settings' && new URLSearchParams(search).get('section') === 'institution';
  const courseRoute = (institutionSettings && !!workspace?.workspace) || pathname === '/courses' || pathname.startsWith('/course/') || pathname === '/settings/institution';
  const personalRoute = ['/xiaoyu', '/notes', '/knowledge-tree', '/knowledge-builder'].some(path => pathname === path || pathname.startsWith(`${path}/`));
  const [selection, setSelection] = useState({ userId, courses: courseRoute });
  if (selection.userId !== userId || ((courseRoute || personalRoute) && selection.courses !== courseRoute)) {
    setSelection({ userId, courses: courseRoute });
  }
  const inCourses = courseRoute || (!personalRoute && selection.userId === userId && selection.courses);
  const courseName = workspace?.workspace?.name || t('课程 Workspace');
  const usage = access?.ai_usage;
  const quota = isFetching ? t('正在读取 AI 额度…') : isError || !usage ? t('查看 AI 额度') : usage.unlimited ? t('AI 问答不限次') : !usage.configured && !usage.addon_remaining ? t('AI 基础额度待配置') : t('AI 剩余 {0} 次', { 0: usage.remaining });
  async function switchInstitution(id: number) {
    if (switching) return;
    setSwitching(true);
    try {
      const result = await api.post(`${workspacePath}switch/`, { workspace_id: id });
      navigate('/courses');
      await syncWorkspace(result.data);
    } catch (error) { toast.error(formatApiErrorToast(error, t('暂时无法切换机构，请稍后重试。'))); }
    finally { setSwitching(false); }
  }

  return <DropdownMenu open={open} onOpenChange={setOpen} modal={false}>
    <DropdownMenuTrigger asChild><button type="button" className="um-space-switcher" aria-label={t('切换空间，当前为{0}', { 0: inCourses ? courseName : t('个人空间') })}>
      {inCourses ? <Buildings size={18} /> : <User size={18} />}<span>{inCourses ? courseName : t('个人空间')}</span><CaretDown size={12} />
    </button></DropdownMenuTrigger>
    <DropdownMenuContent align="start" sideOffset={8} className="um-app-menu um-space-menu">
      <DropdownMenuLabel>{t('学习空间')}</DropdownMenuLabel>
      <DropdownMenuItem onSelect={() => { if (inCourses || pathname !== '/xiaoyu') navigate(personalPath); }}>
        <User size={19} /><div><strong>{t('个人空间')}</strong><span>{t('和小宇一起探索个人学习项目')}</span></div>{!inCourses && <Check size={16} aria-label={t('当前空间')} />}
      </DropdownMenuItem>
      {workspace?.workspaces?.length ? workspace.workspaces.map(item => <DropdownMenuItem key={item.id} disabled={switching || workspaceLoading} onSelect={() => { if (item.is_current) navigate('/courses'); else void switchInstitution(item.id); }}>
        <Buildings size={19} /><div><strong>{item.name}</strong><span>{item.service_active ? t('课程、资料与课程小宇') : t('服务已暂停或到期')}</span></div>{inCourses && item.is_current && <Check size={16} aria-label={t('当前空间')} />}
      </DropdownMenuItem>) : <DropdownMenuItem disabled={featuresLoading || workspaceLoading || switching} onSelect={() => navigate(hasCourseCatalog ? '/courses' : '/settings?section=institution')}>
        <Buildings size={19} /><div><strong>{courseName}</strong><span>{hasCourseCatalog ? t('课程、资料与课程小宇') : t('查看或加入机构学习服务')}</span></div>{inCourses && <Check size={16} aria-label={t('当前空间')} />}
      </DropdownMenuItem>}
      <DropdownMenuItem disabled={workspaceLoading} onSelect={() => navigate('/settings?section=institution')}>
        {workspace?.workspace ? <Buildings size={19} /> : <Key size={19} />}<div><strong>{workspaceError || workspace?.workspace ? t('机构与学习服务') : t('加入机构')}</strong><span>{workspace?.workspace ? t('查看机构信息、课程授权与服务期限') : t('输入机构邀请码，加入课程 Workspace')}</span></div>
      </DropdownMenuItem>
      <DropdownMenuSeparator />
      <DropdownMenuItem onSelect={() => navigate('/billing')}><div><strong>{quota}</strong><span>{t('个人小宇与课程小宇共用账号额度')}</span></div></DropdownMenuItem>
    </DropdownMenuContent>
  </DropdownMenu>;
}
