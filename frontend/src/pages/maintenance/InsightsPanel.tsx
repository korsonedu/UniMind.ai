import React from 'react';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Target, Video, RefreshCw } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useTranslation } from 'react-i18next';

export const InsightsPanel = ({ biData, isLoadingBI, fetchBI }: { biData: any, isLoadingBI: boolean, fetchBI: () => void }) => {
  const { t } = useTranslation('maintenance');
  return (
    <div className="space-y-8 text-left">
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <Card className="p-8 rounded-[2rem] border-none shadow-sm bg-white border border-black/[0.03]">
          <p className="text-[11px] font-bold uppercase tracking-widest text-muted-foreground mb-1">{t('insights.totalUsers')}</p>
          <div className="flex items-baseline gap-2">
            <span className="text-4xl font-black tracking-tighter">{biData?.user_overview?.total || 0}</span>
            <span className="text-[11px] font-bold text-emerald-500 uppercase">Registered</span>
          </div>
        </Card>
        <Card className="p-8 rounded-[2rem] border-none shadow-sm bg-white border border-black/[0.03]">
          <p className="text-[11px] font-bold uppercase tracking-widest text-muted-foreground mb-1">{t('insights.proMembers')}</p>
          <div className="flex items-baseline gap-2">
            <span className="text-4xl font-black tracking-tighter text-amber-600">{biData?.user_overview?.members || 0}</span>
            <span className="text-[11px] font-bold text-amber-500 uppercase">Paid Members</span>
          </div>
        </Card>
        <Card className="p-8 rounded-[2rem] border-none shadow-sm bg-white border border-black/[0.03]">
          <p className="text-[11px] font-bold uppercase tracking-widest text-muted-foreground mb-1">{t('insights.conversionRate')}</p>
          <div className="flex items-baseline gap-2">
            <span className="text-4xl font-black tracking-tighter">{biData?.user_overview?.member_rate || 0}%</span>
            <span className="text-[11px] font-bold text-indigo-500 uppercase">Conversion</span>
          </div>
        </Card>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8 items-start">
        <Card className="border-none shadow-sm rounded-[2.5rem] p-10 bg-white border border-black/[0.03] space-y-8">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <Target className="h-6 w-6 text-red-600" />
              <h3 className="text-xl font-bold tracking-tight text-[#1D1D1F]">{t('insights.academicBottleneck')}</h3>
            </div>
            <Badge variant="outline" className="text-[11px] font-bold border-red-100 text-red-600">{t('insights.sortedByErrors')}</Badge>
          </div>
          <div className="space-y-4">
            {biData?.kp_errors?.map((item: any, i: number) => (
              <div key={i} className="space-y-2">
                <div className="flex justify-between items-center px-1">
                  <span className="text-xs font-bold text-[#1D1D1F]">{item.question__knowledge_point__name}</span>
                  <span className="text-[11px] font-bold tabular-nums text-red-500">{t('insights.errorCount', { count: item.total_errors })}</span>
                </div>
                <div className="h-2 w-full bg-slate-50 rounded-full overflow-hidden">
                  <div 
                    className="h-full bg-red-500/80 rounded-full transition-all duration-1000" 
                    style={{ width: `${(item.total_errors / (biData.kp_errors[0]?.total_errors || 1)) * 100}%` }} 
                  />
                </div>
              </div>
            ))}
            {(!biData?.kp_errors || biData.kp_errors.length === 0) && (
              <div className="py-20 text-center opacity-20 font-bold uppercase text-[11px]">{t('insights.noErrorData')}</div>
            )}
          </div>
        </Card>

        <Card className="border-none shadow-sm rounded-[2.5rem] p-10 bg-[#F5F5F7]/50 border border-black/[0.03] space-y-8">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <Video className="h-6 w-6 text-emerald-600" />
              <h3 className="text-xl font-bold tracking-tight text-[#1D1D1F]">{t('insights.courseEngagement')}</h3>
            </div>
            <Button variant="ghost" size="icon" onClick={fetchBI} className="rounded-full h-8 w-8"><RefreshCw className={cn("w-3.5 h-3.5 opacity-40", isLoadingBI && "animate-spin")} /></Button>
          </div>
          <div className="space-y-2">
            {biData?.course_stats?.map((item: any, i: number) => (
              <div key={i} className="p-5 bg-white rounded-2xl border border-black/[0.02] shadow-sm flex items-center justify-between group">
                <div className="min-w-0 flex-1 pr-4">
                  <p className="text-xs font-bold text-[#1D1D1F] truncate">{item.course__title}</p>
                  <p className="text-[11px] font-medium text-muted-foreground mt-1 uppercase tracking-tighter">
                    {t('insights.viewsAndCompletions', { views: item.total_views, completions: item.completions })}
                  </p>
                </div>
                <div className="text-right shrink-0">
                  <div className="text-[11px] font-black tracking-tighter text-emerald-600">
                    {Math.round((item.completions / (item.total_views || 1)) * 100)}%
                  </div>
                  <p className="text-[11px] font-bold text-muted-foreground/40 uppercase">Finish Rate</p>
                </div>
              </div>
            ))}
            {(!biData?.course_stats || biData.course_stats.length === 0) && (
              <div className="py-20 text-center opacity-20 font-bold uppercase text-[11px]">{t('insights.noViewData')}</div>
            )}
          </div>
        </Card>
      </div>
    </div>
  );
};
