import { Button } from '@/components/ui/button';
import { ArrowLeft, Clock } from '@phosphor-icons/react';
import { Link } from 'react-router-dom';

export default function PromoPlus() {
  return (
    <main className="min-h-screen bg-white px-6 py-20 text-[#1a1a2e]">
      <div className="mx-auto max-w-xl space-y-6 rounded-2xl border border-[#e5e7eb] p-8">
        <Clock className="h-8 w-8 text-[#5a5a7a]" />
        <h1 className="text-3xl font-bold">首批机构活动已结束</h1>
        <p className="leading-relaxed text-[#5a5a7a]">
          首批机构免费开放活动已于 2026 年 6 月 30 日结束。当前方案与价格请查看定价页。
        </p>
        <div className="flex flex-wrap items-center gap-4">
          <Button asChild><Link to="/pricing">查看当前方案</Link></Button>
          <Link to="/" className="inline-flex items-center gap-1 text-sm text-[#5a5a7a]">
            <ArrowLeft className="h-4 w-4" />返回首页
          </Link>
        </div>
      </div>
    </main>
  );
}
