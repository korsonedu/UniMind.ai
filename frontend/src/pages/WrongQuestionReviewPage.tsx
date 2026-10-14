import { useCallback } from 'react';
import '@/styles/practice.css';
import React, { useEffect, useMemo, useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { ArrowLeft, ArrowRight, ArrowClockwise, Spinner } from '@phosphor-icons/react';
import { PageWrapper } from '@/components/PageWrapper';
import { Button } from '@/components/ui/button';
import api from '@/lib/api';
import { toast } from 'sonner';
import { formatApiErrorToast } from '@/lib/apiError';

type DrillItem = {
  drill_type: 'cause' | 'knowledge_point';
  drill_key: string;
  drill_label: string;
  question_count: number;
  question_ids: number[];
  recommended_questions: number;
};

export const WrongQuestionReviewPage: React.FC = () => {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [payload, setPayload] = useState<{ recommended_drills: DrillItem[]; cause_breakdown: { cause_key: string; cause_label: string; ratio: number; question_count: number; wrong_attempts: number }[]; knowledge_point_breakdown: { knowledge_point_id: number; knowledge_point_name: string; avg_wrong_count: number; question_count: number }[]; overview: { wrong_questions: number; wrong_attempts: number }; } | null>(null);

  const fetchInsights = useCallback(() => {

    return api.get('/quizzes/wrong-questions/insights/').then((res) => {
      setPayload(res.data);
      setError(false);
    })
      .catch((e: unknown) => {
        setError(true);
        toast.error(formatApiErrorToast(e, '错题复盘加载失败'));
      })
      .finally(() => {
        setLoading(false);
      });
  }, []);
  const refreshFetchInsights = useCallback(() => {
    setLoading(true);
    return fetchInsights();
  }, [fetchInsights]);


  useEffect(() => {
    fetchInsights();
  }, [fetchInsights]);

  const drills: DrillItem[] = useMemo(() => payload?.recommended_drills || [], [payload]);
  const causeBreakdown = useMemo(() => payload?.cause_breakdown || [], [payload]);
  const kpBreakdown = useMemo(() => payload?.knowledge_point_breakdown || [], [payload]);
  const overview = payload?.overview || { wrong_questions: 0, wrong_attempts: 0 };

  const startDrill = (drill: DrillItem) => {
    if (!drill.question_ids?.length) {
      toast.info('当前专项暂无可训练题目');
      return;
    }
    const ids = drill.question_ids.join(',');
    navigate(`/tests/session?ids=${ids}&label=${encodeURIComponent(drill.drill_label)}`);
  };

  return (
    <PageWrapper title="错题复盘">
      <div className="um-practice-home um-practice-review">
        <Link className="um-practice-back" to="/tests"><ArrowLeft size={15} />返回练习</Link>
        <header className="um-practice-heading">
          <h1>错题复盘</h1>
          <Button variant="ghost" disabled={loading} onClick={refreshFetchInsights}><ArrowClockwise size={16} />刷新</Button>
        </header>
        {loading ? <p className="um-practice-state" role="status"><Spinner size={18} className="animate-spin" />正在读取错题…</p> : error ? <p className="um-practice-state" role="alert">错题数据加载失败，请点击刷新重试。</p> : <>
          <dl className="um-practice-summary">
            <div><dt>错题总数</dt><dd>{overview.wrong_questions || 0}<small> 题</small></dd></div>
            <div><dt>累计错误次数</dt><dd>{overview.wrong_attempts || 0}<small> 次</small></dd></div>
            <div><dt>可练专项</dt><dd>{drills.length}<small> 项</small></dd></div>
          </dl>
          <section className="um-practice-drills" aria-label="专项训练">
            <h2>专项训练</h2>
            {!drills.length ? <div className="um-review-empty"><p>暂无可训练专项</p><Link to="/tests">去做题<ArrowRight size={15} /></Link></div> : <div className="um-review-drill-groups">
              {(['cause', 'knowledge_point'] as const).map(type => {
                const group = drills.filter(drill => drill.drill_type === type);
                if (!group.length) return null;
                return <section key={type} aria-label={type === 'cause' ? '错因专项' : '考点专项'}>
                  <h3 className="um-review-group-title">{type === 'cause' ? '错因专项' : '考点专项'}</h3>
                  <ul>{group.map(drill => <li key={`${type}-${drill.drill_key}`}>
                    <div><h3>{drill.drill_label}</h3><p>本轮 {drill.question_ids.length} 题</p></div>
                    <Button variant="ghost" aria-label={`练习${drill.drill_label}`} onClick={() => startDrill(drill)}>去做题<ArrowRight size={15} /></Button>
                  </li>)}</ul>
                </section>;
              })}
            </div>}
          </section>
          <div className="um-practice-breakdowns">
            <section aria-label="按错因复盘">
              <header><h2>错因分布</h2><span>错题占比</span></header>
              {!causeBreakdown.length && <p className="um-practice-muted">暂无错因数据</p>}
              <ul>{causeBreakdown.map((item) => <li className="um-review-cause" key={item.cause_key}>
                <div className="um-review-cause-heading"><h3>{item.cause_label}</h3><span>{Math.round((item.ratio || 0) * 100)}%</span></div>
                <progress value={item.ratio || 0} max={1} aria-label={`${item.cause_label}错题占比`} />
                <p>{item.question_count} 道错题 · 累计错 {item.wrong_attempts} 次</p>
              </li>)}</ul>
            </section>
            <section aria-label="按考点复盘">
              <header><h2>考点分布</h2><span>错题数</span></header>
              {!kpBreakdown.length && <p className="um-practice-muted">暂无考点数据</p>}
              <ul>{kpBreakdown.map((item) => <li key={`${item.knowledge_point_id || 'unknown'}-${item.knowledge_point_name}`}>
                <div><h3>{item.knowledge_point_name}</h3><p>平均错 {item.avg_wrong_count} 次</p></div>
                <span className="um-review-kp-count">{item.question_count}<small> 题</small></span>
              </li>)}</ul>
            </section>
          </div>
        </>}
      </div>
    </PageWrapper>
  );
};
