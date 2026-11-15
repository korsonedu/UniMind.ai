import { t, useLocale } from '@/i18n';
import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowLeft, ArrowRight } from '@phosphor-icons/react';
import api from '@/lib/api';
import { Button } from '@/components/ui/button';
import type { LearningCatalog } from '@/types/learning';
import { learningPrice } from '@/types/learning';

export default function PricingPage() {
  useLocale();
  const [catalog, setCatalog] = useState<LearningCatalog | null>(null);
  const [error, setError] = useState('');
  const load = () => { void api.get<LearningCatalog>('/users/learning/catalog/').then(response => setCatalog(response.data)).catch(() => setError(t('AI 加量信息加载失败，请重试。'))); };
  useEffect(load, []);
  return <main className="min-h-dvh bg-background px-5 py-8 md:px-10"><div className="mx-auto max-w-4xl">
    <nav className="flex items-center justify-between gap-4"><Link to="/" aria-label={t('返回首页')}><img src="/Unimind_logo_wide.png" alt="UniMind" className="h-8 w-36 object-contain" /></Link><Button asChild variant="ghost"><Link to="/billing"><ArrowLeft size={16} />{t('我的服务')}</Link></Button></nav>
    <header className="py-10 border-b"><h1 className="text-3xl font-semibold">{t('AI 加量')}</h1><p className="mt-4 max-w-2xl text-muted-foreground leading-7">{t('按需增加小宇问答次数。购买加量不会改变课程访问权限。')}</p></header>
    {error ? <div role="alert" className="py-8"><p>{error}</p><Button variant="outline" onClick={() => { setError(''); load(); }}>{t('重试')}</Button></div> : !catalog ? <p role="status" className="py-8">{t('正在加载…')}</p> : <>
      <section className="py-8 border-b"><h2 className="text-xl font-medium">{t('基础周额度')}</h2><p className="mt-3 text-sm text-muted-foreground">{t('非课程学员')} {catalog.experience_weekly_calls === null ? t('待配置') : t('每周 {0} 次', { 0: catalog.experience_weekly_calls })}{t('；课程学员')} {catalog.course_weekly_calls === null ? t('待配置') : t('每周 {0} 次', { 0: catalog.course_weekly_calls })}{t('。上海时间每周一 00:00 恢复，未用次数不累计。')}</p><Button asChild variant="outline" className="mt-4"><Link to="/xiaoyu">{t('使用小宇')}<ArrowRight size={16} /></Link></Button></section>
      <section className="py-8"><h2 className="text-xl font-medium mb-3">{t('可购买的加量')}</h2>
        {catalog.products.length ? <ul className="divide-y">{catalog.products.map(product => <li key={product.id} className="py-6"><div className="flex flex-wrap justify-between items-start gap-4"><div className="min-w-0"><h3 className="font-medium break-words">{product.name}</h3><p className="mt-2 text-sm text-muted-foreground whitespace-pre-wrap">{product.description}</p></div><span className="shrink-0 text-lg">{learningPrice(product.price_cents)}</span></div><p className="text-sm mt-4">{t('额外')} {product.ai_calls} {t('次问答，支付后')} {product.validity_days} {t('天有效。不会每周重复发放。')}</p><Button asChild className="mt-4"><Link to={`/checkout?product=${product.id}`}>{t('查看加量')}<ArrowRight size={16} /></Link></Button></li>)}</ul> : <p className="py-4 text-sm text-muted-foreground">{t('AI 加量尚未上架。次数、价格和有效期确认后会在此展示；你可以等待基础额度恢复或联系我们。')}</p>}
      </section>
    </>}
    <footer className="py-6 border-t flex gap-5 text-sm text-muted-foreground"><Link to="/terms">{t('用户协议')}</Link><Link to="/privacy">{t('隐私政策')}</Link></footer>
  </div></main>;
}
