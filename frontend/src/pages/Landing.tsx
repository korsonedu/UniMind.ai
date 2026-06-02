import React, { useEffect, useState, useRef } from 'react';
import { Button } from '@/components/ui/button';
import { ArrowRight, Menu, X, Clock, Repeat, BarChart3 } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useNavigate, Link } from 'react-router-dom';
import { useAuthStore } from '../store/useAuthStore';
import { LanguageSwitcher } from '@/components/LanguageSwitcher';
import { CocoonCanvas } from '@/components/CocoonCanvas';
import { APP_VERSION, COPYRIGHT_YEAR } from '@/constants/version';
import { useTranslation } from 'react-i18next';

/* ────────────────────────────────────────────
   Dark / light palette constants
   ──────────────────────────────────────────── */

const DARK = '#0a0a14';
const DARK2 = '#0e0e1a';
const LIGHT = '#f8f9fb';
const LIGHT2 = '#ffffff';

/* ────────────────────────────────────────────
   Scroll reveal
   ──────────────────────────────────────────── */

const useScrollReveal = () => {
  const { i18n } = useTranslation();
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
  }, [i18n.language]);
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
   Nav — adaptive dark/light
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

  // Hero is dark → transparent nav with white text; once scrolled → light bar
  const navBg = scrolled
    ? 'bg-[#0a0a14]/90 backdrop-blur-xl border-b border-white/[0.06]'
    : 'bg-transparent';
  const txtColor = 'text-white/70 hover:text-white';
  const logoColor = 'text-white';

  return (
    <nav className={cn('fixed top-0 left-0 right-0 z-[100] transition-all duration-500', navBg)}>
      <div className="max-w-6xl mx-auto px-6 h-14 flex items-center justify-between">
        <button onClick={() => window.scrollTo({ top: 0, behavior: 'smooth' })} className="flex items-center gap-2 shrink-0">
          <img src="/Unimind_logo.png" alt="UniMind" className="h-7 w-7 rounded-lg object-contain" />
          <span className={cn('font-bold text-base tracking-tight', logoColor)}>UniMind</span>
        </button>

        {/* Desktop nav links */}
        <div className="hidden md:flex items-center gap-8">
          {navItems.map(item => (
            <button
              key={item.href}
              onClick={() => scrollTo(item.href)}
              className={cn('text-[13px] font-medium transition-colors', txtColor)}
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
              className="text-white border-white/20 bg-white/10 hover:bg-white/20"
              onClick={() => navigate('/courses')}
            >
              {t('nav.enterConsole')}
            </Button>
          ) : (
            <>
              <button
                className={cn('text-[13px] font-medium transition-colors hidden sm:block', txtColor)}
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
          <button className={cn('md:hidden p-1 transition-colors', txtColor)} onClick={() => setOpen(!open)}>
            {open ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
          </button>
        </div>
      </div>

      {/* Mobile menu */}
      {open && (
        <div className="md:hidden bg-[#0a0a14]/95 backdrop-blur-xl border-b border-white/[0.06] px-6 pb-5 space-y-1">
          {navItems.map(item => (
            <button
              key={item.href}
              onClick={() => scrollTo(item.href)}
              className="block w-full text-left py-3 text-base font-medium text-white/70 hover:text-white transition-colors"
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
   Hero — dark, text only, full viewport
   ──────────────────────────────────────────── */

const Hero: React.FC = () => {
  const { t } = useTranslation('landing');
  const navigate = useNavigate();

  return (
    <section className="flex flex-col items-center justify-center min-h-screen px-6 relative overflow-hidden" style={{ background: '#000' }}>
      {/* Canvas as full background */}
      <CocoonCanvas />

      <div className="max-w-5xl mx-auto w-full text-center relative z-10 space-y-8 pt-32 pb-32 md:pt-44 md:pb-40">
        <div className="reveal space-y-6">
          {/* Promo badge */}
          <button
            onClick={() => navigate('/promo/plus')}
            className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full border border-[#5b5fef]/30 hover:border-[#5b5fef]/50 transition-all duration-300 cursor-pointer group"
            style={{ background: 'rgba(91,95,239,0.1)' }}
          >
            <span className="text-[11px] font-semibold text-[#818cf8]">首批机构专享 · Growth 方案免费开放</span>
            <ArrowRight className="h-3 w-3 text-[#818cf8] group-hover:translate-x-0.5 transition-transform" />
          </button>

          <h1 className="text-[36px] md:text-[52px] lg:text-[64px] font-bold leading-[1.1] text-white max-w-4xl mx-auto" style={{ fontFamily: '"Playfair Display", serif', letterSpacing: '-0.03em' }}>
            {t('hero.titleLine1')}
            <br />
            <span style={{ background: 'linear-gradient(135deg, #818cf8, #5b5fef, #38bdf8)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' }}>
              {t('hero.titleLine2')}
            </span>
          </h1>
          <p className="text-base md:text-lg text-white/50 max-w-xl mx-auto leading-relaxed">
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

        {/* Trust markers */}
        <p className="text-[11px] text-white/30 tracking-wide reveal reveal-delay-2">
          {t('hero.footnote')}
        </p>
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
    <section ref={ref} className="py-20 border-y border-[#e5e7eb]" style={{ background: LIGHT }}>
      <div className="max-w-5xl mx-auto px-6">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-8 md:gap-16">
          {stats.map((item, i) => (
            <div key={item.label} className="text-center space-y-2">
              <p className="text-5xl md:text-6xl font-bold tracking-tight" style={{ fontFamily: '"DM Mono", monospace', background: 'linear-gradient(135deg, #818cf8, #5b5fef, #38bdf8)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' }}>
                {displays[i]}
              </p>
              <p className="text-[12px] font-medium uppercase tracking-[0.2em] text-[#6b7280]">{item.label}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
};

/* ────────────────────────────────────────────
   Pain Points — DARK
   ──────────────────────────────────────────── */

const PainPoints: React.FC = () => {
  const { t } = useTranslation('landing');
  const pain = t('pain', { returnObjects: true }) as { label: string; title: string; subtitle: string; items: Array<{ title: string; desc: string }> };
  const icons = [Clock, Repeat, BarChart3];

  return (
    <section className="py-28 md:py-36 px-6 relative overflow-hidden" style={{ background: DARK }}>
      <div className="max-w-5xl mx-auto">
        <div className="reveal text-center mb-16">
          <p className="text-[10px] font-semibold uppercase tracking-[0.3em] text-[#818cf8] mb-4">{pain.label}</p>
          <h2 className="text-3xl md:text-5xl font-bold tracking-tighter text-white leading-tight max-w-3xl mx-auto">{pain.title}</h2>
          <p className="text-sm text-white/40 max-w-lg mx-auto mt-4">{pain.subtitle}</p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {pain.items.map((item, i) => {
            const Icon = icons[i];
            return (
              <div
                key={item.title}
                className={cn('reveal p-8 rounded-2xl border border-white/[0.06] bg-white/[0.03] hover:bg-white/[0.06] hover:border-white/[0.12] transition-all duration-300 group', `reveal-delay-${i + 1}`)}
              >
                <div className="h-11 w-11 rounded-xl flex items-center justify-center mb-5" style={{ background: 'rgba(255,59,48,0.12)' }}>
                  <Icon className="h-5 w-5 text-[#FF453A]" />
                </div>
                <h3 className="text-lg font-bold text-white mb-3 tracking-tight">{item.title}</h3>
                <p className="text-sm leading-relaxed text-white/50">{item.desc}</p>
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
};

/* ────────────────────────────────────────────
   Demo media — video with screenshot fallback
   ──────────────────────────────────────────── */

const DemoMedia: React.FC<{
  videoSrc: string;
  imgSrc: string;
  alt: string;
}> = ({ videoSrc, imgSrc, alt }) => {
  const [useVideo, setUseVideo] = useState(true);

  return (
    <div className="glow-hover rounded-2xl overflow-hidden">
      {useVideo ? (
        <video
          src={videoSrc}
          autoPlay
          loop
          muted
          playsInline
          className="w-full rounded-2xl border border-[#e5e7eb]"
          style={{ boxShadow: '0 20px 60px rgba(91,95,239,0.06), 0 4px 16px rgba(0,0,0,0.04)' }}
          onError={() => setUseVideo(false)}
        />
      ) : (
        <img
          src={imgSrc}
          alt={alt}
          className="w-full rounded-2xl border border-[#e5e7eb]"
          style={{ boxShadow: '0 20px 60px rgba(91,95,239,0.06), 0 4px 16px rgba(0,0,0,0.04)' }}
        />
      )}
    </div>
  );
};

/* ────────────────────────────────────────────
   Product Showcase — LIGHT
   ──────────────────────────────────────────── */

const Showcase: React.FC = () => {
  const { t } = useTranslation('landing');
  const items = t('features.items', { returnObjects: true }) as Array<{ title: string; subtitle: string; desc: string; points: string[]; screenshotAlt: string }>;
  const media = [
    { video: '/demos/demo-question-gen.mp4', img: '/screenshots/ai-generate.png' },
    { video: '/demos/demo-memorix.mp4', img: '/screenshots/memorix-review.png' },
    { video: '/demos/demo-knowledge.mp4', img: '/screenshots/analytics-dashboard.png' },
  ];

  const sectionRef = useRef<HTMLDivElement>(null);
  useMouseParallax(sectionRef, 0.015);

  return (
    <section id="features" ref={sectionRef} className="py-28 md:py-36 px-6 relative overflow-hidden" style={{ background: LIGHT }}>
      <div className="max-w-6xl mx-auto relative z-10">
        <div className="reveal mb-20 text-center">
          <p className="text-[10px] font-semibold uppercase tracking-[0.3em] text-[#5b5fef] mb-4">{t('features.label')}</p>
          <h2 className="text-3xl md:text-5xl font-bold tracking-tight text-[#1a1a2e]">{t('features.title')}</h2>
          <p className="text-base md:text-lg text-[#5a5a7a] max-w-xl mx-auto mt-4">{t('features.subtitle')}</p>
        </div>

        <div className="space-y-24 md:space-y-32">
          {items.map((item, i) => (
            <div
              key={item.title}
              className={cn(
                'flex flex-col gap-8 items-center reveal',
                i % 2 === 0 ? 'md:flex-row' : 'md:flex-row-reverse',
              )}
            >
              {/* Text */}
              <div className={cn('flex-1 min-w-0', `reveal-delay-${i + 1}`)}>
                <p className="text-xs font-semibold uppercase tracking-[0.2em] text-[#5b5fef] mb-3">{item.subtitle}</p>
                <h3 className="text-2xl md:text-3xl font-bold tracking-tight text-[#1a1a2e] mb-4">{item.title}</h3>
                <p className="text-sm leading-relaxed text-[#5a5a7a]">{item.desc}</p>
              </div>

              {/* Video / Screenshot */}
              <div className={cn('flex-1 min-w-0 reveal-scale', `reveal-delay-${i + 1}`)}>
                <DemoMedia
                  videoSrc={media[i].video}
                  imgSrc={media[i].img}
                  alt={item.screenshotAlt}
                />
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
};

/* ────────────────────────────────────────────
   Testimonials — DARK, infinite scroll
   ──────────────────────────────────────────── */

const Testimonials: React.FC = () => {
  const { t } = useTranslation('landing');
  const items = t('testimonials.items', { returnObjects: true }) as Array<{ name: string; role: string; quote: string }>;
  const doubled = [...items, ...items];

  return (
    <section className="py-28 md:py-36 overflow-hidden" style={{ background: DARK2 }}>
      <div className="max-w-5xl mx-auto px-6 mb-14 text-center reveal">
        <p className="text-[10px] font-semibold uppercase tracking-[0.3em] text-[#818cf8] mb-4">{t('testimonials.label')}</p>
        <h2 className="text-3xl md:text-4xl font-bold tracking-tight text-white">{t('testimonials.title')}</h2>
      </div>

      <div className="relative">
        {/* Fade edges */}
        <div className="absolute left-0 top-0 bottom-0 w-32 z-10" style={{ background: `linear-gradient(90deg, ${DARK2}, transparent)` }} />
        <div className="absolute right-0 top-0 bottom-0 w-32 z-10" style={{ background: `linear-gradient(270deg, ${DARK2}, transparent)` }} />

        <div className="flex animate-scroll-x" style={{ width: 'max-content' }}>
          {doubled.map((item, i) => (
            <div
              key={`${item.name}-${i}`}
              className="flex-shrink-0 w-[340px] mx-3 p-7 rounded-2xl border border-white/[0.06] bg-white/[0.03]"
            >
              {/* Brand-colored opening quote */}
              <p className="text-3xl font-bold leading-none mb-2" style={{ background: 'linear-gradient(135deg, #818cf8, #5b5fef)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' }}>"</p>
              <p className="text-sm leading-relaxed text-white/60 mb-5">{item.quote}</p>
              <div className="flex items-center gap-3">
                <div className="h-9 w-9 rounded-full flex items-center justify-center text-sm font-bold text-white" style={{ background: 'linear-gradient(135deg, #818cf8, #5b5fef)' }}>
                  {item.name[0]}
                </div>
                <div>
                  <p className="text-sm font-semibold text-white">{item.name}</p>
                  <p className="text-[11px] text-white/30">{item.role}</p>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
};

/* ────────────────────────────────────────────
   How It Works — LIGHT, card layout
   ──────────────────────────────────────────── */

const HowItWorks: React.FC = () => {
  const { t } = useTranslation('landing');
  const steps = t('how.steps', { returnObjects: true }) as Array<{ title: string; desc: string }>;

  return (
    <section className="py-28 md:py-36 px-6" style={{ background: LIGHT2 }}>
      <div className="max-w-4xl mx-auto">
        <div className="reveal text-center mb-20">
          <p className="text-[10px] font-semibold uppercase tracking-[0.3em] text-[#5b5fef] mb-4">{t('how.label')}</p>
          <h2 className="text-3xl md:text-5xl font-bold tracking-tight text-[#1a1a2e]">{t('how.title')}</h2>
          <p className="text-sm text-[#5a5a7a] max-w-lg mx-auto mt-4">{t('how.subtitle')}</p>
        </div>

        <div className="space-y-0">
          {steps.map((step, i) => (
            <div key={step.title} className={cn('reveal', `reveal-delay-${i + 1}`)}>
              <div className="flex items-start gap-8 py-10">
                {/* Big gradient number */}
                <span className="text-6xl md:text-7xl font-bold shrink-0 leading-none select-none" style={{ fontFamily: '"DM Mono", monospace', background: 'linear-gradient(135deg, #818cf8, #5b5fef, #38bdf8)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' }}>
                  {String(i + 1).padStart(2, '0')}
                </span>
                <div className="pt-1">
                  <h3 className="text-xl font-bold text-[#1a1a2e] mb-2">{step.title}</h3>
                  <p className="text-sm leading-relaxed text-[#5a5a7a] max-w-md">{step.desc}</p>
                </div>
              </div>
              {/* Dashed connector line */}
              {i < steps.length - 1 && (
                <div className="ml-10 md:ml-12 border-l border-dashed border-[#d1d5db] h-0" />
              )}
            </div>
          ))}
        </div>
      </div>
    </section>
  );
};

/* ────────────────────────────────────────────
   Subjects — DARK, tag cloud
   ──────────────────────────────────────────── */

const Subjects: React.FC = () => {
  const { t } = useTranslation('landing');
  const categories = t('subjects.categories', { returnObjects: true }) as Array<{ name: string; tags: string[] }>;
  const allTags = categories.flatMap(cat => cat.tags);

  return (
    <section id="subjects" className="py-28 md:py-36 px-6" style={{ background: DARK }}>
      <div className="max-w-4xl mx-auto text-center">
        <div className="reveal space-y-6">
          <h2 className="text-3xl md:text-5xl font-bold tracking-tight text-white">{t('subjects.title')}</h2>
          <p className="text-sm text-white/40 max-w-lg mx-auto">{t('subjects.subtitle')}</p>
        </div>
        <div className="mt-14 flex flex-wrap justify-center gap-2.5 reveal reveal-delay-1">
          {allTags.map((tag) => (
            <span
              key={tag}
              className="text-[13px] font-medium px-4 py-2 rounded-full border border-white/[0.08] text-white/50 hover:text-[#818cf8] hover:border-[#5b5fef] hover:bg-[#5b5fef]/[0.08] transition-all duration-300 cursor-default"
            >
              {tag}
            </span>
          ))}
        </div>
        <p className="mt-8 text-xs text-white/20 reveal reveal-delay-2">{t('subjects.footer')}</p>
      </div>
    </section>
  );
};

/* ────────────────────────────────────────────
   Final CTA — DARK
   ──────────────────────────────────────────── */

const FinalCTA: React.FC = () => {
  const { t } = useTranslation('landing');
  const navigate = useNavigate();

  return (
    <section className="py-28 md:py-36 px-6 relative overflow-hidden" style={{ background: DARK2 }}>
      {/* Subtle radial accent */}
      <div className="absolute inset-0 pointer-events-none" style={{ background: 'radial-gradient(ellipse 50% 50% at 50% 50%, rgba(91,95,239,0.05) 0%, transparent 70%)' }} />

      <div className="max-w-3xl mx-auto text-center relative z-10 space-y-8">
        <div className="reveal space-y-5">
          <h2 className="text-4xl md:text-6xl font-bold leading-[1.08] text-white" style={{ letterSpacing: '-0.03em' }}>
            {t('cta.title')}
          </h2>
          <p className="text-base md:text-lg text-white/40 max-w-lg mx-auto">
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
            className="text-sm font-medium text-white/40 hover:text-white transition-colors"
            onClick={() => navigate('/pricing')}
          >
            {t('cta.viewPlans')}
          </button>
        </div>

        <p className="text-xs text-white/20 reveal reveal-delay-2">{t('cta.footnote')}</p>
      </div>
    </section>
  );
};

/* ────────────────────────────────────────────
   Footer — LIGHT
   ──────────────────────────────────────────── */

const Footer: React.FC = () => {
  const { t } = useTranslation('landing');
  const navigate = useNavigate();

  return (
    <footer className="py-12 border-t border-[#e5e7eb]" style={{ background: LIGHT }}>
      <div className="max-w-6xl mx-auto px-6">
        <div className="flex flex-col md:flex-row items-start justify-between gap-8 mb-8">
          <div className="space-y-3">
            <div className="flex items-center gap-3">
              <img src="/Unimind_logo.png" alt="UniMind" className="h-7 w-7 rounded-lg object-contain" />
              <span className="font-bold text-sm text-[#1a1a2e] tracking-tight">UniMind.ai</span>
            </div>
            <p className="text-[12px] text-[#9ca3af]">{t('footer.tagline')}</p>
          </div>
          <div className="flex items-center gap-8">
            <button onClick={() => document.querySelector('#features')?.scrollIntoView({ behavior: 'smooth' })} className="text-[12px] font-medium text-[#5a5a7a] hover:text-[#1a1a2e] transition-colors">{t('footer.features')}</button>
            <button onClick={() => navigate('/pricing')} className="text-[12px] font-medium text-[#5a5a7a] hover:text-[#1a1a2e] transition-colors">{t('footer.pricing')}</button>
            <button onClick={() => navigate('/pricing#faq')} className="text-[12px] font-medium text-[#5a5a7a] hover:text-[#1a1a2e] transition-colors">{t('footer.faq')}</button>
          </div>
        </div>
        <div className="border-t border-[#e5e7eb] pt-6 flex flex-col md:flex-row items-center justify-between gap-4">
          <p className="text-[10px] font-medium text-[#9ca3af]">
            © {COPYRIGHT_YEAR} {t('footer.copyrightEntity')} · {APP_VERSION}
          </p>
          <div className="flex items-center gap-4">
            <Link to="/terms" className="text-[10px] font-medium text-[#9ca3af] hover:text-[#5a5a7a] transition-colors">{t('footer.terms')}</Link>
            <Link to="/privacy" className="text-[10px] font-medium text-[#9ca3af] hover:text-[#5a5a7a] transition-colors">{t('footer.privacy')}</Link>
          </div>
        </div>
      </div>
    </footer>
  );
};

/* ────────────────────────────────────────────
   Main — alternating dark / light rhythm
   ──────────────────────────────────────────── */

export const Landing: React.FC = () => {
  const { token } = useAuthStore();
  useScrollReveal();

  return (
    <div className="w-full min-h-screen font-sans text-left overflow-x-hidden antialiased scroll-smooth" style={{ background: DARK }}>
      <Nav token={token} />
      <Hero />
      <StatsBar />            {/* light */}
      <PainPoints />          {/* dark */}
      <Showcase />            {/* light */}
      <Testimonials />        {/* dark */}
      <HowItWorks />          {/* light */}
      <Subjects />            {/* dark */}
      <FinalCTA />            {/* dark */}
      <Footer />              {/* light */}
    </div>
  );
};
