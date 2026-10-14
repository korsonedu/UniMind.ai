import { Target, CalendarCheck, CheckCircle, ChartBar, BookOpen, Lightbulb, ChatCircleText, Brain, Stethoscope, WarningCircle, PlayCircle } from '@phosphor-icons/react';
import AgentChatLayout from '@/components/AgentChatLayout';
import NativeSessionSidebar from '@/components/NativeSessionSidebar';
import type { Bot } from '@/hooks/useAgentConversation';
import { useXiaoYuStore } from '@/store/useXiaoYuStore';

const findAssistantBot = (bots: Bot[]) => bots.find((bot: Bot) => bot.name === '小宇');

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
  const sharedConversationId = useXiaoYuStore(state => state.conversationId);
  return <AgentChatLayout
    appearance="native" layout="inline" inputTourClass="xiaoyu-input"
    sidebar={props => <NativeSessionSidebar sessions={props.sessions} activeSessionId={props.activeSessionId} onSelect={props.onLoadSession} onDelete={props.onDeleteSession} onNew={props.onNewConversation} botDisplayName={props.botDisplayName} projectControls={props.projectControls} onNewInProject={props.onNewInProject} />}
    findBot={findAssistantBot}
    skills={SKILLS} typewriterWords={['让小宇分析薄弱知识点', '让小宇安排今天的复习', '让小宇推荐适合的课程', '让小宇看看复习进度']}
    chatPlaceholder="和小宇对话…" resetMessage="已开始新对话"
    landingTitle="小宇" landingDescription="" botDisplayName="小宇"
    onDeleteSession={() => {}}
    onLoadSession={(session, handler) => handler(session)}
    onStepDone={(step, previous) => previous.map(message => message.toolStep?.call_id === step.call_id ? { ...message, toolStep: step } : message)}
    initialConversationId={sharedConversationId}
  />;
};

export default XiaoYu;
