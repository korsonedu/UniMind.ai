import React, { useState, useEffect, useMemo } from 'react';
import { Card } from '@/components/ui/card';
import { ArrowRight, Brain, ChartLine, CaretDown, Bell, Target, Info, Funnel } from '@phosphor-icons/react';
import { cn, normalizeOptions } from '@/lib/utils';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { Checkbox } from '@/components/ui/checkbox';
import { PageWrapper } from '@/components/PageWrapper';
import { toast } from "sonner";
import api from '@/lib/api';
import { useSystemStore } from '@/store/useSystemStore';
import { useNavigate } from 'react-router-dom';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import {
  getLearningReminderSettings,
  updateLearningReminderSetting,
  type LearningReminderSettings,
} from '@/lib/learningReminders';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { formatApiErrorToast } from '@/lib/apiError';
import { useIsMobile } from '@/lib/useIsMobile';
import { useQuery } from '@tanstack/react-query';
import { Skeleton, SkeletonCard } from '@/components/ui/skeleton';
import { queryKeys } from '@/lib/queryKeys';

// Modularized Components
import { AssessmentDialog } from './test-ladder/AssessmentDialog';

type MemorixCurvePoint = { date: string; predicted: number; actual: number; count: number };
type MemorixCurvePayload = {
  window_days: number;
  time_series: MemorixCurvePoint[];
  fit_curve: Array<{ bucket: string; predicted: number; actual: number; count: number }>;
  metrics: {
    review_count: number;
    rmse: number | null;
    mae: number | null;
    avg_predicted: number | null;
    avg_actual: number | null;
  };
  profile: {
    last_optimized_at: string | null;
    current_loss: number | null;
    total_reviews_used: number;
    weights_preview?: number[];
  };
};
type MemorixOptimizationHistory = {
  id: number;
  previous_loss: number | null;
  new_loss: number | null;
  improvement_ratio: number;
  reviews_used: number;
  accepted: boolean;
  created_at: string;
};

export const TestLadder: React.FC = () => {
  const navigate = useNavigate();
  const isMobile = useIsMobile();
  const [reminderSettings, setReminderSettings] = useState<LearningReminderSettings>(getLearningReminderSettings());
  const [selectedSubIds, setSelectedSubIds] = useState<number[]>([]);
  const [preference, setPreference] = useState<string>(() => {
    try { return localStorage.getItem('quiz_preference') || 'balanced'; } catch { return 'balanced'; }
  });
  
  // Data State
  const [questions, setQuestions] = useState<any[]>([]);
  const [goals, setGoals] = useState({
    review_goal: 0,
    new_questions: 0,
    at_risk_count: 0,
    recommended_questions: 5,
    estimated_minutes: 14,
    weak_focus_count: 0,
  });
  
  // Assessment UI State
  const [isTestOpen, setIsTestOpen] = useState(false);
  const [difficulty, setDifficulty] = useState("mixed");
  const [qCount, setQCount] = useState("5");
  const [isCustomCount, setIsCustomCount] = useState(false);
  const [currentIdx, setCurrentIdx] = useState(0);
  const [answers, setAnswers] = useState<any>({});
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [gradingMessage] = useState("");

  const [memorixCurve, setMemorixCurve] = useState<MemorixCurvePayload | null>(null);
  const [memorixHistory, setMemorixHistory] = useState<MemorixOptimizationHistory[]>([]);

  useEffect(() => {
    fetchGoals();
    fetchMemorixCurve();
    fetchMemorixHistory();
  }, []);

  // React Query: 学科列表 — 低频变更数据，缓存 2 分钟
  const { data: subjectList = [] } = useQuery({
    queryKey: queryKeys.knowledgePoints.subjects,
    queryFn: () => api.get('/quizzes/knowledge-points/').then(r => {
      const data = Array.isArray(r.data) ? r.data : (r.data?.results || []);
      return data.map((item: any) => ({ id: item.id, name: item.name, code: item.code }));
    }),
    staleTime: 120000,
  });
  const [loadingStates, setLoadingStates] = useState({ goals: true, curve: true, history: true });
  const isPageLoading = loadingStates.goals || loadingStates.curve || loadingStates.history;

  useEffect(() => {
    if (isCustomCount) return;
    const suggested = Number(goals.recommended_questions || 0);
    if (!Number.isFinite(suggested) || suggested <= 0) return;
    setQCount(String(Math.max(1, Math.min(50, suggested))));
  }, [goals.recommended_questions, isCustomCount]);

  const fetchGoals = async () => {
    try {
      const res = await api.get('/quizzes/stats/');
      setGoals(res.data);
    } catch (e) { console.error('fetchGoals failed', e); }
    finally { setLoadingStates(s => ({ ...s, goals: false })); }
  };

  const fetchMemorixCurve = async () => {
    try {
      const res = await api.get('/quizzes/memorix/curve/', { params: { window_days: 90 } });
      setMemorixCurve(res.data as MemorixCurvePayload);
    } catch (e) { console.error('fetchMemorixCurve failed', e); }
    finally { setLoadingStates(s => ({ ...s, curve: false })); }
  };

  const fetchMemorixHistory = async () => {
    try {
      const res = await api.get('/quizzes/memorix/optimization-history/');
      setMemorixHistory((res.data?.results || []) as MemorixOptimizationHistory[]);
    } catch (e) { console.error('fetchMemorixHistory failed', e); }
    finally { setLoadingStates(s => ({ ...s, history: false })); }
  };

  const toggleFavorite = async (qId: number) => {
    try {
      const res = await api.post('/quizzes/favorite/toggle/', { question_id: qId });
      setQuestions(questions.map(q => q.id === qId ? { ...q, is_favorite: res.data.is_favorite } : q));
      toast.success(res.data.is_favorite ? '已加入收藏' : '已取消收藏');
    } catch (e) { toast.error(formatApiErrorToast(e, '操作失败')); }
  };

  const toggleMastered = async (qId: number) => {
    try {
      const res = await api.post('/quizzes/mastered/toggle/', { question_id: qId });
      const isNowMastered = res.data.is_mastered;
      setQuestions(questions.map(q => q.id === qId ? { ...q, is_mastered: isNowMastered } : q));
      if (isNowMastered) {
        const newAnswers = { ...answers };
        delete newAnswers[qId];
        setAnswers(newAnswers);
        toast.success('稳稳拿捏！');
      }
    } catch (e) { toast.error(formatApiErrorToast(e, '操作失败')); }
  };

  const startTest = async () => {
    const parsedCount = Number.parseInt(qCount, 10);
    const normalizedCount = Number.isFinite(parsedCount) ? Math.max(1, Math.min(parsedCount, 50)) : 5;
    if (`${normalizedCount}` !== qCount) setQCount(`${normalizedCount}`);

    if (isMobile) {
      navigate(`/tests/session?count=${normalizedCount}&preference=${preference}`);
      return;
    }

    try {
      const params = new URLSearchParams({ limit: String(normalizedCount) });
      params.set('preference', preference);
      if (selectedSubIds.length > 0) {
        params.set('sub_ids', selectedSubIds.join(','));
      }
      if (difficulty && difficulty !== 'mixed') {
        params.set('difficulty_level', difficulty);
      }
      const res = await api.get(`/quizzes/questions/?${params.toString()}`);
      if (res.data.length === 0) return toast.error('题库暂无可用题目');
      setQuestions(res.data.map((q: any) => ({ ...q, options: normalizeOptions(q.options) })));
      setIsTestOpen(true);
      setAnswers({});
      setCurrentIdx(0);
    } catch (e) { toast.error(formatApiErrorToast(e, '题目加载失败')); }
  };

  const handleSubmit = async () => {
    const unmasteredQuestions = questions.filter(q => !q.is_mastered);
    const answeredCount = Object.keys(answers).length;
    if (unmasteredQuestions.length > 0 && answeredCount < unmasteredQuestions.length) {
      return toast.error(`请完成所有题目 (${answeredCount}/${unmasteredQuestions.length})`);
    }
    if (unmasteredQuestions.length === 0) {
      setIsTestOpen(false);
      return toast.info('练习已结束');
    }
    setIsSubmitting(true);
    try {
      const payload = unmasteredQuestions.map(q => ({ question_id: q.id, answer: answers[q.id] }));
      await api.post('/quizzes/submit-exam/', { answers: payload });
      toast.success('试卷已提交 AI 批改', { description: '完成后请在通知中心点击查看报告。' });
      setIsTestOpen(false);
      fetchGoals();
    } catch (e: any) {
      toast.error(formatApiErrorToast(e, '提交失败'));
    } finally { setIsSubmitting(false); }
  };

  const memorixChart = useMemo(() => {
    const series = memorixCurve?.time_series || [];
    const graphWidth = 760;
    const graphHeight = 220;
    const top = 16;
    const right = 16;
    const bottom = 38;
    const left = 16;
    const innerWidth = graphWidth - left - right;
    const innerHeight = graphHeight - top - bottom;
    const len = series.length;

    const pointAt = (index: number, value: number) => {
      const x = len <= 1 ? left + innerWidth / 2 : left + (index / (len - 1)) * innerWidth;
      const y = top + (1 - Math.max(0, Math.min(1, value))) * innerHeight;
      return { x, y };
    };

    const predictedPoints = series.map((item, idx) => pointAt(idx, Number(item.predicted || 0)));
    const actualPoints = series.map((item, idx) => pointAt(idx, Number(item.actual || 0)));
    const predictedPath = predictedPoints.map((p, idx) => `${idx === 0 ? 'M' : 'L'} ${p.x} ${p.y}`).join(' ');
    const actualPath = actualPoints.map((p, idx) => `${idx === 0 ? 'M' : 'L'} ${p.x} ${p.y}`).join(' ');

    return { graphWidth, graphHeight, top, right, bottom, left, predictedPoints, actualPoints, predictedPath, actualPath };
  }, [memorixCurve]);

  // 全部数据未就绪时渲染骨架屏
  if (isPageLoading) {
    return (
      <PageWrapper title="学术天梯" subtitle="基于 Memorix 记忆算法的智能评估，精准量化学术成长路径。">
        <div className="max-w-6xl mx-auto space-y-8">
          <div className="space-y-4 max-w-2xl">
            <Skeleton className="h-10 w-64 rounded-lg" />
            <Skeleton className="h-5 w-96 rounded-md" />
            <Skeleton className="h-4 w-48 rounded-md" />
          </div>
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
            {Array.from({ length: 4 }).map((_, i) => (
              <SkeletonCard key={i} />
            ))}
          </div>
          <Skeleton className="h-48 w-full rounded-xl" />
        </div>
      </PageWrapper>
    );
  }

  return (
    <PageWrapper title="学术天梯" subtitle="基于 Memorix 记忆算法的智能评估，精准量化学术成长路径。">
      <div className="flex flex-col gap-8 md:gap-12 text-left pb-20 max-w-6xl mx-auto">
        {isMobile && (
            <Popover>
              <PopoverTrigger asChild>
                <Button variant="outline" size="icon" className="h-8 w-8 rounded-lg border-border">
                  <Bell className="h-4 w-4" />
                </Button>
              </PopoverTrigger>
              <PopoverContent side="bottom" align="end" className="w-64 rounded-2xl p-4 bg-card border-border">
                <div className="space-y-3 text-left">
                  <p className="text-xs font-semibold text-muted-foreground">提醒设置</p>
                  <div className="flex items-center justify-between">
                    <Label className="text-xs font-bold">题型提醒</Label>
                    <Switch
                      checked={reminderSettings.questionType}
                      onCheckedChange={(enabled) => {
                        setReminderSettings(updateLearningReminderSetting('questionType', enabled));
                      }}
                    />
                  </div>
                  <div className="flex items-center justify-between">
                    <Label className="text-xs font-bold">做题结果提醒</Label>
                    <Switch
                      checked={reminderSettings.testResult}
                      onCheckedChange={(enabled) => {
                        setReminderSettings(updateLearningReminderSetting('testResult', enabled));
                      }}
                    />
                  </div>
                </div>
              </PopoverContent>
            </Popover>
          )}

        <>{(
          <Card className={cn(
            "bg-card overflow-hidden relative transition-all",
            isMobile ? "border-none shadow-none rounded-none p-0" : "border border-border rounded-2xl p-12 shadow-sm hover:shadow-md"
          )}>
            <div className="absolute top-0 right-0 w-[400px] h-[400px] bg-indigo-500/5 rounded-full blur-[80px] -mr-32 -mt-32 pointer-events-none" />
            <div className={cn(
              "relative z-10",
              isMobile
                ? "flex flex-col items-start justify-between gap-4"
                : "flex flex-col lg:flex-row items-center justify-between gap-12"
            )}>
              <div className={cn("max-w-2xl text-left", isMobile ? "space-y-4" : "space-y-6")}>
                <div className="flex items-start gap-2">
                  <h2 className={cn("font-black tracking-tighter text-foreground leading-[1.1]", isMobile ? "text-2xl" : "text-4xl md:text-5xl")}>
                    Memorix-Field
                    <br />
                    第二代智能评估系统
                  </h2>
                  <Dialog>
                    <DialogTrigger asChild>
                      <button
                        type="button"
                        aria-label="Memorix 拟合曲线"
                        className={cn(
                          "shrink-0 rounded-full border border-border text-muted-foreground hover:text-foreground hover:bg-muted/60 transition-colors",
                          isMobile ? "h-6 w-6 mt-1" : "h-7 w-7 mt-2"
                        )}
                      >
                        <Info className="h-3.5 w-3.5 mx-auto" />
                      </button>
                    </DialogTrigger>
                    <DialogContent className="max-w-xl rounded-2xl">
                      <DialogHeader>
                        <DialogTitle>Memorix-Field：第二代智能评估系统</DialogTitle>
                        <DialogDescription>
                          Memorix-Field 在间隔重复的基础上引入了知识图谱全局诊断。不是替代，是补全——从「单题维度的记忆管理」扩展到「知识结构维度的诊断」。
                        </DialogDescription>
                      </DialogHeader>
                      <div className="space-y-3 text-sm text-muted-foreground leading-relaxed">
                        <p>记忆引擎 — 题级遗忘建模。持续拟合每道题的记忆衰减曲线，以题为单位做个体化参数估计。在临界遗忘点精准介入，减少无效重复，提高单位时间的记忆留存率。这是 Memorix 第一代的核心能力，在第二代中继续作为调度基础。</p>
                        <p>图诊断引擎 — 知识图谱全局推断。将学科知识建模为高斯马尔可夫随机场（GMRF），利用图结构上相邻知识点的掌握度相似性，从部分观测外推全部知识点的掌握度。一场覆盖 10% 知识点的考试，就能输出全域掌握度热力图。</p>
                        <p>双引擎协同。记忆引擎输出「何时复习哪道题」，图诊断引擎输出「哪些知识群存在结构薄弱」。前者优化时间分配，后者优化知识建构。两者共享同一个学生模型，调度结果受诊断结果加权。</p>
                      </div>
                    </DialogContent>
                  </Dialog>
                </div>
                <p className={cn("font-medium leading-relaxed text-muted-foreground max-w-lg", isMobile ? "text-sm" : "text-base")}>
                  {isMobile
                    ? '记忆调度与知识图谱诊断的联合引擎。从你的做题记录出发，在单题层面调度复习，在知识结构层面定位薄弱群。'
                    : 'Memorix-Field 由两个协同模块构成：记忆引擎追踪每道题的遗忘曲线，决定何时复习；图诊断引擎建模整个学科的知识图谱，从稀疏的考试结果推断全部知识点的掌握度。'}
                </p>
                <p className={cn("font-bold text-indigo-600/80", isMobile ? "text-[12px]" : "text-sm")}>
                  {`本轮建议：${goals.recommended_questions} 题，预计 ${goals.estimated_minutes} 分钟（薄弱强化 ${goals.weak_focus_count} 题）`}
                </p>

                {/* ── 三连选行 ── */}
                <div className={cn("flex flex-wrap items-end gap-3 pt-4 w-full", isMobile && "flex-col")}>
                  {/* 题数选择 */}
                  {isMobile ? (
                    <div className="space-y-1.5 flex-1 w-full">
                      <span className="text-[10px] font-bold text-muted-foreground ml-1">抽题数量</span>
                      <Input type="number" min="1" value={qCount} onChange={(e) => setQCount(e.target.value)} onBlur={() => { if (!qCount || parseInt(qCount) < 1) setQCount("1"); }} className="w-full h-9 rounded-xl bg-muted border-border font-bold text-center" />
                    </div>
                  ) : (
                    <div className="flex flex-col gap-1.5">
                      <span className="text-[11px] font-bold text-muted-foreground uppercase tracking-[0.15em] ml-1">题数</span>
                      <div className="flex items-center gap-2">
                        <DropdownMenu modal={false}>
                          <DropdownMenuTrigger asChild>
                            <Button variant="outline" className="h-11 px-4 rounded-xl bg-card border-border text-foreground font-bold text-sm hover:bg-muted/80 transition-all flex items-center gap-2 shadow-sm">
                              {isCustomCount ? '自定义' : `${qCount} 道题`}<CaretDown className="h-3.5 w-3.5 opacity-50" />
                            </Button>
                          </DropdownMenuTrigger>
                          <DropdownMenuContent className="w-32 rounded-xl border-border bg-card shadow-lg p-1.5" align="start">
                            {["3", "5", "10", "20"].map(v => (
                              <DropdownMenuItem key={v} onClick={() => { setIsCustomCount(false); setQCount(v); }} className="rounded-lg font-bold py-2 cursor-pointer text-sm">{`${v} 道题`}</DropdownMenuItem>
                            ))}
                            <DropdownMenuItem onClick={() => setIsCustomCount(true)} className="rounded-lg font-bold py-2 text-indigo-600 cursor-pointer text-sm">自定义</DropdownMenuItem>
                          </DropdownMenuContent>
                        </DropdownMenu>
                        {isCustomCount && <Input type="number" min="1" value={qCount} onChange={(e) => setQCount(e.target.value)} onBlur={() => { if (!qCount || parseInt(qCount) < 1) setQCount("1"); }} className="w-20 h-11 rounded-xl bg-card border-border font-bold text-center shadow-sm" />}
                      </div>
                    </div>
                  )}

                  {/* 难度选择 */}
                  <div className="flex flex-col gap-1.5">
                    <span className="text-[11px] font-bold text-muted-foreground uppercase tracking-[0.15em] ml-1">难度</span>
                    <Select value={difficulty} onValueChange={setDifficulty}>
                      <SelectTrigger className="h-11 px-4 rounded-xl bg-card border-border text-foreground font-bold text-sm shadow-sm w-[130px]"><SelectValue /></SelectTrigger>
                      <SelectContent className="rounded-xl border-border">
                        <SelectItem value="mixed">混合难度</SelectItem>
                        <SelectItem value="entry">入门</SelectItem>
                        <SelectItem value="easy">简单</SelectItem>
                        <SelectItem value="normal">适当</SelectItem>
                        <SelectItem value="hard">困难</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  {/* 抽题偏好 */}
                  <div className="flex flex-col gap-1.5">
                    <span className="text-[11px] font-bold text-muted-foreground uppercase tracking-[0.15em] ml-1">偏好</span>
                    <div className="flex rounded-xl bg-muted p-1 gap-0.5 h-11 items-center">
                      {([
                        { value: 'balanced', label: '智能混合' },
                        { value: 'new_first', label: '偏新题' },
                        { value: 'review_first', label: '偏复习' },
                      ] as const).map(({ value, label }) => (
                        <button
                          key={value}
                          type="button"
                          onClick={() => {
                            setPreference(value);
                            try { localStorage.setItem('quiz_preference', value); } catch {}
                          }}
                          className={cn(
                            "rounded-lg px-3 py-1.5 text-xs font-bold transition-all h-full",
                            preference === value
                              ? "bg-card text-foreground shadow-sm"
                              : "text-muted-foreground hover:text-foreground"
                          )}
                        >
                          {label}
                        </button>
                      ))}
                    </div>
                  </div>

                  {/* 学科筛选 */}
                  <Popover>
                    <PopoverTrigger asChild>
                      <Button variant="outline" className={cn("rounded-xl bg-card border-border text-foreground font-bold transition-all flex items-center gap-2 shadow-sm h-11 px-4 text-sm")}>
                        <Funnel className="h-4 w-4 shrink-0" />
                        <span className="truncate">{selectedSubIds.length > 0 ? '学科筛选' : '全部学科'}</span>
                        <Badge variant="outline" className={cn("ml-0.5 h-5 min-w-[1.25rem] px-1 rounded-full text-[10px] font-bold", selectedSubIds.length > 0 ? "bg-indigo-600 text-white border-indigo-600" : "bg-muted text-muted-foreground border-border")}>{selectedSubIds.length}</Badge>
                      </Button>
                    </PopoverTrigger>
                    <PopoverContent side="bottom" align="start" className="w-56 rounded-2xl p-3 bg-card border-border">
                      <div className="space-y-1">
                        <p className="text-xs font-semibold text-muted-foreground mb-2 pb-1 border-b border-border">学科筛选</p>
                        {subjectList.length === 0 ? (<p className="text-xs text-muted-foreground py-2">加载中...</p>) : (
                          subjectList.map((subject: { id: number; name: string; code: string }) => (
                            <div key={subject.id} className="flex items-center gap-2 py-1.5 px-1 rounded-lg hover:bg-muted/60 transition-colors">
                              <Checkbox id={`subject-${subject.id}`} checked={selectedSubIds.includes(subject.id)} onCheckedChange={(checked) => { checked ? setSelectedSubIds(prev => [...prev, subject.id]) : setSelectedSubIds(prev => prev.filter(id => id !== subject.id)); }} />
                              <label htmlFor={`subject-${subject.id}`} className="text-xs font-medium cursor-pointer select-none flex-1 leading-tight">{subject.name}</label>
                            </div>
                          ))
                        )}
                        {subjectList.length > 0 && selectedSubIds.length > 0 && (<button onClick={() => setSelectedSubIds([])} className="text-xs font-bold text-indigo-600 hover:text-indigo-700 pt-1 w-full text-left">清除筛选</button>)}
                      </div>
                    </PopoverContent>
                  </Popover>
                </div>

                {/* ── CTA 按钮行 ── */}
                <div className={cn("flex flex-wrap items-center gap-3 pt-2 w-full", isMobile && "flex-col")}>
                  <Button onClick={startTest} className={cn("text-white rounded-xl font-bold shadow-lg transition-all active:scale-95 bg-primary hover:opacity-90 border-0 flex-1", isMobile ? "h-12 px-6 text-sm" : "h-14 px-12 text-lg")}>
                    <Brain className="mr-2 h-5 w-5" />开启训练<ArrowRight className="ml-2 h-5 w-5" />
                  </Button>
                  <Button variant="outline" onClick={() => navigate('/tests/review')} className={cn("rounded-xl font-bold border-border shadow-sm hover:shadow-md transition-all", isMobile ? "h-10 text-sm flex-1" : "h-14 px-6 text-sm")}>
                    <Target className="mr-2 h-4 w-4" />错题复盘
                  </Button>
                </div>
              </div>

              <div className={cn(
                isMobile
                  ? "grid grid-cols-2 gap-2 w-full shrink-0"
                  : "flex flex-col gap-4 w-full lg:w-72 shrink-0"
              )}>
                <div className={cn(
                  "bg-muted transition-all flex flex-col justify-center",
                  isMobile ? "p-3 rounded-xl border-none shadow-none" : "p-7 border border-border rounded-xl hover:bg-card hover:shadow-lg"
                )}>
                  <div className="flex items-center gap-3 mb-2">
                    <div className={cn("bg-card shadow-sm flex items-center justify-center text-indigo-500", isMobile ? "h-8 w-8 rounded-xl" : "h-9 w-9 rounded-2xl")}><Brain className="h-4 w-4" /></div>
                    <p className={cn("font-bold text-muted-foreground uppercase tracking-widest leading-none", isMobile ? "text-[11px]" : "text-[14px]")}>今日复习</p>
                  </div>
                  <div className="flex items-baseline gap-1">
                    <p className={cn("font-black text-foreground tabular-nums", isMobile ? "text-3xl" : "text-4xl")}>{goals.review_goal}</p>
                    <span className="text-[12px] font-bold text-muted-foreground uppercase">Due</span>
                  </div>
                </div>
                <div className={cn(
                  "bg-muted transition-all flex flex-col justify-center",
                  isMobile ? "p-3 rounded-xl border-none shadow-none" : "p-7 border border-border rounded-xl hover:bg-card hover:shadow-lg"
                )}>
                  <div className="flex items-center gap-3 mb-2">
                    <div className={cn("bg-card shadow-sm flex items-center justify-center text-muted-foreground", isMobile ? "h-8 w-8 rounded-xl" : "h-9 w-9 rounded-2xl")}><ChartLine className="h-4 w-4" /></div>
                    <p className={cn("font-bold text-muted-foreground uppercase tracking-widest leading-none", isMobile ? "text-[11px]" : "text-[14px]")}>记忆临界</p>
                  </div>
                  <div className="flex items-baseline gap-1">
                    <p className={cn("font-black text-foreground tabular-nums", isMobile ? "text-3xl" : "text-4xl")}>{goals.at_risk_count || 0}</p>
                    <span className="text-[12px] font-bold text-muted-foreground uppercase">At Risk</span>
                  </div>
                </div>
              </div>
            </div>
          </Card>
        )}

        {(
          <Card className={cn(
            "bg-card overflow-hidden transition-all",
            isMobile ? "border border-border rounded-2xl p-4" : "border border-border rounded-xl p-6 shadow-sm"
          )}>
            <div className="flex items-center justify-between gap-3 mb-4">
              <div>
                <p className="label-meta">Memorix 拟合曲线</p>
                <p className="text-sm font-bold text-foreground mt-1">{`记忆预测 vs 实际掌握（近 ${memorixCurve?.window_days || 90} 天）`}</p>
              </div>
              <Button variant="outline" className="h-8 rounded-lg text-xs font-bold" onClick={() => { fetchMemorixCurve(); fetchMemorixHistory(); }}>
                刷新
              </Button>
            </div>
            {(memorixCurve?.time_series || []).length > 0 ? (
              <div className="space-y-4">
                <div className="grid grid-cols-2 md:grid-cols-5 gap-2">
                  <div className="rounded-xl bg-muted px-3 py-2">
                    <p className="text-[10px] font-bold text-muted-foreground uppercase">样本量</p>
                    <p className="text-sm font-bold text-foreground">{memorixCurve?.metrics?.review_count ?? 0}</p>
                  </div>
                  <div className="rounded-xl bg-muted px-3 py-2">
                    <p className="text-[10px] font-bold text-muted-foreground uppercase">预测准确度</p>
                    <p className="text-sm font-bold text-foreground">{memorixCurve?.metrics?.rmse ?? '--'}</p>
                  </div>
                  <div className="rounded-xl bg-muted px-3 py-2">
                    <p className="text-[10px] font-bold text-muted-foreground uppercase">平均误差</p>
                    <p className="text-sm font-bold text-foreground">{memorixCurve?.metrics?.mae ?? '--'}</p>
                  </div>
                  <div className="rounded-xl bg-muted px-3 py-2">
                    <p className="text-[10px] font-bold text-muted-foreground uppercase">预测掌握度</p>
                    <p className="text-sm font-bold text-foreground">{memorixCurve?.metrics?.avg_predicted ?? '--'}</p>
                  </div>
                  <div className="rounded-xl bg-muted px-3 py-2">
                    <p className="text-[10px] font-bold text-muted-foreground uppercase">实际掌握度</p>
                    <p className="text-sm font-bold text-foreground">{memorixCurve?.metrics?.avg_actual ?? '--'}</p>
                  </div>
                </div>
                <div className="rounded-2xl border border-border bg-muted/30 p-3">
                  <svg viewBox={`0 0 ${memorixChart.graphWidth} ${memorixChart.graphHeight}`} className="w-full h-48">
                    <line x1={memorixChart.left} y1={memorixChart.graphHeight - memorixChart.bottom} x2={memorixChart.graphWidth - memorixChart.right} y2={memorixChart.graphHeight - memorixChart.bottom} stroke="currentColor" className="text-border" />
                    <path d={memorixChart.predictedPath} fill="none" stroke="#4f46e5" strokeWidth="2.5" />
                    <path d={memorixChart.actualPath} fill="none" stroke="#10b981" strokeWidth="2.5" />
                  </svg>
                  <div className="mt-2 flex items-center gap-4 text-[11px] font-bold">
                    <span className="text-indigo-600">预测曲线</span>
                    <span className="text-emerald-600">实际曲线</span>
                    <span className="text-muted-foreground">{`最近优化：${memorixCurve?.profile?.last_optimized_at ? new Date(memorixCurve.profile.last_optimized_at).toLocaleString('zh-CN') : '尚未优化'}`}</span>
                  </div>
                </div>
                <div className="rounded-2xl border border-border bg-card p-3">
                  <p className="text-[10px] font-bold uppercase text-muted-foreground">最近调优记录</p>
                  {memorixHistory.length === 0 ? (
                    <p className="text-xs font-bold text-muted-foreground mt-2">暂无调优记录</p>
                  ) : (
                    <div className="space-y-1.5 mt-2">
                      {memorixHistory.slice(0, 3).map((item) => (
                        <div key={item.id} className="rounded-lg border border-border px-2.5 py-2 text-[11px]">
                          <p className="font-bold">
                            {item.accepted ? '已采纳' : '未采纳'} · 改善率 {(Number(item.improvement_ratio || 0) * 100).toFixed(2)}%
                          </p>
                          <p className="text-muted-foreground mt-1">
                            样本 {item.reviews_used} · {new Date(item.created_at).toLocaleString('zh-CN')}
                          </p>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            ) : (
              <div className="rounded-xl border border-dashed border-border p-6 text-xs font-bold text-muted-foreground">
                当前复习记录不足，完成几轮训练后这里会显示你的 Memorix 个性化拟合曲线。
              </div>
            )}
          </Card>
        )}</>

        {/* Modularized Assessment Flow */}
        <AssessmentDialog 
          open={isTestOpen} 
          onOpenChange={setIsTestOpen} 
          questions={questions} 
          currentIdx={currentIdx} 
          setCurrentIdx={setCurrentIdx} 
          answers={answers} 
          handleSelect={(id, val) => setAnswers({ ...answers, [id]: val })} 
          toggleMastered={toggleMastered} 
          toggleFavorite={toggleFavorite} 
          handleSubmit={handleSubmit} 
          isSubmitting={isSubmitting}
          gradingMessage={gradingMessage}
        />
      </div>
    </PageWrapper>
  );
};
