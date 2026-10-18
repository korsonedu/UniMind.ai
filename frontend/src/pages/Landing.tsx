import { Link } from 'react-router-dom';
import { ArrowRight } from '@phosphor-icons/react';
import { Button } from '@/components/ui/button';
import { useAuthStore } from '@/store/useAuthStore';
import { APP_VERSION, COPYRIGHT_YEAR } from '@/constants/version';

export function Landing() {
  const token = useAuthStore(state => state.token);
  const entry = token ? '/xiaoyu' : '/register';
  return <div className="min-h-dvh bg-white text-zinc-900">
    <header className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-4 px-5 py-6 md:px-8">
      <Link to="/" aria-label="UniMind 首页"><img src="/Unimind_logo_wide.png" alt="UniMind.ai" className="h-8 w-36 object-contain" /></Link>
      <nav className="flex flex-wrap items-center gap-4 text-sm md:gap-7">
        <Link to="/pricing" className="hover:underline">AI 加量</Link>
        {!token && <Link to="/login" className="hover:underline">登录</Link>}
        <Button asChild className="rounded-lg"><Link to={entry}>{token ? '继续学习' : '免费开始'}<ArrowRight size={16} /></Link></Button>
      </nav>
    </header>
    <main>
      <section className="mx-auto max-w-6xl px-5 py-16 md:px-8 md:py-24">
        <h1 className="text-5xl font-semibold leading-tight md:text-6xl">UniMind.ai</h1>
        <p className="mt-6 max-w-2xl text-xl leading-9 md:text-2xl">科晟课程的学习与交付平台。</p>
        <p className="mt-5 max-w-2xl text-base leading-8 text-zinc-600">课程学员在这里学习课程、练习和复习。还未报名课程，也可以先和小宇聊聊学习问题，体验每周有限的问答服务。</p>
        <div className="mt-8 flex flex-wrap items-center gap-5"><Button asChild className="rounded-lg"><Link to={entry}>开始学习<ArrowRight size={16} /></Link></Button><Link to="/pricing" className="text-sm underline underline-offset-4">查看 AI 加量</Link></div>
      </section>
      <section className="bg-zinc-50 px-5 py-12 md:px-8 md:py-16">
        <div className="mx-auto max-w-6xl">
          <div className="mb-8 flex flex-wrap items-baseline justify-between gap-4"><h2 className="text-2xl font-medium">把练习和复习接起来</h2><span className="text-sm text-zinc-500">练习 · 错题 · Memorix · 学习记录</span></div>
          <img src="/screenshots/memorix-review.png" alt="UniMind 的 Memorix 复习界面" width="1440" height="900" className="block h-auto w-full object-contain" />
        </div>
      </section>
      <section className="mx-auto grid max-w-6xl gap-10 px-5 py-16 md:grid-cols-3 md:px-8 md:py-20">
        {[
          { title: '按自己的节奏练习', text: '课程学员可以围绕知识点练习，把错题留在记录里，再回到薄弱的地方。课程学习与配套功能由管理员开通。' },
          { title: '有问题，找小宇聊聊', text: '每周问答额度用于梳理概念与讨论学习问题，课程学员享有更多额度。用完后可以等待恢复或联系我们，也可按需购买 AI 加量。' },
          { title: '课程服务由科晟安排', text: '课程在线下报名和付费，管理员手动开通学员状态。AI 加量只增加问答次数，不会开放课程访问权限。' },
        ].map(item => <div key={item.title}><h2 className="text-xl font-medium">{item.title}</h2><p className="mt-4 text-sm leading-7 text-zinc-600">{item.text}</p></div>)}
      </section>
      <section className="border-t border-zinc-100 px-5 py-14 md:px-8">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-6"><div><h2 className="text-2xl font-medium">先开始学习，再选择需要的服务</h2><p className="mt-3 text-sm leading-7 text-zinc-600">付费服务到期后，你的学习记录仍会保留，基础学习可以继续使用。</p></div><Button asChild className="rounded-lg"><Link to={entry}>进入 UniMind<ArrowRight size={16} /></Link></Button></div>
      </section>
    </main>
    <footer className="border-t border-zinc-100 px-5 py-8 text-xs text-zinc-500 md:px-8">
      <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-5"><span>© {COPYRIGHT_YEAR} 北京融知高科 · UniMind.ai · {APP_VERSION}</span><div className="flex flex-wrap gap-5"><a href="https://beian.miit.gov.cn/" target="_blank" rel="noopener noreferrer">京ICP备2023012726号-2</a><Link to="/terms">用户协议</Link><Link to="/privacy">隐私政策</Link></div></div>
    </footer>
  </div>;
}
