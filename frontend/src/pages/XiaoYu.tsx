import React from 'react';
import { Target, CalendarCheck, CheckCircle2, BarChart3, BookOpen, Lightbulb, MessageCircleQuestion, BrainCircuit } from 'lucide-react';
import { VisualCanvas, type VisualData } from './xiaoyu/DashboardPanel';
import AgentChatLayout from '@/components/AgentChatLayout';
import type { RightPanelProps } from '@/components/AgentChatLayout';
import type { Bot, Message, ConversationSession } from '@/hooks/useAgentConversation';

const SKILLS = [
  { icon: Target, label: '分析薄弱点', prompt: '帮我分析薄弱知识点，给出提升建议' },
  { icon: CalendarCheck, label: '制定学习计划', prompt: '根据我的现状制定一份学习计划' },
  { icon: CheckCircle2, label: '查看复习任务', prompt: '帮我看看今天有哪些需要复习的内容' },
  { icon: BarChart3, label: '学习数据总览', prompt: '帮我分析学习数据，看看整体情况' },
  { icon: BookOpen, label: '推荐课程', prompt: '根据我的薄弱点推荐适合的课程' },
  { icon: Lightbulb, label: '解释一个概念', prompt: '请帮我讲解一个知识点' },
  { icon: MessageCircleQuestion, label: '分析一道题', prompt: '帮我分析这道题的解题思路' },
  { icon: BrainCircuit, label: '总结知识点', prompt: '帮我总结某个知识点的核心内容' },
];

const extractLastVisual = (msgs: Message[]): VisualData | VisualData[] | null => {
  for (let i = msgs.length - 1; i >= 0; i--) {
    const m = msgs[i];
    const all = m.metadata?.all_visuals as VisualData[] | undefined;
    if (all?.length) return all;
    if (m.metadata?.visual) return m.metadata.visual as VisualData;
  }
  return null;
};

export const XiaoYu: React.FC = () => {
  return (
    <AgentChatLayout
      findBot={(bots) => bots.find((b: Bot) => b.name === '小宇')}
      skills={SKILLS}
      typewriterWords={['让小宇帮你制定学习计划', '让小宇分析薄弱知识点', '让小宇推荐适合的课程', '让小宇看看复习进度']}
      chatPlaceholder="和小宇对话..."
      resetMessage="已开始新对话"
      landingTitle="小宇XiaoYu让学习更具效率。对话即学习。"
      landingDescription="最懂你的学习agent，从数据分析到知识讲解，一个入口搞定"
      botDisplayName="小宇"
      onDeleteSession={() => {}}
      onLoadSession={(session, defaultHandler) => {
        defaultHandler(session);
      }}
      onDone={(refreshSessions) => {
        refreshSessions();
      }}
      onStepDone={(step, prev) => {
        return prev.map(m =>
          m.toolStep?.call_id === step.call_id ? { ...m, toolStep: step } : m
        );
      }}
      extractVisualFromStep={(step) => {
        if (step.name === 'render_visual' && step.visual) {
          return step.visual as VisualData;
        }
        return null;
      }}
      renderRightPanel={(rp: RightPanelProps) => (
        <VisualCanvas visual={rp.visual} />
      )}
    />
  );
};

export default XiaoYu;
