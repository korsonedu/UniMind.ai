import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { attachBlockResource, deleteBlockResource, blockAssessment, attachBlockResourceToProject, ensureBlockProject, getBlockResources, inferAtomDifficultyTier, resolvePublicAssetLink, updateBlockResource, voteBlockResource } from '@/lib/knowledgeBuilderApi';
import type { AssetSourceKind, AssetTrack, AtomDifficultyTier, BlockResourcesResponse, BlockResourceUpdatePayload, BlockQuizMode, BlockResourceItem, BlockResourcePayload, BlockStep, KnowledgeTreeBuildDetail, LearningBlock, TreeAtomPoint } from '@/types/knowledgeBuilder';
import { learningKey, learningUrl, useProjectLearning, type ProjectLearning } from '@/lib/projectLearning';
import { MarkdownContent } from '@/components/MarkdownContent';
import { PracticeQuizCard } from '@/pages/xiaoyu/visuals/PracticeQuizCard';
import { useXiaoYuChat } from '@/pages/xiaoyu/xiaoYuChatContext';
import { Link } from 'react-router-dom';
import { useAuthStore } from '@/store/useAuthStore';
import { t } from '@/i18n';

interface Props {
  tree: KnowledgeTreeBuildDetail; block: LearningBlock; initialAtomId?: number | null; project?: ProjectLearning;
  onClose: () => void; onChanged: () => void;
}
const roleLabels: Record<string, string> = {
  series_episode: '系列主线讲次', concept_intuition: '概念直觉', core_derivation: '核心推导',
  worked_example: '例题实战', wiki_reference: '权威词条定义',
};
const tracks: AssetTrack[] = ['spine', 'spotlight', 'wiki'];
const videoSources: AssetSourceKind[] = ['bilibili', 'youtube', 'course'];
const studyGuides = {
  L1: {
    mark: '🟢',
    theme: 'border-emerald-200 bg-emerald-50 text-emerald-950 dark:border-emerald-900 dark:bg-emerald-950/40 dark:text-emerald-100',
    advice: '💡 基础速通知识点：本点属于概念界定与基础理解，无需观看冗长外部视频。直接点击右侧小宇快捷提问，3 分钟快问快答即可过关！',
    prompts: ['💬 用大白话 2 分钟讲透这个概念', '⚡ 出一道快检题考考我', '🧭 帮我理清它的核心要素'],
  },
  L2: {
    mark: '🟡',
    theme: 'border-amber-200 bg-amber-50 text-amber-950 dark:border-amber-900 dark:bg-amber-950/40 dark:text-amber-100',
    advice: '🔍 机制辨析知识点：建议结合下方配套分 P / 权威规则，并在右侧让小宇针对常见误区考你一道辨析题。',
    prompts: ['🔍 针对常见误区考我一道辨析题', '📊 帮我对比梳理核心差异', '⚖️ 结合实务场景帮我理解机制'],
  },
  L3: {
    mark: '🔴',
    theme: 'border-rose-200 bg-rose-50 text-rose-950 dark:border-rose-900 dark:bg-rose-950/40 dark:text-rose-100',
    advice: '🔥 硬核攻坚知识点：本点涉及核心推导、计算或综合应用，已为你重点匹配精讲视频，建议先看视频推演，再让右侧小宇手把手带练实战。',
    prompts: ['🧪 手把手带我推演/算一遍', '📝 出一道实战计算或综合案例题', '🎯 拆解这个难点的解题步骤'],
  },
} satisfies Record<AtomDifficultyTier, { mark: string; theme: string; advice: string; prompts: string[] }>;

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

function resourceTrack(resource: BlockResourceItem): AssetTrack {
  return resource.asset_track ?? (resource.source_kind === 'course' ? 'spine' : resource.source_kind === 'wikipedia' ? 'wiki' : 'spotlight');
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
  const atomById = new Map(tree.atoms.map(atom => [atom.id, atom]));
  const stepGroups = block.steps.map(step => ({
    step,
    entries: [...step.step_atoms].sort((a, b) => a.position - b.position).flatMap(item => {
      const atom = atomById.get(item.atom);
      return atom ? [{ atom, step, core: item.membership_type === 'core', difficulty: inferAtomDifficultyTier(atom) }] : [];
    }),
  }));
  const entries = stepGroups.flatMap(group => group.entries);
  const atoms = [...new Map(entries.map(({ atom }) => [atom.id, atom])).values()];
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
  const [resourceScope, setResourceScope] = useState<'atom' | 'block'>(requestedAtom ? 'atom' : 'block');
  const resourceKey = ['knowledge-block-resources', userId, tree.id, block.id];
  const resourcesQuery = useQuery({ queryKey: resourceKey, queryFn: () => getBlockResources(tree.id, block.id) });
  const [tab, setTab] = useState<'resources' | 'quiz'>('resources');
  const [query, setQuery] = useState(`${tree.subject} ${block.short_title}`);
  const [url, setUrl] = useState('');
  const [atomId, setAtomId] = useState(requestedAtom ? String(requestedAtom.atom.id) : '');
  const [assetTrack, setAssetTrack] = useState<AssetTrack>('spotlight');
  const [locator, setLocator] = useState('');
  const [saveToLibrary, setSaveToLibrary] = useState(false);
  const [searchResults, setSearchResults] = useState<BlockResourcesResponse | null>(null);
  const [searched, setSearched] = useState(false);
  const [mode, setMode] = useState<BlockQuizMode>('objective');
  const [error, setError] = useState('');
  const onError = (err: unknown) => setError(errorMessage(err));
  const refresh = () => { void queryClient.invalidateQueries({ queryKey: resourceKey }); onChanged(); };
  const attach = useMutation({
    mutationFn: (payload: BlockResourcePayload) => attachBlockResource(tree.id, block.id, payload),
    onSuccess: () => { setUrl(''); refresh(); }, onError,
  });
  const update = useMutation({ mutationFn: (payload: BlockResourceUpdatePayload) => updateBlockResource(tree.id, block.id, payload), onSuccess: refresh, onError });
  const remove = useMutation({ mutationFn: (id: number) => deleteBlockResource(tree.id, block.id, id), onSuccess: refresh, onError });
  const voteMutation = useMutation({
    mutationFn: ({ resourceId, vote }: { resourceId: number; vote: 1 | -1 | 0 }) => voteBlockResource(tree.id, block.id, resourceId, vote),
    onSuccess: refresh, onError,
  });
  const search = useMutation({
    mutationFn: () => getBlockResources(tree.id, block.id, query),
    onSuccess: data => { setSearchResults(data); setSearched(true); }, onError,
  });
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
      if (targetId === null) return;
      if (!dialogOpen.current) return;
      if (result) setBoundProject(result);
      await openProject(targetId, (result?.conversation_id ?? projectConversation) || undefined);
      void queryClient.invalidateQueries({ queryKey: learningKey(userId, targetId) });
    },
    onSettled: () => { bindingInFlight.current = false; },
  });
  const connectProject = useCallback((atomId: number | undefined) => {
    if (!chatReady || connected || openingProject || bindingInFlight.current) return;
    bindingInFlight.current = true;
    void ensureProject(atomId).catch(() => {
      // React Query exposes the error to both connection buttons.
    });
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
    // Silent sends keep the structured context out of the visible user bubble.
    const row = { id: crypto.randomUUID(), conversationId, position: messageCount, text: question.text, prompt: question.prompt };
    setLocalQuestions(previous => [...previous, row]);
    if (question.clearDraft) setDraft(previous => previous.trim() === question.text ? '' : previous);
    void doSend(question.prompt, true).catch(err => setError(errorMessage(err))).finally(() => { sending.current = false; });
  }, [conversationId, doSend, messageCount, setDraft, setError, setLocalQuestions]);
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
    if (!question || !chatReady || connected && loading || queuedQuestion || sending.current) return;
    const next = { text: question, prompt: studyPrompt(tree.subject, block, question, activeAtom, activeStep), clearDraft };
    if (connected && !binding && !openingProject) sendQuestion(next);
    else {
      setQueuedQuestion(next);
      connectProject(activeAtomId);
    }
  };
  const connecting = binding || openingProject;
  const connectionFailed = !connected && !connecting && (bindingError || bindingFinished);
  const linkProjectButton = <Button size="sm" variant="outline" disabled={connecting || !chatReady} onClick={() => connectProject(activeAtomId)}>
    {t(connecting ? '正在关联学习项目…' : '⚡ 自动关联《{subject}》学习项目', { subject: tree.subject })}
  </Button>;
  const workspaceLink = learningUrl('/xiaoyu', projectId, (connected ? conversationId : projectConversation) || undefined);
  const quizWorkspaceLink = learningUrl('/xiaoyu?learning_view=knowledge', projectId ?? project?.project_id ?? null, (projectConversation ?? project?.conversation_id) || undefined);

  const visibleQuestions = localQuestions.filter(row => row.conversationId === conversationId
    && !messages.slice(row.position).some(message => message.role === 'user' && message.content === row.prompt));
  const transcript = connected ? messages.flatMap((message, index) => [
    ...visibleQuestions.filter(row => row.position === index).map(row => ({ key: row.id, role: 'user', content: row.text })),
    ...(message.visible === false ? [] : [{
      key: message._id ?? message.id ?? index,
      role: message.role,
      content: message.role === 'user' ? displayQuestion(message.content) : message.content || message.toolStep?.label || '',
    }]),
  ]).concat(visibleQuestions.filter(row => row.position >= messages.length).map(row => ({ key: row.id, role: 'user', content: row.text }))) : [];

  const assessmentKey = ['block-assessment', userId, projectId, tree.id, block.id];
  const assessmentQuery = useQuery({ queryKey: assessmentKey, enabled: !!canAssess,
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
  const generate = useMutation({
    mutationFn: () => blockAssessment(tree.id, block.id, { project_id: projectId!, action: 'generate', mode, retest: !!assessment }),
    onSuccess: data => { queryClient.setQueryData(assessmentKey, data); refreshTasks(); }, onError,
  });
  const [notice, setNotice] = useState('');
  const useResource = useMutation({
    mutationFn: (id: number) => attachBlockResourceToProject(tree.id, block.id, taskProjectId!, id),
    onSuccess: data => { setNotice(data.notice); refreshTasks(); }, onError,
  });
  const busy = attach.isPending || update.isPending || remove.isPending || search.isPending || generate.isPending || useResource.isPending || voteMutation.isPending;
  const mountWeb = (link: string) => { setError(''); attach.mutate({ url: link.trim(), asset_track: assetTrack, locator: locator.trim(), save_to_library: saveToLibrary, ...(atomId ? { atom_id: Number(atomId) } : {}) }); };
  const resources = resourcesQuery.data?.resources ?? block.resources ?? [];
  const focusedResources = activeAtom ? resources.filter(resource => resource.atom === activeAtom.id) : [];
  const visibleResources = activeAtom && resourceScope === 'atom' ? focusedResources : resources;
  const guideAdvice = activeDiff?.tier === 'L3' && !focusedResources.some(resource => videoSources.includes(resource.source_kind))
    ? '🔥 硬核攻坚知识点：本点涉及核心推导、计算或综合应用，可以先让小宇带你推演，再做一道实战题。'
    : guide?.advice;
  const orderedTracks: AssetTrack[] = activeDiff?.tier === 'L1' ? ['wiki', 'spine', 'spotlight']
    : activeDiff?.tier === 'L3' ? ['spotlight', 'spine', 'wiki'] : tracks;
  const resourcePriority = (resource: BlockResourceItem) => {
    if (resource.atom !== activeAtomId) return 0;
    if (activeDiff?.tier === 'L3' && videoSources.includes(resource.source_kind)) return 2;
    if (activeDiff?.tier === 'L2' && resource.locator) return 2;
    return 1;
  };
  const candidateData = searchResults ?? resourcesQuery.data;
  const isIntl = (candidateData?.region_pref ?? tree.region_pref ?? 'cn') === 'intl';
  const sourceLabels: Record<AssetSourceKind, string> = {
    course: '站内课程', library: '个人资料快照', web: '公开网页', bilibili: 'B站', github: '开源讲义仓库',
    wikipedia: isIntl ? 'Wikipedia' : 'OI-Wiki / 开源学科词条', youtube: isIntl ? 'YouTube / OCW' : '公开视频', marketplace: '共享市场',
  };
  const trackLabels: Record<AssetTrack, string> = { spine: '🎬 主线配套课', spotlight: '🌟 单点神作', wiki: isIntl ? '📖 Wikipedia 词条' : '📖 专业开源 Wiki 词条' };
  const renderResource = (resource: BlockResourceItem, allowEdit = true) => {
    const track = resourceTrack(resource);
    const href = resource.source_kind === 'course' && resource.course_id ? `/course/${resource.course_id}` : resolvePublicAssetLink(resource.url, resource.locator);
    const focused = !!activeAtom && resource.atom === activeAtom.id;
    return <article key={resource.id} className={`kb-study-resource kb-study-track-resource is-${track}`}>
      <div className="flex flex-wrap items-center gap-2">
        <a href={href} target="_blank" rel="noopener noreferrer" className="font-semibold underline">{resource.title}</a>
        <span className="kb-badge">{sourceLabels[resource.source_kind]}</span>
        {resource.origin === 'auto' && <span className="kb-badge">AI 自动挂载</span>}
        {resource.locator && <span className="kb-badge kb-resource-locator">{resource.locator}</span>}
        {resource.pedagogical_role && <span className="kb-badge">{roleLabels[resource.pedagogical_role] ?? resource.pedagogical_role}</span>}
        {focused && <span className="kb-badge">{t('🎯 当前知识点专属')}</span>}
        {track === 'spine' && <span className="text-sm text-muted-foreground">体系连贯主干</span>}
      </div>
      <p className="text-sm text-muted-foreground">{block.steps.find(step => step.id === resource.step)?.step_title ?? '整个知识块'}{resource.atom ? ` · ${atoms.find(atom => atom.id === resource.atom)?.name ?? ''}` : ''}</p>
      {track === 'wiki' ? <p className="whitespace-pre-wrap text-sm">{resource.excerpt || '暂无词条摘要。'}</p>
        : <details><summary>查看正文摘要</summary><p className="whitespace-pre-wrap text-sm">{resource.excerpt || '暂无正文摘要。'}</p></details>}
      <a href={href} target="_blank" rel="noopener noreferrer" className="kb-resource-direct-link underline">直接打开{resource.locator ? `（${resource.locator}）` : ''}</a>
      {taskProjectId !== null && <Button size="sm" variant="outline" disabled={busy} onClick={() => { setError(''); useResource.mutate(resource.id); }}>用于当前小宇项目</Button>}
      <div className="flex flex-wrap items-center gap-2">
        <Button size="sm" variant={resource.user_vote === 1 ? 'default' : 'outline'} disabled={busy} aria-label={`${resource.title}有用`} aria-pressed={resource.user_vote === 1} onClick={() => {
          setError(''); voteMutation.mutate({ resourceId: resource.id, vote: resource.user_vote === 1 ? 0 : 1 });
        }}>👍 有用 ({resource.upvotes ?? 0})</Button>
        <Button size="sm" variant={resource.user_vote === -1 ? 'default' : 'outline'} disabled={busy} aria-label={`${resource.title}没用`} aria-pressed={resource.user_vote === -1} onClick={() => {
          setError(''); voteMutation.mutate({ resourceId: resource.id, vote: resource.user_vote === -1 ? 0 : -1 });
        }}>👎 没用 ({resource.downvotes ?? 0})</Button>
      </div>
      {allowEdit && <div className="kb-resource-adjustments flex flex-wrap items-center gap-2">
        <label className="text-sm">轨道<select className="kb-study-select" aria-label={`${resource.title}的资源轨道`} value={track} disabled={busy} onChange={event => {
          setError(''); update.mutate({ resource_id: resource.id, asset_track: event.target.value as AssetTrack });
        }}><option value="spine">主线</option><option value="spotlight">神作</option><option value="wiki">{trackLabels.wiki}</option></select></label>
        <label className="text-sm">绑定原子知识点<select className="kb-study-select" aria-label={`${resource.title}绑定的原子知识点`} value={resource.atom ?? ''} disabled={busy} onChange={event => {
          setError(''); update.mutate({ resource_id: resource.id, atom_id: event.target.value ? Number(event.target.value) : null, step_id: null });
        }}><option value="">整个知识块</option>{atoms.map(atom => <option key={atom.id} value={atom.id}>{atom.name}</option>)}</select></label>
        <Button size="sm" variant="ghost" disabled={busy} onClick={() => { setError(''); remove.mutate(resource.id); }}>移除挂载</Button>
      </div>}
    </article>;
  };
  const selectAtom = (id: number | null, stepId?: number) => {
    setSelection({ atomId: id, stepId });
    setResourceScope(id === null ? 'block' : 'atom');
    setAtomId(id === null ? '' : String(id));
  };
  return <Dialog open onOpenChange={open => { if (!open) onClose(); }}>
    <DialogContent className="w-screen max-w-none sm:max-w-none h-dvh max-h-dvh content-start rounded-none border-0 p-6 md:p-10 overflow-y-auto kb-study-dialog kb-study-dialog--fullscreen">
      <DialogHeader className="pr-8"><DialogTitle>{block.code} · {block.short_title}</DialogTitle>
        <DialogDescription>第 {block.layer} 层 · 学习资源与项目检测</DialogDescription></DialogHeader>
      <nav aria-label={t('切换知识点')} className="space-y-3 border-b pb-4">
        <Button size="sm" variant={activeAtom ? 'outline' : 'default'} className="h-auto min-h-8 whitespace-normal rounded-full py-1 text-left" aria-pressed={!activeAtom} onClick={() => selectAtom(null)}>
          📋 {t('整块总览（{count}）', { count: atoms.length })}
        </Button>
        {stepGroups.map(({ step, entries: group }) => group.length > 0 && <div key={step.id} className="flex flex-wrap items-center gap-2">
          <span className="mr-1 text-xs font-semibold text-muted-foreground">STEP {step.step_index} · {step.step_title}</span>
          {group.map(({ atom, difficulty }) => {
            const selected = atom.id === activeAtom?.id && step.id === activeStep?.id;
            return <Button key={atom.id} size="sm" variant={selected ? 'default' : 'outline'} className="h-auto min-h-8 max-w-full whitespace-normal rounded-full py-1 text-left break-words" aria-pressed={selected} onClick={() => selectAtom(atom.id, step.id)}>
              <span className="shrink-0">{studyGuides[difficulty.tier].mark} {difficulty.tier}</span>
              <span className="min-w-0">{atom.name}</span>
            </Button>;
          })}
        </div>)}
      </nav>
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        <div className="min-w-0 space-y-4 lg:col-span-7">
          {activeAtom && activeStep && activeDiff && guide ? <article className="space-y-4 break-words rounded-xl border bg-card p-4 sm:p-5">
            <header className="space-y-2">
              <p className="text-xs font-semibold text-muted-foreground">STEP {activeStep.step_index} · {activeStep.step_title} · {activeAtom.code}</p>
              <h2 className="text-xl font-bold tracking-tight sm:text-2xl">{activeAtom.name}</h2>
              <div className="flex flex-wrap items-center gap-2 text-xs">
                <span className={`rounded-full border px-2.5 py-1 font-semibold ${guide.theme}`}>{guide.mark} {activeDiff.tier} {t(activeDiff.label)}</span>
                <span className="rounded-full border px-2.5 py-1">{t(activeAtom.cognitive_level)} · {t(activeAtom.goal_type)}</span>
                <span className="rounded-full border px-2.5 py-1">{t('预计 {minutes} 分钟', { minutes: activeAtom.granularity_minutes })}</span>
              </div>
            </header>
            <section>
              <h3 className="font-semibold">{t('🎯 掌握目标')}</h3>
              <p className="mt-1 whitespace-pre-wrap text-sm leading-relaxed">{activeAtom.goal_statement}</p>
            </section>
            {!!activeAtom.key_elements?.length && <section>
              <h3 className="font-semibold">{t('🧩 核心要素')}</h3>
              <ul className="mt-2 flex flex-wrap gap-2">
                {activeAtom.key_elements.map((item, index) => <li key={index} className="rounded-md bg-muted px-2.5 py-1 text-sm">{item}</li>)}
              </ul>
            </section>}
            {!!activeAtom.common_misconceptions?.length && <section className="rounded-lg border border-amber-200 bg-amber-50/60 p-3 dark:border-amber-900 dark:bg-amber-950/30">
              <h3 className="font-semibold">{t('⚠️ 常见易混误区')}</h3>
              <ul className="mt-1 list-disc space-y-1 pl-5 text-sm leading-relaxed">
                {activeAtom.common_misconceptions.map((item, index) => <li key={index}>{item}</li>)}
              </ul>
            </section>}
          </article> : block.narrative_summary && <p className="whitespace-pre-wrap rounded-xl border bg-card p-4 text-sm leading-relaxed">{block.narrative_summary}</p>}
          {guide && <p className={`rounded-lg border px-4 py-3 text-sm leading-relaxed ${guide.theme}`}>{t(guideAdvice)}</p>}
          <p className="text-sm text-muted-foreground">检测与小宇共用项目任务、原始作答和后续建议。本次通过后仍需换题检验。</p>
          <div className="flex gap-2" role="tablist" aria-label="知识块学习">
            <Button id="kb-study-resources-tab" role="tab" aria-selected={tab === 'resources'} aria-controls="kb-study-resources" variant={tab === 'resources' ? 'default' : 'outline'} onClick={() => setTab('resources')}>学习资源</Button>
            <Button id="kb-study-quiz-tab" role="tab" aria-selected={tab === 'quiz'} aria-controls="kb-study-quiz" variant={tab === 'quiz' ? 'default' : 'outline'} onClick={() => setTab('quiz')}>项目检测</Button>
          </div>
          {notice && <p role="status">{notice}</p>}
          {error && <p role="alert" className="text-red-600">{error}</p>}
          {tab === 'resources' ? <section id="kb-study-resources" role="tabpanel" aria-labelledby="kb-study-resources-tab" className="space-y-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h3 className="font-semibold">已挂载资源 · {visibleResources.length}</h3>
              {activeAtom && <label className="flex items-center gap-2 text-sm">
                <input type="checkbox" checked={resourceScope === 'block'} onChange={event => setResourceScope(event.target.checked ? 'block' : 'atom')} />
                {t('本块全部资源')}
              </label>}
            </div>
            {resourcesQuery.isLoading && <p>正在读取资源…</p>}
            {resourcesQuery.error && <p role="alert">{errorMessage(resourcesQuery.error)} <Button variant="ghost" onClick={() => void resourcesQuery.refetch()}>重试</Button></p>}
            {orderedTracks.map(track => {
              const trackResources = visibleResources.filter(resource => resourceTrack(resource) === track)
                .sort((a, b) => resourcePriority(b) - resourcePriority(a));
              return <section key={track} className={`kb-study-track is-${track}`} aria-label={trackLabels[track]}>
                <h3 className="font-semibold">{trackLabels[track]} · {trackResources.length}</h3>
                <p className="text-sm text-muted-foreground">{track === 'spine' ? '按讲次连贯学习，直达对应分 P 或章节。' : track === 'spotlight' ? '围绕当前难点，查看概念直觉、核心推导与例题实战。' : '随时查阅概念定义、章节锚点与开源文档。'}</p>
                {trackResources.map(resource => renderResource(resource))}
                {trackResources.length === 0 && <p className="text-sm text-muted-foreground">当前轨道还没有挂载资源。</p>}
              </section>;
            })}
            <section className="space-y-2" aria-label={`${trackLabels.wiki}推荐`}>
              <h3 className="font-semibold">{trackLabels.wiki}推荐</h3>
              {candidateData?.wiki_candidates?.map(candidate => <article key={candidate.url} className="kb-study-resource space-y-2">
                <a href={resolvePublicAssetLink(candidate.url, candidate.locator)} target="_blank" rel="noopener noreferrer" className="font-medium underline">{candidate.title}</a>
                {candidate.locator && <span className="kb-badge">{candidate.locator}</span>}
                <p className="text-sm">{candidate.summary}</p>
                <Button size="sm" variant="outline" disabled={busy} onClick={() => { setError(''); attach.mutate({ url: candidate.url, asset_track: 'wiki', pedagogical_role: candidate.pedagogical_role, locator: candidate.locator, ...(atomId ? { atom_id: Number(atomId) } : {}) }); }}>挂载到本块</Button>
              </article>)}
              {candidateData && !candidateData.wiki_candidates?.length && <p className="text-sm text-muted-foreground">暂无匹配的概念词条。</p>}
            </section>
            <section className="space-y-2" aria-label="精选资产池候选">
              <h3 className="font-semibold">🌟 精选资产池候选</h3>
              {candidateData?.catalog_candidates?.map(candidate => <article key={candidate.id} className="kb-study-resource space-y-2">
                <div className="flex flex-wrap items-center gap-2"><a href={resolvePublicAssetLink(candidate.url)} target="_blank" rel="noopener noreferrer" className="font-medium underline">{candidate.title}</a><span className="kb-badge">{sourceLabels[candidate.source_kind]}</span><span className="kb-badge">{trackLabels[candidate.asset_track]}</span></div>
                <p className="text-sm">{candidate.description}</p>
                <Button size="sm" variant="outline" disabled={busy} onClick={() => { setError(''); attach.mutate({ public_asset_id: candidate.id, asset_track: candidate.asset_track, pedagogical_role: candidate.pedagogical_role, ...(atomId ? { atom_id: Number(atomId) } : {}) }); }}>挂载到本块</Button>
              </article>)}
              {candidateData && !candidateData.catalog_candidates?.length && <p className="text-sm text-muted-foreground">暂无匹配的精选资产。</p>}
            </section>
            <h3 className="font-semibold">匹配的站内课程与个人资料</h3>
            {resourcesQuery.data?.internal_candidates.map((candidate, index) => <article key={index} className="kb-study-resource flex items-center justify-between gap-2">
              <div><a href={resolvePublicAssetLink(candidate.url, candidate.locator)} target="_blank" rel="noopener noreferrer" className="font-semibold underline">{candidate.title}</a><p className="text-sm">{sourceLabels[candidate.source_kind]}</p></div>
              <Button variant="outline" size="sm" disabled={busy} onClick={() => { setError(''); attach.mutate({ ...(candidate.course_id ? { course_id: candidate.course_id } : { library_resource_id: candidate.library_resource_id }), atom_id: candidate.atom_id, step_id: candidate.step_id }); }}>挂载到本块</Button>
            </article>)}
            {resourcesQuery.data?.internal_candidates.length === 0 && <p className="text-sm text-muted-foreground">暂未匹配到站内资源，可搜索或粘贴公开网页。</p>}
            <div className="kb-study-resource space-y-3">
              <h3 className="font-semibold">搜索网上公开资源</h3>
              <form className="flex gap-2" onSubmit={event => { event.preventDefault(); setError(''); search.mutate(); }}>
                <Input aria-label="资源搜索词" value={query} maxLength={300} onChange={event => setQuery(event.target.value)} />
                <Button disabled={busy}>{search.isPending ? '搜索中…' : '联网搜索'}</Button>
              </form>
              <label className="flex gap-2 text-sm"><input type="checkbox" checked={saveToLibrary} onChange={event => setSaveToLibrary(event.target.checked)} />同时存入我的个人资料库</label>
              <label className="block text-sm">关联原子知识点<select className="kb-study-select" value={atomId} onChange={event => setAtomId(event.target.value)}>
                <option value="">自动匹配原子点</option>{atoms.map(atom => <option key={atom.id} value={atom.id}>{atom.name}</option>)}
              </select></label>
              {searched && searchResults?.web_candidates.length === 0 && <p>没有找到公开 HTTPS 候选，请调整搜索词。</p>}
              {searchResults?.web_candidates.map(candidate => <article key={candidate.url} className="kb-study-resource space-y-2">
                <a href={resolvePublicAssetLink(candidate.url)} target="_blank" rel="noopener noreferrer" className="font-medium underline">{candidate.title}</a><p className="text-sm">{candidate.summary}</p>
                <Button size="sm" variant="outline" disabled={busy} onClick={() => mountWeb(candidate.url)}>读取正文并挂载到本块</Button>
              </article>)}
              <h3 className="font-semibold">直接粘贴 HTTPS 链接</h3>
              <div className="flex flex-wrap gap-3">
                <label className="text-sm">挂载轨道<select className="kb-study-select" value={assetTrack} onChange={event => setAssetTrack(event.target.value as AssetTrack)}>
                  <option value="spotlight">🌟 单点神作</option><option value="spine">🎬 主线配套</option><option value="wiki">{trackLabels.wiki}</option>
                </select></label>
                <label className="flex-1 text-sm">定位符<Input aria-label="资源定位符" value={locator} maxLength={300} placeholder="P3 · 05:20 或 #资本市场线" onChange={event => setLocator(event.target.value)} /></label>
              </div>
              <form className="flex flex-wrap gap-2" onSubmit={event => { event.preventDefault(); mountWeb(url); }}>
                <Input className="flex-1 min-w-48" aria-label="公开 HTTPS 链接" type="url" required pattern="https://.*" value={url} maxLength={1000} placeholder="https://…" onChange={event => setUrl(event.target.value)} />
                <Button disabled={busy || !url.trim()}>{attach.isPending ? '读取并挂载中…' : '读取正文并挂载'}</Button>
              </form>
            </div>
          </section> : <section id="kb-study-quiz" role="tabpanel" aria-labelledby="kb-study-quiz-tab" className="space-y-4">
            {!canAssess ? <div className="space-y-2">
              {linkProjectButton}
              {connectionFailed && <p role="alert">{bindingError ? errorMessage(bindingError) : t('项目暂时无法关联，请重试。')}</p>}
            </div> : <>
              <label className="block text-sm">题型模式<select className="kb-study-select" value={mode} disabled={busy || !!assessment && !assessment.complete} onChange={event => setMode(event.target.value as BlockQuizMode)}>
                <option value="objective">客观题快测</option><option value="challenge">进阶挑战（加一道开放题）</option>
              </select></label>
              <p className="text-sm text-muted-foreground">逐个覆盖本块核心点，核心题均达到 75%，且平均得分率达到 75%，视为本次检测通过。开放题为模型参考评价。</p>
              {assessmentQuery.isLoading && <p>正在恢复项目任务…</p>}
              {assessmentQuery.error && <p role="alert">{errorMessage(assessmentQuery.error)} <Button variant="ghost" onClick={() => void assessmentQuery.refetch()}>重试</Button></p>}
              {!assessmentQuery.isError && <Button disabled={busy || preparing || assessmentQuery.isLoading || !!assessment && !assessment.complete} onClick={() => { setError(''); generate.mutate(); }}>{generate.isPending || preparing ? '正在准备项目任务…' : assessment ? '换题再检验' : '开始本块检测'}</Button>}
              {assessmentQuery.data?.preparation?.error && <p role="alert">{assessmentQuery.data.preparation.error}</p>}
              {preparing && <p role="status">正在后台逐点准备题目，关闭后可以从本块或小宇恢复。</p>}
              {assessment?.items.map(item => <article key={item.task.id} className="kb-study-resource space-y-2">
                <p>{item.atom_name} · {item.membership_type === 'core' ? '核心点' : '拓展点'}</p>
                {item.task.status === 'unavailable' || item.task.is_current === false && !item.task.exam_id ? <p>当前任务已停止使用，请回小宇确认新的学习安排。</p> : <PracticeQuizCard payload={{ ...item.task.payload, learning_task_id: item.task.id, project_id: projectId!, conversation_id: projectConversation || undefined, assistance: item.task.assistance, response_type: item.task.response_type, label_source: item.task.summary?.label_source }} onResult={refreshTasks} />}
              </article>)}
              {assessment?.complete && <p className={`kb-study-status ${assessment.passed ? 'is-complete' : 'is-review'}`} role="status">{assessment.passed ? '本次检测通过' : '本次检测待强化'} · {Math.round((assessment.accuracy ?? 0) * 100)}%。长期状态与下一步建议请在小宇查看。</p>}
            </>}
            <Link className="underline" to={quizWorkspaceLink} onClick={onClose}>回小宇查看学习安排与下一步</Link>

          </section>}
        </div>
        <aside aria-labelledby="kb-study-companion-title" className="flex min-w-0 flex-col self-start rounded-xl border bg-card shadow-sm lg:sticky lg:top-0 lg:col-span-5 lg:max-h-[calc(100dvh-2rem)]">
          <header className="shrink-0 space-y-2 border-b p-4">
            <h2 id="kb-study-companion-title" className="break-words font-semibold">
              {t('🤖 小宇伴学 · 当前聚焦：{name}', { name: activeAtom?.name ?? block.short_title })}
            </h2>
            {connected ? <span className="inline-block max-w-full break-words rounded-full bg-muted px-2.5 py-1 text-xs">
              {t('已连入项目：{name}', { name: currentProject?.name || boundProject?.project_name || tree.subject })}
            </span> : linkProjectButton}
            {!chatReady && <p role="status" className="text-sm text-muted-foreground">{t('小宇暂时未就绪，请稍后重试。')}</p>}
            {connectionFailed && <p role="alert" className="break-words text-sm text-destructive">{bindingError ? errorMessage(bindingError) : t('项目暂时无法关联，请重试。')}</p>}
          </header>
          <div className="flex shrink-0 flex-wrap gap-2 px-4 py-3">
            {(guide ?? studyGuides.L1).prompts.map(prompt => <Button key={prompt} size="sm" variant="outline"
              className="h-auto min-h-8 max-w-full whitespace-normal rounded-full px-3 py-1 text-left"
              disabled={!chatReady || (connected && loading) || !!queuedQuestion} onClick={() => askXiaoYu(t(prompt))}>
              {t(prompt)}
            </Button>)}
          </div>
          <div ref={transcriptRef} role="log" aria-label={t('向小宇提问')} aria-live="off"
            className="h-[min(45dvh,24rem)] min-h-24 space-y-3 overflow-y-auto overscroll-contain border-y bg-muted/30 p-4"
            onScroll={event => {
              const list = event.currentTarget;
              followTranscript.current = list.scrollHeight - list.scrollTop - list.clientHeight < 48;
            }}>
            {transcript.length === 0 && <p className="text-sm text-muted-foreground">
              {t(connecting ? '正在打开项目对话…' : '从快捷提问开始，或输入你想问的问题。')}
            </p>}
            {transcript.map(message => message.content && <div key={message.key}
              className={`w-fit max-w-[94%] overflow-x-auto break-words rounded-xl px-3 py-2 text-sm leading-relaxed ${message.role === 'user' ? 'ml-auto bg-primary text-primary-foreground' : 'border bg-background'}`}>
              {message.role === 'user' ? <p className="whitespace-pre-wrap">{message.content}</p> : <MarkdownContent content={message.content} className="prose prose-sm max-w-none dark:prose-invert" />}
            </div>)}
          </div>
          <footer className="shrink-0 space-y-2 p-4">
            {connected && loading && <p role="status" className="text-sm text-muted-foreground">{t('小宇正在思考…')}</p>}
            <form className="flex items-end gap-2" onSubmit={event => { event.preventDefault(); askXiaoYu(draft, true); }}>
              <Input className="min-w-0 flex-1" aria-label={t('向小宇提问')} placeholder={t('向小宇提问')} value={draft} onChange={event => setDraft(event.target.value)}
                onKeyDown={event => { if (event.key === 'Enter' && event.nativeEvent.isComposing) event.preventDefault(); }} />
              <Button disabled={!draft.trim() || !chatReady || (connected && loading) || !!queuedQuestion}>{t('发送')}</Button>
            </form>
            <Link className="inline-block text-sm text-muted-foreground underline underline-offset-4" to={workspaceLink} onClick={onClose}>
              {t('跳转小宇全屏工作区')}
            </Link>
          </footer>
        </aside>
      </div>
    </DialogContent>
  </Dialog>;
}
