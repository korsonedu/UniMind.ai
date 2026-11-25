import { useState } from 'react';
import * as Popover from '@radix-ui/react-popover';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ArrowLeft, Plus } from '@phosphor-icons/react';
import { Link, useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { t } from '@/i18n';
import type { ConversationProject } from '@/hooks/useConversationProjects';
import { useXiaoYuChat } from '@/pages/xiaoyu/xiaoYuChatContext';
import api from '@/lib/api';
import { normalizeApiError } from '@/lib/apiError';
import { companionReturnHref } from '@/lib/companionVideo';
import { useProjectLearning } from '@/lib/projectLearning';
import { queryKeys } from '@/lib/queryKeys';
import { importWorkbenchSource } from '@/lib/workbenchApi';
import { WorkspaceToolbar } from '@/components/WorkspaceToolbar';

function AddCourseToWorkbench({ courseId, projectId, conversationId }: {
  courseId: number;
  projectId: number | null;
  conversationId?: string;
}) {
  const [open, setOpen] = useState(false);
  const [selected, setSelected] = useState(projectId?.toString() ?? '');
  const [name, setName] = useState('');
  const client = useQueryClient();
  const navigate = useNavigate();
  const projects = useQuery({
    queryKey: ['course-import-projects'],
    queryFn: async ({ signal }) => (await api.get<ConversationProject[]>('/ai/projects/', { signal })).data,
    enabled: open,
  });
  const add = useMutation({
    mutationFn: async () => {
      let target = Number(selected);
      if (selected === 'new') {
        const { data } = await api.post<ConversationProject>('/ai/projects/', { name: name.trim() });
        target = data.id;
        setSelected(String(target));
        await client.cancelQueries({ queryKey: ['course-import-projects'], exact: true });
        client.setQueryData<ConversationProject[]>(['course-import-projects'], previous => [...(previous ?? []), data]);
      }
      const source = await importWorkbenchSource(target, { kind: 'course', course_id: courseId });
      return { source, target };
    },
    onSuccess: ({ source, target }) => {
      void client.invalidateQueries({ queryKey: queryKeys.workbench.sources(target) });
      setOpen(false);
      const message = source.status === 'failed' ? t('课程已加入工作台，资料解析失败') : t('课程已加入工作台');
      toast.success(message, { action: { label: t('打开工作台 →'), onClick: () => navigate(companionReturnHref(target, target === projectId ? conversationId : undefined)) } });
    },
  });

  return <Popover.Root open={open} onOpenChange={next => {
    if (add.isPending) return;
    if (next) add.reset();
    setOpen(next);
  }}>
    <Popover.Trigger asChild><button type="button" className="um-course-workbench-add" title={t('加入小宇工作台')}>
      <Plus size={16} />{t('加入工作台')}
    </button></Popover.Trigger>
    <Popover.Portal>
      <Popover.Content align="end" sideOffset={8} collisionPadding={12} className="um-native-agent um-course-workbench-popover"
        aria-label={t('加入小宇工作台')}>
        <form onSubmit={event => {
          event.preventDefault();
          if (!add.isPending && selected && (selected !== 'new' || name.trim())) add.mutate();
        }}>
          <label>{t('选择项目')}<select value={selected} disabled={projects.isPending || add.isPending}
            onChange={event => { setSelected(event.target.value); add.reset(); }} required>
            <option value="" disabled>{t('请选择工作台项目')}</option>
            {projects.data?.map(project => <option key={project.id} value={project.id}>{project.name}</option>)}
            <option value="new">{t('＋ 新建项目')}</option>
          </select></label>
          {selected === 'new' && <label>{t('项目名称')}<input maxLength={60} value={name} required
            disabled={add.isPending} onChange={event => setName(event.target.value)} /></label>}
          {projects.isPending && <p role="status">{t('正在读取项目…')}</p>}
          {projects.isError && <button type="button" className="um-agent-button" onClick={() => void projects.refetch()}>{t('项目列表读取失败，重试')}</button>}
          {add.isError && <p role="alert">{normalizeApiError(add.error, '课程加入失败，请重试。').message}</p>}
          <button type="submit" className="um-agent-button um-agent-button-primary"
            disabled={projects.isPending || add.isPending || !selected || (selected === 'new' && !name.trim())}>
            {add.isPending ? t('正在加入…') : t('加入工作台')}
          </button>
        </form>
      </Popover.Content>
    </Popover.Portal>
  </Popover.Root>;
}

export function CourseWorkbenchToolbar({ courseId, title, projectId, linkedConversation, canImport }: {
  courseId: number;
  title: string;
  projectId: number | null;
  linkedConversation?: string;
  canImport: boolean;
}) {
  const { chat } = useXiaoYuChat();
  const { data: project } = useProjectLearning(projectId);
  const conversationId = linkedConversation || (chat.projectId === projectId ? chat.conversationId : undefined);
  const back = project?.name ? t('回到「{0}」工作台', { 0: project.name }) : t('回到项目工作台');
  return <WorkspaceToolbar className="um-course-workbench-toolbar">
    {projectId ? <Link className="um-course-workbench-return" to={companionReturnHref(projectId, conversationId)} title={back}>
      <ArrowLeft size={17} /><span>{back}</span>
    </Link> : <span className="um-course-workbench-title" title={title}>{title}</span>}
    {canImport && <AddCourseToWorkbench courseId={courseId} projectId={projectId} conversationId={conversationId} />}
  </WorkspaceToolbar>;
}
