import React, { useState, useEffect, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { Card } from '@/components/ui/card';
import { ArrowRight, BrainCircuit, Activity, ChevronDown, Bell, Target, Info, Filter } from 'lucide-react';
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
import { useNavigate, useSearchParams } from 'react-router-dom';
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

// Modularized Components
import { AssessmentDialog } from './test-ladder/AssessmentDialog';
import { ResultReportDialog } from './test-ladder/ResultReportDialog';

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
  const { t, i18n } = useTranslation(['testLadder', 'pages']);
  const { primaryColor } = useSystemStore();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const isMobile = useIsMobile();
  const [reminderSettings, setReminderSettings] = useState<LearningReminderSettings>(getLearningReminderSettings());
  const [selectedSubIds, setSelectedSubIds] = useState<number[]>([]);
  const [subjectList, setSubjectList] = useState<Array<{ id: number; name: string; code: string }>>([]);
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
  const [gradingMessage, setGradingMessage] = useState("");

  // Report UI State
  const [results, setResults] = useState<any[]>([]);
  const [showResultDialog, setShowResultDialog] = useState(false);
  const [currentReportIdx, setCurrentReportIdx] = useState(0);
  const [examSummary, setExamSummary] = useState<any>(null);
  const [memorixCurve, setMemorixCurve] = useState<MemorixCurvePayload | null>(null);
  const [memorixHistory, setMemorixHistory] = useState<MemorixOptimizationHistory[]>([]);

  useEffect(() => {
    fetchGoals();
    fetchMemorixCurve();
    fetchMemorixHistory();
    fetchSubjects();
  }, []);

  useEffect(() => {
    if (isCustomCount) return;
    const suggested = Number(goals.recommended_questions || 0);
    if (!Number.isFinite(suggested) || suggested <= 0) return;
    setQCount(String(Math.max(1, Math.min(50, suggested))));
  }, [goals.recommended_questions, isCustomCount]);

  useEffect(() => {
    const action = searchParams.get('action');
    const examId = searchParams.get('exam_id');
    if (action === 'view_report' && examId) {
      fetchExamReport(examId);
      setSearchParams({});
    }
  }, [searchParams, setSearchParams]);

  const fetchExamReport = async (examId: string) => {
    try {
      const res = await api.get(`/quizzes/exams/${examId}/`);
      setExamSummary({
        total_score: res.data.total_score,
        max_score: res.data.max_score,
        elo_change: res.data.elo_change,
        created_at: res.data.created_at_fmt,
        summary: res.data.summary || ''
      });
      const mappedResults = res.data.results.map((r: any) => ({
        question: r.question_detail,
        user_answer: r.user_answer,
        score: r.score,
        max_score: r.max_score,
        feedback: r.feedback,
        analysis: r.analysis,
        is_correct: r.is_correct
      }));
      setResults(mappedResults);
      setCurrentReportIdx(0);
      setShowResultDialog(true);
    } catch (e) { toast.error(formatApiErrorToast(e, t('toast.loadReportError'))); }
  };

  const fetchSubjects = async () => {
    try {
      const res = await api.get('/quizzes/knowledge-points/');
      const data = Array.isArray(res.data) ? res.data : (res.data?.results || []);
      setSubjectList(data.map((item: any) => ({ id: item.id, name: item.name, code: item.code })));
    } catch (e) { console.error('fetchSubjects failed', e); }
  };

  const fetchGoals = async () => {
    try {
      const res = await api.get('/quizzes/stats/');
      setGoals(res.data);
    } catch (e) { console.error('fetchGoals failed', e); }
  };

  const fetchMemorixCurve = async () => {
    try {
      const res = await api.get('/quizzes/memorix/curve/', { params: { window_days: 90 } });
      setMemorixCurve(res.data as MemorixCurvePayload);
    } catch (e) { console.error('fetchMemorixCurve failed', e); }
  };

  const fetchMemorixHistory = async () => {
    try {
      const res = await api.get('/quizzes/memorix/optimization-history/');
      setMemorixHistory((res.data?.results || []) as MemorixOptimizationHistory[]);
    } catch (e) { console.error('fetchMemorixHistory failed', e); }
  };

  const toggleFavorite = async (qId: number) => {
    try {
      const res = await api.post('/quizzes/favorite/toggle/', { question_id: qId });
      setQuestions(questions.map(q => q.id === qId ? { ...q, is_favorite: res.data.is_favorite } : q));
      toast.success(res.data.is_favorite ? t('toast.addedToFavorites') : t('toast.removedFromFavorites'));
    } catch (e) { toast.error(formatApiErrorToast(e, t('toast.operationFailed'))); }
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
        toast.success(t('toast.mastered'));
      }
    } catch (e) { toast.error(formatApiErrorToast(e, t('toast.operationFailed'))); }
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
      if (res.data.length === 0) return toast.error(t('toast.noQuestions'));
      setQuestions(res.data.map((q: any) => ({ ...q, options: normalizeOptions(q.options) })));
      setIsTestOpen(true);
      setAnswers({});
      setCurrentIdx(0);
      setResults([]);
    } catch (e) { toast.error(formatApiErrorToast(e, t('toast.loadQuestionsError'))); }
  };

  const handleSubmit = async () => {
    const unmasteredQuestions = questions.filter(q => !q.is_mastered);
    const answeredCount = Object.keys(answers).length;
    if (unmasteredQuestions.length > 0 && answeredCount < unmasteredQuestions.length) {
      return toast.error(t('toast.notAllAnswered', { answered: answeredCount, total: unmasteredQuestions.length }));
    }
    if (unmasteredQuestions.length === 0) {
      setIsTestOpen(false);
      return toast.info(t('toast.exerciseCompleted'));
    }
    setIsSubmitting(true);
    try {
      const payload = unmasteredQuestions.map(q => ({ question_id: q.id, answer: answers[q.id] }));
      await api.post('/quizzes/submit-exam/', { answers: payload });
      toast.success(t('toast.submissionSent'), { description: t('toast.submissionSentDesc') });
      setIsTestOpen(false);
      fetchGoals();
    } catch (e: any) {
      toast.error(formatApiErrorToast(e, t('toast.submissionFailed')));
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

  return (
    <PageWrapper title={t('pages:academicLadder.title')} subtitle={t('pages:academicLadder.subtitle')}>
      <div className="flex flex-col gap-8 md:gap-12 text-left animate-in fade-in duration-700 pb-20 max-w-6xl mx-auto">
        {isMobile && (
            <Popover>
              <PopoverTrigger asChild>
                <Button variant="outline" size="icon" className="h-8 w-8 rounded-lg border-border">
                  <Bell className="h-4 w-4" />
                </Button>
              </PopoverTrigger>
              <PopoverContent side="bottom" align="end" className="w-64 rounded-2xl p-4 bg-card border-border">
                <div className="space-y-3 text-left">
                  <p className="text-xs font-semibold text-muted-foreground">{t('reminder.title')}</p>
                  <div className="flex items-center justify-between">
                    <Label className="text-xs font-bold">{t('reminder.questionType')}</Label>
                    <Switch
                      checked={reminderSettings.questionType}
                      onCheckedChange={(enabled) => {
                        setReminderSettings(updateLearningReminderSetting('questionType', enabled));
                      }}
                    />
                  </div>
                  <div className="flex items-center justify-between">
                    <Label className="text-xs font-bold">{t('reminder.testResult')}</Label>
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
            isMobile ? "border-none shadow-none rounded-none p-0" : "border border-border rounded-apple-4xl p-12 shadow-sm hover:shadow-md"
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
                    {t('hero.title1')}
                    <br />
                    {t('hero.title2')}
                  </h2>
                  <Dialog>
                    <DialogTrigger asChild>
                      <button
                        type="button"
                        aria-label={t('memorix.curveTitle')}
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
                        <DialogTitle>{t('memorixDialog.title')}</DialogTitle>
                        <DialogDescription>
                          {t('memorixDialog.description')}
                        </DialogDescription>
                      </DialogHeader>
                      <div className="space-y-3 text-sm text-muted-foreground leading-relaxed">
                        <p>{t('memorixDialog.p1')}</p>
                        <p>{t('memorixDialog.p2')}</p>
                        <p>{t('memorixDialog.p3')}</p>
                      </div>
                    </DialogContent>
                  </Dialog>
                </div>
                <p className={cn("font-medium leading-relaxed text-muted-foreground max-w-lg", isMobile ? "text-sm" : "text-base")}>
                  {isMobile
                    ? t('hero.mobileSubtitle')
                    : t('hero.desktopSubtitle')}
                </p>
                <p className={cn("font-bold text-indigo-600/80", isMobile ? "text-[12px]" : "text-sm")}>
                  {t('suggestion', { recommended: goals.recommended_questions, estimated: goals.estimated_minutes, weakFocus: goals.weak_focus_count })}
                </p>

                {/* ── 三连选行 ── */}
                <div className={cn("flex flex-wrap items-end gap-3 pt-4 w-full", isMobile && "flex-col")}>
                  {/* 题数选择 */}
                  {isMobile ? (
                    <div className="space-y-1.5 flex-1 w-full">
                      <span className="text-[10px] font-bold text-muted-foreground ml-1">{t('questionCountMobile')}</span>
                      <Input type="number" min="1" value={qCount} onChange={(e) => setQCount(e.target.value)} onBlur={() => { if (!qCount || parseInt(qCount) < 1) setQCount("1"); }} className="w-full h-9 rounded-xl bg-muted border-border font-bold text-center" />
                    </div>
                  ) : (
                    <div className="flex flex-col gap-1.5">
                      <span className="text-[11px] font-bold text-muted-foreground uppercase tracking-[0.15em] ml-1">{t('questionCount')}</span>
                      <div className="flex items-center gap-2">
                        <DropdownMenu modal={false}>
                          <DropdownMenuTrigger asChild>
                            <Button variant="outline" className="h-11 px-4 rounded-xl bg-card border-border text-foreground font-bold text-sm hover:bg-muted/80 transition-all flex items-center gap-2 shadow-sm">
                              {isCustomCount ? t('custom') : t('questionsWithCount', { count: qCount })}<ChevronDown className="h-3.5 w-3.5 opacity-50" />
                            </Button>
                          </DropdownMenuTrigger>
                          <DropdownMenuContent className="w-32 rounded-xl border-border bg-card shadow-lg p-1.5" align="start">
                            {["3", "5", "10", "20"].map(v => (
                              <DropdownMenuItem key={v} onClick={() => { setIsCustomCount(false); setQCount(v); }} className="rounded-lg font-bold py-2 cursor-pointer text-sm">{t('questionsWithCount', { count: v })}</DropdownMenuItem>
                            ))}
                            <DropdownMenuItem onClick={() => setIsCustomCount(true)} className="rounded-lg font-bold py-2 text-indigo-600 cursor-pointer text-sm">{t('custom')}</DropdownMenuItem>
                          </DropdownMenuContent>
                        </DropdownMenu>
                        {isCustomCount && <Input type="number" min="1" value={qCount} onChange={(e) => setQCount(e.target.value)} onBlur={() => { if (!qCount || parseInt(qCount) < 1) setQCount("1"); }} className="w-20 h-11 rounded-xl bg-card border-border font-bold text-center shadow-sm" />}
                      </div>
                    </div>
                  )}

                  {/* 难度选择 */}
                  <div className="flex flex-col gap-1.5">
                    <span className="text-[11px] font-bold text-muted-foreground uppercase tracking-[0.15em] ml-1">{t('difficulty.label')}</span>
                    <Select value={difficulty} onValueChange={setDifficulty}>
                      <SelectTrigger className="h-11 px-4 rounded-xl bg-card border-border text-foreground font-bold text-sm shadow-sm w-[130px]"><SelectValue /></SelectTrigger>
                      <SelectContent className="rounded-xl border-border">
                        <SelectItem value="mixed">{t('difficulty.mixed')}</SelectItem>
                        <SelectItem value="entry">{t('difficulty.entry')}</SelectItem>
                        <SelectItem value="easy">{t('difficulty.easy')}</SelectItem>
                        <SelectItem value="normal">{t('difficulty.normal')}</SelectItem>
                        <SelectItem value="hard">{t('difficulty.hard')}</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  {/* 抽题偏好 */}
                  <div className="flex flex-col gap-1.5">
                    <span className="text-[11px] font-bold text-muted-foreground uppercase tracking-[0.15em] ml-1">{t('preference.label')}</span>
                    <div className="flex rounded-xl bg-muted p-1 gap-0.5 h-11 items-center">
                      {([
                        { value: 'balanced', label: t('preference.balanced') },
                        { value: 'new_first', label: t('preference.newFirst') },
                        { value: 'review_first', label: t('preference.reviewFirst') },
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
                        <Filter className="h-4 w-4 shrink-0" />
                        <span className="truncate">{selectedSubIds.length > 0 ? t('subjectFilter') : t('allSubjects')}</span>
                        <Badge variant="outline" className={cn("ml-0.5 h-5 min-w-[1.25rem] px-1 rounded-full text-[10px] font-bold", selectedSubIds.length > 0 ? "bg-indigo-600 text-white border-indigo-600" : "bg-muted text-muted-foreground border-border")}>{selectedSubIds.length}</Badge>
                      </Button>
                    </PopoverTrigger>
                    <PopoverContent side="bottom" align="start" className="w-56 rounded-2xl p-3 bg-card border-border">
                      <div className="space-y-1">
                        <p className="text-xs font-semibold text-muted-foreground mb-2 pb-1 border-b border-border">{t('subjectFilter')}</p>
                        {subjectList.length === 0 ? (<p className="text-xs text-muted-foreground py-2">{t('loading')}</p>) : (
                          subjectList.map((subject) => (
                            <div key={subject.id} className="flex items-center gap-2 py-1.5 px-1 rounded-lg hover:bg-muted/60 transition-colors">
                              <Checkbox id={`subject-${subject.id}`} checked={selectedSubIds.includes(subject.id)} onCheckedChange={(checked) => { checked ? setSelectedSubIds(prev => [...prev, subject.id]) : setSelectedSubIds(prev => prev.filter(id => id !== subject.id)); }} />
                              <label htmlFor={`subject-${subject.id}`} className="text-xs font-medium cursor-pointer select-none flex-1 leading-tight">{subject.name}</label>
                            </div>
                          ))
                        )}
                        {subjectList.length > 0 && selectedSubIds.length > 0 && (<button onClick={() => setSelectedSubIds([])} className="text-xs font-bold text-indigo-600 hover:text-indigo-700 pt-1 w-full text-left">{t('clearFilter')}</button>)}
                      </div>
                    </PopoverContent>
                  </Popover>
                </div>

                {/* ── CTA 按钮行 ── */}
                <div className={cn("flex flex-wrap items-center gap-3 pt-2 w-full", isMobile && "flex-col")}>
                  <Button onClick={startTest} className={cn("text-white rounded-xl font-bold shadow-lg transition-all active:scale-95 bg-primary hover:opacity-90 border-0 flex-1", isMobile ? "h-12 px-6 text-sm" : "h-14 px-12 text-lg")}>
                    <BrainCircuit className="mr-2 h-5 w-5" />{t('startTraining')}<ArrowRight className="ml-2 h-5 w-5" />
                  </Button>
                  <Button variant="outline" onClick={() => navigate('/tests/review')} className={cn("rounded-xl font-bold border-border shadow-sm hover:shadow-md transition-all", isMobile ? "h-10 text-sm flex-1" : "h-14 px-6 text-sm")}>
                    <Target className="mr-2 h-4 w-4" />{t('wrongQuestionReview')}
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
                  isMobile ? "p-3 rounded-xl border-none shadow-none" : "p-7 border border-border rounded-apple-3xl hover:bg-card hover:shadow-lg"
                )}>
                  <div className="flex items-center gap-3 mb-2">
                    <div className={cn("bg-card shadow-sm flex items-center justify-center text-indigo-500", isMobile ? "h-8 w-8 rounded-xl" : "h-9 w-9 rounded-2xl")}><BrainCircuit className="h-4 w-4" /></div>
                    <p className={cn("font-bold text-muted-foreground uppercase tracking-widest leading-none", isMobile ? "text-[11px]" : "text-[14px]")}>{t('stats.todayReview')}</p>
                  </div>
                  <div className="flex items-baseline gap-1">
                    <p className={cn("font-black text-foreground tabular-nums", isMobile ? "text-3xl" : "text-4xl")}>{goals.review_goal}</p>
                    <span className="text-[12px] font-bold text-muted-foreground uppercase">{t('stats.due')}</span>
                  </div>
                </div>
                <div className={cn(
                  "bg-muted transition-all flex flex-col justify-center",
                  isMobile ? "p-3 rounded-xl border-none shadow-none" : "p-7 border border-border rounded-apple-3xl hover:bg-card hover:shadow-lg"
                )}>
                  <div className="flex items-center gap-3 mb-2">
                    <div className={cn("bg-card shadow-sm flex items-center justify-center text-muted-foreground", isMobile ? "h-8 w-8 rounded-xl" : "h-9 w-9 rounded-2xl")}><Activity className="h-4 w-4" /></div>
                    <p className={cn("font-bold text-muted-foreground uppercase tracking-widest leading-none", isMobile ? "text-[11px]" : "text-[14px]")}>{t('stats.atRisk')}</p>
                  </div>
                  <div className="flex items-baseline gap-1">
                    <p className={cn("font-black text-foreground tabular-nums", isMobile ? "text-3xl" : "text-4xl")}>{goals.at_risk_count || 0}</p>
                    <span className="text-[12px] font-bold text-muted-foreground uppercase">{t('stats.atRiskUnit')}</span>
                  </div>
                </div>
              </div>
            </div>
          </Card>
        )}

        {(
          <Card className={cn(
            "bg-card overflow-hidden transition-all",
            isMobile ? "border border-border rounded-2xl p-4" : "border border-border rounded-apple-2xl p-6 shadow-sm"
          )}>
            <div className="flex items-center justify-between gap-3 mb-4">
              <div>
                <p className="label-meta">{t('memorix.curveTitle')}</p>
                <p className="text-sm font-bold text-foreground mt-1">{t('memorix.curveSubtitle', { days: memorixCurve?.window_days || 90 })}</p>
              </div>
              <Button variant="outline" className="h-8 rounded-lg text-xs font-bold" onClick={() => { fetchMemorixCurve(); fetchMemorixHistory(); }}>
                {t('refresh')}
              </Button>
            </div>
            {(memorixCurve?.time_series || []).length > 0 ? (
              <div className="space-y-4">
                <div className="grid grid-cols-2 md:grid-cols-5 gap-2">
                  <div className="rounded-xl bg-muted px-3 py-2">
                    <p className="text-[10px] font-bold text-muted-foreground uppercase">{t('memorix.sampleCount')}</p>
                    <p className="text-sm font-black text-foreground">{memorixCurve?.metrics?.review_count ?? 0}</p>
                  </div>
                  <div className="rounded-xl bg-muted px-3 py-2">
                    <p className="text-[10px] font-bold text-muted-foreground uppercase">{t('memorix.predictionAccuracy')}</p>
                    <p className="text-sm font-black text-foreground">{memorixCurve?.metrics?.rmse ?? '--'}</p>
                  </div>
                  <div className="rounded-xl bg-muted px-3 py-2">
                    <p className="text-[10px] font-bold text-muted-foreground uppercase">{t('memorix.avgError')}</p>
                    <p className="text-sm font-black text-foreground">{memorixCurve?.metrics?.mae ?? '--'}</p>
                  </div>
                  <div className="rounded-xl bg-muted px-3 py-2">
                    <p className="text-[10px] font-bold text-muted-foreground uppercase">{t('memorix.predictedMastery')}</p>
                    <p className="text-sm font-black text-foreground">{memorixCurve?.metrics?.avg_predicted ?? '--'}</p>
                  </div>
                  <div className="rounded-xl bg-muted px-3 py-2">
                    <p className="text-[10px] font-bold text-muted-foreground uppercase">{t('memorix.actualMastery')}</p>
                    <p className="text-sm font-black text-foreground">{memorixCurve?.metrics?.avg_actual ?? '--'}</p>
                  </div>
                </div>
                <div className="rounded-2xl border border-border bg-muted/30 p-3">
                  <svg viewBox={`0 0 ${memorixChart.graphWidth} ${memorixChart.graphHeight}`} className="w-full h-48">
                    <line x1={memorixChart.left} y1={memorixChart.graphHeight - memorixChart.bottom} x2={memorixChart.graphWidth - memorixChart.right} y2={memorixChart.graphHeight - memorixChart.bottom} stroke="currentColor" className="text-border" />
                    <path d={memorixChart.predictedPath} fill="none" stroke="#4f46e5" strokeWidth="2.5" />
                    <path d={memorixChart.actualPath} fill="none" stroke="#10b981" strokeWidth="2.5" />
                  </svg>
                  <div className="mt-2 flex items-center gap-4 text-[11px] font-bold">
                    <span className="text-indigo-600">{t('memorix.predictedCurve')}</span>
                    <span className="text-emerald-600">{t('memorix.actualCurve')}</span>
                    <span className="text-muted-foreground">{t('memorix.lastOptimized', { date: memorixCurve?.profile?.last_optimized_at ? new Date(memorixCurve.profile.last_optimized_at).toLocaleString(i18n.language?.startsWith('zh') ? 'zh-CN' : 'en-US') : t('memorix.notOptimized') })}</span>
                  </div>
                </div>
                <div className="rounded-2xl border border-border bg-card p-3">
                  <p className="text-[10px] font-bold uppercase text-muted-foreground">{t('memorix.tuningHistory')}</p>
                  {memorixHistory.length === 0 ? (
                    <p className="text-xs font-bold text-muted-foreground mt-2">{t('memorix.noTuningHistory')}</p>
                  ) : (
                    <div className="space-y-1.5 mt-2">
                      {memorixHistory.slice(0, 3).map((item) => (
                        <div key={item.id} className="rounded-lg border border-border px-2.5 py-2 text-[11px]">
                          <p className="font-bold">
                            {item.accepted ? t('memorix.accepted') : t('memorix.notAccepted')} · {t('memorix.improvementRate')} {(Number(item.improvement_ratio || 0) * 100).toFixed(2)}%
                          </p>
                          <p className="text-muted-foreground mt-1">
                            {t('memorix.samples')} {item.reviews_used} · {new Date(item.created_at).toLocaleString(i18n.language?.startsWith('zh') ? 'zh-CN' : 'en-US')}
                          </p>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            ) : (
              <div className="rounded-xl border border-dashed border-border p-6 text-xs font-bold text-muted-foreground">
                {t('memorix.emptyCurve')}
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

        <ResultReportDialog 
          open={showResultDialog} 
          onOpenChange={setShowResultDialog} 
          examSummary={examSummary} 
          results={results} 
          currentReportIdx={currentReportIdx} 
          setCurrentReportIdx={setCurrentReportIdx} 
        />
      </div>
    </PageWrapper>
  );
};
