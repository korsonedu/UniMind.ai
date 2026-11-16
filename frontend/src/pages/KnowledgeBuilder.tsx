import { useEffect, useMemo, useState } from 'react';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ArrowClockwise, Plus, Spinner } from '@phosphor-icons/react';
import { useAuthStore } from '@/store/useAuthStore';
import { queryKeys } from '@/lib/queryKeys';
import {
  createKnowledgeBuild,
  getKnowledgeBuildDetail,
  getKnowledgeBuildStatus,
  listKnowledgeBuilds,
} from '@/lib/knowledgeBuilderApi';
import type { BuildArchetype, BuildStatus, BuildSummary } from '@/types/knowledgeBuilder';
import { KnowledgeIntakeWizard } from '@/components/KnowledgeIntakeWizard';
import { ProjectLearningContent } from '@/components/ProjectLearningPanel';
import { useXiaoYuChat } from '@/pages/xiaoyu/xiaoYuChatContext';
import { knowledgeBuildPlanningPrompt } from '@/lib/knowledgeBuildPlanning';
import { KnowledgeBuilderGraph } from '@/components/KnowledgeBuilderGraph';
import { BlockStudyDialog } from '@/components/BlockStudyDialog';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import '../styles/knowledge-builder.css';

const ARCHETYPE_OPTIONS: { value: BuildArchetype; label: string }[] = [
  { value: 'auto', label: '自动识别结构范式（推荐）' },
  { value: 'institution_mechanism_theory', label: '制度 · 机制 · 理论辨析型' },
  { value: 'formula_derivation_chain', label: '公式 · 推导 · 定量演绎型' },
  { value: 'taskflow_diagnostic_tree', label: '流程 · 排障 · 实务作业型' },
  { value: 'case_synthesis_deduction', label: '案例 · 要件 · 综合推演型' },
];

const STATUS_LABEL: Record<BuildStatus, string> = {
  PENDING: '等待中',
  RUNNING: '构建中',
  COMPLETED: '已完成',
  FAILED: '失败',
};

function extractApiError(error: unknown): string {
  if (typeof error === 'object' && error !== null && 'response' in error) {
    const resp = (error as { response?: { data?: Record<string, unknown> } }).response;
    const data = resp?.data;
    if (data && typeof data.detail === 'string') return data.detail;
    if (data && Array.isArray(data.subject) && typeof data.subject[0] === 'string') {
      return data.subject[0];
    }
    if (data && typeof data.error === 'string') return data.error;
  }
  if (error instanceof Error && error.message) return error.message;
  return '请求失败，请稍后重试。';
}

export default function KnowledgeBuilder() {
  const { buildId: paramBuildId } = useParams<{ buildId?: string }>();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const projectTab = searchParams.get('tab') === 'project';
  const { chat, openingProject } = useXiaoYuChat();
  const [selectedBlocks, setSelectedBlocks] = useState<Set<number>>(new Set());
  const [studyBlockId, setStudyBlockId] = useState<number | null>(null);
  const queryClient = useQueryClient();
  const userId = useAuthStore(s => s.user?.id);

  const [createOpen, setCreateOpen] = useState(false);
  const [newSubject, setNewSubject] = useState('');
  const [newArchetype, setNewArchetype] = useState<BuildArchetype>('auto');
  const [formError, setFormError] = useState<string | null>(null);

  const listQuery = useQuery({
    queryKey: queryKeys.knowledgeBuilder.list(userId),
    queryFn: ({ signal }) => listKnowledgeBuilds(signal),
  });

  const builds = useMemo(() => listQuery.data ?? [], [listQuery.data]);

  const defaultBuildId = useMemo(() => {
    const completed = builds.find(b => b.status === 'COMPLETED');
    return completed?.id ?? builds[0]?.id ?? null;
  }, [builds]);

  useEffect(() => {
    if (!projectTab && !paramBuildId && defaultBuildId) {
      navigate({ pathname: `/knowledge-builder/${encodeURIComponent(defaultBuildId)}`, search: searchParams.toString() }, { replace: true });
    }
  }, [paramBuildId, defaultBuildId, navigate, projectTab, searchParams]);

  const activeBuildId = paramBuildId ?? defaultBuildId;
  useEffect(() => { setSelectedBlocks(new Set()); }, [activeBuildId]);

  const selectedFromList = useMemo(
    () => (activeBuildId ? builds.find(b => b.id === activeBuildId) ?? null : null),
    [activeBuildId, builds]
  );

  const shouldPollStatus = Boolean(
    activeBuildId &&
      (!selectedFromList ||
        selectedFromList.status === 'PENDING' ||
        selectedFromList.status === 'RUNNING')
  );

  const statusQuery = useQuery({
    queryKey: queryKeys.knowledgeBuilder.status(activeBuildId ?? ''),
    queryFn: ({ signal }) => getKnowledgeBuildStatus(activeBuildId!, signal),
    enabled: shouldPollStatus,
    refetchInterval: query => {
      const status = query.state.data?.status ?? selectedFromList?.status;
      return status === 'PENDING' || status === 'RUNNING' ? 3000 : false;
    },
  });

  const effectiveSummary: BuildSummary | null = statusQuery.data ?? selectedFromList;

  useEffect(() => {
    if (!activeBuildId) return;
    if (statusQuery.data?.status === 'COMPLETED' && selectedFromList?.status !== 'COMPLETED') {
      void queryClient.invalidateQueries({ queryKey: queryKeys.knowledgeBuilder.list(userId) });
      void queryClient.invalidateQueries({ queryKey: queryKeys.knowledgeBuilder.detail(activeBuildId) });
    }
  }, [activeBuildId, queryClient, selectedFromList?.status, statusQuery.data?.status, userId]);

  const detailQuery = useQuery({
    queryKey: queryKeys.knowledgeBuilder.detail(activeBuildId ?? ''),
    queryFn: ({ signal }) => getKnowledgeBuildDetail(activeBuildId!, signal),
    enabled: Boolean(activeBuildId && effectiveSummary?.status === 'COMPLETED'),
  });

  const createMutation = useMutation({
    mutationFn: createKnowledgeBuild,
    onSuccess: created => {
      setCreateOpen(false);
      setNewSubject('');
      setNewArchetype('auto');
      setFormError(null);
      void queryClient.invalidateQueries({ queryKey: queryKeys.knowledgeBuilder.list(userId) });
      navigate(`/knowledge-builder/${encodeURIComponent(created.id)}`);
    },
    onError: err => {
      setFormError(extractApiError(err));
    },
  });

  const buildPicker = (
    <div className="kb-subject-picker">
      <select
        aria-label="选择知识结构图谱"
        className="kb-subject-select"
        value={activeBuildId ?? ''}
        onChange={e => {
          const nextId = e.target.value;
          if (nextId) navigate({ pathname: `/knowledge-builder/${encodeURIComponent(nextId)}`, search: searchParams.toString() });
        }}
      >
        {builds.length === 0 && effectiveSummary && (
          <option value={effectiveSummary.id}>{effectiveSummary.subject}</option>
        )}
        {builds.map(b => (
          <option key={b.id} value={b.id}>
            {b.subject}
            {b.status !== 'COMPLETED' ? ` · ${STATUS_LABEL[b.status]}` : ''}
          </option>
        ))}
      </select>
    </div>
  );

  const createButton = (
    <button
      type="button"
      className="kb-create-btn"
      onClick={() => {
        setFormError(null);
        setCreateOpen(true);
      }}
    >
      <Plus size={14} weight="bold" aria-hidden="true" />
      新建学科
    </button>
  );

  const createModal = (
    <Dialog open={createOpen} onOpenChange={setCreateOpen}>
      <DialogContent className="sm:max-w-[900px] max-h-[90dvh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>新建知识结构图谱</DialogTitle>
          <DialogDescription>
            先明确学习需求与基础，再生成知识原子、学习块与完整前置关系。也可以跳过问答直接构建。
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div className="space-y-1.5">
            <label htmlFor="kb-new-subject" className="text-sm font-medium text-foreground">
              学科 / 科目名称
            </label>
            <Input
              id="kb-new-subject"
              disabled={createMutation.isPending}
              value={newSubject}
              onChange={e => setNewSubject(e.target.value)}
              placeholder="例如：公司理财 · 资本结构 / 基金从业《私募股权》"
              maxLength={120}
              autoFocus
            />
          </div>

          <div className="space-y-1.5">
            <label htmlFor="kb-new-archetype" className="text-sm font-medium text-foreground">
              学科结构范式
            </label>
            <select
              id="kb-new-archetype"
              value={newArchetype}
              onChange={e => setNewArchetype(e.target.value as BuildArchetype)}
              className="um-focus-field flex h-10 w-full rounded-lg border border-input bg-background px-3 py-1 text-sm text-foreground"
            >
              {ARCHETYPE_OPTIONS.map(opt => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
          </div>

          {formError && (
            <p className="text-sm text-destructive" role="alert">
              {formError}
            </p>
          )}

          <KnowledgeIntakeWizard key={newSubject.trim()} subject={newSubject} archetype={newArchetype} building={createMutation.isPending}
            onBuild={requirements => {
              setFormError(null);
              createMutation.mutate({ subject: newSubject.trim(), archetype: newArchetype === 'auto' && requirements
                ? requirements.recommended_archetype : newArchetype, ...(requirements ? { requirements } : {}) });
            }} />
        </div>
      </DialogContent>
    </Dialog>
  );

  const workspaceTabs = <nav className="kb-workspace-tabs" aria-label="知识结构视图" role="tablist">
    <button type="button" role="tab" aria-selected={!projectTab} onClick={() => setSearchParams(previous => { const next = new URLSearchParams(previous); next.delete('tab'); return next; })}>学科知识结构图谱</button>
    <button type="button" role="tab" aria-selected={projectTab} onClick={() => setSearchParams(previous => { const next = new URLSearchParams(previous); next.set('tab', 'project'); return next; })}>小宇项目知识路径（知识关系）</button>
  </nav>;

  if (projectTab) return <div className="kb-unified-workspace">{workspaceTabs}<div className="kb-project-view"><ProjectLearningContent knowledgeOnly /></div>{createModal}</div>;

  // Render full 431 v3 interactive graph when completed detail data is ready.
  if (effectiveSummary?.status === 'COMPLETED' && detailQuery.data) {
    return (
      <div className="kb-unified-workspace">
        {workspaceTabs}
        <div className="kb-plan-toolbar">
          <span>已选择 {selectedBlocks.size} 个目标学习块</span>
          <Button type="button" variant="outline" disabled={!selectedBlocks.size || openingProject} onClick={() => {
            chat.setInput(knowledgeBuildPlanningPrompt(detailQuery.data, selectedBlocks));
            navigate({ pathname: '/xiaoyu', search: searchParams.toString() });
          }}>带入小宇学习项目规划路径</Button>
          {!!detailQuery.data.requirements && Object.keys(detailQuery.data.requirements).length > 0 && <details className="kb-requirements-summary">
            <summary>本次构建需求 · {String(detailQuery.data.requirements.learning_goal || '自定义学习需求')}</summary>
            <p>重点模块：{Array.isArray(detailQuery.data.requirements.scope_inclusions) ? detailQuery.data.requirements.scope_inclusions.join('、') : '未指定'}</p>
            <p>深度：{String(detailQuery.data.requirements.depth_preference || '未指定')}</p>
            <p>推荐入口：{Array.isArray(detailQuery.data.requirements.suggested_entry_topics) ? detailQuery.data.requirements.suggested_entry_topics.join('、') : '未指定'}</p>
            <p>{String((detailQuery.data.requirements.baseline_summary as Record<string, unknown> | undefined)?.entry_strategy || '')}</p>
          </details>}
        </div>
        <KnowledgeBuilderGraph
          key={detailQuery.data.id}
          tree={detailQuery.data}
          headerLeftSlot={buildPicker}
          headerRightSlot={createButton}
          selectedBlockIds={selectedBlocks}
          onToggleBlockSelection={id => setSelectedBlocks(current => { const next = new Set(current); if (next.has(id)) next.delete(id); else next.add(id); return next; })}
          onStudyBlock={setStudyBlockId}
        />
        {detailQuery.data.blocks.filter(block => block.id === studyBlockId).map(block => <BlockStudyDialog
          key={`${detailQuery.data.id}:${block.id}`} tree={detailQuery.data} block={block}
          progress={detailQuery.data.block_progress?.find(progress => progress.block === block.id)}
          onClose={() => setStudyBlockId(null)}
          onChanged={() => { void queryClient.invalidateQueries({ queryKey: queryKeys.knowledgeBuilder.detail(detailQuery.data.id) }); }}
        />)}
        {createModal}
      </div>
    );
  }

  return (
    <div className="kb-unified-workspace">{workspaceTabs}<div className="kb-workspace">
      <header className="kb-header">
        <div className="kb-brand">
          {builds.length > 0 || effectiveSummary ? buildPicker : <strong>学科知识结构图谱</strong>}
          {effectiveSummary && (
            <p className="kb-status">
              状态：{STATUS_LABEL[effectiveSummary.status]}
              {effectiveSummary.current_stage ? ` · ${effectiveSummary.current_stage}` : ''}
            </p>
          )}
        </div>
        <div className="kb-nav">{createButton}</div>
      </header>

      <div className="kb-viewport">
        {listQuery.isLoading || (activeBuildId && !effectiveSummary && statusQuery.isLoading) ? (
          <div className="kb-state-card">
            <Spinner size={28} className="animate-spin mx-auto mb-3 opacity-80" />
            <h2>正在载入知识结构列表…</h2>
            <p>正在同步已构建完成的学科知识块与依赖关系。</p>
          </div>
        ) : listQuery.isError ? (
          <div className="kb-state-card">
            <h2>无法获取知识结构列表</h2>
            <p>{extractApiError(listQuery.error)}</p>
            <Button type="button" onClick={() => void listQuery.refetch()}>
              <ArrowClockwise size={15} className="mr-1.5" />
              重试
            </Button>
          </div>
        ) : !activeBuildId || !effectiveSummary ? (
          <div className="kb-state-card">
            <h2>还没有可用的学科知识结构</h2>
            <p>点击右上角“新建学科”，即可为任意科目自动构建结构化 431 知识图谱。</p>
            <Button type="button" onClick={() => setCreateOpen(true)}>
              <Plus size={15} className="mr-1.5" />
              立即新建学科
            </Button>
          </div>
        ) : effectiveSummary.status === 'PENDING' || effectiveSummary.status === 'RUNNING' ? (
          <div className="kb-state-card">
            <Spinner size={28} className="animate-spin mx-auto mb-3 opacity-80" />
            <h2>正在构建《{effectiveSummary.subject}》</h2>
            <p>
              当前阶段：{effectiveSummary.current_stage || '等待后台任务启动'}（每 3 秒自动刷新进度）
            </p>
            {effectiveSummary.stats && Object.keys(effectiveSummary.stats).length > 0 && (
              <p className="text-xs">
                已生成：
                {effectiveSummary.stats.module_count ?? 0} 模块 ·{' '}
                {effectiveSummary.stats.atom_count ?? 0} 原子 ·{' '}
                {effectiveSummary.stats.block_count ?? 0} 块
              </p>
            )}
            <Button type="button" variant="outline" onClick={() => void statusQuery.refetch()}>
              <ArrowClockwise size={15} className="mr-1.5" />
              立即刷新状态
            </Button>
          </div>
        ) : effectiveSummary.status === 'FAILED' ? (
          <div className="kb-state-card">
            <h2>《{effectiveSummary.subject}》构建失败</h2>
            <p>{effectiveSummary.error_message || '后台构建流水线未能正常完成，请重新发起构建。'}</p>
            <Button
              type="button"
              onClick={() => {
                setNewSubject(effectiveSummary.subject);
                setFormError(null);
                setCreateOpen(true);
              }}
            >
              重新构建该科目
            </Button>
          </div>
        ) : detailQuery.isError ? (
          <div className="kb-state-card">
            <h2>加载图谱详情失败</h2>
            <p>{extractApiError(detailQuery.error)}</p>
            <Button type="button" onClick={() => void detailQuery.refetch()}>
              <ArrowClockwise size={15} className="mr-1.5" />
              重新加载
            </Button>
          </div>
        ) : (
          <div className="kb-state-card">
            <Spinner size={28} className="animate-spin mx-auto mb-3 opacity-80" />
            <h2>正在展开《{effectiveSummary.subject}》结构图…</h2>
            <p>正在获取学习块、步骤与跨块接口点数据。</p>
          </div>
        )}
      </div>

      {createModal}
    </div></div>
  );
}
