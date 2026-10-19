import type { QuizQuestion, KnowledgePoint } from '@/types/api';
import '@/styles/practice.css';
import React, { useState, useEffect } from 'react';
import { ArrowRight, CaretDown, Bell, Info } from '@phosphor-icons/react';
import { normalizeOptions } from '@/lib/utils';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogDescription, DialogTitle, DialogTrigger } from '@/components/ui/dialog';

import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { Checkbox } from '@/components/ui/checkbox';
import { PageWrapper } from '@/components/PageWrapper';
import { toast } from "sonner";
import api from '@/lib/api';

import { useNavigate } from 'react-router-dom';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import {
  getLearningReminderSettings,
  updateLearningReminderSetting,
  type LearningReminderSettings,
} from '@/lib/learningReminders';
import { formatApiErrorToast } from '@/lib/apiError';
import { useIsMobile } from '@/lib/useIsMobile';
import { useQuery } from '@tanstack/react-query';
import { queryKeys } from '@/lib/queryKeys';
import { useExamActivityStore } from '@/store/useExamActivityStore';

// Modularized Components
import { AssessmentDialog } from './test-ladder/AssessmentDialog';

export const TestLadder: React.FC = () => {
  const navigate = useNavigate();
  const isMobile = useIsMobile();
  const [reminderSettings, setReminderSettings] = useState<LearningReminderSettings>(getLearningReminderSettings());
  const [selectedSubIds, setSelectedSubIds] = useState<number[]>([]);
  const [preference, setPreference] = useState<string>(() => {
    try { return localStorage.getItem('quiz_preference') || 'balanced'; } catch { return 'balanced'; }
  });

  // Data State
  const [questions, setQuestions] = useState<QuizQuestion[]>([]);
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
  const [customQCount, setQCount] = useState("5");
  const [isCustomCount, setIsCustomCount] = useState(false);
  const [currentIdx, setCurrentIdx] = useState(0);
  const [answers, setAnswers] = useState<Record<number, string>>({});
  const [starting, setStarting] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [gradingMessage] = useState("");



  // React Query: 学科列表 — 低频变更数据，缓存 2 分钟
  const { data: subjectList = [] } = useQuery({
    queryKey: queryKeys.knowledgePoints.subjects,
    queryFn: () => api.get('/quizzes/knowledge-points/').then(r => {
      const data = Array.isArray(r.data) ? r.data : (r.data?.results || []);
      return data.map((item: KnowledgePoint) => ({ id: item.id, name: item.name, code: item.code }));
    }),
    staleTime: 120000,
  });
  const [loadingStates, setLoadingStates] = useState({ goals: true });

  const suggestedCount = Number(goals.recommended_questions);
  const qCount = isCustomCount || !Number.isFinite(suggestedCount) || suggestedCount <= 0
    ? customQCount : String(Math.max(1, Math.min(50, suggestedCount)));

  const fetchGoals = () => {

    return api.get('/quizzes/stats/').then((res) => {
      setGoals(res.data);
    })
      .catch((e: unknown) => { console.error('fetchGoals failed', e); })
      .finally(() => {
        setLoadingStates(s => ({ ...s, goals: false }));

      });
  };

  useEffect(() => {
    fetchGoals();
  }, []);

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
        toast.success('已标记掌握');
      }
    } catch (e) { toast.error(formatApiErrorToast(e, '操作失败')); }
  };

  const startTest = async () => {
    const parsedCount = Number.parseInt(qCount, 10);
    const normalizedCount = Number.isFinite(parsedCount) ? Math.max(1, Math.min(parsedCount, 50)) : 5;
    if (`${normalizedCount}` !== qCount) setQCount(`${normalizedCount}`);

    const params = new URLSearchParams({ preference });
    if (selectedSubIds.length) params.set('sub_ids', selectedSubIds.join(','));
    if (difficulty !== 'mixed') params.set('difficulty_level', difficulty);
    if (isMobile) {
      params.set('count', String(normalizedCount));
      navigate(`/tests/session?${params}`);
      return;
    }
    if (starting) return;
    setStarting(true);
    params.set('limit', String(normalizedCount));
    try {
      const res = await api.get(`/quizzes/questions/?${params.toString()}`);
      if (res.data.length === 0) return toast.error('题库暂无可用题目');
      setQuestions(res.data.map((q: QuizQuestion) => ({ ...q, options: normalizeOptions(q.options) })));
      setIsTestOpen(true);
      setAnswers({});
      setCurrentIdx(0);
    } catch (e) { toast.error(formatApiErrorToast(e, '题目加载失败')); }
    finally { setStarting(false); }
  };

  const handleSubmit = async () => {
    const unmasteredQuestions = questions.filter(q => !q.is_mastered);
    const answeredCount = unmasteredQuestions.filter(q => typeof answers[q.id] === 'string' && answers[q.id].trim()).length;
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
      const response = await api.post('/quizzes/submit-exam/', { answers: payload });
      const examId = Number(response.data?.exam_id);
      if (Number.isFinite(examId)) {
        useExamActivityStore.getState().start({
          examId,
          total: Number(response.data?.total_questions) || unmasteredQuestions.length,
        });
      }
      toast.success('已提交 AI 批改');
      setIsTestOpen(false);
      fetchGoals();
    } catch (e: unknown) {
      toast.error(formatApiErrorToast(e, '提交失败'));
    } finally { setIsSubmitting(false); }
  };

  return (
    <PageWrapper title="习题训练">
      <div className="um-practice-home">
        <section className="um-memorix-intro" aria-label="Memorix-Field 产品介绍">
          <div className="um-memorix-copy">
            <h1>由 <span>Memorix-Field</span> <span className="um-memorix-drive">驱动。</span><br />持续进化的调度算法，<br />为强化记忆而打造。</h1>
            <Dialog>
              <DialogTrigger asChild><Button variant="ghost" className="um-memorix-about"><Info size={16} />了解双引擎</Button></DialogTrigger>
              <DialogContent className="um-memorix-explanation">
                <DialogTitle>Memorix-Field 双引擎</DialogTitle>
                <DialogDescription>Memorix-Field 在间隔重复的基础上引入了知识图谱全局诊断，从「单题维度的记忆管理」扩展到「知识结构维度的诊断」。</DialogDescription>
                <div className="um-memorix-explanation-body">
                  <section><h3>记忆引擎：题级遗忘建模</h3><p>持续拟合每道题的记忆衰减曲线，以题为单位做个体化参数估计。在临界遗忘点精准介入，减少无效重复，提高单位时间的记忆留存率。这是 Memorix 第一代的核心能力，在第二代中继续作为调度基础。</p></section>
                  <section><h3>图诊断引擎：知识图谱全局推断</h3><p>将学科知识建模为高斯马尔可夫随机场（GMRF），利用图结构上相邻知识点的掌握度相似性，从部分观测外推全部知识点的掌握度。一场覆盖 10% 知识点的考试，就能输出全域掌握度热力图。</p></section>
                  <section><h3>双引擎协同</h3><p>记忆引擎输出「何时复习哪道题」，图诊断引擎输出「哪些知识群存在结构薄弱」。前者优化时间分配，后者优化知识建构。两者共享同一个学生模型，调度结果受诊断结果加权。</p></section>
                </div>
              </DialogContent>
            </Dialog>
          </div>
          <dl className="um-memorix-stats" aria-label="复习状态"><div><dt>今日待复习</dt><dd>{loadingStates.goals ? '—' : goals.review_goal}<small> 题</small></dd></div><div><dt>接近遗忘</dt><dd>{loadingStates.goals ? '—' : goals.at_risk_count || 0}<small> 题</small></dd></div><div><dt>尚未练习</dt><dd>{loadingStates.goals ? '—' : goals.new_questions}<small> 题</small></dd></div></dl>
        </section>
        <section className="um-practice-setup" aria-label="练习设置">
        <header className="um-practice-heading"><div><h2>本轮训练</h2><p>{loadingStates.goals ? '正在读取练习建议…' : `建议 ${goals.recommended_questions} 题，预计 ${goals.estimated_minutes} 分钟，含 ${goals.weak_focus_count} 题薄弱强化。`}</p></div><div className="um-practice-heading-actions"><Button variant="ghost" onClick={() => navigate('/tests/history')}>最近练习<ArrowRight size={15} /></Button><Button variant="ghost" onClick={() => navigate('/tests/review')}>错题复盘<ArrowRight size={15} /></Button>{isMobile && <Popover><PopoverTrigger asChild><Button variant="ghost" size="icon" aria-label="提醒设置"><Bell size={16} /></Button></PopoverTrigger><PopoverContent className="um-practice-popover" align="end"><h2>提醒设置</h2><Label>题型提醒<Switch checked={reminderSettings.questionType} onCheckedChange={enabled => setReminderSettings(updateLearningReminderSetting('questionType', enabled))} /></Label><Label>做题结果提醒<Switch checked={reminderSettings.testResult} onCheckedChange={enabled => setReminderSettings(updateLearningReminderSetting('testResult', enabled))} /></Label></PopoverContent></Popover>}</div></header>
          <div className="um-practice-controls">
            <label className="um-practice-count"><span>题数</span><select aria-label="题数" value={isCustomCount ? 'custom' : qCount} onChange={event => { setIsCustomCount(event.target.value === 'custom'); if (event.target.value !== 'custom') setQCount(event.target.value); }}>
              {[...new Set([String(goals.recommended_questions || 5), '3', '5', '10', '20'])].map(value => <option key={value} value={value}>{value} 题</option>)}<option value="custom">自定义</option>
            </select>{isCustomCount && <Input aria-label="自定义题数" type="number" min="1" max="50" value={qCount} onChange={event => setQCount(event.target.value)} />}</label>
            <label>难度<select aria-label="难度" value={difficulty} onChange={event => setDifficulty(event.target.value)}><option value="mixed">混合难度</option><option value="entry">入门</option><option value="easy">简单</option><option value="normal">适当</option><option value="hard">困难</option></select></label>

            <div className="um-practice-subject"><span className="um-practice-label">学科范围</span><Popover><PopoverTrigger asChild><Button variant="outline" aria-label="选择学科">{selectedSubIds.length ? `已选 ${selectedSubIds.length} 个学科` : '全部学科'}<CaretDown size={14} /></Button></PopoverTrigger><PopoverContent className="um-practice-popover" align="start"><h2>学科范围</h2>{subjectList.map((subject: { id: number; name: string }) => <Label key={subject.id}><Checkbox checked={selectedSubIds.includes(subject.id)} onCheckedChange={checked => setSelectedSubIds(prev => checked ? [...prev, subject.id] : prev.filter(id => id !== subject.id))} />{subject.name}</Label>)}{!subjectList.length && <p>暂无可选学科</p>}{selectedSubIds.length > 0 && <Button variant="ghost" onClick={() => setSelectedSubIds([])}>清除筛选</Button>}</PopoverContent></Popover></div>
          </div>
          <div className="um-practice-start"><div><span className="um-practice-label">练习偏好</span><div className="um-practice-preference" role="group" aria-label="练习偏好">{[{ value: 'balanced', label: '均衡' }, { value: 'new_first', label: '偏新题' }, { value: 'review_first', label: '偏复习' }].map(item => <button type="button" key={item.value} aria-pressed={preference === item.value} onClick={() => { setPreference(item.value); try { localStorage.setItem('quiz_preference', item.value); } catch { /* Browser may deny local storage. */ } }}>{item.label}</button>)}</div></div><Button onClick={startTest} disabled={starting || loadingStates.goals} className="um-practice-primary">{starting ? '正在读取题目…' : '开始练习'}<ArrowRight size={15} /></Button></div>
        </section>
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
