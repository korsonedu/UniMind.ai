import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowRight } from '@phosphor-icons/react';
import api from '@/lib/api';
import { Button } from '@/components/ui/button';
import { toast } from 'sonner';
import { formatApiErrorToast } from '@/lib/apiError';
import { queryClient } from '@/lib/queryClient';
import { useInstitutionStore } from '@/store/useInstitutionStore';
import type { LearningGrant } from '@/types/learning';
import { learningDate, learningPrice } from '@/types/learning';

interface Access { ai_usage: { used: number; limit: number | null }; grants: LearningGrant[]; }
interface Order { id: number; product_name: string; status: string; amount_cents: number; created_at: string; }

export function BillingPage() {
  const [access, setAccess] = useState<Access | null>(null);
  const [orders, setOrders] = useState<Order[]>([]);
  const [error, setError] = useState('');
  const [code, setCode] = useState('');
  const [activating, setActivating] = useState(false);
  const load = () => {
    setError('');
    void Promise.all([api.get<Access>('/users/learning/access/'), api.get<Order[]>('/payments/orders/')])
      .then(([rights, history]) => { setAccess(rights.data); setOrders(history.data); })
      .catch(() => setError('学习服务加载失败，请重试。'));
  };
  useEffect(load, []);
  const activate = async (event: React.FormEvent) => {
    event.preventDefault(); if (activating || !code.trim()) return;
    setActivating(true);
    try {
      await api.post('/users/me/activate/', { code: code.trim() });
      await queryClient.invalidateQueries();
      await useInstitutionStore.getState().fetchFeatures();
      setCode(''); load(); toast.success('权益已激活');
    } catch (error) { toast.error(formatApiErrorToast(error, '激活失败')); }
    finally { setActivating(false); }
  };
  const status: Record<string, string> = { paid: '已支付', pending: '待支付', refunded: '已退款', expired: '已过期', cancelled: '已取消' };
  return <main className="max-w-4xl mx-auto py-6 space-y-8">
    <header className="flex flex-wrap justify-between items-center gap-4"><h1 className="text-2xl font-semibold">学习服务与账单</h1><Button asChild variant="outline"><Link to="/pricing">查看学习服务<ArrowRight size={16} /></Link></Button></header>
    {error ? <div role="alert"><p>{error}</p><Button variant="outline" onClick={load}>重试</Button></div> : !access ? <p role="status">正在加载…</p> : <>
      <section className="border-y py-6"><h2 className="font-medium">本月 AI 对话</h2><p className="mt-3 text-2xl tabular-nums">{access.ai_usage.used}<span className="text-sm text-muted-foreground"> / {access.ai_usage.limit ?? '不限'} 次</span></p><p className="mt-2 text-sm text-muted-foreground">基础学习持续开放。服务到期后，学习记录会保留。</p></section>
      <section><h2 className="font-medium mb-3">我的权益</h2><ul className="divide-y">{access.grants.map(grant => <li key={grant.id} className="py-4"><div className="flex flex-wrap justify-between gap-3"><span>{grant.snapshot.name}</span><span className="text-sm text-muted-foreground">{grant.source === 'course' ? '课程配套' : grant.source === 'admin' ? '赠送' : '个人购买'}</span></div><p className="text-sm mt-2 text-muted-foreground">有效至 {learningDate(grant.expires_at)} · 每月 {grant.snapshot.monthly_ai_calls} 次 AI 对话</p></li>)}</ul>{!access.grants.length && <p className="text-sm text-muted-foreground">当前使用基础学习服务。课程配套或购买的服务将在这里显示。</p>}</section>
      <section><h2 className="font-medium mb-3">激活已有权益</h2><form className="flex gap-3 max-w-lg" onSubmit={activate}><input aria-label="权益激活码" value={code} onChange={event => setCode(event.target.value)} placeholder="输入激活码" className="border rounded-md px-3 py-2 min-w-0 flex-1 bg-background" /><Button type="submit" disabled={activating || !code.trim()}>{activating ? '激活中…' : '激活'}</Button></form></section>
      <section><h2 className="font-medium mb-3">购买记录</h2><ul className="divide-y">{orders.map(order => <li key={order.id} className="flex flex-wrap justify-between gap-3 py-4 text-sm"><div><p>{order.product_name}</p><p className="mt-1 text-muted-foreground">{learningDate(order.created_at)}</p></div><p>{learningPrice(order.amount_cents)} · {status[order.status] || order.status}</p></li>)}</ul>{!orders.length && <p className="text-sm text-muted-foreground">暂无购买记录</p>}</section>
    </>}
  </main>;
}
