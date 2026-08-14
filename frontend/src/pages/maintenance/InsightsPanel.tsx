import React, { useState, useEffect, useCallback } from 'react';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Target, Video, ArrowsClockwise } from '@phosphor-icons/react';
import { cn } from '@/lib/utils';
import api from '@/lib/api';
import { toast } from 'sonner';

export const InsightsPanel: React.FC = () => {
  const [biData, setBIData] = useState<any>(null);
  const [isLoading, setIsLoading] = useState(false);

  const fetchBI = useCallback(async () => {
    setIsLoading(true);
    try {
      const res = await api.get('/users/admin/bi/');
      setBIData(res.data);
    } catch {
      toast.error('分析数据同步失败');
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => { fetchBI(); }, [fetchBI]);

  return (
    <div className="space-y-8 text-left">
      <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
        <Card className="p-8 rounded-2xl border border-black/[0.04] shadow-[0_1px_2px_rgba(0,0,0,0.02),0_4px_16px_rgba(0,0,0,0.03)] bg-white">
          <p className="text-xs font-medium text-[#6E6E73] mb-2">注册总用户</p>
          <div className="flex items-baseline gap-2">
            <span className="text-4xl font-semibold tracking-tight">{biData?.user_overview?.total || 0}</span>
            <span className="text-xs font-medium text-emerald-500">Registered</span>
          </div>
        </Card>
        <Card className="p-8 rounded-2xl border border-black/[0.04] shadow-[0_1px_2px_rgba(0,0,0,0.02),0_4px_16px_rgba(0,0,0,0.03)] bg-white">
          <p className="text-xs font-medium text-[#6E6E73] mb-2">正式学员 (Enterprise)</p>
          <div className="flex items-baseline gap-2">
            <span className="text-4xl font-semibold tracking-tight text-amber-500">{biData?.user_overview?.members || 0}</span>
            <span className="text-xs font-medium text-amber-500">Paid Members</span>
          </div>
        </Card>
        <Card className="p-8 rounded-2xl border border-black/[0.04] shadow-[0_1px_2px_rgba(0,0,0,0.02),0_4px_16px_rgba(0,0,0,0.03)] bg-white">
          <p className="text-xs font-medium text-[#6E6E73] mb-2">付费转化率</p>
          <div className="flex items-baseline gap-2">
            <span className="text-4xl font-semibold tracking-tight">{biData?.user_overview?.member_rate || 0}%</span>
            <span className="text-xs font-medium text-indigo-500">Conversion</span>
          </div>
        </Card>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 items-start">
        <Card className="rounded-2xl p-8 bg-white border border-black/[0.04] shadow-[0_1px_2px_rgba(0,0,0,0.02),0_4px_16px_rgba(0,0,0,0.03)] space-y-6">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <Target className="h-5 w-5 text-red-500" />
              <h3 className="text-lg font-semibold tracking-tight">学术瓶颈 Top 10</h3>
            </div>
            <Badge variant="outline" className="text-xs font-medium border-red-100 text-red-500 rounded-lg">按错题总数降序</Badge>
          </div>
          <div className="space-y-4">
            {biData?.kp_errors?.map((item: any, i: number) => (
              <div key={i} className="space-y-2">
                <div className="flex justify-between items-center px-1">
                  <span className="text-xs font-medium">{item.question__knowledge_point__name}</span>
                  <span className="text-xs font-medium tabular-nums text-red-500">{`${item.total_errors} 次错误`}</span>
                </div>
                <div className="h-1.5 w-full bg-[#F5F5F7] rounded-full overflow-hidden">
                  <div
                    className="h-full bg-red-400 rounded-full transition-[width] duration-700"
                    style={{ width: `${(item.total_errors / (biData.kp_errors[0]?.total_errors || 1)) * 100}%` }}
                  />
                </div>
              </div>
            ))}
            {(!biData?.kp_errors || biData.kp_errors.length === 0) && (
              <div className="py-20 text-center text-sm text-[#AEAEB2] font-medium">暂无错题数据</div>
            )}
          </div>
        </Card>

        <Card className="rounded-2xl p-8 bg-[#F5F5F7]/60 border border-black/[0.03] space-y-6">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <Video className="h-5 w-5 text-emerald-500" />
              <h3 className="text-lg font-semibold tracking-tight">课程吸睛指数</h3>
            </div>
            <Button variant="ghost" size="icon" onClick={fetchBI} className="rounded-full h-8 w-8 hover:bg-black/[0.04]">
              <ArrowsClockwise className={cn("w-3.5 h-3.5 text-[#8E8E93]", isLoading && "animate-spin")} />
            </Button>
          </div>
          <div className="space-y-2">
            {biData?.course_stats?.map((item: any, i: number) => (
              <div key={i} className="p-4 bg-white rounded-xl border border-transparent hover:border-black/[0.04] hover:shadow-[0_2px_8px_rgba(0,0,0,0.03)] flex items-center justify-between group transition-[border-color,box-shadow]">
                <div className="min-w-0 flex-1 pr-4">
                  <p className="text-sm font-medium truncate">{item.course__title}</p>
                  <p className="text-xs text-[#8E8E93] mt-1">
                    {`${item.total_views} 位学员观看 · ${item.completions} 位已达成`}
                  </p>
                </div>
                <div className="text-right shrink-0">
                  <div className="text-sm font-semibold tracking-tight text-emerald-500">
                    {Math.round((item.completions / (item.total_views || 1)) * 100)}%
                  </div>
                  <p className="text-[11px] font-medium text-[#AEAEB2]">Finish Rate</p>
                </div>
              </div>
            ))}
            {(!biData?.course_stats || biData.course_stats.length === 0) && (
              <div className="py-20 text-center text-sm text-[#AEAEB2] font-medium">暂无观看记录</div>
            )}
          </div>
        </Card>
      </div>
    </div>
  );
};
