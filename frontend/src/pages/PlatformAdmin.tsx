/**
 * 平台管理 — 超管统一面板。
 * 仅展示平台级全局管理功能，机构级管理在机构后台。
 */
import React, { useState, useEffect, useCallback } from 'react';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Card } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Gauge, Buildings, Package, Megaphone,
  ArrowsClockwise, Spinner, Ticket, ShieldCheck,
  Users, CurrencyCircleDollar, Crown, TrendUp,
} from '@phosphor-icons/react';
import { cn } from '@/lib/utils';
import api from '@/lib/api';
import { toast } from 'sonner';

// ── sub-panels ──
import { BotSection } from './maintenance/BotSection';
import { NotificationSection } from './maintenance/NotificationSection';
import { KnowledgeSystemPanel } from './maintenance/KnowledgeSystemPanel';
import InstitutionAdmin from './InstitutionAdmin';
import InviteCodeAdmin from './InviteCodeAdmin';
import AuditLogs from './AuditLogs';
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
    // analytics — essential
    try {
      const aRes = await api.get('/users/admin/analytics/dashboard/');
      setAnalytics(aRes.data);
    } catch {
      toast.error('加载平台数据失败');
      setAnalytics(null);
    }
    // revenue — optional (may fail if payments app disabled)
    try {
      const rRes = await api.get('/users/admin/revenue/');
      setRevenue(rRes.data);
    } catch {
      setRevenue(null);
    }
    setLoading(false);
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

  const fmtNum = (n: number) => n?.toLocaleString() || '0';
  const fmtMoney = (n: number) => n != null ? `¥${n.toLocaleString()}` : '---';

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
      {analytics && (
      <>{/* ── 运行状态 ── */}
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
          <MetricCard icon={CurrencyCircleDollar} label="累计营收" value={fmtMoney(revenue?.total_revenue ?? null as any)} color="text-unimind-green" />
          <MetricCard icon={CurrencyCircleDollar} label="MRR" value={fmtMoney(revenue?.mrr ?? null as any)} sub={revenue ? `ARR ${fmtMoney(revenue.arr)}` : undefined} color="text-unimind-green" />
          <MetricCard icon={Crown} label="活跃订阅" value={revenue ? fmtNum(revenue.active_subscriptions) : '---'} />
          <MetricCard icon={Users} label="付费用户" value={revenue ? fmtNum(revenue.paying_users) : '---'} sub={revenue ? `ARPU ¥${revenue.arpu}` : undefined} />
        </div>
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

      {/* Refresh */}
      <Button variant="ghost" size="sm" onClick={fetchAll} className="gap-1.5 text-muted-foreground">
        <ArrowsClockwise className="h-3.5 w-3.5" /> 刷新
      </Button>
      </>
    )}
    </div>
  );
};

// ───────────────────────────────────────
// Content Tab — 仅平台级全局内容
// ───────────────────────────────────────

const ContentTab: React.FC = () => (
  <Tabs defaultValue="prompts" className="space-y-6">
    <TabsList className="bg-white/70 backdrop-blur-xl backdrop-saturate-150 p-1 rounded-2xl border border-white/20 shadow-sm h-auto flex flex-wrap gap-0.5 w-fit">
      <TabsTrigger value="prompts" className="rounded-xl px-3 py-1.5 text-[11px] font-medium data-[state=active]:bg-[#0071E3] data-[state=active]:text-white text-[#6E6E73]">
        Prompt 模板
      </TabsTrigger>
      <TabsTrigger value="bots" className="rounded-xl px-3 py-1.5 text-[11px] font-medium data-[state=active]:bg-[#0071E3] data-[state=active]:text-white text-[#6E6E73]">
        AI Bot
      </TabsTrigger>
      <TabsTrigger value="knowledge" className="rounded-xl px-3 py-1.5 text-[11px] font-medium data-[state=active]:bg-[#0071E3] data-[state=active]:text-white text-[#6E6E73]">
        知识体系
      </TabsTrigger>
    </TabsList>
    <TabsContent value="prompts"><PromptTemplatesAdmin /></TabsContent>
    <TabsContent value="bots"><BotSection /></TabsContent>
    <TabsContent value="knowledge"><KnowledgeSystemPanel /></TabsContent>
  </Tabs>
);

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
          </TabsList>
        </div>

        <TabsContent value="overview"><OverviewTab /></TabsContent>
        <TabsContent value="institutions"><InstitutionAdmin /></TabsContent>
        <TabsContent value="content">
          <ContentTab />
        </TabsContent>
        <TabsContent value="ops">
          <Tabs defaultValue="notifications" className="space-y-6">
            <TabsList className="bg-white/70 backdrop-blur-xl backdrop-saturate-150 p-1 rounded-2xl border border-white/20 shadow-sm h-auto flex flex-wrap gap-0.5 w-fit">
              <TabsTrigger value="notifications" className="rounded-xl px-3 py-1.5 text-[11px] font-medium data-[state=active]:bg-[#0071E3] data-[state=active]:text-white text-[#6E6E73]">
                <Megaphone className="w-3 h-3 mr-1.5" />站内广播
              </TabsTrigger>
              <TabsTrigger value="invites" className="rounded-xl px-3 py-1.5 text-[11px] font-medium data-[state=active]:bg-[#0071E3] data-[state=active]:text-white text-[#6E6E73]">
                <Ticket className="w-3 h-3 mr-1.5" />邀请码管理
              </TabsTrigger>
              <TabsTrigger value="audit" className="rounded-xl px-3 py-1.5 text-[11px] font-medium data-[state=active]:bg-[#0071E3] data-[state=active]:text-white text-[#6E6E73]">
                <ShieldCheck className="w-3 h-3 mr-1.5" />审计日志
              </TabsTrigger>
            </TabsList>
            <TabsContent value="notifications"><NotificationSection /></TabsContent>
            <TabsContent value="invites"><InviteCodeAdmin /></TabsContent>
            <TabsContent value="audit"><AuditLogs /></TabsContent>
          </Tabs>
        </TabsContent>
      </Tabs>
    </div>
  );
};

export default PlatformAdmin;
