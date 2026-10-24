import { Link } from 'react-router-dom';
import { ArrowUpRight } from '@phosphor-icons/react';
import { AgentShowcase } from '@/components/landing/AgentShowcase';
import { LandingEntrance } from '@/components/landing/LandingEntrance';
import { LearningInstrument } from '@/components/landing/LearningInstrument';
import { useAuthStore } from '@/store/useAuthStore';
import { COPYRIGHT_YEAR } from '@/constants/version';
import '@/styles/landing.css';

export function Landing() {
  const user = useAuthStore(state => state.user);
  const entry = user ? '/xiaoyu' : '/register';
  return <div className="um-landing">
    <LandingEntrance />
    <div className="landing-atmosphere" aria-hidden="true"><div className="landing-background" /><div className="landing-light-sweep" /><div className="landing-floor-reflection" /></div>
    <header className="landing-header landing-wrap">
      <Link to="/" aria-label="UniMind 首页" className="landing-brand"><img src="/Unimind_logo_wide.png" alt="UniMind.ai" width="150" height="34" /></Link>
      <nav aria-label="首页导航">
        <div className="landing-nav-links"><a href="#tools">探索小宇</a><a href="#workspace">学习空间</a><Link to="/pricing">AI 加量</Link></div>
        <div className="landing-nav-actions">{!user && <Link to="/login">登录</Link>}<Link to={entry} className="landing-nav-entry">{user ? '进入学习空间' : '开始体验'}<ArrowUpRight size={16} /></Link></div>
      </nav>
    </header>

    <main>
      <section className="landing-hero landing-wrap" id="agent">
        <div className="landing-hero-copy">
          <h1><span className="landing-hero-invitation">和小宇一起</span><span className="landing-hero-statement"><span>将人工智能</span><span>转化为人类智慧</span></span></h1>
          <p className="landing-hero-description"><span>查资料、画图讲解、练习与复习，</span><span>和小宇一起把问题弄清楚。</span></p>
          <Link to={entry} className="landing-button">开始对话<ArrowUpRight size={18} /></Link>
        </div>
      </section>

      <section className="landing-agent landing-wrap" id="agent-preview" aria-label="小宇对话界面">
        <AgentShowcase />
      </section>

      <section className="landing-experience" id="tools" aria-label="探索小宇的工具"><LearningInstrument /></section>

      <section className="landing-product landing-wrap" id="workspace" aria-label="学习空间界面">
        <figure className="landing-product-main">
          <figcaption><div><span>课程与资料</span><p>课程、课件与学习进度，放在一起。</p></div><Link to="/courses">浏览课程<ArrowUpRight size={18} /></Link></figcaption>
          <div className="landing-product-stage"><div className="landing-ui-frame"><img src="/screenshots/landing-workspace-demo.webp" alt="虚构学员小林的课程、课件、学习进度与历史活动" width="3840" height="3660" loading="lazy" /></div></div>
        </figure>
        <figure className="landing-product-secondary">
          <div className="landing-product-stage"><div className="landing-ui-frame"><img src="/screenshots/landing-learning-records-demo.webp" alt="虚构学员的练习表现、知识掌握和历史考试记录" width="3840" height="2400" loading="lazy" /></div></div>
          <figcaption><span>学习记录</span><p>查看练习表现，<br />了解知识掌握情况。</p><Link to="/report-card">查看学习记录<ArrowUpRight size={18} /></Link></figcaption>
        </figure>
      </section>

      <section className="landing-start landing-wrap">
        <h2>试着问小宇一个问题。</h2>
        <Link to={entry} className="landing-button">{user ? '回到小宇' : '开始体验'}<ArrowUpRight size={19} /></Link>
      </section>

    </main>

    <footer className="landing-footer landing-wrap"><span>© {COPYRIGHT_YEAR} 北京融知高科 · UniMind.ai</span><div><a href="https://beian.miit.gov.cn/" target="_blank" rel="noopener noreferrer">京ICP备2023012726号-2</a><Link to="/terms">用户协议</Link><Link to="/privacy">隐私政策</Link></div></footer>
  </div>;
}
