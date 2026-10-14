import { useEffect, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import api from '@/lib/api';
import { Button } from '@/components/ui/button';
import { formatApiErrorToast } from '@/lib/apiError';
import type { LearningCatalog } from '@/types/learning';
import { learningPrice } from '@/types/learning';

export function Checkout() {
  const [params] = useSearchParams();
  const [catalog, setCatalog] = useState<LearningCatalog | null>(null);
  const [gateway, setGateway] = useState('');
  const [error, setError] = useState('');
  const [paying, setPaying] = useState(false);
  useEffect(() => {
    void api.get<LearningCatalog>('/users/learning/catalog/').then(response => { setCatalog(response.data); setGateway(response.data.payment_methods[0] || ''); }).catch(() => setError('服务信息加载失败，请返回后重试。'));
  }, []);
  const product = catalog?.products.find(item => item.id === Number(params.get('product')));
  const pay = async () => {
    if (!product || !gateway || paying) return;
    setError(''); setPaying(true);
    try {
      const { data } = await api.post('/payments/create-session/', { product: product.id, gateway });
      sessionStorage.setItem('last_order_id', String(data.order_id));
      if (gateway === 'stub') {
        await api.post(`/payments/orders/${data.order_id}/simulate/`);
        window.location.assign('/payments/result');
        return;
      }
      const target = new URL(data.checkout_url, window.location.origin);
      if (target.protocol !== 'https:' || !['openapi.alipay.com', 'openapi-sandbox.dl.alipaydev.com', 'mapi.alipay.com'].includes(target.hostname)) throw new Error('支付地址异常，请联系客服。');
      window.location.assign(target.href);
    } catch (error) { setError(formatApiErrorToast(error, '创建订单失败，请重试')); setPaying(false); }
  };
  return <main className="min-h-dvh px-5 py-12 bg-background"><div className="max-w-xl mx-auto space-y-7">
    <Link to="/pricing" className="text-sm text-muted-foreground">返回学习服务</Link>
    <h1 className="text-2xl font-semibold">确认购买</h1>
    {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
    {!catalog ? <p role="status">正在加载…</p> : !product ? <p>该服务尚未上架或已下架，请返回选择其他服务。</p> : <>
      <section className="border-y py-6 space-y-4"><h2 className="text-xl font-medium">{product.name}</h2><p className="text-muted-foreground whitespace-pre-wrap">{product.description}</p><p>{product.duration_days} 天有效 · 每月 {product.monthly_ai_calls} 次 AI 对话</p>{product.module_names.length > 0 && <p className="text-sm">课程模块：{product.module_names.join('、')}</p>}<p className="text-2xl">{learningPrice(product.price_cents)}</p></section>
      {catalog.payment_methods.length ? <><fieldset className="space-y-3"><legend className="text-sm mb-3">支付方式</legend>{catalog.payment_methods.map(method => <label key={method} className="flex items-center gap-2"><input type="radio" name="gateway" value={method} checked={gateway === method} onChange={() => setGateway(method)} />{method === 'alipay' ? '支付宝' : '开发环境模拟支付'}</label>)}</fieldset><p className="text-sm text-muted-foreground">本次为一次性购买，不会自动续费。</p><Button disabled={paying || !gateway} onClick={() => { void pay(); }}>{paying ? '正在创建订单…' : '确认支付'}</Button></> : <p className="text-sm text-muted-foreground">在线支付暂未开通，请稍后再试。</p>}
    </>}
  </div></main>;
}
