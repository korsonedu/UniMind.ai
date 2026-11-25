import { t, useLocale } from '@/i18n';
import { useCallback, useMemo, useState } from 'react';
import { createPortal } from 'react-dom';
import { useQueryClient } from '@tanstack/react-query';
import { LearningPathCanvas } from '@/components/LearningPathCanvas';
import { learningComposerId, useLearningWorkspace } from '@/components/LearningWorkspace';
import { Target, CalendarCheck, CheckCircle, ChartBar, BookOpen, Lightbulb, ChatCircleText, Brain, Stethoscope, WarningCircle, PlayCircle, Books } from '@phosphor-icons/react';
import AgentChatLayout, { type AgentChatLayoutProps } from '@/components/AgentChatLayout';
import NativeSessionSidebar from '@/components/NativeSessionSidebar';
import { useNotesSidebarAvailability } from '@/components/WorkspaceContext';
import { useAuthStore } from '@/store/useAuthStore';
import { useXiaoYuChat } from './xiaoyu/xiaoYuChatContext';
import { WorkbenchLayout, type WorkbenchTab } from '@/components/workbench/WorkbenchLayout';
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
  useNotesSidebarAvailability(chat.hasConversation);
  return <>
    {workspace.sidebar.host && createPortal(<LearningPathCanvas workspace={workspace} messages={chat.messages} conversationId={chat.conversationId} />, workspace.sidebar.host)}
    <XiaoYuConversation getExtraPayload={workspace.getExtraPayload}
      toolbarAction={{ icon: BookOpen, label: t('学习路径'), tooltip: t('在右侧查看学习路径'), onClick: workspace.openLearning }} />
  </>;
}

function XiaoYuWorkbench({ projectId }: { projectId: number }) {
  const { chat } = useXiaoYuChat();
  const workspace = useLearningWorkspace({ studio: true });
  const getLearningPayload = workspace.getExtraPayload;
  const stageCount = workspace.project?.plan.stages?.length ?? 0;
  const query = useWorkbenchSources(projectId);
  const client = useQueryClient();
  const selected = selectedReadySources(query.data?.sources ?? []);
  const noReadySources = query.data?.selected_count
    ? t('已选资料尚未就绪，当前仅使用通用知识')
    : t('未勾选任何资料，当前仅使用通用知识');
  const [anchor, setAnchor] = useState<SourceAnchor | null>(null);
  const [addOpen, setAddOpen] = useState(false);
  const [leftOpen, setLeftOpen] = useState(true);
  const [mobileTab, setMobileTab] = useState<WorkbenchTab>('chat');
  const onSelect = useCallback((target: SourceAnchor) => {
    setAnchor(target);
    setLeftOpen(true);
    setMobileTab('sources');
  }, [setAnchor, setLeftOpen, setMobileTab]);
  const citationContext = useMemo(() => ({ onSelect, conversationId: chat.conversationId }), [onSelect, chat.conversationId]);
  const getSources = useCallback(() => client.getQueryData<ProjectSourceList>(queryKeys.workbench.sources(projectId)), [client, projectId]);
  const getExtraPayload = useCallback(() => ({
    workbench_source_ids: selectedReadySources(getSources()?.sources ?? []).map(source => source.id),
    ...getLearningPayload(),
  }), [getSources, getLearningPayload]);
  const beforeSend = useCallback(async () => {
    if (!getSources()) throw new Error(t('请先加载项目资料，再发送消息。'));
  }, [getSources]);
  const openAdd = () => { setAnchor(null); setLeftOpen(true); setMobileTab('sources'); setAddOpen(true); };

  return <WorkbenchCitationContext.Provider value={citationContext}>
    {!!stageCount && workspace.sidebar.visible && workspace.sidebar.host && createPortal(
      <LearningPathCanvas workspace={workspace} messages={chat.messages} conversationId={chat.conversationId} />, workspace.sidebar.host,
    )}
    <XiaoYuConversation getExtraPayload={getExtraPayload} beforeSend={beforeSend} workbench={{
      canSend: !!query.data,
      composerContext: <div className="um-wb-grounding" role="status">
        <span data-warning={!!query.data && selected.length === 0}>
          <Books size={14} />{!query.data
            ? query.isError ? t('资料加载失败，请在资料面板重试') : t('正在读取项目资料…')
            : selected.length > 0 ? t('基于已选 {0} 份资料回答', { 0: selected.length }) : noReadySources}
        </span>
      </div>,
      renderEmpty: (onSend, canSend) => query.data && <WorkbenchOverviewBanner
        projectId={projectId} totalCount={query.data.total_count} selected={selected}
        canSend={canSend} onAdd={openAdd} onSend={onSend} />,
      wrapChat: children => <WorkbenchLayout
        sourceCount={query.data?.total_count ?? 0} reading={!!anchor}
        mobileTab={mobileTab} setMobileTab={setMobileTab} leftOpen={leftOpen} setLeftOpen={setLeftOpen}
        sources={<WorkbenchSourcesPane projectId={projectId} query={query} activeAnchor={anchor}
          onSelect={onSelect} onBack={() => setAnchor(null)} addOpen={addOpen} setAddOpen={setAddOpen}
          conversationId={chat.conversationId} />}
        studio={<WorkbenchStudioPane projectId={projectId} selected={selected} legacyPath={stageCount > 0 &&
          <button className="um-agent-button" onClick={() => { workspace.show('path'); workspace.openLearning(); }}>
            <BookOpen size={16} />{t('查看阶段计划 ({0})', { 0: stageCount })}
          </button>} />}>{children}</WorkbenchLayout>,
    }} />
  </WorkbenchCitationContext.Provider>;
}

function XiaoYuConversation(props: Pick<AgentChatLayoutProps, 'getExtraPayload' | 'toolbarAction' | 'beforeSend' | 'workbench'>) {
  const { chat } = useXiaoYuChat();
  return <AgentChatLayout
    {...props} composerId={learningComposerId}
    appearance="native" layout="inline" enableNoteMentions inputTourClass="xiaoyu-input"
    sidebar={props => <NativeSessionSidebar initialInstructions={chat.input} claimMenuRequest={props.claimMenuRequest} sessions={props.sessions} activeSessionId={props.activeSessionId} thinkingIds={props.thinkingIds} unreadIds={props.unreadIds} onSelect={props.onLoadSession} onUpdate={props.onUpdateSession} onDelete={props.onDeleteSession} onNew={props.onNewConversation} botDisplayName={props.botDisplayName} projectControls={props.projectControls} onNewInProject={props.onNewInProject} />}
    skills={SKILLS.map(skill => ({ ...skill, label: t(skill.label), prompt: t(skill.prompt) }))} typewriterWords={[t('让小宇分析薄弱知识点'), t('让小宇安排今天的复习'), t('让小宇推荐适合的课程'), t('让小宇看看复习进度')]}
    chatPlaceholder={t('和小宇对话，@ 引用笔记…')}
    landingTitle={t('小宇')} landingDescription="" botDisplayName={t('小宇')}
    onDeleteSession={() => {}}
    onLoadSession={(session, handler) => handler(session)}
  />;
}

export default XiaoYu;
