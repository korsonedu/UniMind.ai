import { useEffect, useState, useRef } from 'react';
import { FileText, GraduationCap, MagicWand, CheckSquareOffset } from '@phosphor-icons/react';
import api from '@/lib/api';
import { processMathContent } from '@/lib/utils';
import QuestionPanel from './workbench/QuestionPanel';
import AgentChatLayout from '@/components/AgentChatLayout';
import type { RightPanelProps } from '@/components/AgentChatLayout';
import type { Bot, Message } from '@/hooks/useAgentConversation';

interface QuestionData {
  question: string;
  q_type: string;
  subjective_type?: string | null;
  options?: string[] | null;
  answer: string;
  grading_points?: string[] | null;
  difficulty_level: string;
  kp_name?: string;
  kp_code?: string;
  review_score?: number;
  review_feedback?: string;
}

const SKILLS = [
  { icon: FileText, label: '针对薄弱点出题', prompt: '根据班级薄弱知识点出题' },
  { icon: GraduationCap, label: '出一套模拟卷', prompt: '出一套期末模拟卷，30题，难度适中' },
  { icon: MagicWand, label: '自定义出题', prompt: '帮我出10道微积分极限的客观题' },
  { icon: CheckSquareOffset, label: '周测出题', prompt: '出一套周测，15题，覆盖最近学的知识点' },
];

// ── Right Panel Component ──

function WorkbenchRightPanel({ rp, savedIndices, setSavedIndices, manualPipelineTaskId, setManualPipelineTaskId }: {
  rp: RightPanelProps;
  savedIndices: Set<number>;
  setSavedIndices: React.Dispatch<React.SetStateAction<Set<number>>>;
  manualPipelineTaskId: number | null;
  setManualPipelineTaskId: React.Dispatch<React.SetStateAction<number | null>>;
}) {
  const prevMsgLenRef = useRef(0);

  // Clear savedIndices on new conversation
  if (rp.messages.length === 0 && savedIndices.size > 0) {
    setSavedIndices(new Set());
  }

  // Refresh metadata when messages change (after SSE done)
  useEffect(() => {
    if (rp.messages.length <= 0 || rp.messages.length === prevMsgLenRef.current) return;
    prevMsgLenRef.current = rp.messages.length;

    const refreshMetadata = async () => {
      if (!rp.bot) return;
      try {
        const hRes = await api.get('/ai/history/', { params: { bot_id: rp.bot.id, conversation_id: rp.conversationId } });
        if (hRes.data.length > 0) {
          const allMsgs: Message[] = hRes.data
            .filter((m: Record<string, unknown>) => m.content !== '[Thinking...]')
            .map((m: Record<string, unknown>) => ({
              ...m,
              content: processMathContent(m.content as string),
              visible: true,
            }));
          rp.setSessions(rp.groupIntoSessions(allMsgs));
        }
      } catch (e) { console.error('[Workbench] metadata fetch failed:', e); }
    };
    refreshMetadata();
  }, [rp.messages.length]);

  const generatedQuestions = rp.messages
    .filter(m => m.role === 'assistant' && (m.metadata as { generated_questions?: QuestionData[] })?.generated_questions?.length)
    .flatMap(m => (m.metadata as { generated_questions: QuestionData[] }).generated_questions);

  const activePipelineTaskId = manualPipelineTaskId || rp.messages
    .filter(m => m.role === 'assistant' && (m.metadata as { pipeline_task_id?: number | null })?.pipeline_task_id)
    .map(m => (m.metadata as { pipeline_task_id: number }).pipeline_task_id)
    .pop() || null;

  return (
    <QuestionPanel
      questions={generatedQuestions}
      savedIndices={savedIndices}
      pipelineTaskId={activePipelineTaskId}
      bot={rp.bot}
      onPipelineStart={setManualPipelineTaskId}
      onQuestionsSaved={(indices) => setSavedIndices(prev => { const next = new Set(prev); indices.forEach(i => next.add(i)); return next; })}
      onSystemMessage={(msg) => rp.doSend(msg)}
    />
  );
}

// ── Main Component ──

export default function Workbench() {
  const [manualPipelineTaskId, setManualPipelineTaskId] = useState<number | null>(null);
  const [savedIndices, setSavedIndices] = useState<Set<number>>(() => {
    try {
      const stored = localStorage.getItem('wb_saved_indices');
      return stored ? new Set(JSON.parse(stored)) : new Set();
    } catch { return new Set(); }
  });

  // Persist savedIndices to localStorage
  useEffect(() => {
    try { localStorage.setItem('wb_saved_indices', JSON.stringify(Array.from(savedIndices))); } catch {}
  }, [savedIndices]);

  return (
    <AgentChatLayout
      findBot={(bots) => bots.find((b: Bot) => b.bot_type === 'exam_generator')}
      skills={SKILLS}
      typewriterWords={['描述你的出题需求...', '根据薄弱知识点出题', '出一套期末模拟卷', '帮我出10道微积分客观题']}
      chatPlaceholder="描述出题需求..."
      resetMessage="已开始新对话"
      landingTitle="你好，我是命题官"
      landingDescription="你的 AI 命题官"
      skillTooltip="快捷出题"
      botDisplayName="命题官"
      processContent={processMathContent}
      onDone={(refreshSessions) => {
        refreshSessions();
      }}
      renderRightPanel={(rp) => (
        <WorkbenchRightPanel
          rp={rp}
          savedIndices={savedIndices}
          setSavedIndices={setSavedIndices}
          manualPipelineTaskId={manualPipelineTaskId}
          setManualPipelineTaskId={setManualPipelineTaskId}
        />
      )}
    />
  );
}
