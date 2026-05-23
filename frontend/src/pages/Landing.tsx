import React, { useEffect, useState, useRef } from 'react';
import { Button } from '@/components/ui/button';
import { ArrowRight, Menu, X } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useNavigate } from 'react-router-dom';
import { useAuthStore } from '../store/useAuthStore';
import { LanguageSwitcher } from '@/components/LanguageSwitcher';
import { APP_VERSION, COPYRIGHT_YEAR, COPYRIGHT_ENTITY } from '@/constants/version';
import { useTranslation } from 'react-i18next';

/* ────────────────────────────────────────────
   Scroll reveal
   ──────────────────────────────────────────── */

const useScrollReveal = () => {
  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) entry.target.classList.add('visible');
        });
      },
      { threshold: 0.15, rootMargin: '0px 0px -60px 0px' }
    );
    const timer = setTimeout(() => {
      document.querySelectorAll('.reveal, .reveal-left, .reveal-right, .reveal-scale').forEach((el) => observer.observe(el));
    }, 100);
    return () => { clearTimeout(timer); observer.disconnect(); };
  }, []);
};

/* ────────────────────────────────────────────
   Mouse parallax hook
   ──────────────────────────────────────────── */

const useMouseParallax = (ref: React.RefObject<HTMLElement | null>, speed: number = 0.03) => {
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const onMove = (e: MouseEvent) => {
      const rect = el.getBoundingClientRect();
      const x = (e.clientX - rect.left) / rect.width - 0.5;
      const y = (e.clientY - rect.top) / rect.height - 0.5;
      el.style.transform = `translate(${x * speed * 100}px, ${y * speed * 100}px)`;
    };
    window.addEventListener('mousemove', onMove, { passive: true });
    return () => window.removeEventListener('mousemove', onMove);
  }, [ref, speed]);
};

/* ────────────────────────────────────────────
   Animated counter
   ──────────────────────────────────────────── */

const useCountUp = (target: number, duration: number, shouldStart: boolean) => {
  const [count, setCount] = useState(0);
  const raf = useRef<number>(0);
  useEffect(() => {
    if (!shouldStart) return;
    let start = 0;
    const step = (timestamp: number) => {
      if (!start) start = timestamp;
      const progress = Math.min((timestamp - start) / duration, 1);
      setCount(Math.floor((1 - Math.pow(1 - progress, 3)) * target));
      if (progress < 1) raf.current = requestAnimationFrame(step);
    };
    raf.current = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf.current);
  }, [target, duration, shouldStart]);
  return count;
};

/* ────────────────────────────────────────────
   Nav — minimal
   ──────────────────────────────────────────── */

const Nav: React.FC<{ token: string | null }> = ({ token }) => {
  const { t } = useTranslation('landing');
  const [open, setOpen] = useState(false);
  const [scrolled, setScrolled] = useState(false);
  const navigate = useNavigate();

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 40);
    window.addEventListener('scroll', onScroll, { passive: true });
    return () => window.removeEventListener('scroll', onScroll);
  }, []);

  const scrollTo = (href: string) => {
    setOpen(false);
    if (href.startsWith('/')) {
      navigate(href);
    } else {
      document.querySelector(href)?.scrollIntoView({ behavior: 'smooth' });
    }
  };

  const navItems = [
    { label: t('nav.features'), href: '#features' },
    { label: t('nav.subjects'), href: '#subjects' },
    { label: t('nav.pricing'), href: '/pricing' },
  ];

  return (
    <nav className={cn(
      'fixed top-0 left-0 right-0 z-[100] transition-all duration-500',
      scrolled ? 'bg-[#0a0a0d]/80 backdrop-blur-xl border-b border-white/[0.06]' : 'bg-transparent'
    )}>
      <div className="max-w-6xl mx-auto px-6 h-14 flex items-center justify-between">
        <button onClick={() => window.scrollTo({ top: 0, behavior: 'smooth' })} className="flex items-center gap-2 shrink-0">
          <img src="/Unimind_logo.png" alt="UniMind" className="h-7 w-7 rounded-lg object-contain" />
          <span className="font-bold text-base tracking-tight text-white">UniMind</span>
        </button>

        {/* Desktop nav links */}
        <div className="hidden md:flex items-center gap-8">
          {navItems.map(item => (
            <button
              key={item.href}
              onClick={() => scrollTo(item.href)}
              className="text-[13px] font-medium text-white/50 hover:text-white transition-colors"
            >
              {item.label}
            </button>
          ))}
        </div>

        <div className="flex items-center gap-3">
          <LanguageSwitcher variant="full" />
          {token ? (
            <Button
              size="sm"
              className="text-white border-white/20 bg-transparent hover:bg-white/10"
              onClick={() => navigate('/courses')}
            >
              {t('nav.enterConsole')}
            </Button>
          ) : (
            <>
              <button
                className="text-[13px] font-medium text-white/60 hover:text-white transition-colors hidden sm:block"
                onClick={() => navigate('/login')}
              >
                {t('nav.login')}
              </button>
              <Button
                size="sm"
                className="text-white border-0 font-semibold"
                style={{ background: '#5b5fef' }}
                onClick={() => navigate('/register')}
              >
                {t('nav.freeTrial')}
              </Button>
            </>
          )}
          <button className="md:hidden p-1 text-white/60 hover:text-white" onClick={() => setOpen(!open)}>
            {open ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
          </button>
        </div>
      </div>

      {/* Mobile menu */}
      {open && (
        <div className="md:hidden bg-[#0a0a0d]/95 backdrop-blur-xl border-b border-white/[0.06] px-6 pb-5 space-y-1">
          {navItems.map(item => (
            <button
              key={item.href}
              onClick={() => scrollTo(item.href)}
              className="block w-full text-left py-3 text-base font-medium text-white/50 hover:text-white transition-colors"
            >
              {item.label}
            </button>
          ))}
        </div>
      )}
    </nav>
  );
};

/* ────────────────────────────────────────────
   Hero — one line, one image, one CTA
   ──────────────────────────────────────────── */

const Hero: React.FC = () => {
  const { t } = useTranslation('landing');
  const navigate = useNavigate();
  const imgRef = useRef<HTMLDivElement>(null);
  useMouseParallax(imgRef, 0.02);

  return (
    <section className="min-h-screen flex flex-col items-center justify-center pt-20 pb-12 px-6 relative overflow-hidden">
      {/* Ambient orbs */}
      <div className="absolute inset-0 pointer-events-none overflow-hidden">
        <div className="absolute top-1/4 -left-32 w-[500px] h-[500px] rounded-full blur-[120px] opacity-[0.07]" style={{ background: '#5b5fef' }} />
        <div className="absolute bottom-1/4 -right-32 w-[400px] h-[400px] rounded-full blur-[100px] opacity-[0.05]" style={{ background: '#38bdf8' }} />
      </div>

      <div className="max-w-4xl mx-auto w-full text-center relative z-10 space-y-8">
        <div className="reveal space-y-5">
          <h1 className="text-[38px] md:text-[56px] lg:text-[72px] font-bold leading-[1.05] tracking-tight text-white max-w-3xl mx-auto">
            {t('hero.titleLine1')}
            <br />
            <span style={{ background: 'linear-gradient(135deg, #818cf8, #5b5fef, #38bdf8)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' }}>
              {t('hero.titleLine2')}
            </span>
          </h1>
          <p className="text-sm md:text-base text-white/40 max-w-lg mx-auto leading-relaxed">
            {t('hero.subtitle')}
          </p>
        </div>

        <div className="flex items-center justify-center gap-3 pt-2 reveal reveal-delay-2">
          <Button
            size="lg"
            className="h-12 px-8 text-sm font-bold rounded-xl text-white border-0"
            style={{ background: '#5b5fef' }}
            onClick={() => navigate('/register')}
          >
            {t('hero.cta')}
            <ArrowRight className="ml-1.5 h-4 w-4" />
          </Button>
        </div>

        {/* Product image with depth */}
        <div ref={imgRef} className="max-w-4xl mx-auto pt-8 reveal reveal-delay-3" style={{ perspective: '1000px' }}>
          <div className="relative glow-hover rounded-2xl" style={{ transform: 'rotateX(2deg)' }}>
            <img
              src="/screenshots/hero-dashboard.png"
              alt="UniMind"
              className="w-full rounded-2xl border border-white/[0.08]"
              style={{ boxShadow: '0 40px 120px rgba(91,95,239,0.12), 0 8px 24px rgba(0,0,0,0.4)' }}
            />
          </div>
        </div>
      </div>
    </section>
  );
};

/* ────────────────────────────────────────────
   Stats — big numbers, no words
   ──────────────────────────────────────────── */

const StatsBar: React.FC = () => {
  const { t } = useTranslation('landing');
  const stats = t('stats', { returnObjects: true }) as Array<{ label: string; value: string; desc: string }>;
  const [visible, setVisible] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const obs = new IntersectionObserver(([e]) => { if (e.isIntersecting) setVisible(true); }, { threshold: 0.6 });
    obs.observe(el);
    return () => obs.disconnect();
  }, []);

  const c0 = useCountUp(10, 1200, visible);
  const c1 = useCountUp(50000, 1800, visible);
  const c2 = useCountUp(50, 1200, visible);
  const c3 = useCountUp(50, 1200, visible);
  const displays = [`${c0}+`, `${(c1 / 1000).toFixed(0)}k+`, `${c2}+`, `${c3}×`];

  return (
    <section ref={ref} className="py-16 border-y border-white/[0.06]" style={{ background: 'rgba(255,255,255,0.01)' }}>
      <div className="max-w-5xl mx-auto px-6">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-8 md:gap-16">
          {stats.map((item, i) => (
            <div key={item.label} className="text-center space-y-1">
              <p className="text-4xl md:text-5xl font-bold tracking-tight text-white" style={{ fontFamily: '"DM Mono", monospace' }}>
                {displays[i]}
              </p>
              <p className="text-[11px] font-medium uppercase tracking-[0.15em] text-white/25">{item.label}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
};

/* ────────────────────────────────────────────
   Product Showcase — images with one-line labels
   ──────────────────────────────────────────── */

const Showcase: React.FC = () => {
  const { t } = useTranslation('landing');
  const items = t('features.items', { returnObjects: true }) as Array<{ title: string; subtitle: string; desc: string; points: string[]; screenshotAlt: string }>;
  const screenshots = ['/screenshots/ai-generate.png', '/screenshots/memorix-review.png', '/screenshots/analytics-dashboard.png'];

  const sectionRef = useRef<HTMLDivElement>(null);
  useMouseParallax(sectionRef, 0.015);

  return (
    <section id="features" ref={sectionRef} className="py-24 md:py-32 px-6 relative overflow-hidden">
      {/* Subtle bg orb */}
      <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[600px] rounded-full blur-[150px] opacity-[0.04] pointer-events-none" style={{ background: '#5b5fef' }} />

      <div className="max-w-6xl mx-auto relative z-10">
        <div className="reveal mb-20 text-center">
          <p className="text-[10px] font-semibold uppercase tracking-[0.3em] text-[#5b5fef] mb-4">{t('features.label')}</p>
          <h2 className="text-3xl md:text-5xl font-bold tracking-tight text-white">{t('features.title')}</h2>
        </div>

        <div className="space-y-32 md:space-y-40">
          {items.map((item, i) => (
            <div key={item.title} className={cn('flex flex-col md:flex-row gap-8 md:gap-16 items-center', i % 2 === 1 ? 'md:flex-row-reverse' : '')}>
              {/* Image — the star */}
              <div className={cn('flex-1 w-full', i % 2 === 0 ? 'reveal-right' : 'reveal-left', `reveal-delay-${i + 1}`)}>
                <div className="glow-hover rounded-2xl overflow-hidden">
                  <img
                    src={screenshots[i]}
                    alt={item.screenshotAlt}
                    className="w-full rounded-2xl border border-white/[0.06]"
                    style={{ boxShadow: '0 24px 80px rgba(0,0,0,0.5)' }}
                  />
                </div>
              </div>

              {/* Label — minimal */}
              <div className={cn('flex-1 space-y-4 text-center md:text-left', i % 2 === 0 ? 'reveal-left' : 'reveal-right', `reveal-delay-${i + 1}`)}>
                <p className="text-xs font-semibold uppercase tracking-[0.2em] text-[#5b5fef]">{item.subtitle}</p>
                <h3 className="text-2xl md:text-3xl font-bold tracking-tight text-white">{item.title}</h3>
                <p className="text-sm leading-relaxed text-white/35 max-w-sm mx-auto md:mx-0">{item.desc}</p>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
};

/* ────────────────────────────────────────────
   How It Works — visual flow
   ──────────────────────────────────────────── */

const HowItWorks: React.FC = () => {
  const { t } = useTranslation('landing');
  const steps = t('how.steps', { returnObjects: true }) as Array<{ title: string; desc: string }>;

  return (
    <section className="py-24 md:py-32 px-6" style={{ background: 'rgba(255,255,255,0.015)' }}>
      <div className="max-w-5xl mx-auto">
        <div className="reveal text-center mb-20">
          <h2 className="text-3xl md:text-5xl font-bold tracking-tight text-white">{t('how.title')}</h2>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-1 md:gap-0">
          {steps.map((step, i) => (
            <div key={step.title} className={cn('relative p-8 text-center group reveal-scale', `reveal-delay-${i + 1}`)}>
              {/* Connector */}
              {i < 2 && (
                <div className="hidden md:block absolute top-12 right-0 w-full h-px" style={{ background: 'linear-gradient(90deg, rgba(255,255,255,0.08), transparent)' }} />
              )}
              <div className="h-12 w-12 rounded-2xl mx-auto mb-6 flex items-center justify-center text-lg font-bold text-white" style={{ background: 'rgba(91,95,239,0.2)' }}>
                {i + 1}
              </div>
              <h3 className="font-bold text-lg text-white mb-2">{step.title}</h3>
              <p className="text-sm leading-relaxed text-white/30">{step.desc}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
};

/* ────────────────────────────────────────────
   Subjects — tag cloud
   ──────────────────────────────────────────── */

const Subjects: React.FC = () => {
  const { t } = useTranslation('landing');
  const categories = t('subjects.categories', { returnObjects: true }) as Array<{ name: string; tags: string[] }>;
  const allTags = categories.flatMap(cat => cat.tags);

  return (
    <section id="subjects" className="py-24 md:py-32 px-6">
      <div className="max-w-4xl mx-auto text-center">
        <div className="reveal space-y-6">
          <h2 className="text-3xl md:text-5xl font-bold tracking-tight text-white">{t('subjects.title')}</h2>
          <p className="text-sm text-white/30 max-w-lg mx-auto">{t('subjects.subtitle')}</p>
        </div>
        <div className="mt-12 flex flex-wrap justify-center gap-2 reveal reveal-delay-1">
          {allTags.map((tag, i) => (
            <span
              key={tag}
              className="text-[12px] font-medium px-3 py-1.5 rounded-full border border-white/[0.08] text-white/50 hover:text-white hover:border-white/20 hover:bg-white/[0.04] transition-all duration-300 cursor-default"
            >
              {tag}
            </span>
          ))}
        </div>
        <p className="mt-6 text-xs text-white/20 reveal reveal-delay-2">{t('subjects.footer')}</p>
      </div>
    </section>
  );
};

/* ────────────────────────────────────────────
   Final CTA — one question, one button
   ──────────────────────────────────────────── */

const FinalCTA: React.FC = () => {
  const { t } = useTranslation('landing');
  const navigate = useNavigate();

  return (
    <section className="py-24 md:py-32 px-6 relative overflow-hidden">
      <div className="absolute inset-0 pointer-events-none">
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[700px] h-[400px] rounded-full blur-[150px] opacity-[0.06]" style={{ background: '#5b5fef' }} />
      </div>

      <div className="max-w-2xl mx-auto text-center relative z-10 space-y-8">
        <div className="reveal space-y-4">
          <h2 className="text-3xl md:text-5xl font-bold tracking-tight text-white leading-[1.15]">
            {t('cta.title')}
          </h2>
          <p className="text-sm md:text-base text-white/30 max-w-md mx-auto">
            {t('cta.subtitle')}
          </p>
        </div>

        <div className="flex flex-col sm:flex-row items-center justify-center gap-4 reveal reveal-delay-1">
          <Button
            size="lg"
            className="h-12 px-8 text-sm font-bold rounded-xl text-white border-0"
            style={{ background: '#5b5fef' }}
            onClick={() => navigate('/register')}
          >
            {t('cta.button')}
            <ArrowRight className="ml-1.5 h-4 w-4" />
          </Button>
          <button
            className="text-sm font-medium text-white/35 hover:text-white/70 transition-colors"
            onClick={() => navigate('/pricing')}
          >
            {t('cta.viewPlans')} →
          </button>
        </div>

        <p className="text-xs text-white/15 reveal reveal-delay-2">{t('cta.footnote')}</p>
      </div>
    </section>
  );
};

/* ────────────────────────────────────────────
   Footer — minimal
   ──────────────────────────────────────────── */

const Footer: React.FC = () => {
  const { t } = useTranslation('landing');
  const navigate = useNavigate();

  return (
    <footer className="py-10 border-t border-white/[0.06]">
      <div className="max-w-6xl mx-auto px-6 flex flex-col md:flex-row items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <img src="/Unimind_logo.png" alt="UniMind" className="h-7 w-7 rounded-lg object-contain" />
          <span className="font-bold text-sm text-white/60 tracking-tight">UniMind.ai</span>
        </div>
        <div className="flex items-center gap-6">
          <button onClick={() => navigate('/pricing')} className="text-[12px] font-medium text-white/30 hover:text-white/60 transition-colors">{t('footer.pricing')}</button>
        </div>
        <p className="text-[10px] font-medium text-white/15">
          © {COPYRIGHT_YEAR} {COPYRIGHT_ENTITY} · {APP_VERSION}
        </p>
      </div>
    </footer>
  );
};

/* ────────────────────────────────────────────
   Main
   ──────────────────────────────────────────── */

export const Landing: React.FC = () => {
  const { token } = useAuthStore();
  useScrollReveal();

  return (
    <div className="w-full min-h-screen font-sans text-left overflow-x-hidden antialiased scroll-smooth" style={{ background: '#0a0a0d' }}>
      <Nav token={token} />
      <Hero />
      <StatsBar />
      <Showcase />
      <HowItWorks />
      <Subjects />
      <FinalCTA />
      <Footer />
    </div>
  );
};
