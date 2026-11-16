import { t, useLocale } from '@/i18n';
import { useLearningWorkspace } from '@/components/LearningWorkspace';
import { Target, CalendarCheck, CheckCircle, ChartBar, BookOpen, Lightbulb, ChatCircleText, Brain, Stethoscope, WarningCircle, PlayCircle } from '@phosphor-icons/react';
import AgentChatLayout from '@/components/AgentChatLayout';
import NativeSessionSidebar from '@/components/NativeSessionSidebar';
import { useNotesSidebarAvailability } from '@/components/WorkspaceContext';
import { useAuthStore } from '@/store/useAuthStore';
import { useXiaoYuChat } from './xiaoyu/xiaoYuChatContext';

const SKILLS = [
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
  return <XiaoYuProject key={`${userId}:${chat.projectId}`} />;
};

function XiaoYuProject() {
  useLocale();
  const { chat } = useXiaoYuChat();
  useNotesSidebarAvailability(chat.hasConversation);
  const { workspace, getExtraPayload, openLearning } = useLearningWorkspace();
  return <AgentChatLayout
    workspace={workspace} getExtraPayload={getExtraPayload}
    toolbarAction={{ icon: BookOpen, label: t('学习工作区'), tooltip: t('查看项目学习内容'), onClick: openLearning }}
    appearance="native" layout="inline" enableNoteMentions inputTourClass="xiaoyu-input"
    sidebar={props => <NativeSessionSidebar initialInstructions={chat.input} claimMenuRequest={props.claimMenuRequest} sessions={props.sessions} activeSessionId={props.activeSessionId} thinkingIds={props.thinkingIds} unreadIds={props.unreadIds} onSelect={props.onLoadSession} onUpdate={props.onUpdateSession} onDelete={props.onDeleteSession} onNew={props.onNewConversation} botDisplayName={props.botDisplayName} projectControls={props.projectControls} onNewInProject={props.onNewInProject} />}
    skills={SKILLS.map(skill => ({ ...skill, label: t(skill.label), prompt: t(skill.prompt) }))} typewriterWords={[t('让小宇分析薄弱知识点'), t('让小宇安排今天的复习'), t('让小宇推荐适合的课程'), t('让小宇看看复习进度')]}
    chatPlaceholder={t('和小宇对话，@ 引用笔记…')}
    landingTitle={t('小宇')} landingDescription="" botDisplayName={t('小宇')}
    onDeleteSession={() => {}}
    onLoadSession={(session, handler) => handler(session)}
  />;
};

export default XiaoYu;
