/**
 * 平台管理 — 超管统一面板。
 * 取代 Maintenance.tsx + PlatformAnalytics.tsx，按业务线组织。
 */
import React, { useState, useEffect, useCallback } from 'react';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Card } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Gauge, Buildings, Package, Megaphone, ChartLine, ArrowsClockwise, Spinner,
  Users, CurrencyCircleDollar, Crown, TrendUp,
} from '@phosphor-icons/react';
import { cn } from '@/lib/utils';
import api from '@/lib/api';
import { toast } from 'sonner';

// ── sub-panels (from maintenance) ──
import { AlbumSection } from './maintenance/AlbumSection';
import { BotSection } from './maintenance/BotSection';
import { MaterialSection } from './maintenance/MaterialSection';
import { TagSection } from './maintenance/TagSection';
import { NotificationSection } from './maintenance/NotificationSection';
import { NotificationConfigSection } from './maintenance/NotificationConfigSection';
import { ClassSection } from './maintenance/ClassSection';
import { InstitutionInviteSection } from './maintenance/InstitutionInviteSection';
import { PipelinePanel } from './maintenance/PipelinePanel';
import { KnowledgeSystemPanel } from './maintenance/KnowledgeSystemPanel';
import { BusinessDashboard } from './maintenance/BusinessDashboard';

// ── analytics ──
import { AnalyticsPanel } from './maintenance/AnalyticsPanel';
import { InsightsPanel } from './maintenance/InsightsPanel';

// ── existing pages ──
import InstitutionAdmin from './InstitutionAdmin';
import { PromptTemplatesAdmin } from './PromptTemplatesAdmin';

// ───────────────────────────────────────
// Overview Tab
// ───────────────────────────────────────

interface RevenueData {
  total_revenue: number;
  revenue_this_month: number;
  paying_users: number;
  arpu: number;
  mrr: number;
  arr: number;
  active_subscriptions: number;
  subs_by_plan: Record<string, number>;
  inst_by_plan: Record<string, number>;
}

const OverviewTab: React.FC = () => {
  const [analytics, setAnalytics] = useState<any>(null);
  const [revenue, setRevenue] = useState<RevenueData | null>(null);
  const [loading, setLoading] = useState(true);

  const fetchAll = useCallback(async () => {
    setLoading(true);
    try {
      const [aRes, rRes] = await Promise.all([
        api.get('/users/admin/analytics/dashboard/'),
        api.get('/users/admin/revenue/'),
      ]);
      setAnalytics(aRes.data);
      setRevenue(rRes.data);
    } catch {
      toast.error('加载平台数据失败');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchAll(); }, [fetchAll]);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Spinner className="h-6 w-6 animate-spin text-muted-foreground/30" />
      </div>
    );
  }

  const s = analytics?.summary || {};
  const nps = analytics?.nps || {};

  const fmtNum = (n: number) => n?.toLocaleString() || '0';
  const fmtMoney = (n: number) => `¥${n?.toLocaleString() || '0'}`;

  const MetricCard = ({ icon: Icon, label, value, sub, color = 'text-foreground' }: any) => (
    <Card className="p-5 rounded-2xl border border-black/[0.04] shadow-sm bg-white space-y-1.5">
      <div className="flex items-center gap-2 text-muted-foreground">
        <Icon className="h-4 w-4" />
        <span className="text-[11px] font-bold uppercase tracking-wide">{label}</span>
      </div>
      <div className={cn('text-[28px] font-black tracking-tight tabular-nums', color)}>{value}</div>
      {sub && <div className="text-[11px] text-muted-foreground font-medium">{sub}</div>}
    </Card>
  );

  return (
    <div className="space-y-8 text-left">
      {/* ── 运行状态 ── */}
      <div>
        <h3 className="text-[13px] font-extrabold text-foreground mb-3 flex items-center gap-2">
          <Gauge className="h-4 w-4 text-primary" /> 运行状态
        </h3>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <MetricCard icon={Users} label="总用户" value={fmtNum(s.total_users)} />
          <MetricCard icon={Users} label="日活 (DAU)" value={fmtNum(s.dau)} sub={`MAU ${fmtNum(s.mau)}`} />
          <MetricCard icon={Buildings} label="机构总数" value={fmtNum(s.total_institutions)} />
          <MetricCard icon={TrendUp} label="7日留存" value={`${Math.round((s.day7_retention || 0) * 100)}%`} />
        </div>
      </div>

      {/* ── 商业化 ── */}
      <div>
        <h3 className="text-[13px] font-extrabold text-foreground mb-3 flex items-center gap-2">
          <CurrencyCircleDollar className="h-4 w-4 text-unimind-green" /> 商业化
        </h3>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <MetricCard icon={CurrencyCircleDollar} label="累计营收" value={fmtMoney(revenue?.total_revenue || 0)} color="text-unimind-green" />
          <MetricCard icon={CurrencyCircleDollar} label="MRR" value={fmtMoney(revenue?.mrr || 0)} sub={`ARR ${fmtMoney(revenue?.arr || 0)}`} color="text-unimind-green" />
          <MetricCard icon={Crown} label="活跃订阅" value={fmtNum(revenue?.active_subscriptions || 0)} />
          <MetricCard icon={Users} label="付费用户" value={fmtNum(revenue?.paying_users || 0)} sub={`ARPU ¥${revenue?.arpu || 0}`} />
        </div>
        {/* Plan 分布 */}
        {revenue?.subs_by_plan && Object.keys(revenue.subs_by_plan).length > 0 && (
          <div className="mt-3 flex flex-wrap gap-2">
            {Object.entries(revenue.subs_by_plan).map(([plan, count]) => (
              <Badge key={plan} variant="secondary" className="text-[11px] font-bold gap-1.5">
                {plan} <span className="text-muted-foreground">{count as number}</span>
              </Badge>
            ))}
          </div>
        )}
      </div>

      {/* ── NPS ── */}
      {nps.total > 0 && (
        <div>
          <h3 className="text-[13px] font-extrabold text-foreground mb-3 flex items-center gap-2">
            <ChartLine className="h-4 w-4 text-amber-500" /> NPS 评分
          </h3>
          <div className="flex items-center gap-3">
            <span className={cn(
              'text-[32px] font-black tabular-nums',
              nps.score >= 50 ? 'text-unimind-green' : nps.score >= 0 ? 'text-amber-500' : 'text-red-500',
            )}>{nps.score}</span>
            <div className="text-[11px] text-muted-foreground">
              <div>共 {nps.total} 份评分</div>
              <div>推荐 {nps.distribution?.promoters || 0} · 被动 {nps.distribution?.passives || 0} · 贬损 {nps.distribution?.detractors || 0}</div>
            </div>
          </div>
        </div>
      )}

      {/* Refresh */}
      <Button variant="ghost" size="sm" onClick={fetchAll} className="gap-1.5 text-muted-foreground">
        <ArrowsClockwise className="h-3.5 w-3.5" /> 刷新
      </Button>
    </div>
  );
};

// ───────────────────────────────────────
// Main Page
// ───────────────────────────────────────

export const PlatformAdmin: React.FC = () => {
  return (
    <div className="min-h-screen bg-[#F2F2F6] p-6 md:p-8 space-y-8 max-w-[1600px] mx-auto text-left">
      <Tabs defaultValue="overview" className="space-y-8">
        <div className="sticky top-0 z-20 pt-2 pb-1 -mt-2">
          <TabsList className="bg-white/70 backdrop-blur-xl backdrop-saturate-150 p-1 rounded-2xl border border-white/20 shadow-[0_1px_3px_rgba(0,0,0,0.02),0_8px_24px_rgba(0,0,0,0.04)] h-auto flex flex-wrap gap-0.5 w-fit mx-auto">
            <TabsTrigger value="overview" className="rounded-xl px-4 py-2 text-xs font-medium data-[state=active]:bg-[#0071E3] data-[state=active]:text-white data-[state=active]:shadow-[0_1px_3px_rgba(0,113,227,0.35)] text-[#6E6E73] hover:text-[#1D1D1F] transition-[color,background-color,box-shadow] duration-200 gap-2">
              <Gauge className="w-3.5 h-3.5" />总览
            </TabsTrigger>
            <TabsTrigger value="institutions" className="rounded-xl px-4 py-2 text-xs font-medium data-[state=active]:bg-[#0071E3] data-[state=active]:text-white data-[state=active]:shadow-[0_1px_3px_rgba(0,113,227,0.35)] text-[#6E6E73] hover:text-[#1D1D1F] transition-[color,background-color,box-shadow] duration-200 gap-2">
              <Buildings className="w-3.5 h-3.5" />机构
            </TabsTrigger>
            <TabsTrigger value="content" className="rounded-xl px-4 py-2 text-xs font-medium data-[state=active]:bg-[#0071E3] data-[state=active]:text-white data-[state=active]:shadow-[0_1px_3px_rgba(0,113,227,0.35)] text-[#6E6E73] hover:text-[#1D1D1F] transition-[color,background-color,box-shadow] duration-200 gap-2">
              <Package className="w-3.5 h-3.5" />内容配置
            </TabsTrigger>
            <TabsTrigger value="ops" className="rounded-xl px-4 py-2 text-xs font-medium data-[state=active]:bg-[#0071E3] data-[state=active]:text-white data-[state=active]:shadow-[0_1px_3px_rgba(0,113,227,0.35)] text-[#6E6E73] hover:text-[#1D1D1F] transition-[color,background-color,box-shadow] duration-200 gap-2">
              <Megaphone className="w-3.5 h-3.5" />运营
            </TabsTrigger>
            <TabsTrigger value="analytics" className="rounded-xl px-4 py-2 text-xs font-medium data-[state=active]:bg-[#0071E3] data-[state=active]:text-white data-[state=active]:shadow-[0_1px_3px_rgba(0,113,227,0.35)] text-[#6E6E73] hover:text-[#1D1D1F] transition-[color,background-color,box-shadow] duration-200 gap-2">
              <ChartLine className="w-3.5 h-3.5" />数据
            </TabsTrigger>
          </TabsList>
        </div>

        <TabsContent value="overview"><OverviewTab /></TabsContent>
        <TabsContent value="institutions"><InstitutionAdmin /></TabsContent>
        <TabsContent value="content">
          <ContentTab />
        </TabsContent>
        <TabsContent value="ops">
          <OpsTab />
        </TabsContent>
        <TabsContent value="analytics">
          <AnalyticsTab />
        </TabsContent>
      </Tabs>
    </div>
  );
};

// ── Sub-tab: 内容配置 ──
const ContentTab: React.FC = () => (
  <Tabs defaultValue="albums" className="space-y-6">
    <TabsList className="bg-white/70 backdrop-blur-xl backdrop-saturate-150 p-1 rounded-2xl border border-white/20 shadow-sm h-auto flex flex-wrap gap-0.5 w-fit">
      <TabsTrigger value="albums" className="rounded-xl px-3 py-1.5 text-[11px] font-medium data-[state=active]:bg-[#0071E3] data-[state=active]:text-white text-[#6E6E73]">专辑</TabsTrigger>
      <TabsTrigger value="tags" className="rounded-xl px-3 py-1.5 text-[11px] font-medium data-[state=active]:bg-[#0071E3] data-[state=active]:text-white text-[#6E6E73]">标签</TabsTrigger>
      <TabsTrigger value="materials" className="rounded-xl px-3 py-1.5 text-[11px] font-medium data-[state=active]:bg-[#0071E3] data-[state=active]:text-white text-[#6E6E73]">启动物料</TabsTrigger>
      <TabsTrigger value="bots" className="rounded-xl px-3 py-1.5 text-[11px] font-medium data-[state=active]:bg-[#0071E3] data-[state=active]:text-white text-[#6E6E73]">AI Bot</TabsTrigger>
      <TabsTrigger value="prompts" className="rounded-xl px-3 py-1.5 text-[11px] font-medium data-[state=active]:bg-[#0071E3] data-[state=active]:text-white text-[#6E6E73]">Prompt 模板</TabsTrigger>
      <TabsTrigger value="pipeline" className="rounded-xl px-3 py-1.5 text-[11px] font-medium data-[state=active]:bg-[#0071E3] data-[state=active]:text-white text-[#6E6E73]">AI 管线</TabsTrigger>
      <TabsTrigger value="knowledge" className="rounded-xl px-3 py-1.5 text-[11px] font-medium data-[state=active]:bg-[#0071E3] data-[state=active]:text-white text-[#6E6E73]">知识体系</TabsTrigger>
    </TabsList>
    <TabsContent value="albums"><AlbumSection /></TabsContent>
    <TabsContent value="tags"><TagSection /></TabsContent>
    <TabsContent value="materials"><MaterialSection /></TabsContent>
    <TabsContent value="bots"><BotSection /></TabsContent>
    <TabsContent value="prompts"><PromptTemplatesAdmin /></TabsContent>
    <TabsContent value="pipeline"><PipelinePanel /></TabsContent>
    <TabsContent value="knowledge"><KnowledgeSystemPanel /></TabsContent>
  </Tabs>
);

// ── Sub-tab: 运营 ──
const OpsTab: React.FC = () => (
  <Tabs defaultValue="notifications" className="space-y-6">
    <TabsList className="bg-white/70 backdrop-blur-xl backdrop-saturate-150 p-1 rounded-2xl border border-white/20 shadow-sm h-auto flex flex-wrap gap-0.5 w-fit">
      <TabsTrigger value="notifications" className="rounded-xl px-3 py-1.5 text-[11px] font-medium data-[state=active]:bg-[#0071E3] data-[state=active]:text-white text-[#6E6E73]">站内广播</TabsTrigger>
      <TabsTrigger value="invites" className="rounded-xl px-3 py-1.5 text-[11px] font-medium data-[state=active]:bg-[#0071E3] data-[state=active]:text-white text-[#6E6E73]">邀请链接</TabsTrigger>
      <TabsTrigger value="reminders" className="rounded-xl px-3 py-1.5 text-[11px] font-medium data-[state=active]:bg-[#0071E3] data-[state=active]:text-white text-[#6E6E73]">复习提醒</TabsTrigger>
      <TabsTrigger value="classes" className="rounded-xl px-3 py-1.5 text-[11px] font-medium data-[state=active]:bg-[#0071E3] data-[state=active]:text-white text-[#6E6E73]">班级管理</TabsTrigger>
      <TabsTrigger value="business" className="rounded-xl px-3 py-1.5 text-[11px] font-medium data-[state=active]:bg-[#0071E3] data-[state=active]:text-white text-[#6E6E73]">机构商业</TabsTrigger>
    </TabsList>
    <TabsContent value="notifications"><NotificationSection /></TabsContent>
    <TabsContent value="invites"><InstitutionInviteSection /></TabsContent>
    <TabsContent value="reminders"><NotificationConfigSection /></TabsContent>
    <TabsContent value="classes"><ClassSection /></TabsContent>
    <TabsContent value="business"><BusinessDashboard /></TabsContent>
  </Tabs>
);

// ── Sub-tab: 数据 ──
const AnalyticsTab: React.FC = () => (
  <Tabs defaultValue="dashboard" className="space-y-6">
    <TabsList className="bg-white/70 backdrop-blur-xl backdrop-saturate-150 p-1 rounded-2xl border border-white/20 shadow-sm h-auto flex flex-wrap gap-0.5 w-fit">
      <TabsTrigger value="dashboard" className="rounded-xl px-3 py-1.5 text-[11px] font-medium data-[state=active]:bg-[#0071E3] data-[state=active]:text-white text-[#6E6E73]">趋势图表</TabsTrigger>
      <TabsTrigger value="insights" className="rounded-xl px-3 py-1.5 text-[11px] font-medium data-[state=active]:bg-[#0071E3] data-[state=active]:text-white text-[#6E6E73]">BI 洞察</TabsTrigger>
    </TabsList>
    <TabsContent value="dashboard"><AnalyticsPanel /></TabsContent>
    <TabsContent value="insights"><InsightsPanel /></TabsContent>
  </Tabs>
);

export default PlatformAdmin;
