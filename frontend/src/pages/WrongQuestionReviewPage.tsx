import React, { useEffect, useMemo, useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { ArrowLeft, BrainCircuit, Target, BookOpenCheck, Loader2 } from 'lucide-react';
import { PageWrapper } from '@/components/PageWrapper';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
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
  const { t } = useTranslation(['testLadder', 'pages']);
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [payload, setPayload] = useState<any>(null);

  const fetchInsights = async () => {
    setLoading(true);
    try {
      const res = await api.get('/quizzes/wrong-questions/insights/');
      setPayload(res.data);
    } catch (e) {
      toast.error(formatApiErrorToast(e, t('toast.loadWrongReviewError')));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchInsights();
  }, []);

  const drills: DrillItem[] = useMemo(() => payload?.recommended_drills || [], [payload]);
  const causeBreakdown = useMemo(() => payload?.cause_breakdown || [], [payload]);
  const kpBreakdown = useMemo(() => payload?.knowledge_point_breakdown || [], [payload]);
  const overview = payload?.overview || { wrong_questions: 0, wrong_attempts: 0 };

  const startDrill = (drill: DrillItem) => {
    if (!drill.question_ids?.length) {
      toast.info(t('wrongReview.noDrillQuestions'));
      return;
    }
    const ids = drill.question_ids.join(',');
    navigate(`/tests/session?ids=${ids}&label=${encodeURIComponent(drill.drill_label)}`);
  };

  return (
    <PageWrapper title={t('pages:wrongReview.title')} subtitle={t('pages:wrongReview.subtitle')}>
      <div className="max-w-6xl mx-auto pb-20 space-y-6 text-left">
        <div className="flex items-center gap-3">
          <Link to="/tests"><Button variant="outline" className="rounded-xl">
            <ArrowLeft className="h-4 w-4 mr-1" />
            {t('wrongReview.backToTraining')}
          </Button>
          <Button variant="ghost" className="rounded-xl" onClick={fetchInsights}>
            {t('wrongReview.refreshReview')}
          </Button>
        </div>

        {loading ? (
          <div className="h-56 flex items-center justify-center">
            <Loader2 className="h-7 w-7 animate-spin text-muted-foreground/60" />
          </div>
        ) : (
          <>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <Card className="rounded-2xl border border-border bg-card p-5">
                <p className="text-xs font-bold uppercase tracking-widest text-muted-foreground">{t('wrongReview.wrongQuestionCount')}</p>
                <p className="text-3xl font-black tabular-nums mt-2">{overview.wrong_questions || 0}</p>
              </Card>
              <Card className="rounded-2xl border border-border bg-card p-5">
                <p className="text-xs font-bold uppercase tracking-widest text-muted-foreground">{t('wrongReview.totalWrongAttempts')}</p>
                <p className="text-3xl font-black tabular-nums mt-2">{overview.wrong_attempts || 0}</p>
              </Card>
              <Card className="rounded-2xl border border-border bg-card p-5">
                <p className="text-xs font-bold uppercase tracking-widest text-muted-foreground">{t('wrongReview.recommendedDrills')}</p>
                <p className="text-3xl font-black tabular-nums mt-2">{drills.length}</p>
              </Card>
            </div>

            <Card className="rounded-2xl border border-border bg-card p-5 space-y-4">
              <div className="flex items-center gap-2">
                <Target className="h-4 w-4 text-indigo-600" />
                <h3 className="text-base font-black">{t('wrongReview.drillTraining')}</h3>
              </div>
              {!drills.length ? (
                <p className="text-sm text-muted-foreground">{t('wrongReview.noDrillsAvailable')}</p>
              ) : (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  {drills.map((drill, idx) => (
                    <Card key={`${drill.drill_type}-${drill.drill_key}-${idx}`} className="rounded-xl border border-border p-4 bg-muted/30">
                      <div className="flex items-center justify-between gap-3">
                        <div>
                          <p className="font-bold text-foreground">{drill.drill_label}</p>
                          <p className="text-xs text-muted-foreground mt-1">
                            {t('wrongReview.questionCount', { count: drill.question_count, suggested: drill.recommended_questions })}
                          </p>
                        </div>
                        <Badge variant="secondary" className="rounded-lg">
                          {drill.drill_type === 'cause' ? t('wrongReview.cause') : t('wrongReview.knowledgePoint')}
                        </Badge>
                      </div>
                      <Button className="mt-3 rounded-xl w-full" onClick={() => startDrill(drill)}>
                        {t('wrongReview.startDrill')}
                      </Button>
                    </Card>
                  ))}
                </div>
              )}
            </Card>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <Card className="rounded-2xl border border-border bg-card p-5">
                <div className="flex items-center gap-2 mb-3">
                  <BrainCircuit className="h-4 w-4 text-indigo-600" />
                  <h3 className="text-base font-black">{t('wrongReview.causeBreakdown')}</h3>
                </div>
                <div className="space-y-2">
                  {causeBreakdown.length === 0 && <p className="text-sm text-muted-foreground">{t('wrongReview.noCauseData')}</p>}
                  {causeBreakdown.map((item: any) => (
                    <div key={item.cause_key} className="flex items-center justify-between rounded-xl border border-border px-3 py-2 bg-muted/20">
                      <div>
                        <p className="font-bold text-sm">{item.cause_label}</p>
                        <p className="text-xs text-muted-foreground">{t('wrongReview.wrongQuestions', { count: item.question_count, attempts: item.wrong_attempts })}</p>
                      </div>
                      <Badge className="rounded-lg bg-indigo-50 text-indigo-700 border border-indigo-100">
                        {Math.round((item.ratio || 0) * 100)}%
                      </Badge>
                    </div>
                  ))}
                </div>
              </Card>

              <Card className="rounded-2xl border border-border bg-card p-5">
                <div className="flex items-center gap-2 mb-3">
                  <BookOpenCheck className="h-4 w-4 text-emerald-600" />
                  <h3 className="text-base font-black">{t('wrongReview.kpBreakdown')}</h3>
                </div>
                <div className="space-y-2">
                  {kpBreakdown.length === 0 && <p className="text-sm text-muted-foreground">{t('wrongReview.noKpData')}</p>}
                  {kpBreakdown.map((item: any) => (
                    <div key={`${item.knowledge_point_id || 'unknown'}-${item.knowledge_point_name}`} className="rounded-xl border border-border px-3 py-2 bg-muted/20">
                      <p className="font-bold text-sm">{item.knowledge_point_name}</p>
                      <p className="text-xs text-muted-foreground">
                        {t('wrongReview.avgWrongCount', { count: item.question_count, avg: item.avg_wrong_count })}
                      </p>
                    </div>
                  ))}
                </div>
              </Card>
            </div>
          </>
        )}
      </div>
    </PageWrapper>
  );
};
