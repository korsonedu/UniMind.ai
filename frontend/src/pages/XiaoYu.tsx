import { t, useLocale } from '@/i18n';
import { useCallback, useContext, useMemo, useState } from 'react';
import { createPortal } from 'react-dom';
import { Link } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import api from '@/lib/api';
import { activeWorkspace } from '@/lib/activeWorkspace';
import { learningUrl } from '@/lib/projectLearning';
import { useIsMobile } from '@/lib/useIsMobile';
import { useInstitutionStore } from '@/store/useInstitutionStore';
import type { CourseProgress } from './course-center/types';
import { LearningPathCanvas } from '@/components/LearningPathCanvas';
import { learningComposerId, useLearningWorkspace } from '@/components/LearningWorkspace';
import { Target, CalendarCheck, CheckCircle, ChartBar, BookOpen, Lightbulb, ChatCircleText, Brain, Stethoscope, WarningCircle, PlayCircle, NotePencil, CaretRight } from '@phosphor-icons/react';
import AgentChatLayout, { type AgentChatLayoutProps } from '@/components/AgentChatLayout';
import NativeSessionSidebar from '@/components/NativeSessionSidebar';
import { useNotesSidebarAvailability, WorkbenchSidebarContext } from '@/components/WorkspaceContext';
import { useAuthStore } from '@/store/useAuthStore';
import { useXiaoYuChat } from './xiaoyu/xiaoYuChatContext';
import '@/components/workbench/workbench.css';
import { WorkbenchOverviewBanner } from '@/components/workbench/WorkbenchOverviewBanner';
import { WorkbenchSourcesPane } from '@/components/workbench/WorkbenchSourcesPane';
import { WorkbenchStudioPane } from '@/components/workbench/WorkbenchStudioPane';
import { WorkbenchCitationContext } from '@/components/workbench/workbenchCitations';
import { queryKeys } from '@/lib/queryKeys';
import { selectedReadySources, useWorkbenchSources } from '@/lib/workbenchApi';
import { personalWorkbenchProjectId } from '@/lib/workbenchMode';
import type { ProjectSourceList, SourceAnchor } from '@/types/workbench';

const SKILLS = [
  { icon: Target, label: '制定学习路径', prompt: '我想系统学一个目标，能帮我制定学习路径吗？' },
  { icon: Target, label: '分析薄弱点', prompt: '帮我分析薄弱知识点，给出提升建议' },
  { icon: CalendarCheck, label: '制定复习安排', prompt: '根据我的薄弱点和到期复习情况，帮我安排今天的复习' },
  { icon: CheckCircle, label: '查看复习任务', prompt: '帮我看看今天有哪些需要复习的内容' },
  { icon: ChartBar, label: '学习数据总览', prompt: '帮我分析学习数据，看看整体情况' },
  { icon: BookOpen, label: '推荐课程', prompt: '根据我的薄弱点推荐适合的课程' },
  { icon: Lightbulb, label: '解释一个概念', prompt: '请帮我讲解一个知识点' },
  { icon: ChatCircleText, label: '分析一道题', prompt: '帮我分析这道题的解题思路' },
  { icon: Brain, label: '总结知识点', prompt: '帮我总结某个知识点的核心内容' },
  { icon: Stethoscope, label: '做诊断测试', prompt: '帮我做一次诊断测试，了解我的学习水平' },
  { icon: WarningCircle, label: '查看错题', prompt: '帮我分析错题，找出薄弱环节' },
  { icon: PlayCircle, label: '开始刷题', prompt: '帮我出几道题练习一下' },
];

export const XiaoYu = () => {
  useLocale();
  const { chat } = useXiaoYuChat();
  const userId = useAuthStore(state => state.user?.id);
  const projectId = personalWorkbenchProjectId(chat.projectId);
  const key = `${userId}:${chat.projectId}`;
  return projectId === null ? <XiaoYuProject key={key} /> : <XiaoYuWorkbench key={key} projectId={projectId} />;
};

function XiaoYuProject() {
  useLocale();
  const { chat } = useXiaoYuChat();
  const workspace = useLearningWorkspace();
  const isMobile = useIsMobile();
  const courseSpace = activeWorkspace();
  const { hasFeature, hasCourseCatalog } = useInstitutionStore();
  const { data: progress } = useQuery({
    queryKey: ['mobile-course-progress', courseSpace],
    enabled: isMobile && !chat.hasConversation && courseSpace !== 'personal' && hasCourseCatalog && hasFeature('course.video'),
    queryFn: async ({ signal }) => (await api.get<CourseProgress[]>('/courses/learning-progress/', { signal })).data,
    staleTime: 0,
    retry: false,
  });
  const resumeCourse = progress?.find(course => !course.is_finished && course.last_position > 0);
  useNotesSidebarAvailability(chat.hasConversation);
  return <>
    {workspace.sidebar.host && createPortal(<LearningPathCanvas workspace={workspace} messages={chat.messages} conversationId={chat.conversationId} />, workspace.sidebar.host)}
    <XiaoYuConversation
      getExtraPayload={workspace.getExtraPayload}
      toolbarAction={(!isMobile || chat.projectId) ? { icon: BookOpen, label: t('学习路径'), tooltip: t('在右侧查看学习路径'), onClick: workspace.openLearning } : undefined}
      landingShortcuts={isMobile ? ({ fillPrompt }) => (
        <div className="um-m-landing-prompts" aria-label={t('学习快捷入口')}>
          <div className="um-m-prompt-pills">
            <button type="button" className="um-m-prompt-pill" onClick={() => fillPrompt(t(SKILLS[0].prompt))}>
              <Target size={14} /><span>{t('制定学习路径')}</span>
            </button>
            <button type="button" className="um-m-prompt-pill" onClick={() => fillPrompt(t(SKILLS[6].prompt))}>
              <Lightbulb size={14} /><span>{t('解释一个概念')}</span>
            </button>
            <button type="button" className="um-m-prompt-pill" onClick={() => fillPrompt(t(SKILLS[11].prompt))}>
              <PlayCircle size={14} /><span>{t('开始刷题')}</span>
            </button>
            <Link className="um-m-prompt-pill" to="/notes?new=1">
              <NotePencil size={14} /><span>{t('新建笔记')}</span>
            </Link>
          </div>
          {resumeCourse && (
            <Link className="um-m-resume-strip um-m-card" to={learningUrl(`/course/${resumeCourse.course}?view=video`, chat.projectId)}>
              <PlayCircle size={17} weight="fill" className="um-m-resume-play" />
              <span>{t('继续观看')}</span>
              <CaretRight size={14} className="um-m-resume-arrow" />
            </Link>
          )}
        </div>
      ) : undefined}
    />
  </>;
}

function XiaoYuWorkbench({ projectId }: { projectId: number }) {
  const { chat } = useXiaoYuChat();
  const sidebar = useContext(WorkbenchSidebarContext);
  const { open: openSidebar } = sidebar;
  const workspace = useLearningWorkspace({ autoOpen: false });
  const getLearningPayload = workspace.getExtraPayload;
  const query = useWorkbenchSources(projectId);
  const client = useQueryClient();
  const selected = selectedReadySources(query.data?.sources ?? []);
  const [anchor, setAnchor] = useState<SourceAnchor | null>(null);
  const onSelect = useCallback((target: SourceAnchor) => {
    setAnchor(target);
    openSidebar('project-sources');
  }, [openSidebar]);
  const citationContext = useMemo(() => ({ onSelect, conversationId: chat.conversationId }), [onSelect, chat.conversationId]);
  const getSources = useCallback(() => client.getQueryData<ProjectSourceList>(queryKeys.workbench.sources(projectId)), [client, projectId]);
  const getExtraPayload = useCallback(() => ({
    workbench_source_ids: selectedReadySources(getSources()?.sources ?? []).map(source => source.id),
    ...getLearningPayload(),
  }), [getSources, getLearningPayload]);
  const beforeSend = useCallback(async () => {
    if (!getSources()) throw new Error(t('请先加载项目资料，再发送消息。'));
  }, [getSources]);
  return <WorkbenchCitationContext.Provider value={citationContext}>
    {workspace.sidebar.host && createPortal(
      <LearningPathCanvas workspace={workspace} messages={chat.messages} conversationId={chat.conversationId} />, workspace.sidebar.host,
    )}
    {sidebar.host && createPortal(<>
      <section id="sidebar-panel-project-sources" aria-labelledby="sidebar-tab-project-sources" role="tabpanel" className="um-right-panel-content um-wb-sidebar" hidden={sidebar.view !== 'project-sources'}>
        <WorkbenchSourcesPane projectId={projectId} query={query} activeAnchor={anchor}
          onSelect={onSelect} onBack={() => setAnchor(null)}
          conversationId={chat.conversationId} />
      </section>
      <section id="sidebar-panel-studio" aria-labelledby="sidebar-tab-studio" role="tabpanel" className="um-right-panel-content um-wb-sidebar" hidden={sidebar.view !== 'studio'}>
        <WorkbenchStudioPane projectId={projectId} selected={selected} />
      </section>
    </>, sidebar.host)}
    <XiaoYuConversation getExtraPayload={getExtraPayload} beforeSend={beforeSend} workbench={{
      canSend: !!query.data,
      renderEmpty: (onSend, canSend) => query.data && <WorkbenchOverviewBanner
        projectId={projectId} totalCount={query.data.total_count} selected={selected}
        canSend={canSend} onSend={onSend} />,
    }} />
  </WorkbenchCitationContext.Provider>;
}

function XiaoYuConversation(props: Pick<AgentChatLayoutProps, 'getExtraPayload' | 'toolbarAction' | 'beforeSend' | 'workbench' | 'landingShortcuts'>) {
  const { chat } = useXiaoYuChat();
  const isMobile = useIsMobile();
  return <AgentChatLayout
    {...props} composerId={learningComposerId}
    appearance="native" layout="inline" enableNoteMentions inputTourClass="xiaoyu-input"
    sidebar={props => <NativeSessionSidebar initialInstructions={chat.input} claimMenuRequest={props.claimMenuRequest} sessions={props.sessions} activeSessionId={props.activeSessionId} thinkingIds={props.thinkingIds} unreadIds={props.unreadIds} onSelect={props.onLoadSession} onUpdate={props.onUpdateSession} onDelete={props.onDeleteSession} onNew={props.onNewConversation} botDisplayName={props.botDisplayName} projectControls={props.projectControls} onNewInProject={props.onNewInProject} />}
    skills={SKILLS.map(skill => ({ ...skill, label: t(skill.label), prompt: t(skill.prompt) }))} typewriterWords={[t('让小宇分析薄弱知识点'), t('让小宇安排今天的复习'), t('让小宇推荐适合的课程'), t('让小宇看看复习进度')]}
    chatPlaceholder={isMobile ? t('问问小宇') : t('和小宇对话，@ 引用笔记…')}
    landingTitle={t('小宇')} landingDescription="" botDisplayName={t('小宇')}
    onDeleteSession={() => {}}
    onLoadSession={(session, handler) => handler(session)}
  />;
}

export default XiaoYu;
