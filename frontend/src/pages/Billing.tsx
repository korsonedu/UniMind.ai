import { t, useLocale } from '@/i18n';
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
  useLocale();
  const [access, setAccess] = useState<LearningAccess | null>(null);
  const [orders, setOrders] = useState<Order[]>([]);
  const [error, setError] = useState('');
  const [contactOpen, setContactOpen] = useState(false);
  const load = () => {
    void Promise.all([api.get<LearningAccess>('/users/learning/access/'), api.get<Order[]>('/payments/orders/')])
      .then(([rights, history]) => { setAccess(rights.data); setOrders(history.data); })
      .catch(() => setError(t('我的服务加载失败，请重试。')));
  };
  useEffect(load, []);
  const usagePercent = access?.ai_usage.limit ? Math.min(100, Math.round(access.ai_usage.used / access.ai_usage.limit * 100)) : 0;
  const status: Record<string, string> = { paid: t('已支付'), pending: t('待支付'), refunded: t('已退款'), expired: t('已过期'), cancelled: t('已取消') };
  const cohortStates: Record<string, string> = { active: t('服务中'), scheduled: t('尚未开始'), expired: t('已结束'), disabled: t('已停用') };
  return <main className="max-w-4xl mx-auto py-6 space-y-8">
    <header className="flex flex-wrap justify-between items-center gap-4"><h1 className="text-2xl font-semibold">{t('我的服务')}</h1><div className="flex gap-3"><Button variant="outline" onClick={() => setContactOpen(true)}>{t('联系我们')}</Button><Button asChild variant="outline"><Link to="/pricing">{t('AI 加量')}<ArrowRight size={16} /></Link></Button></div></header>
    {error ? <div role="alert"><p>{t(error)}</p><Button variant="outline" onClick={() => { setError(''); load(); }}>{t('重试')}</Button></div> : !access ? <p role="status">{t('正在加载…')}</p> : <>
      <section><h2 className="font-medium">{t('当前身份')}</h2><p className="mt-3">{access.ai_usage.unlimited ? t('管理员') : access.is_course_student ? t('课程学员') : t('注册学生')}</p><p className="mt-2 text-sm text-muted-foreground">{access.is_course_student ? t('课程服务由科晟线下安排，学员状态与服务批次由管理员调整。') : t('可以观看公开课并使用有限小宇问答。课程服务请联系科晟，购买 AI 加量不会开通课程。')}</p>
        {access.cohort ? <div className="mt-3 space-y-1 text-sm"><p>{access.cohort.name} · {t('{0}届 · {1}', { 0: access.cohort.target_year, 1: cohortStates[access.cohort.state] })}</p><p>{t('服务日期：{0} 至 {1}（上海日期，含结束当日）', { 0: access.cohort.starts_on, 1: access.cohort.ends_on })}</p><p>{t('实际考试日期：')}{access.cohort.exam_date || t('待教研设置')}</p>{!access.cohort.service_active && <p className="text-muted-foreground">{t('该批次当前未向此账号提供全权益，历史学习记录保留。')}</p>}</div> : access.is_course_student && !access.ai_usage.unlimited && <p className="mt-3 text-sm text-muted-foreground">{t('沿用原手工课程授权，尚未分配年度批次；请联系科晟核对服务日期。')}</p>}
      </section>
      <section className="border-y py-6"><h2 className="font-medium">{t('本周 AI 问答')}</h2>
        <p className="mt-3 text-2xl tabular-nums">{access.ai_usage.used}<span className="text-sm text-muted-foreground"> / {access.ai_usage.unlimited ? t('不限') : access.ai_usage.configured ? access.ai_usage.limit : t('待配置')} {t('次基础额度')}</span></p>
        {access.ai_usage.configured && !access.ai_usage.unlimited && <div className="mt-4 space-y-2"><div className="flex justify-between text-sm text-muted-foreground"><span>{t('基础额度已用')}</span><span className="tabular-nums">{usagePercent}%</span></div><Progress value={usagePercent} role="progressbar" aria-label={t('本周基础额度使用进度')} aria-valuemin={0} aria-valuemax={100} aria-valuenow={usagePercent} aria-valuetext={t('已用 {0} / {1} 次基础额度', { 0: access.ai_usage.used, 1: access.ai_usage.limit })} /></div>}
        <p className="mt-2 text-sm">{t('剩余可用：{0}，其中 AI 加量 {1} 次。', { 0: access.ai_usage.unlimited ? t('不限') : t('{0} 次', { 0: access.ai_usage.remaining }), 1: access.ai_usage.addon_remaining })}</p>
        <p className="mt-2 text-sm text-muted-foreground">{t('基础额度按上海时间自然周恢复，下次恢复：{0}。一次完整成功答复计一次，失败或取消不扣次。', { 0: learningReset(access.ai_usage.resets_at) })}</p>
        {!access.ai_usage.configured && <p className="mt-2 text-sm text-muted-foreground">{t('基础周额度尚未配置，请联系科晟确认。')}</p>}
        {access.ai_usage.remaining === 0 && access.ai_usage.configured && <p className="mt-2 text-sm text-muted-foreground">{t('本周额度已用完，可以等待恢复或联系我们。')}</p>}
      </section>
      <section><h2 className="font-medium mb-3">{t('可用 AI 加量')}</h2><ul className="divide-y">{access.addons.map(addon => <li key={addon.id} className="py-4"><p>{addon.name}</p><p className="text-sm mt-2 text-muted-foreground">{t('剩余 {0} 次，有效至 {1}', { 0: Math.max(0, addon.ai_calls - addon.used_calls), 1: learningDate(addon.expires_at) })}</p></li>)}</ul>{!access.addons.length && <p className="text-sm text-muted-foreground">{t('暂无可用加量。加量仅用于 AI 问答。')}</p>}</section>
      <section><h2 className="font-medium mb-3">{t('购买记录')}</h2><ul className="divide-y">{orders.map(order => <li key={order.id} className="flex flex-wrap justify-between gap-3 py-4 text-sm"><div><p>{order.product_name}</p><p className="mt-1 text-muted-foreground">{learningDate(order.created_at)}</p></div><p>{learningPrice(order.amount_cents)} · {status[order.status] || order.status}</p></li>)}</ul>{!orders.length && <p className="text-sm text-muted-foreground">{t('暂无购买记录。线下课程付费不在此生成订单。')}</p>}</section>
    </>}
    <ContactAdminModal open={contactOpen} onOpenChange={setContactOpen} />
  </main>;
}
