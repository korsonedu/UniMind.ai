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
        <Link to="/pricing" className="hover:underline">学习服务</Link>
        {!token && <Link to="/login" className="hover:underline">登录</Link>}
        <Button asChild className="rounded-lg"><Link to={entry}>{token ? '继续学习' : '免费开始'}<ArrowRight size={16} /></Link></Button>
      </nav>
    </header>
    <main>
      <section className="mx-auto max-w-6xl px-5 py-16 md:px-8 md:py-24">
        <h1 className="text-5xl font-semibold leading-tight md:text-6xl">UniMind.ai</h1>
        <p className="mt-6 max-w-2xl text-xl leading-9 md:text-2xl">面向每一位学习者的智能学习平台。</p>
        <p className="mt-5 max-w-2xl text-base leading-8 text-zinc-600">从一次练习开始，记录错题，安排复习，和小宇一起梳理不理解的知识。基础学习免费开放，你也可以按需要选择课程模块和额外的学习服务。</p>
        <div className="mt-8 flex flex-wrap items-center gap-5"><Button asChild className="rounded-lg"><Link to={entry}>开始学习<ArrowRight size={16} /></Link></Button><Link to="/pricing" className="text-sm underline underline-offset-4">查看学习服务</Link></div>
      </section>
      <section className="bg-zinc-50 px-5 py-12 md:px-8 md:py-16">
        <div className="mx-auto max-w-6xl">
          <div className="mb-8 flex flex-wrap items-baseline justify-between gap-4"><h2 className="text-2xl font-medium">把练习和复习接起来</h2><span className="text-sm text-zinc-500">练习 · 错题 · Memorix · 学习记录</span></div>
          <img src="/screenshots/memorix-review.png" alt="UniMind 的 Memorix 复习界面" width="1440" height="900" className="block h-auto w-full object-contain" />
        </div>
      </section>
      <section className="mx-auto grid max-w-6xl gap-10 px-5 py-16 md:grid-cols-3 md:px-8 md:py-20">
        {[
          { title: '按自己的节奏练习', text: '围绕知识点练习，把错题留在记录里，再回到薄弱的地方。练习、错题复习和学习记录向所有注册用户开放。' },
          { title: '有问题，找小宇聊聊', text: '基础服务提供每月 AI 对话额度，用于梳理概念与讨论学习问题。需要更多额度时，可以查看可选学习服务。' },
          { title: '课程与服务按需选择', text: '公开课程模块免费学习。其他课程模块按个人权益开放，科晟智慧学员可获得所报课程对应的配套服务。' },
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
