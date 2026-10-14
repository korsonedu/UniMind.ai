import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowLeft, ArrowRight, Check } from '@phosphor-icons/react';
import api from '@/lib/api';
import { Button } from '@/components/ui/button';
import type { LearningCatalog } from '@/types/learning';
import { learningPrice } from '@/types/learning';

export default function PricingPage() {
  const [catalog, setCatalog] = useState<LearningCatalog | null>(null);
  const [error, setError] = useState('');
  const load = () => { setError(''); void api.get<LearningCatalog>('/users/learning/catalog/').then(response => setCatalog(response.data)).catch(() => setError('学习服务加载失败，请重试。')); };
  useEffect(load, []);
  return <main className="min-h-dvh bg-background px-5 py-8 md:px-10">
    <div className="mx-auto max-w-4xl">
      <nav className="flex items-center justify-between gap-4"><Link to="/" aria-label="返回首页"><img src="/Unimind_logo_wide.png" alt="UniMind" className="h-8 w-36 object-contain" /></Link><Button asChild variant="ghost"><Link to="/"><ArrowLeft size={16} />返回</Link></Button></nav>
      <header className="py-10 border-b"><h1 className="text-3xl font-semibold">个人学习服务</h1><p className="mt-4 max-w-2xl text-muted-foreground leading-7">基础学习向每位学习者开放。你可以根据需要购买课程模块和额外的 AI 对话额度，科晟学员也可获得课程配套权益。</p></header>
      {error ? <div role="alert" className="py-8"><p>{error}</p><Button variant="outline" onClick={load}>重试</Button></div> : !catalog ? <p role="status" className="py-8">正在加载…</p> : <>
        <section className="py-8 border-b">
          <div className="flex flex-wrap justify-between gap-4"><h2 className="text-xl font-medium">基础学习</h2><span className="text-lg">免费</span></div>
          <ul className="grid gap-3 py-5 text-sm md:grid-cols-2">{['习题训练与错题复习', 'Memorix 复习与学习记录', '学习记录与学习社区', `每月 ${catalog.free_ai_calls} 次 AI 对话`].map(item => <li key={item} className="flex gap-2"><Check size={16} className="shrink-0 text-emerald-600" />{item}</li>)}</ul>
          <Button asChild><Link to="/xiaoyu">开始学习<ArrowRight size={16} /></Link></Button>
        </section>
        <section className="py-8"><h2 className="text-xl font-medium mb-3">可选学习服务</h2><p className="text-sm text-muted-foreground">同时持有多个服务时，AI 月额度取最高值，不累加；同一服务续购会顺延有效期。</p>
          {catalog.products.length ? <ul className="divide-y">{catalog.products.map(product => <li key={product.id} className="py-6">
            <div className="flex flex-wrap justify-between items-start gap-4"><div className="min-w-0"><h3 className="font-medium break-words">{product.name}</h3><p className="mt-2 text-sm text-muted-foreground whitespace-pre-wrap">{product.description}</p></div><span className="shrink-0 text-lg">{learningPrice(product.price_cents)}</span></div>
            <p className="text-sm mt-4">{product.duration_days} 天有效 · 每月 {Math.max(catalog.free_ai_calls, product.monthly_ai_calls)} 次 AI 对话</p>
            {product.module_names.length > 0 && <p className="mt-2 text-sm text-muted-foreground">课程模块：{product.module_names.join('、')}</p>}
            <Button asChild className="mt-4"><Link to={`/checkout?product=${product.id}`}>查看服务<ArrowRight size={16} /></Link></Button>
          </li>)}</ul> : <p className="py-4 text-sm text-muted-foreground">付费服务尚未上架，你可以先使用基础学习功能。</p>}
        </section>
      </>}
      <footer className="py-6 border-t flex gap-5 text-sm text-muted-foreground"><Link to="/terms">用户协议</Link><Link to="/privacy">隐私政策</Link></footer>
    </div>
  </main>;
}
