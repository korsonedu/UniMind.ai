import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  blockAssessment,
  ensureBlockProject,
  generateAtomMicroLesson,
  getAtomMicroLesson,
  getBlockResources,
  inferAtomDifficultyTier,
  resolvePublicAssetLink,
} from '@/lib/knowledgeBuilderApi';
import type {
  AtomDifficultyTier,
  AtomMicroLessonResponse,
  BlockQuizMode,
  BlockStep,
  KnowledgeTreeBuildDetail,
  LearningBlock,
  MicroLessonCitation,
  MicroLessonStyle,
  SourceAlignmentItem,
  TreeAtomPoint,
} from '@/types/knowledgeBuilder';
import { learningKey, learningUrl, useProjectLearning, type ProjectLearning } from '@/lib/projectLearning';
import { MarkdownContent } from '@/components/MarkdownContent';
import { InlineVisualCard } from '@/components/InlineVisualCard';
import { DshToolCard, type DshCard } from '@/components/DshToolCard';
import { BlockResourceDrawer } from '@/components/BlockResourceDrawer';
import { PracticeQuizCard } from '@/pages/xiaoyu/visuals/PracticeQuizCard';
import type { VisualData } from '@/pages/xiaoyu/visuals';
import { useXiaoYuChat } from '@/pages/xiaoyu/xiaoYuChatContext';
import { useSpeechNarration } from '@/hooks/useSpeechNarration';
import { Link } from 'react-router-dom';
import { useAuthStore } from '@/store/useAuthStore';
import { t } from '@/i18n';

interface Props {
  tree: KnowledgeTreeBuildDetail;
  block: LearningBlock;
  initialAtomId?: number | null;
  project?: ProjectLearning;
  onClose: () => void;
  onChanged: () => void;
}

const studyGuides = {
  L1: {
    mark: '🟢',
    theme: 'border-emerald-200 bg-emerald-50 text-emerald-950 dark:border-emerald-900 dark:bg-emerald-950/40 dark:text-emerald-100',
    prompts: ['💬 用大白话 2 分钟讲透这个概念', '⚡ 出一道快检题考考我', '🧭 帮我理清它的核心要素'],
  },
  L2: {
    mark: '🟡',
    theme: 'border-amber-200 bg-amber-50 text-amber-950 dark:border-amber-900 dark:bg-amber-950/40 dark:text-amber-100',
    prompts: ['🔍 针对常见误区考我一道辨析题', '📊 帮我对比梳理核心差异', '⚖️ 结合实务场景帮我理解机制'],
  },
  L3: {
    mark: '🔴',
    theme: 'border-rose-200 bg-rose-50 text-rose-950 dark:border-rose-900 dark:bg-rose-950/40 dark:text-rose-100',
    prompts: ['🧪 手把手带我推演/算一遍', '📝 出一道实战计算或综合案例题', '🎯 拆解这个难点的解题步骤'],
  },
} satisfies Record<AtomDifficultyTier, { mark: string; theme: string; prompts: string[] }>;

const styleOptions: { value: MicroLessonStyle; label: string }[] = [
  { value: 'balanced', label: '标准均衡' },
  { value: 'intuition', label: '大白话直觉' },
  { value: 'exam', label: '考场辨析防坑' },
  { value: 'visual', label: '强图解板书' },
];

const blockNode = (project: ProjectLearning | undefined, treeId: string, blockId: number) => {
  if (project?.knowledge?.builder?.build_id !== treeId) return undefined;
  const nodes = project.knowledge.nodes;
  return nodes.find(node => node.id === `kb_${blockId}`) ?? nodes.find(node => node.builder_block_ids?.includes(blockId));
};

const contextHeading = '【学习上下文】\n';
const questionSeparator = '\n\n【我的问题】\n';

interface StudyQuestion { text: string; prompt: string; clearDraft: boolean }
interface LocalQuestion { id: string; conversationId: string; position: number; text: string; prompt: string }

function studyPrompt(subject: string, block: LearningBlock, question: string, atom?: TreeAtomPoint, step?: BlockStep) {
  const context = [
    `学科：${subject}`,
    `知识块：${block.code} · ${block.short_title}`,
  ];
  if (atom && step) {
    const difficulty = inferAtomDifficultyTier(atom);
    context.push(
      `步骤：STEP ${step.step_index} · ${step.step_title}`,
      `知识点：${atom.code} · ${atom.name}`,
      `difficulty_tier：${difficulty.tier} ${difficulty.label}`,
      `掌握目标（goal_statement）：${atom.goal_statement}`,
      `核心要素（key_elements）：${JSON.stringify(atom.key_elements ?? [])}`,
      `常见易混误区（common_misconceptions）：${JSON.stringify(atom.common_misconceptions ?? [])}`,
    );
  }
  return contextHeading + context.join('\n') + questionSeparator + question;
}

function displayQuestion(content: string) {
  const boundary = content.indexOf(questionSeparator);
  return content.startsWith(contextHeading) && boundary >= 0 ? content.slice(boundary + questionSeparator.length) : content;
}

function errorMessage(error: unknown): string {
  const data = (error as { response?: { data?: unknown } })?.response?.data;
  if (typeof data === 'string') return data;
  if (Array.isArray(data)) return data.join('；');
  if (data && typeof data === 'object') return Object.values(data).flat().join('；');
  return error instanceof Error ? error.message : '请求失败，请稍后重试。';
}

export function BlockStudyDialog({ tree, block, initialAtomId, project, onClose, onChanged }: Props) {
  const userId = useAuthStore(state => state.user?.id);
  const queryClient = useQueryClient();
  const { chat, activate, openProject, openingProject, setPageHooks } = useXiaoYuChat();
  const { bot, initialized, projectId: chatProjectId, conversationId, loading, messages, doSend } = chat;
  const speech = useSpeechNarration();

  const atomById = useMemo(() => new Map(tree.atoms.map(atom => [atom.id, atom])), [tree.atoms]);
  const stepGroups = useMemo(() => block.steps.map(step => ({
    step,
    entries: [...step.step_atoms].sort((a, b) => a.position - b.position).flatMap(item => {
      const atom = atomById.get(item.atom);
      return atom ? [{ atom, step, core: item.membership_type === 'core', difficulty: inferAtomDifficultyTier(atom) }] : [];
    }),
  })), [atomById, block.steps]);
  const entries = useMemo(() => stepGroups.flatMap(group => group.entries), [stepGroups]);
  const atoms = useMemo(() => [...new Map(entries.map(({ atom }) => [atom.id, atom])).values()], [entries]);
  const requestedAtom = entries.find(({ atom }) => atom.id === initialAtomId);
  const initialEntry = requestedAtom ?? entries.find(entry => entry.core) ?? entries[0];

  const [selection, setSelection] = useState<{ atomId: number | null; stepId?: number }>();
  const activeEntry = selection
    ? entries.find(({ atom, step }) => atom.id === selection.atomId && step.id === selection.stepId)
    : initialEntry;
  const activeAtom = activeEntry?.atom;
  const activeAtomId = activeAtom?.id;
  const activeStep = activeEntry?.step;
  const activeDiff = activeEntry?.difficulty;
  const guide = activeDiff ? studyGuides[activeDiff.tier] : undefined;

  // Fast resource & source-alignment load (include_candidates=0 keeps dialog snappy)
  const resourceKey = ['knowledge-block-resources', userId, tree.id, block.id];
  const resourcesQuery = useQuery({
    queryKey: resourceKey,
    queryFn: () => getBlockResources(tree.id, block.id, undefined, { includeCandidates: false }),
  });

  // Native multimodal micro-lesson lazy fetch + auto-generate
  const microLessonKey = ['knowledge-atom-micro-lesson', userId, tree.id, activeAtomId];
  const microLessonQuery = useQuery({
    queryKey: microLessonKey,
    enabled: Boolean(activeAtomId),
    queryFn: ({ signal }) => getAtomMicroLesson(tree.id, activeAtomId!, signal),
    staleTime: 60_000,
  });

  const [lessonStyle, setLessonStyle] = useState<MicroLessonStyle>('balanced');
  const [selectedCheckKey, setSelectedCheckKey] = useState<string | null>(null);
  const [sourcesExpanded, setSourcesExpanded] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [focusedCitation, setFocusedCitation] = useState<MicroLessonCitation | SourceAlignmentItem | null>(null);
  const autoGenAttempted = useRef<Set<number>>(new Set());

  const generateLessonMutation = useMutation({
    mutationFn: ({ atomId, regenerate, style }: { atomId: number; regenerate?: boolean; style?: MicroLessonStyle }) =>
      generateAtomMicroLesson(tree.id, atomId, { regenerate, style }),
    onSuccess: (data, vars) => {
      queryClient.setQueryData(['knowledge-atom-micro-lesson', userId, tree.id, vars.atomId], data);
      setSelectedCheckKey(null);
    },
  });

  useEffect(() => {
    if (!activeAtomId) return;
    const data = microLessonQuery.data;
    if (data && !data.exists && !generateLessonMutation.isPending && !autoGenAttempted.current.has(activeAtomId)) {
      autoGenAttempted.current.add(activeAtomId);
      generateLessonMutation.mutate({ atomId: activeAtomId, regenerate: false, style: 'balanced' });
    }
  }, [activeAtomId, generateLessonMutation, microLessonQuery.data]);

  const microLesson: AtomMicroLessonResponse | undefined = microLessonQuery.data;

  const [tab, setTab] = useState<'lesson' | 'quiz'>('lesson');
  const [mode, setMode] = useState<BlockQuizMode>('objective');
  const [error, setError] = useState('');
  const onError = (err: unknown) => setError(errorMessage(err));

  // Project companion wiring
  const existingProjectId = project?.status === 'active' && blockNode(project, tree.id, block.id) ? project.project_id : null;
  const [boundProject, setBoundProject] = useState<Awaited<ReturnType<typeof ensureBlockProject>>>();
  const projectId = boundProject?.project_id ?? existingProjectId;
  const projectQuery = useProjectLearning(projectId);
  const currentProject = projectQuery.data ?? (project?.project_id === projectId ? project : undefined);
  const projectConversation = boundProject?.conversation_id ?? currentProject?.conversation_id;
  const canAssess = projectId !== null && (boundProject ? boundProject.status === 'active' : existingProjectId !== null);
  const chatReady = !!userId && initialized && !!bot;
  const connected = chatReady && canAssess && chatProjectId === projectId
    && (!boundProject?.conversation_id || conversationId === boundProject.conversation_id);
  const bindingInFlight = useRef(false);
  const dialogOpen = useRef(false);
  const autoStarted = useRef(false);

  const { mutateAsync: ensureProject, isPending: binding, isSuccess: bindingFinished, error: bindingError } = useMutation({
    mutationFn: async (atomId: number | undefined) => {
      const result = canAssess ? boundProject : await ensureBlockProject(tree.id, block.id, {
        project_id: project?.project_id ?? chatProjectId,
        atom_id: atomId,
      });
      const targetId = result?.project_id ?? projectId;
      if (targetId === null || !dialogOpen.current) return;
      if (result) setBoundProject(result);
      await openProject(targetId, (result?.conversation_id ?? projectConversation) || undefined);
      void queryClient.invalidateQueries({ queryKey: learningKey(userId, targetId) });
    },
    onSettled: () => { bindingInFlight.current = false; },
  });

  const connectProject = useCallback((atomId: number | undefined) => {
    if (!chatReady || connected || openingProject || bindingInFlight.current) return;
    bindingInFlight.current = true;
    void ensureProject(atomId).catch(() => {});
  }, [chatReady, connected, ensureProject, openingProject]);

  useLayoutEffect(() => {
    dialogOpen.current = true;
    return () => { dialogOpen.current = false; };
  }, []);
  useEffect(() => { activate(); }, [activate]);
  useEffect(() => {
    if (!chatReady || connected || openingProject || autoStarted.current) return;
    autoStarted.current = true;
    connectProject(activeAtomId);
  }, [activeAtomId, chatReady, connected, connectProject, openingProject]);

  const matchedNodeId = blockNode(currentProject, tree.id, block.id)?.id;
  const versionId = currentProject?.knowledge?.version_id;
  useLayoutEffect(() => {
    if (!connected || !matchedNodeId || !versionId) return;
    setPageHooks({ getExtraPayload: () => ({ learning_activity: { node_id: matchedNodeId, version_id: versionId } }) });
    return () => setPageHooks(null);
  }, [connected, matchedNodeId, setPageHooks, versionId]);

  const [draft, setDraft] = useState('');
  const [queuedQuestion, setQueuedQuestion] = useState<StudyQuestion>();
  const [localQuestions, setLocalQuestions] = useState<LocalQuestion[]>([]);
  const sending = useRef(false);
  const messageCount = messages.length;
  const transcriptRef = useRef<HTMLDivElement>(null);
  const followTranscript = useRef(true);

  const sendQuestion = useCallback((question: StudyQuestion) => {
    if (sending.current) return;
    sending.current = true;
    followTranscript.current = true;
    const row = { id: crypto.randomUUID(), conversationId, position: messageCount, text: question.text, prompt: question.prompt };
    setLocalQuestions(previous => [...previous, row]);
    if (question.clearDraft) setDraft(previous => previous.trim() === question.text ? '' : previous);
    void doSend(question.prompt, true).catch(err => setError(errorMessage(err))).finally(() => { sending.current = false; });
  }, [conversationId, doSend, messageCount]);

  useEffect(() => {
    if (!queuedQuestion || binding || bindingInFlight.current || openingProject) return;
    if (connected ? loading : !bindingError && !bindingFinished) return;
    let cancelled = false;
    queueMicrotask(() => {
      if (cancelled) return;
      setQueuedQuestion(undefined);
      if (connected) sendQuestion(queuedQuestion);
    });
    return () => { cancelled = true; };
  }, [binding, bindingError, bindingFinished, connected, loading, openingProject, queuedQuestion, sendQuestion]);

  useLayoutEffect(() => {
    const transcript = transcriptRef.current;
    if (transcript && followTranscript.current) transcript.scrollTop = transcript.scrollHeight;
  }, [connected, conversationId, loading, localQuestions, messages]);

  const askXiaoYu = (text: string, clearDraft = false) => {
    const question = text.trim();
    if (!question || !chatReady || (connected && loading) || queuedQuestion || sending.current) return;
    const next = { text: question, prompt: studyPrompt(tree.subject, block, question, activeAtom, activeStep), clearDraft };
    if (connected && !binding && !openingProject) sendQuestion(next);
    else {
      setQueuedQuestion(next);
      connectProject(activeAtomId);
    }
  };

  const connecting = binding || openingProject;
  const connectionFailed = !connected && !connecting && (bindingError || bindingFinished);
  const linkProjectButton = (
    <Button size="sm" variant="outline" disabled={connecting || !chatReady} onClick={() => connectProject(activeAtomId)}>
      {t(connecting ? '正在关联学习项目…' : '⚡ 自动关联《{subject}》学习项目', { subject: tree.subject })}
    </Button>
  );
  const workspaceLink = learningUrl('/xiaoyu', projectId, (connected ? conversationId : projectConversation) || undefined);
  const quizWorkspaceLink = learningUrl('/xiaoyu?learning_view=knowledge', projectId ?? project?.project_id ?? null, (projectConversation ?? project?.conversation_id) || undefined);

  const visibleQuestions = localQuestions.filter(row => row.conversationId === conversationId
    && !messages.slice(row.position).some(message => message.role === 'user' && message.content === row.prompt));

  type TranscriptEntry = {
    key: string | number;
    role: string;
    content: string;
    dshCards?: DshCard[];
    visuals?: VisualData[];
  };

  const transcript: TranscriptEntry[] = connected ? messages.flatMap((message, index): TranscriptEntry[] => {
    const before = visibleQuestions
      .filter(row => row.position === index)
      .map(row => ({ key: row.id, role: 'user', content: row.text }));
    if (message.visible === false) return before;
    const meta = (message.metadata ?? {}) as Record<string, unknown>;
    const dshCards = Array.isArray(meta.dsh_cards) ? (meta.dsh_cards as DshCard[]) : undefined;
    const msgVisuals: VisualData[] = [];
    if (Array.isArray(meta.visuals)) {
      msgVisuals.push(...(meta.visuals as VisualData[]));
    }
    if (message.toolStep?.status === 'succeeded' && message.toolStep.visual) {
      msgVisuals.push(message.toolStep.visual as VisualData);
    }
    return [
      ...before,
      {
        key: message._id ?? message.id ?? index,
        role: message.role,
        content: message.role === 'user' ? displayQuestion(message.content) : message.content || message.toolStep?.label || '',
        dshCards,
        visuals: msgVisuals.length ? msgVisuals : undefined,
      },
    ];
  }).concat(visibleQuestions.filter(row => row.position >= messages.length).map(row => ({ key: row.id, role: 'user', content: row.text }))) : [];

  // Block Quiz assessment query
  const assessmentKey = ['block-assessment', userId, projectId, tree.id, block.id];
  const assessmentQuery = useQuery({
    queryKey: assessmentKey,
    enabled: !!canAssess && tab === 'quiz',
    queryFn: () => blockAssessment(tree.id, block.id, { project_id: projectId!, action: 'read' }),
    refetchInterval: query => query.state.data?.preparation?.status === 'pending' || query.state.data?.assessment?.items.some(item => item.task.status === 'processing') ? 2500 : false,
  });
  const assessment = assessmentQuery.data?.assessment;
  const preparing = assessmentQuery.data?.preparation?.status === 'pending';
  const taskProjectId = projectId ?? project?.project_id ?? null;
  const refreshTasks = () => {
    void queryClient.invalidateQueries({ queryKey: assessmentKey });
    void queryClient.invalidateQueries({ queryKey: ['learning-tasks', userId, taskProjectId] });
    void queryClient.invalidateQueries({ queryKey: learningKey(userId, taskProjectId) });
    onChanged();
  };
  const generateQuiz = useMutation({
    mutationFn: () => blockAssessment(tree.id, block.id, { project_id: projectId!, action: 'generate', mode, retest: !!assessment }),
    onSuccess: data => { queryClient.setQueryData(assessmentKey, data); refreshTasks(); },
    onError,
  });

  // Combined citations & extended resources for collapsible bottom anchor bar
  const blockResources = resourcesQuery.data?.resources ?? block.resources ?? [];
  const blockAlignments = resourcesQuery.data?.source_alignments ?? [];
  const atomCitations = useMemo(() => {
    if (microLesson?.citations?.length) return microLesson.citations;
    return blockAlignments
      .filter(a => !activeAtomId || a.atom === activeAtomId || a.atom === null)
      .map<MicroLessonCitation>(a => ({
        alignment_id: a.id,
        source_id: a.source_document,
        title: a.source_title,
        source_kind: a.source_kind,
        section_title: a.section_title,
        locator: a.locator,
        quote: a.excerpt_quote,
        full_excerpt: a.full_excerpt,
        url: a.source_url,
        alignment_role: a.alignment_role,
        match_reason: a.match_reason,
        is_verified: a.is_verified,
      }));
  }, [activeAtomId, blockAlignments, microLesson?.citations]);

  const atomResources = activeAtomId ? blockResources.filter(r => r.atom === activeAtomId || r.atom === null) : blockResources;
  const totalSourceCount = atomCitations.length + atomResources.length;

  const selectAtom = (id: number | null, stepId?: number) => {
    speech.stop();
    setSelectedCheckKey(null);
    setSelection({ atomId: id, stepId });
  };

  const handleStyleChange = (nextStyle: MicroLessonStyle) => {
    setLessonStyle(nextStyle);
    if (activeAtomId) {
      generateLessonMutation.mutate({ atomId: activeAtomId, regenerate: true, style: nextStyle });
    }
  };

  const activePitfalls = (microLesson?.exists && microLesson.pitfalls?.length)
    ? microLesson.pitfalls
    : (activeAtom?.common_misconceptions ?? []);
  const quickCheck = microLesson?.exists ? microLesson.quick_check : undefined;
  const isLessonGenerating = microLessonQuery.isLoading || generateLessonMutation.isPending;

  return (
    <>
      <Dialog open onOpenChange={open => { if (!open) { speech.stop(); onClose(); } }}>
        <DialogContent className="w-screen max-w-none sm:max-w-none h-dvh max-h-dvh content-start rounded-none border-0 p-5 md:p-8 overflow-y-auto kb-study-dialog kb-study-dialog--fullscreen">
          <DialogHeader className="pr-8">
            <DialogTitle className="flex flex-wrap items-center gap-2">
              <span>{block.code} · {block.short_title}</span>
              <span className="text-xs font-normal text-muted-foreground">第 {block.layer} 层</span>
            </DialogTitle>
            <DialogDescription>原生多模态微课件 · 主线出处溯源 · 小宇伴学</DialogDescription>
          </DialogHeader>

          {/* Top compact single-row / wrapping atom switcher */}
          <nav aria-label={t('切换知识点')} className="flex flex-wrap items-center gap-1.5 border-b pb-3">
            <Button
              size="sm"
              variant={activeAtom ? 'outline' : 'default'}
              className="h-7 rounded-full px-3 text-xs"
              aria-pressed={!activeAtom}
              onClick={() => selectAtom(null)}
            >
              📋 {t('整块总览（{count}）', { count: atoms.length })}
            </Button>
            {stepGroups.flatMap(({ step, entries: group }) =>
              group.map(({ atom, difficulty }) => {
                const selected = atom.id === activeAtom?.id && step.id === activeStep?.id;
                return (
                  <Button
                    key={`${step.id}-${atom.id}`}
                    size="sm"
                    variant={selected ? 'default' : 'outline'}
                    className="h-7 max-w-full rounded-full px-3 text-xs"
                    aria-pressed={selected}
                    onClick={() => selectAtom(atom.id, step.id)}
                  >
                    <span className="mr-1 shrink-0">{studyGuides[difficulty.tier].mark} {difficulty.tier}</span>
                    <span className="truncate max-w-[16rem]">{atom.name}</span>
                  </Button>
                );
              })
            )}
          </nav>

          <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
            {/* LEFT C-POSITION: Native Multimodal Micro-Lesson + Collapsible Citations */}
            <div className="min-w-0 space-y-4 lg:col-span-7">
              <div className="flex flex-wrap items-center justify-between gap-2" role="tablist" aria-label="知识块学习">
                <div className="flex gap-2">
                  <Button
                    id="kb-study-lesson-tab"
                    role="tab"
                    size="sm"
                    aria-selected={tab === 'lesson'}
                    aria-controls="kb-study-lesson"
                    variant={tab === 'lesson' ? 'default' : 'outline'}
                    onClick={() => setTab('lesson')}
                  >
                    ✨ 原生微课件
                  </Button>
                  <Button
                    id="kb-study-quiz-tab"
                    role="tab"
                    size="sm"
                    aria-selected={tab === 'quiz'}
                    aria-controls="kb-study-quiz"
                    variant={tab === 'quiz' ? 'default' : 'outline'}
                    onClick={() => setTab('quiz')}
                  >
                    📝 项目检测
                  </Button>
                </div>
                <Button
                  size="sm"
                  variant="ghost"
                  className="text-xs"
                  onClick={() => { setFocusedCitation(null); setDrawerOpen(true); }}
                >
                  📚 资源抽屉 ({totalSourceCount})
                </Button>
              </div>

              {error && <p role="alert" className="text-sm text-red-600">{error}</p>}

              {tab === 'lesson' ? (
                <section id="kb-study-lesson" role="tabpanel" aria-labelledby="kb-study-lesson-tab" className="space-y-4">
                  {activeAtom && activeStep && activeDiff && guide ? (
                    <article className="space-y-4 break-words rounded-2xl border bg-card p-4 sm:p-5 shadow-sm">
                      {/* Micro-lesson compact header strip */}
                      <header className="space-y-2 border-b pb-3">
                        <div className="flex flex-wrap items-start justify-between gap-2">
                          <div className="space-y-1 min-w-0">
                            <p className="text-xs font-medium text-muted-foreground">
                              STEP {activeStep.step_index} · {activeStep.step_title} · {activeAtom.code}
                            </p>
                            <h2 className="text-xl font-bold tracking-tight sm:text-2xl">{activeAtom.name}</h2>
                          </div>
                          <div className="flex flex-wrap items-center gap-1.5">
                            {speech.supported && microLesson?.exists && microLesson.narration_script && (
                              <Button
                                size="sm"
                                variant={speech.speakingKey === `lesson-${activeAtom.id}` ? 'default' : 'outline'}
                                className="h-8 rounded-full text-xs"
                                onClick={() => speech.toggleSpeak(`lesson-${activeAtom.id}`, microLesson.narration_script!)}
                              >
                                {speech.speakingKey === `lesson-${activeAtom.id}` ? '⏹ 停止朗读' : '🎧 听 1 分钟串讲'}
                              </Button>
                            )}
                            <select
                              aria-label="微课件讲解风格"
                              className="kb-study-select h-8 rounded-full text-xs"
                              value={microLesson?.style ?? lessonStyle}
                              disabled={isLessonGenerating}
                              onChange={e => handleStyleChange(e.target.value as MicroLessonStyle)}
                            >
                              {styleOptions.map(opt => (
                                <option key={opt.value} value={opt.value}>{opt.label}</option>
                              ))}
                            </select>
                            <Button
                              size="sm"
                              variant="outline"
                              className="h-8 rounded-full text-xs"
                              disabled={isLessonGenerating}
                              onClick={() => generateLessonMutation.mutate({ atomId: activeAtom.id, regenerate: true, style: lessonStyle })}
                            >
                              {generateLessonMutation.isPending ? '生成中…' : '↻ 换种讲法'}
                            </Button>
                          </div>
                        </div>
                        <div className="flex flex-wrap items-center gap-1.5 text-xs">
                          <span className={`rounded-full border px-2.5 py-0.5 font-semibold ${guide.theme}`}>
                            {guide.mark} {activeDiff.tier} {t(activeDiff.label)}
                          </span>
                          <span className="rounded-full border px-2.5 py-0.5">
                            {t(activeAtom.cognitive_level)} · {t(activeAtom.goal_type)}
                          </span>
                          <span className="rounded-full border px-2.5 py-0.5">
                            {t('预计 {minutes} 分钟', { minutes: activeAtom.granularity_minutes })}
                          </span>
                          <span className={`rounded-full border px-2.5 py-0.5 ${microLesson?.is_source_grounded ? 'border-sky-200 bg-sky-50 text-sky-900 dark:border-sky-900 dark:bg-sky-950/40 dark:text-sky-100' : 'text-muted-foreground'}`}>
                            {microLesson?.is_source_grounded ? '📌 基于已对齐主线资料提炼' : '🌐 基于通用学科知识生成'}
                          </span>
                        </div>
                      </header>

                      {/* Core intuition / skeleton during lazy generation */}
                      {isLessonGenerating && !microLesson?.exists ? (
                        <div className="space-y-3">
                          <div className="rounded-xl border bg-muted/30 p-3.5 space-y-2">
                            <p className="text-xs font-medium text-primary animate-pulse">✨ 正在按 {activeDiff.tier} 难度编排多模态微课件（约 3 秒）…</p>
                            <p className="text-sm leading-relaxed">{activeAtom.goal_statement}</p>
                            {!!activeAtom.key_elements?.length && (
                              <ul className="flex flex-wrap gap-1.5 pt-1">
                                {activeAtom.key_elements.map((el, i) => (
                                  <li key={i} className="rounded-md bg-muted px-2 py-0.5 text-xs">{el}</li>
                                ))}
                              </ul>
                            )}
                          </div>
                          <div className="h-36 rounded-xl bg-muted/50 animate-pulse" aria-hidden="true" />
                        </div>
                      ) : generateLessonMutation.isError && !microLesson?.exists ? (
                        <div className="rounded-xl border border-red-200 bg-red-50/50 p-4 space-y-2 text-sm">
                          <p className="text-red-700">{errorMessage(generateLessonMutation.error)}</p>
                          <p className="text-muted-foreground">{activeAtom.goal_statement}</p>
                          <Button size="sm" variant="outline" onClick={() => generateLessonMutation.mutate({ atomId: activeAtom.id, regenerate: true, style: lessonStyle })}>
                            重新生成微课件
                          </Button>
                        </div>
                      ) : microLesson?.exists ? (
                        <div className="space-y-4">
                          {/* 1-sentence core intuition */}
                          <div className="rounded-xl border border-primary/20 bg-primary/5 px-4 py-3">
                            <p className="text-xs font-semibold text-primary mb-1">💡 一句话核心直觉</p>
                            <p className="text-sm leading-relaxed font-medium">{microLesson.hook_summary}</p>
                          </div>

                          {/* Inline Multimodal Visual Cards */}
                          {Array.isArray(microLesson.visuals) && microLesson.visuals.length > 0 && (
                            <div className="space-y-2">
                              {microLesson.visuals.map((visual, idx) => (
                                <InlineVisualCard key={`${activeAtom.id}-v-${idx}`} visual={visual} index={idx} />
                              ))}
                            </div>
                          )}

                          {/* L3 Interactive experiment CTA */}
                          {activeDiff.tier === 'L3' && (
                            <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-rose-200 bg-rose-50/50 px-4 py-2.5 dark:border-rose-900 dark:bg-rose-950/30">
                              <span className="text-xs font-medium">🔴 硬核攻坚点：建议结合分步板书，让右侧小宇手把手带练推导</span>
                              <Button
                                size="sm"
                                variant="outline"
                                className="h-7 rounded-full text-xs"
                                onClick={() => askXiaoYu(`请围绕「${activeAtom.name}」启动交互式分步推导带练，先给我第一步并让我作答。`)}
                              >
                                🧪 启动小宇交互带练
                              </Button>
                            </div>
                          )}

                          {/* 30-second Inline Quick Check */}
                          {quickCheck && quickCheck.options?.length >= 2 && (
                            <details className="rounded-xl border bg-muted/20 p-3.5" open>
                              <summary className="cursor-pointer text-sm font-semibold">
                                ⚡ 30 秒快检题
                                {selectedCheckKey && (
                                  <span className={`ml-2 text-xs ${selectedCheckKey === quickCheck.answer ? 'text-emerald-600' : 'text-rose-600'}`}>
                                    {selectedCheckKey === quickCheck.answer ? '✓ 答对了' : `✕ 正确答案 ${quickCheck.answer}`}
                                  </span>
                                )}
                              </summary>
                              <div className="mt-2.5 space-y-2.5">
                                <p className="text-sm leading-relaxed">{quickCheck.question}</p>
                                <div className="grid gap-1.5">
                                  {quickCheck.options.map(opt => {
                                    const picked = selectedCheckKey === opt.key;
                                    const isCorrect = opt.key === quickCheck.answer;
                                    let btnStyle = 'border bg-background hover:bg-muted/60';
                                    if (selectedCheckKey) {
                                      if (isCorrect) btnStyle = 'border-emerald-500 bg-emerald-50 text-emerald-950 dark:bg-emerald-950/40 dark:text-emerald-100';
                                      else if (picked) btnStyle = 'border-rose-500 bg-rose-50 text-rose-950 dark:bg-rose-950/40 dark:text-rose-100';
                                    }
                                    return (
                                      <button
                                        key={opt.key}
                                        type="button"
                                        className={`w-full rounded-lg px-3 py-2 text-left text-sm transition ${btnStyle}`}
                                        onClick={() => setSelectedCheckKey(opt.key)}
                                      >
                                        <strong className="mr-2">{opt.key}.</strong>
                                        <span>{opt.label}</span>
                                      </button>
                                    );
                                  })}
                                </div>
                                {selectedCheckKey && (
                                  <p className="rounded-lg bg-muted/60 px-3 py-2 text-xs leading-relaxed">
                                    <strong>解析：</strong>{quickCheck.explanation}
                                  </p>
                                )}
                              </div>
                            </details>
                          )}

                          {/* Pitfalls capsule */}
                          {activePitfalls.length > 0 && (
                            <section className="rounded-xl border border-amber-200 bg-amber-50/60 p-3 dark:border-amber-900 dark:bg-amber-950/30">
                              <h3 className="text-xs font-semibold">⚠️ 易混误区与防坑点拨</h3>
                              <ul className="mt-1 list-disc space-y-1 pl-5 text-xs leading-relaxed">
                                {activePitfalls.map((item, index) => <li key={index}>{item}</li>)}
                              </ul>
                            </section>
                          )}
                        </div>
                      ) : (
                        <div className="space-y-3">
                          <p className="text-sm leading-relaxed">{activeAtom.goal_statement}</p>
                          <Button size="sm" onClick={() => generateLessonMutation.mutate({ atomId: activeAtom.id, regenerate: false, style: lessonStyle })}>
                            ✨ 生成多模态微课件
                          </Button>
                        </div>
                      )}
                    </article>
                  ) : (
                    /* Block overview mode */
                    <div className="space-y-3 rounded-2xl border bg-card p-5">
                      <h2 className="text-lg font-bold">{block.short_title} · 整块导览</h2>
                      {block.narrative_summary && <p className="whitespace-pre-wrap text-sm leading-relaxed text-muted-foreground">{block.narrative_summary}</p>}
                      <div className="grid gap-2 sm:grid-cols-2">
                        {entries.map(({ atom, step, difficulty }) => (
                          <button
                            key={`${step.id}-${atom.id}`}
                            type="button"
                            className="rounded-xl border p-3 text-left hover:bg-muted/40 transition space-y-1"
                            onClick={() => selectAtom(atom.id, step.id)}
                          >
                            <div className="flex items-center justify-between gap-2 text-xs">
                              <span className="font-semibold">{studyGuides[difficulty.tier].mark} {difficulty.tier} {difficulty.label}</span>
                              <span className="text-muted-foreground">STEP {step.step_index}</span>
                            </div>
                            <p className="font-semibold text-sm">{atom.name}</p>
                            <p className="text-xs text-muted-foreground line-clamp-2">{atom.goal_statement}</p>
                          </button>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Bottom Lightweight Collapsible Anchor Bar: 📚 权威出处与延伸资源（N） */}
                  <section className="rounded-xl border bg-card/80">
                    <button
                      type="button"
                      className="flex w-full items-center justify-between gap-2 px-4 py-2.5 text-left text-sm"
                      aria-expanded={sourcesExpanded}
                      onClick={() => setSourcesExpanded(prev => !prev)}
                    >
                      <span className="font-semibold shrink-0">📚 权威出处与延伸资源（{totalSourceCount}）</span>
                      <span className="truncate text-xs text-muted-foreground">
                        {atomCitations.length > 0
                          ? atomCitations.slice(0, 2).map(c => `《${c.title}》${c.locator || c.section_title}`).join(' · ')
                          : atomResources.length > 0
                            ? atomResources.slice(0, 2).map(r => r.title).join(' · ')
                            : '点击查看或补充外部参考'}
                      </span>
                      <span className="text-xs text-muted-foreground shrink-0">{sourcesExpanded ? '收起 ▲' : '展开 ▼'}</span>
                    </button>

                    {sourcesExpanded && (
                      <div className="border-t px-4 py-3 space-y-3">
                        {atomCitations.length > 0 && (
                          <div className="space-y-2">
                            <p className="text-xs font-semibold text-muted-foreground">📌 主线资料精准锚点</p>
                            <div className="grid gap-2">
                              {atomCitations.map(citation => {
                                const href = citation.url ? resolvePublicAssetLink(citation.url, citation.locator) : undefined;
                                return (
                                  <article key={citation.alignment_id} className="rounded-lg border bg-muted/20 p-2.5 text-xs space-y-1">
                                    <div className="flex flex-wrap items-center justify-between gap-2">
                                      <div className="flex flex-wrap items-center gap-1.5">
                                        <strong>《{citation.title}》</strong>
                                        {citation.locator && <span className="kb-badge kb-resource-locator">{citation.locator}</span>}
                                        {citation.section_title && <span className="text-muted-foreground">{citation.section_title}</span>}
                                      </div>
                                      <div className="flex items-center gap-2">
                                        <Button
                                          size="sm"
                                          variant="outline"
                                          className="h-6 px-2 text-xs"
                                          onClick={() => { setFocusedCitation(citation); setDrawerOpen(true); }}
                                        >
                                          查看原文切片
                                        </Button>
                                        {href && (
                                          <a href={href} target="_blank" rel="noopener noreferrer" className="underline underline-offset-4">
                                            直达链接 →
                                          </a>
                                        )}
                                      </div>
                                    </div>
                                    {citation.match_reason && <p className="text-muted-foreground">看点：{citation.match_reason}</p>}
                                  </article>
                                );
                              })}
                            </div>
                          </div>
                        )}

                        {atomResources.length > 0 && (
                          <div className="space-y-1.5">
                            <p className="text-xs font-semibold text-muted-foreground">🔗 延伸参考</p>
                            <ul className="space-y-1.5">
                              {atomResources.slice(0, 4).map(resource => {
                                const href = resource.source_kind === 'course' && resource.course_id
                                  ? `/course/${resource.course_id}`
                                  : resolvePublicAssetLink(resource.url, resource.locator);
                                return (
                                  <li key={resource.id} className="flex flex-wrap items-center justify-between gap-2 rounded-lg border px-2.5 py-1.5 text-xs">
                                    <a href={href} target="_blank" rel="noopener noreferrer" className="font-medium underline underline-offset-4">
                                      {resource.title}
                                    </a>
                                    {resource.locator && <span className="kb-badge kb-resource-locator">{resource.locator}</span>}
                                  </li>
                                );
                              })}
                            </ul>
                          </div>
                        )}

                        <div className="flex flex-wrap items-center justify-between gap-2 pt-1">
                          <span className="text-xs text-muted-foreground">可在「主线资料与切片对齐」整树绑定教材/B站合集，或在此单块补充。</span>
                          <Button size="sm" variant="outline" className="h-7 text-xs" onClick={() => { setFocusedCitation(null); setDrawerOpen(true); }}>
                            + 补充与管理外部资源
                          </Button>
                        </div>
                      </div>
                    )}
                  </section>
                </section>
              ) : (
                <section id="kb-study-quiz" role="tabpanel" aria-labelledby="kb-study-quiz-tab" className="space-y-4">
                  <p className="text-sm text-muted-foreground">检测与小宇共用项目任务、原始作答和后续建议。本次通过后仍需换题检验。</p>
                  {!canAssess ? (
                    <div className="space-y-2">
                      {linkProjectButton}
                      {connectionFailed && <p role="alert">{bindingError ? errorMessage(bindingError) : t('项目暂时无法关联，请重试。')}</p>}
                    </div>
                  ) : (
                    <>
                      <label className="block text-sm">
                        题型模式
                        <select className="kb-study-select ml-2" value={mode} disabled={generateQuiz.isPending || (!!assessment && !assessment.complete)} onChange={event => setMode(event.target.value as BlockQuizMode)}>
                          <option value="objective">客观题快测</option>
                          <option value="challenge">进阶挑战（加一道开放题）</option>
                        </select>
                      </label>
                      <p className="text-sm text-muted-foreground">逐个覆盖本块核心点，核心题均达到 75%，且平均得分率达到 75%，视为本次检测通过。开放题为模型参考评价。</p>
                      {assessmentQuery.isLoading && <p>正在恢复项目任务…</p>}
                      {assessmentQuery.error && <p role="alert">{errorMessage(assessmentQuery.error)} <Button variant="ghost" onClick={() => void assessmentQuery.refetch()}>重试</Button></p>}
                      {!assessmentQuery.isError && (
                        <Button disabled={generateQuiz.isPending || preparing || assessmentQuery.isLoading || (!!assessment && !assessment.complete)} onClick={() => { setError(''); generateQuiz.mutate(); }}>
                          {generateQuiz.isPending || preparing ? '正在准备项目任务…' : assessment ? '换题再检验' : '开始本块检测'}
                        </Button>
                      )}
                      {assessmentQuery.data?.preparation?.error && <p role="alert">{assessmentQuery.data.preparation.error}</p>}
                      {preparing && <p role="status">正在后台逐点准备题目，关闭后可以从本块或小宇恢复。</p>}
                      {assessment?.items.map(item => (
                        <article key={item.task.id} className="kb-study-resource space-y-2">
                          <p>{item.atom_name} · {item.membership_type === 'core' ? '核心点' : '拓展点'}</p>
                          {item.task.status === 'unavailable' || (item.task.is_current === false && !item.task.exam_id) ? (
                            <p>当前任务已停止使用，请回小宇确认新的学习安排。</p>
                          ) : (
                            <PracticeQuizCard
                              payload={{
                                ...item.task.payload,
                                learning_task_id: item.task.id,
                                project_id: projectId!,
                                conversation_id: projectConversation || undefined,
                                assistance: item.task.assistance,
                                response_type: item.task.response_type,
                                label_source: item.task.summary?.label_source,
                              }}
                              onResult={refreshTasks}
                            />
                          )}
                        </article>
                      ))}
                      {assessment?.complete && (
                        <p className={`kb-study-status ${assessment.passed ? 'is-complete' : 'is-review'}`} role="status">
                          {assessment.passed ? '本次检测通过' : '本次检测待强化'} · {Math.round((assessment.accuracy ?? 0) * 100)}%。长期状态与下一步建议请在小宇查看。
                        </p>
                      )}
                    </>
                  )}
                  <Link className="underline text-sm" to={quizWorkspaceLink} onClick={onClose}>回小宇查看学习安排与下一步</Link>
                </section>
              )}
            </div>

            {/* RIGHT XIAOYU COMPANION PANEL */}
            <aside aria-labelledby="kb-study-companion-title" className="flex min-w-0 flex-col self-start rounded-2xl border bg-card shadow-sm lg:sticky lg:top-0 lg:col-span-5 lg:max-h-[calc(100dvh-2rem)]">
              <header className="shrink-0 space-y-2 border-b p-4">
                <h2 id="kb-study-companion-title" className="break-words font-semibold">
                  {t('🤖 小宇伴学 · 当前聚焦：{name}', { name: activeAtom?.name ?? block.short_title })}
                </h2>
                {connected ? (
                  <span className="inline-block max-w-full break-words rounded-full bg-muted px-2.5 py-1 text-xs">
                    {t('已连入项目：{name}', { name: currentProject?.name || boundProject?.project_name || tree.subject })}
                  </span>
                ) : linkProjectButton}
                {!chatReady && <p role="status" className="text-sm text-muted-foreground">{t('小宇暂时未就绪，请稍后重试。')}</p>}
                {connectionFailed && <p role="alert" className="break-words text-sm text-destructive">{bindingError ? errorMessage(bindingError) : t('项目暂时无法关联，请重试。')}</p>}
              </header>
              <div className="flex shrink-0 flex-wrap gap-1.5 px-4 py-2.5">
                {(guide ?? studyGuides.L1).prompts.map(prompt => (
                  <Button
                    key={prompt}
                    size="sm"
                    variant="outline"
                    className="h-auto min-h-7 max-w-full whitespace-normal rounded-full px-3 py-1 text-left text-xs"
                    disabled={!chatReady || (connected && loading) || !!queuedQuestion}
                    onClick={() => askXiaoYu(t(prompt))}
                  >
                    {t(prompt)}
                  </Button>
                ))}
              </div>
              <div
                ref={transcriptRef}
                role="log"
                aria-label={t('向小宇提问')}
                aria-live="off"
                className="h-[min(50dvh,28rem)] min-h-24 space-y-3 overflow-y-auto overscroll-contain border-y bg-muted/30 p-4"
                onScroll={event => {
                  const list = event.currentTarget;
                  followTranscript.current = list.scrollHeight - list.scrollTop - list.clientHeight < 48;
                }}
              >
                {transcript.length === 0 && (
                  <p className="text-sm text-muted-foreground">
                    {t(connecting ? '正在打开项目对话…' : '边看左侧微课件边随时打断小宇追问，或点上方快捷问题开始。')}
                  </p>
                )}
                {transcript.map(message => (message.content || message.dshCards?.length || message.visuals?.length) && (
                  <div
                    key={message.key}
                    className={`w-fit max-w-[96%] overflow-x-auto break-words rounded-xl px-3 py-2 text-sm leading-relaxed ${message.role === 'user' ? 'ml-auto bg-primary text-primary-foreground' : 'border bg-background space-y-2'}`}
                  >
                    {message.role === 'user' ? (
                      <p className="whitespace-pre-wrap">{message.content}</p>
                    ) : (
                      <>
                        {message.content && (
                          <MarkdownContent content={message.content} className="prose prose-sm max-w-none dark:prose-invert" />
                        )}
                        {message.dshCards?.map((card, i) => <DshToolCard key={`dsh-${i}`} card={card} />)}
                        {message.visuals?.map((visual, i) => <InlineVisualCard key={`vis-${i}`} visual={visual} index={i} />)}
                        {speech.supported && message.content && (
                          <div className="pt-1">
                            <button
                              type="button"
                              className="text-xs text-muted-foreground hover:text-foreground underline underline-offset-4"
                              onClick={() => speech.toggleSpeak(`msg-${message.key}`, message.content)}
                            >
                              {speech.speakingKey === `msg-${message.key}` ? '⏹ 停止朗读' : '🔊 朗读回复'}
                            </button>
                          </div>
                        )}
                      </>
                    )}
                  </div>
                ))}
              </div>
              <footer className="shrink-0 space-y-2 p-4">
                {connected && loading && <p role="status" className="text-sm text-muted-foreground">{t('小宇正在思考…')}</p>}
                <form className="flex items-end gap-2" onSubmit={event => { event.preventDefault(); askXiaoYu(draft, true); }}>
                  <Input
                    className="min-w-0 flex-1"
                    aria-label={t('向小宇提问')}
                    placeholder={t('向小宇提问')}
                    value={draft}
                    onChange={event => setDraft(event.target.value)}
                    onKeyDown={event => { if (event.key === 'Enter' && event.nativeEvent.isComposing) event.preventDefault(); }}
                  />
                  <Button disabled={!draft.trim() || !chatReady || (connected && loading) || !!queuedQuestion}>{t('发送')}</Button>
                </form>
                <Link className="inline-block text-xs text-muted-foreground underline underline-offset-4" to={workspaceLink} onClick={onClose}>
                  {t('跳转小宇全屏工作区')}
                </Link>
              </footer>
            </aside>
          </div>
        </DialogContent>
      </Dialog>

      <BlockResourceDrawer
        open={drawerOpen}
        tree={tree}
        block={block}
        atoms={atoms}
        activeAtom={activeAtom}
        taskProjectId={taskProjectId}
        focusedCitation={focusedCitation}
        onClose={() => setDrawerOpen(false)}
        onChanged={onChanged}
      />
    </>
  );
}
