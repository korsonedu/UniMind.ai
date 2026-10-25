import { useEffect, useRef } from 'react';
import { Link } from 'react-router-dom';
import { ArrowUpRight } from '@phosphor-icons/react';
import { AgentShowcase } from '@/components/landing/AgentShowcase';
import { LandingEntrance } from '@/components/landing/LandingEntrance';
import { LandingCoda } from '@/components/landing/LandingCoda';
import { LearningInstrument } from '@/components/landing/LearningInstrument';
import { useAuthStore } from '@/store/useAuthStore';
import { COPYRIGHT_YEAR } from '@/constants/version';
import '@/styles/landing.css';

export function Landing() {
  const user = useAuthStore(state => state.user);
  const entry = user ? '/xiaoyu' : '/register';
  const pageRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const page = pageRef.current;
    if (!page || window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    const layers = [...page.querySelectorAll<HTMLElement>('[data-landing-depth]')];
    let magnet: HTMLElement | null = null;
    let magnetBounds: DOMRect | null = null;
    const resetMagnet = () => {
      magnet?.style.removeProperty('--magnet-x');
      magnet?.style.removeProperty('--magnet-y');
      magnet = null; magnetBounds = null;
    };
    const moveMagnet = (event: PointerEvent) => {
      if (event.pointerType !== 'mouse') return;
      const target = event.target instanceof Element ? event.target.closest<HTMLElement>('.landing-button,.landing-nav-entry,.landing-showcase-next') : null;
      if (target !== magnet) { resetMagnet(); magnet = target; magnetBounds = target?.getBoundingClientRect() || null; }
      if (!magnet || !magnetBounds) return;
      const x = Math.max(-8, Math.min(8, (event.clientX - magnetBounds.left - magnetBounds.width / 2) * .16));
      const y = Math.max(-6, Math.min(6, (event.clientY - magnetBounds.top - magnetBounds.height / 2) * .25));
      magnet.style.setProperty('--magnet-x', `${x.toFixed(2)}px`);
      magnet.style.setProperty('--magnet-y', `${y.toFixed(2)}px`);
    };
    const leaveMagnet = (event: PointerEvent) => {
      if (!(event.relatedTarget instanceof Node) || !magnet?.contains(event.relatedTarget)) resetMagnet();
    };
    const traceNav = (event: PointerEvent) => {
      if (event.pointerType !== 'mouse') return;
      const link = event.target instanceof Element ? event.target.closest<HTMLElement>('.landing-header nav a') : null;
      if (!link || (event.relatedTarget instanceof Node && link.contains(event.relatedTarget))) return;
      const header = page.querySelector<HTMLElement>('.landing-header')!;
      const box = header.getBoundingClientRect();
      const target = link.getBoundingClientRect();
      const x = target.left + target.width / 2 - box.left;
      const bottom = box.height - 10;
      const end = Math.min(bottom - 4, target.bottom - box.top + 4);
      header.querySelectorAll<SVGPathElement>('.landing-nav-fiber path').forEach((path, index) => {
        path.setAttribute('d', `M18 ${box.height / 2} Q18 ${bottom} 48 ${bottom} H${x - 16} Q${x} ${bottom} ${x} ${end}`);
        path.getAnimations().forEach(animation => animation.cancel());
        path.animate(index ? [
          { strokeDashoffset: .08, opacity: 0 }, { opacity: 1, offset: .12 },
          { opacity: 1, offset: .8 }, { strokeDashoffset: -1, opacity: 0 },
        ] : [{ strokeDashoffset: 1, opacity: 0 }, { strokeDashoffset: 0, opacity: .28, offset: .7 }, { opacity: 0 }],
        { duration: 1000, easing: 'ease-in-out', fill: 'both' });
      });
    };
    let frame = 0;
    const paint = () => {
      frame = 0;
      const height = window.innerHeight;
      layers.forEach(layer => {
        const rect = layer.getBoundingClientRect();
        const depth = Math.max(-1, Math.min(1, (height / 2 - rect.top - rect.height / 2) / ((height + rect.height) / 2)));
        layer.style.setProperty('--scene-depth', depth.toFixed(3));
      });
      page.style.setProperty('--floor-shift', `${Math.min(48, window.scrollY * .018)}px`);
    };
    const schedule = () => { if (!frame) frame = requestAnimationFrame(paint); };
    const scroll = () => { resetMagnet(); schedule(); };
    paint();
    window.addEventListener('scroll', scroll, { passive: true });
    window.addEventListener('resize', schedule);
    page.addEventListener('pointermove', moveMagnet, { passive: true });
    page.addEventListener('pointerout', leaveMagnet);
    page.addEventListener('pointerover', traceNav);
    return () => {
      cancelAnimationFrame(frame);
      resetMagnet();
      window.removeEventListener('scroll', scroll);
      window.removeEventListener('resize', schedule);
      page.removeEventListener('pointermove', moveMagnet);
      page.removeEventListener('pointerout', leaveMagnet);
      page.removeEventListener('pointerover', traceNav);
    };
  }, []);

  return <div ref={pageRef} className="um-landing">
    <LandingEntrance />
    <svg className="landing-fx-defs" aria-hidden="true" width="0" height="0"><defs><filter id="landing-glass-warp" x="-10%" y="-10%" width="120%" height="120%" colorInterpolationFilters="sRGB"><feTurbulence type="fractalNoise" baseFrequency=".012 .035" numOctaves="1" seed="8" result="distortion" /><feDisplacementMap in="SourceGraphic" in2="distortion" scale="24" xChannelSelector="R" yChannelSelector="G" /></filter></defs></svg>
    <div className="landing-atmosphere" aria-hidden="true"><div className="landing-background" /><div className="landing-refraction" /><div className="landing-light-sweep" /><div className="landing-floor-reflection" /></div>
    <header className="landing-header landing-wrap">
      <svg className="landing-nav-fiber" aria-hidden="true"><path pathLength="1" /><path pathLength="1" /></svg>
      <Link to="/" aria-label="UniMind 首页" className="landing-brand"><img src="/Unimind_logo_wide.png" alt="UniMind.ai" width="150" height="34" /></Link>
      <nav aria-label="首页导航">
        <div className="landing-nav-links"><a href="#tools">探索小宇</a><a href="#workspace">学习空间</a><Link to="/pricing">AI 加量</Link></div>
        <div className="landing-nav-actions">{!user && <Link to="/login">登录</Link>}<Link to={entry} className="landing-nav-entry">{user ? '进入学习空间' : '开始体验'}<ArrowUpRight size={16} /></Link></div>
      </nav>
    </header>

    <main>
      <section className="landing-hero landing-wrap" id="agent">
        <div className="landing-hero-copy">
          <h1 aria-label="和小宇一起，将人工智能转化为人类智慧"><span className="landing-hero-invitation">和小宇一起</span><span className="landing-hero-statement"><span data-text="将人工智能">将人工智能</span><span data-text="转化为人类智慧">转化为人类智慧</span></span></h1>
          <p className="landing-hero-description"><span>查资料、画图讲解、练习与复习，</span><span>和小宇一起把问题弄清楚。</span></p>
          <Link to={entry} className="landing-button">开始对话<ArrowUpRight size={18} /></Link>
        </div>
      </section>

      <section className="landing-agent landing-wrap" id="agent-preview" aria-label="小宇对话界面" data-landing-depth>
        <AgentShowcase />
      </section>

      <section className="landing-experience" id="tools" aria-label="探索小宇的工具"><LearningInstrument /></section>

      <section className="landing-product landing-wrap" id="workspace" aria-label="学习空间界面">
        <figure className="landing-product-main">
          <figcaption><div><span>课程与资料</span><p>课程、课件与学习进度，放在一起。</p></div><Link to="/courses">浏览课程<ArrowUpRight size={18} /></Link></figcaption>
          <div className="landing-product-stage" data-landing-depth><div className="landing-ui-frame"><img src="/screenshots/landing-workspace-desktop-demo.webp" alt="虚构学员小林的课程、课件、学习进度与历史活动" width="4800" height="3000" loading="lazy" /></div></div>
        </figure>
        <figure className="landing-product-secondary">
          <div className="landing-product-stage" data-landing-depth><div className="landing-ui-frame"><img src="/screenshots/landing-learning-records-demo.webp" alt="虚构学员的练习表现、知识掌握和历史考试记录" width="3840" height="2400" loading="lazy" /></div></div>
          <figcaption><span>学习记录</span><p>查看练习表现，<br />了解知识掌握情况。</p><Link to="/report-card">查看学习记录<ArrowUpRight size={18} /></Link></figcaption>
        </figure>
      </section>

      <section className="landing-start landing-wrap">
        <LandingCoda />
        <h2>试着问小宇一个问题。</h2>
        <Link to={entry} className="landing-button">{user ? '回到小宇' : '开始体验'}<ArrowUpRight size={19} /></Link>
      </section>

    </main>

    <footer className="landing-footer landing-wrap"><span>© {COPYRIGHT_YEAR} 北京融知高科 · UniMind.ai</span><div><a href="https://beian.miit.gov.cn/" target="_blank" rel="noopener noreferrer">京ICP备2023012726号-2</a><Link to="/terms">用户协议</Link><Link to="/privacy">隐私政策</Link></div></footer>
  </div>;
}
