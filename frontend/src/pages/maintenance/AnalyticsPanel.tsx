import React, { useState, useEffect, useCallback } from 'react';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Users, Buildings, ChartLine, TrendUp, ArrowsClockwise, Chat, Download } from '@phosphor-icons/react';
import { cn } from '@/lib/utils';
import api from '@/lib/api';
import { toast } from 'sonner';
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, BarChart, Bar, PieChart, Pie, Cell,
} from 'recharts';

const COLORS = ['#0071E3', '#34C759', '#FF9500', '#AF52DE', '#FF3B30', '#5856D6'];

interface DailyStats {
  date: string;
  dau: number;
  new_users: number;
  new_institutions: number;
  quiz_attempts: number;
  quiz_correct_rate: number;
  ai_chat_sessions: number;
  course_views: number;
  day1_retention: number;
}

interface DashboardData {
  summary: {
    total_users: number;
    total_institutions: number;
    dau: number;
    mau: number;
    day7_retention: number;
  };
  trends: DailyStats[];
  feature_breakdown: Record<string, number>;
  institution_top: Array<{
    id: number;
    name: string;
    student_count: number;
    created_at: string;
  }>;
  nps: {
    score: number;
    total: number;
    distribution: {
      promoters: number;
      passives: number;
      detractors: number;
    };
    recent_feedback: Array<{
      username: string;
      score: number;
      feedback: string;
      created_at: string;
    }>;
  };
}

export const AnalyticsPanel: React.FC = () => {
  const [data, setData] = useState<DashboardData | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [days, setDays] = useState(30);

  const fetchData = useCallback(async () => {
    setIsLoading(true);
    try {
      const res = await api.get(`/users/admin/analytics/dashboard/?days=${days}`);
      setData(res.data);
    } catch {
      toast.error('加载分析数据失败');
    } finally {
      setIsLoading(false);
    }
  }, [days]);

  const exportCSV = useCallback(async (type: string) => {
    try {
      const res = await api.get(`/users/admin/analytics/export/?type=${type}&days=${days}`, {
        responseType: 'blob',
      });
      const url = URL.createObjectURL(res.data);
      const a = document.createElement('a');
      a.href = url;
      a.download = `analytics_${type}_${new Date().toISOString().slice(0, 10)}.csv`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
      toast.success('导出成功');
    } catch {
      toast.error('导出失败');
    }
  }, [days]);

  useEffect(() => { fetchData(); }, [fetchData]);

  if (!data) {
    return (
      <div className="flex items-center justify-center py-20 text-[#8E8E93]">
        {isLoading ? '加载中...' : '暂无数据'}
      </div>
    );
  }

  const featureData = Object.entries(data.feature_breakdown).map(([key, value]) => ({
    name: EVENT_LABELS[key] || key,
    value,
  }));

  return (
    <div className="space-y-8 text-left">
      {/* 汇总卡片 */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
        <MetricCard icon={<Users className="h-4 w-4" />} label="总用户" value={data.summary.total_users} color="text-blue-500" />
        <MetricCard icon={<Buildings className="h-4 w-4" />} label="总机构" value={data.summary.total_institutions} color="text-emerald-500" />
        <MetricCard icon={<ChartLine className="h-4 w-4" />} label="DAU" value={data.summary.dau} color="text-amber-500" />
        <MetricCard icon={<TrendUp className="h-4 w-4" />} label="MAU" value={data.summary.mau} color="text-indigo-500" />
        <MetricCard icon={<TrendUp className="h-4 w-4" />} label="7日留存" value={`${(data.summary.day7_retention * 100).toFixed(1)}%`} color="text-rose-500" />
      </div>

      {/* 时间范围 + 导出 */}
      <div className="flex items-center gap-2 flex-wrap">
        {[7, 14, 30, 90].map(d => (
          <Button
            key={d}
            variant={days === d ? 'default' : 'outline'}
            size="sm"
            onClick={() => setDays(d)}
            className="rounded-lg text-xs"
          >
            {d}天
          </Button>
        ))}
        <div className="flex items-center gap-1 ml-auto">
          <Button
            variant="outline"
            size="sm"
            onClick={() => exportCSV('trends')}
            className="rounded-lg text-xs gap-1.5"
          >
            <Download className="w-3.5 h-3.5" />导出趋势
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => exportCSV('events')}
            className="rounded-lg text-xs gap-1.5"
          >
            <Download className="w-3.5 h-3.5" />导出事件
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => exportCSV('nps')}
            className="rounded-lg text-xs gap-1.5"
          >
            <Download className="w-3.5 h-3.5" />导出NPS
          </Button>
          <Button variant="ghost" size="icon" onClick={fetchData} className="rounded-full h-8 w-8">
            <ArrowsClockwise className={cn("w-3.5 h-3.5", isLoading && "animate-spin")} />
          </Button>
        </div>
      </div>

      {/* 趋势图 */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <ChartCard title="DAU 趋势" subtitle="每日活跃用户数">
          <ResponsiveContainer width="100%" height={250}>
            <LineChart data={data.trends}>
              <CartesianGrid strokeDasharray="3 3" stroke="#F5F5F7" />
              <XAxis dataKey="date" tick={{ fontSize: 11 }} tickFormatter={v => v.slice(5)} />
              <YAxis tick={{ fontSize: 11 }} />
              <Tooltip />
              <Line type="monotone" dataKey="dau" stroke="#0071E3" strokeWidth={2} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard title="新增用户" subtitle="每日注册数">
          <ResponsiveContainer width="100%" height={250}>
            <BarChart data={data.trends}>
              <CartesianGrid strokeDasharray="3 3" stroke="#F5F5F7" />
              <XAxis dataKey="date" tick={{ fontSize: 11 }} tickFormatter={v => v.slice(5)} />
              <YAxis tick={{ fontSize: 11 }} />
              <Tooltip />
              <Bar dataKey="new_users" fill="#34C759" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard title="学习活动" subtitle="答题量 + AI 对话量">
          <ResponsiveContainer width="100%" height={250}>
            <LineChart data={data.trends}>
              <CartesianGrid strokeDasharray="3 3" stroke="#F5F5F7" />
              <XAxis dataKey="date" tick={{ fontSize: 11 }} tickFormatter={v => v.slice(5)} />
              <YAxis tick={{ fontSize: 11 }} />
              <Tooltip />
              <Line type="monotone" dataKey="quiz_attempts" stroke="#FF9500" strokeWidth={2} dot={false} name="答题" />
              <Line type="monotone" dataKey="ai_chat_sessions" stroke="#AF52DE" strokeWidth={2} dot={false} name="AI对话" />
            </LineChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard title="次日留存率" subtitle="前一天注册用户的次日登录率">
          <ResponsiveContainer width="100%" height={250}>
            <LineChart data={data.trends}>
              <CartesianGrid strokeDasharray="3 3" stroke="#F5F5F7" />
              <XAxis dataKey="date" tick={{ fontSize: 11 }} tickFormatter={v => v.slice(5)} />
              <YAxis tick={{ fontSize: 11 }} tickFormatter={v => `${(v * 100).toFixed(0)}%`} />
              <Tooltip formatter={(v: any) => `${(Number(v) * 100).toFixed(1)}%`} />
              <Line type="monotone" dataKey="day1_retention" stroke="#FF3B30" strokeWidth={2} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </ChartCard>
      </div>

      {/* 功能分布 + 机构 Top */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <ChartCard title="功能使用分布" subtitle="各模块事件占比">
          {featureData.length > 0 ? (
            <div className="flex items-center gap-6">
              <ResponsiveContainer width={180} height={180}>
                <PieChart>
                  <Pie data={featureData} dataKey="value" cx="50%" cy="50%" outerRadius={80} innerRadius={40}>
                    {featureData.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
                  </Pie>
                  <Tooltip />
                </PieChart>
              </ResponsiveContainer>
              <div className="space-y-2 flex-1">
                {featureData.map((item, i) => (
                  <div key={i} className="flex items-center justify-between text-sm">
                    <div className="flex items-center gap-2">
                      <div className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: COLORS[i % COLORS.length] }} />
                      <span>{item.name}</span>
                    </div>
                    <span className="tabular-nums text-[#8E8E93]">{item.value}</span>
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <div className="py-16 text-center text-sm text-[#AEAEB2]">暂无事件数据</div>
          )}
        </ChartCard>

        <ChartCard title="机构 Top 10" subtitle="按学生数排序">
          <div className="space-y-2">
            {data.institution_top.map((inst, i) => (
              <div key={inst.id} className="flex items-center justify-between p-3 rounded-xl hover:bg-[#F5F5F7] transition-colors">
                <div className="flex items-center gap-3">
                  <span className="text-xs font-medium text-[#8E8E93] w-5">{i + 1}</span>
                  <span className="text-sm font-medium">{inst.name}</span>
                </div>
                <div className="flex items-center gap-2">
                  <Badge variant="outline" className="text-xs rounded-lg">{inst.student_count} 学员</Badge>
                  <span className="text-xs text-[#AEAEB2]">{inst.created_at}</span>
                </div>
              </div>
            ))}
            {data.institution_top.length === 0 && (
              <div className="py-16 text-center text-sm text-[#AEAEB2]">暂无机构数据</div>
            )}
          </div>
        </ChartCard>
      </div>

      {/* NPS */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <Card className="rounded-2xl p-8 bg-white border border-black/[0.04] shadow-[0_1px_2px_rgba(0,0,0,0.02),0_4px_16px_rgba(0,0,0,0.03)]">
          <div className="flex items-center gap-3 mb-4">
            <Chat className="h-5 w-5 text-blue-500" />
            <h3 className="text-lg font-semibold tracking-tight">NPS 净推荐值</h3>
          </div>
          <div className="flex items-baseline gap-2 mb-6">
            <span className={cn(
              "text-5xl font-bold tracking-tight",
              data.nps.score > 0 ? 'text-emerald-500' : data.nps.score < 0 ? 'text-red-500' : 'text-[#8E8E93]'
            )}>
              {data.nps.score}
            </span>
            <span className="text-sm text-[#8E8E93]">/ 100</span>
          </div>
          <div className="text-xs text-[#8E8E93] mb-2">{data.nps.total} 份问卷</div>
          <div className="flex gap-4 text-xs">
            <span className="text-emerald-500">推荐 {data.nps.distribution.promoters}</span>
            <span className="text-amber-500">中立 {data.nps.distribution.passives}</span>
            <span className="text-red-500">贬损 {data.nps.distribution.detractors}</span>
          </div>
        </Card>

        <Card className="lg:col-span-2 rounded-2xl p-8 bg-white border border-black/[0.04] shadow-[0_1px_2px_rgba(0,0,0,0.02),0_4px_16px_rgba(0,0,0,0.03)]">
          <h3 className="text-lg font-semibold tracking-tight mb-4">近期反馈</h3>
          <div className="space-y-3">
            {data.nps.recent_feedback.map((fb, i) => (
              <div key={i} className="p-4 rounded-xl bg-[#F5F5F7]/60 flex items-start justify-between gap-4">
                <div>
                  <span className="text-sm font-medium">{fb.username}</span>
                  <p className="text-sm text-[#6E6E73] mt-1">{fb.feedback}</p>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  <Badge variant="outline" className={cn(
                    "text-xs rounded-lg",
                    fb.score >= 9 ? 'border-emerald-200 text-emerald-600' :
                    fb.score >= 7 ? 'border-amber-200 text-amber-600' :
                    'border-red-200 text-red-600'
                  )}>
                    {fb.score}分
                  </Badge>
                  <span className="text-xs text-[#AEAEB2]">{fb.created_at.slice(0, 10)}</span>
                </div>
              </div>
            ))}
            {data.nps.recent_feedback.length === 0 && (
              <div className="py-12 text-center text-sm text-[#AEAEB2]">暂无反馈</div>
            )}
          </div>
        </Card>
      </div>
    </div>
  );
};

// ── 子组件 ──

const MetricCard: React.FC<{
  icon: React.ReactNode;
  label: string;
  value: number | string;
  color: string;
}> = ({ icon, label, value, color }) => (
  <Card className="p-5 rounded-2xl border border-black/[0.04] shadow-[0_1px_2px_rgba(0,0,0,0.02),0_4px_16px_rgba(0,0,0,0.03)] bg-white">
    <div className="flex items-center gap-2 mb-2">
      <div className={color}>{icon}</div>
      <p className="text-xs font-medium text-[#6E6E73]">{label}</p>
    </div>
    <span className="text-2xl font-semibold tracking-tight">{value}</span>
  </Card>
);

const ChartCard: React.FC<{
  title: string;
  subtitle?: string;
  children: React.ReactNode;
}> = ({ title, subtitle, children }) => (
  <Card className="rounded-2xl p-6 bg-white border border-black/[0.04] shadow-[0_1px_2px_rgba(0,0,0,0.02),0_4px_16px_rgba(0,0,0,0.03)]">
    <div className="mb-4">
      <h3 className="text-base font-semibold tracking-tight">{title}</h3>
      {subtitle && <p className="text-xs text-[#8E8E93] mt-0.5">{subtitle}</p>}
    </div>
    {children}
  </Card>
);

const EVENT_LABELS: Record<string, string> = {
  user_login: '用户登录',
  diagnostic_start: '诊断开始',
  diagnostic_complete: '诊断完成',
  quiz_attempt: '刷题',
  ai_chat_start: 'AI对话',
  course_view: '课程浏览',
  course_complete: '课程完成',
  pdf_export: 'PDF导出',
  invite_click: '邀请链接',
};
