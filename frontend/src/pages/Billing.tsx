import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowRight } from '@phosphor-icons/react';
import api from '@/lib/api';
import { Button } from '@/components/ui/button';
import { Progress } from '@/components/ui/progress';
import { ContactAdminModal } from '@/components/ContactAdminModal';
import type { LearningAccess } from '@/types/learning';
import { learningDate, learningPrice, learningReset } from '@/types/learning';

interface Order { id: number; product_name: string; status: string; amount_cents: number; created_at: string; }

export function BillingPage() {
  const [access, setAccess] = useState<LearningAccess | null>(null);
  const [orders, setOrders] = useState<Order[]>([]);
  const [error, setError] = useState('');
  const [contactOpen, setContactOpen] = useState(false);
  const load = () => {
    setError('');
    void Promise.all([api.get<LearningAccess>('/users/learning/access/'), api.get<Order[]>('/payments/orders/')])
      .then(([rights, history]) => { setAccess(rights.data); setOrders(history.data); })
      .catch(() => setError('我的服务加载失败，请重试。'));
  };
  useEffect(load, []);
  const usagePercent = access?.ai_usage.limit ? Math.min(100, Math.round(access.ai_usage.used / access.ai_usage.limit * 100)) : 0;
  const status: Record<string, string> = { paid: '已支付', pending: '待支付', refunded: '已退款', expired: '已过期', cancelled: '已取消' };
  const cohortStates: Record<string, string> = { active: '服务中', scheduled: '尚未开始', expired: '已结束', disabled: '已停用' };
  return <main className="max-w-4xl mx-auto py-6 space-y-8">
    <header className="flex flex-wrap justify-between items-center gap-4"><h1 className="text-2xl font-semibold">我的服务</h1><div className="flex gap-3"><Button variant="outline" onClick={() => setContactOpen(true)}>联系我们</Button><Button asChild variant="outline"><Link to="/pricing">AI 加量<ArrowRight size={16} /></Link></Button></div></header>
    {error ? <div role="alert"><p>{error}</p><Button variant="outline" onClick={load}>重试</Button></div> : !access ? <p role="status">正在加载…</p> : <>
      <section><h2 className="font-medium">当前身份</h2><p className="mt-3">{access.ai_usage.unlimited ? '管理员' : access.is_course_student ? '课程学员' : '注册学生'}</p><p className="mt-2 text-sm text-muted-foreground">{access.is_course_student ? '课程服务由科晟线下安排，学员状态与服务批次由管理员调整。' : '可以观看公开课并使用有限小宇问答。课程服务请联系科晟，购买 AI 加量不会开通课程。'}</p>
        {access.cohort ? <div className="mt-3 space-y-1 text-sm"><p>{access.cohort.name} · {access.cohort.target_year}届 · {cohortStates[access.cohort.state]}</p><p>服务日期：{access.cohort.starts_on} 至 {access.cohort.ends_on}（上海日期，含结束当日）</p><p>实际考试日期：{access.cohort.exam_date || '待教研设置'}</p>{!access.cohort.service_active && <p className="text-muted-foreground">该批次当前未向此账号提供全权益，历史学习记录保留。</p>}</div> : access.is_course_student && !access.ai_usage.unlimited && <p className="mt-3 text-sm text-muted-foreground">沿用原手工课程授权，尚未分配年度批次；请联系科晟核对服务日期。</p>}
      </section>
      <section className="border-y py-6"><h2 className="font-medium">本周 AI 问答</h2>
        <p className="mt-3 text-2xl tabular-nums">{access.ai_usage.used}<span className="text-sm text-muted-foreground"> / {access.ai_usage.unlimited ? '不限' : access.ai_usage.configured ? access.ai_usage.limit : '待配置'} 次基础额度</span></p>
        {access.ai_usage.configured && !access.ai_usage.unlimited && <div className="mt-4 space-y-2"><div className="flex justify-between text-sm text-muted-foreground"><span>基础额度已用</span><span className="tabular-nums">{usagePercent}%</span></div><Progress value={usagePercent} role="progressbar" aria-label="本周基础额度使用进度" aria-valuemin={0} aria-valuemax={100} aria-valuenow={usagePercent} aria-valuetext={`已用 ${access.ai_usage.used} / ${access.ai_usage.limit} 次基础额度`} /></div>}
        <p className="mt-2 text-sm">剩余可用：{access.ai_usage.unlimited ? '不限' : `${access.ai_usage.remaining} 次`}，其中 AI 加量 {access.ai_usage.addon_remaining} 次。</p>
        <p className="mt-2 text-sm text-muted-foreground">基础额度按上海时间自然周恢复，下次恢复：{learningReset(access.ai_usage.resets_at)}。一次完整成功答复计一次，失败或取消不扣次。</p>
        {!access.ai_usage.configured && <p className="mt-2 text-sm text-muted-foreground">基础周额度尚未配置，请联系科晟确认。</p>}
        {access.ai_usage.remaining === 0 && access.ai_usage.configured && <p className="mt-2 text-sm text-muted-foreground">本周额度已用完，可以等待恢复或联系我们。</p>}
      </section>
      <section><h2 className="font-medium mb-3">可用 AI 加量</h2><ul className="divide-y">{access.addons.map(addon => <li key={addon.id} className="py-4"><p>{addon.name}</p><p className="text-sm mt-2 text-muted-foreground">剩余 {Math.max(0, addon.ai_calls - addon.used_calls)} 次，有效至 {learningDate(addon.expires_at)}</p></li>)}</ul>{!access.addons.length && <p className="text-sm text-muted-foreground">暂无可用加量。加量仅用于 AI 问答。</p>}</section>
      <section><h2 className="font-medium mb-3">购买记录</h2><ul className="divide-y">{orders.map(order => <li key={order.id} className="flex flex-wrap justify-between gap-3 py-4 text-sm"><div><p>{order.product_name}</p><p className="mt-1 text-muted-foreground">{learningDate(order.created_at)}</p></div><p>{learningPrice(order.amount_cents)} · {status[order.status] || order.status}</p></li>)}</ul>{!orders.length && <p className="text-sm text-muted-foreground">暂无购买记录。线下课程付费不在此生成订单。</p>}</section>
    </>}
    <ContactAdminModal open={contactOpen} onOpenChange={setContactOpen} />
  </main>;
}
