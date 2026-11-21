import { useCallback, useContext, useEffect, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useSearchParams } from 'react-router-dom';
import { toast } from 'sonner';
import api from '@/lib/api';
import { normalizeApiError } from '@/lib/apiError';
import { learningKey, passedLearningTask, useProjectLearning, type LearningTask, type ProjectLearning } from '@/lib/projectLearning';
import { queryClient } from '@/lib/queryClient';
import { t, useLocale } from '@/i18n';
import { useAuthStore } from '@/store/useAuthStore';
import { useXiaoYuChat } from '@/pages/xiaoyu/xiaoYuChatContext';
import { LearningPathSidebarContext } from './WorkspaceContext';

export const learningComposerId = 'xiaoyu-learning-composer';

type Overview = 'path' | 'proposal' | 'knowledge' | 'report';
type View = { kind: Overview } | { kind: 'task'; id: string; back: Overview };

export function useLearningWorkspace() {
  const locale = useLocale();
  const { chat, openingProject } = useXiaoYuChat();
  const userId = useAuthStore(state => state.user?.id);
  const [params, setParams] = useSearchParams();
  const sidebar = useContext(LearningPathSidebarContext);
  const { open, setAvailable } = sidebar;
  const query = useProjectLearning(chat.projectId);
  const project = query.data;
  const taskQuery = useQuery({
    queryKey: ['learning-tasks', userId, chat.projectId],
    enabled: !!project?.planning_enabled,
    queryFn: ({ signal }) => api.get<{ tasks: LearningTask[] }>(`/ai/projects/${chat.projectId}/learning/tasks/`, { signal }).then(response => response.data),
    refetchInterval: query => query.state.data?.tasks.some(task => task.status === 'processing') ? 2500 : false,
  });
  const tasks = taskQuery.data?.tasks || [];
  const [view, setView] = useState<View>({ kind: 'path' });
  const [busy, setBusy] = useState(false);
  const inFlight = useRef(false);
  const activity = useRef<{ conversationId: string; payload?: Record<string, unknown> } | null>(null);
  const getExtraPayload = useCallback(() => {
    const reference = activity.current;
    return reference?.conversationId === chat.conversationId && reference.payload ? { learning_activity: reference.payload } : {};
  }, [chat.conversationId]);
  const refresh = useCallback(() => {
    void queryClient.invalidateQueries({ queryKey: learningKey(userId, chat.projectId) });
    void queryClient.invalidateQueries({ queryKey: ['learning-tasks', userId, chat.projectId] });
  }, [userId, chat.projectId]);

  const stages = project?.plan.stages || [];
  const completedStages = new Set(stages.filter(stage => tasks.some(task => task.stage_id === stage.id &&
    task.is_current !== false && task.purpose !== 'diagnostic' && passedLearningTask(task))).map(stage => stage.id));
  const allDone = stages.length > 0 && stages.every(stage => completedStages.has(stage.id));
  const nextStage = stages.find(stage => stage.id === project?.current_stage && !completedStages.has(stage.id))
    || stages.find(stage => !completedStages.has(stage.id) && stage.prerequisites.every(id => completedStages.has(id)));

  useEffect(() => {
    setAvailable(true);
    return () => setAvailable(false);
  }, [setAvailable]);

  const deepTask = params.get('learning_task');
  const deepView = params.get('learning_view');
  const overview = deepView === 'knowledge' || deepView === 'proposal' || deepView === 'path' ? deepView : null;
  const explicitProject = params.has('project');
  const proposalRevision = project?.pending_plan.plan ? project.pending_plan.base_revision ?? project.revision : null;
  const diagnostic = [...tasks].reverse().find(task => task.purpose === 'diagnostic');
  const latestTaskId = [...tasks].reverse().find(task => task.is_current !== false)?.id;
  const event = project?.planning_enabled
    ? JSON.stringify([project.status, project.current_stage, proposalRevision, latestTaskId, diagnostic?.status === 'completed', [...completedStages]])
    : null;
  const eventReady = !!event && !openingProject && !explicitProject;
  const [handledEvent, setHandledEvent] = useState<string | null>(null);
  if (eventReady && event !== handledEvent) {
    setHandledEvent(event);
    if (!deepTask && !overview && proposalRevision !== null) setView({ kind: 'proposal' });
    else if (!deepTask && !overview && project?.status === 'completed') setView({ kind: 'report' });
  }
  const seenEvent = useRef<string | null>(null);
  useEffect(() => {
    if (!eventReady || event === seenEvent.current) return;
    seenEvent.current = event;
    open();
  }, [eventReady, event, open]);

  const deepReady = !explicitProject && !openingProject && !!chat.projectId && (!!deepTask || !!overview);
  const deepKey = deepReady ? `${chat.projectId}:${deepTask || ''}:${deepView || ''}` : null;
  const [handledDeep, setHandledDeep] = useState<string | null>(null);
  if (deepKey !== handledDeep) {
    setHandledDeep(deepKey);
    if (deepKey) {
      if (deepTask) {
        setView({ kind: 'task', id: deepTask, back: project?.pending_plan.plan ? 'proposal' : project?.status === 'completed' ? 'report' : 'path' });
      } else if (overview) {
        setView({ kind: overview });
      }
    }
  }
  useEffect(() => {
    if (!deepKey) return;
    open();
    setParams(previous => {
      const next = new URLSearchParams(previous);
      next.delete('learning_task');
      next.delete('learning_view');
      return next;
    }, { replace: true });
  }, [deepKey, open, setParams]);

  const show = (kind: Overview) => setView({ kind });
  const openTask = (id: string) => {
    setView(previous => ({ kind: 'task', id, back: previous.kind === 'task' ? previous.back : previous.kind }));
    open();
  };
  const ask = (message: string, payload?: Record<string, unknown>) => {
    if (chat.loading || activity.current?.conversationId === chat.conversationId || !chat.bot || openingProject) {
      toast.info(t('小宇正在处理，请稍后再试。'));
      return;
    }
    if (window.matchMedia('(max-width: 767px)').matches) sidebar.close();
    const reference = { conversationId: chat.conversationId, payload };
    activity.current = reference;
    void chat.doSend(message, false, { preserveDraft: true }).finally(() => {
      if (activity.current === reference) activity.current = null;
    });
  };
  const prefill = (text: string) => {
    if (!chat.input.trim()) chat.setInput(text);
    if (window.matchMedia('(max-width: 767px)').matches) sidebar.close();
    requestAnimationFrame(() => document.getElementById(learningComposerId)?.focus());
  };
  const act = async (action: string, extra: Record<string, unknown> = {}) => {
    if (!project || inFlight.current) return false;
    inFlight.current = true;
    setBusy(true);
    try {
      const { data } = await api.patch<ProjectLearning>(`/ai/projects/${project.project_id}/learning/`,
        { action, revision: project.revision, ...extra }, { headers: { 'Accept-Language': locale } });
      queryClient.setQueryData(learningKey(userId, project.project_id, locale), data);
      if (action === 'accept' || action === 'reject' || action === 'resume') show('path');
      refresh();
      return true;
    } catch (error) {
      toast.error(normalizeApiError(error, t('学习安排未更新，请重试。')).message);
      refresh();
      return false;
    } finally {
      inFlight.current = false;
      setBusy(false);
    }
  };
  const setupSample = async () => {
    if (!project || inFlight.current) return;
    inFlight.current = true;
    setBusy(true);
    try {
      await api.post(`/ai/projects/${project.project_id}/learning/tasks/`, { action: 'sample' });
      refresh();
    } catch (error) {
      toast.error(normalizeApiError(error, t('样板暂时无法接入。')).message);
    } finally {
      inFlight.current = false;
      setBusy(false);
    }
  };
  return { sidebar, query, taskQuery, project, tasks, openingProject, completedStages, nextStage, allDone, view, show,
    openLearning: open, openTask, ask, prefill, act, busy, refresh, setupSample, getExtraPayload };
}

export type LearningWorkspace = ReturnType<typeof useLearningWorkspace>;
