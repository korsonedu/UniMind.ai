import React, { useEffect, useState } from 'react';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
  ArrowRight, Check, ChevronDown, ChevronUp,
  BrainCircuit, BarChart3,
  Globe, Clock, TrendingUp,
  Menu, X, Gauge, Cpu, Image
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { useNavigate } from 'react-router-dom';
import { useAuthStore } from '../store/useAuthStore';
import { LanguageSwitcher } from '@/components/LanguageSwitcher';
import { APP_VERSION, COPYRIGHT_YEAR, COPYRIGHT_ENTITY } from '@/constants/version';
import { useTranslation } from 'react-i18next';

/* ────────────────────────────────────────────
   Screenshot component
   ──────────────────────────────────────────── */

const Screenshot: React.FC<{
  src: string;
  alt: string;
  className?: string;
}> = ({ src, alt, className }) => {
  if (!src) {
    return (
      <div className={cn(
        'flex flex-col items-center justify-center gap-3 rounded-2xl border border-border min-h-[200px]',
        className
      )}>
        <Image className="h-8 w-8 text-unimind-text-quaternary" />
        <span className="text-xs font-medium text-unimind-text-tertiary max-w-[200px] text-center leading-relaxed">
          {alt}
        </span>
      </div>
    );
  }

  return <img src={src} alt={alt} className="w-full" />;
};

/* ────────────────────────────────────────────
   Shared — Section Header
   ──────────────────────────────────────────── */

const SectionHeader = ({
  label,
  title,
  subtitle,
  centered = true,
}: {
  label: string;
  title: string;
  subtitle?: string;
  centered?: boolean;
}) => (
  <div className={cn('mb-16', centered && 'text-center')}>
    <p className="text-[11px] font-extrabold text-primary uppercase tracking-[0.25em] mb-4">
      {label}
    </p>
    <h2 className="text-3xl md:text-4xl lg:text-5xl font-extrabold tracking-tight text-foreground leading-[1.12]">
      {title}
    </h2>
    {subtitle && (
      <p className="mt-5 text-[15px] md:text-base text-muted-foreground max-w-2xl mx-auto font-medium leading-relaxed">
        {subtitle}
      </p>
    )}
  </div>
);

/* ────────────────────────────────────────────
   Navigation
   ──────────────────────────────────────────── */

const Nav: React.FC<{ token: string | null }> = ({ token }) => {
  const { t } = useTranslation('landing');
  const [open, setOpen] = useState(false);
  const [scrolled, setScrolled] = useState(false);
  const navigate = useNavigate();

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 20);
    window.addEventListener('scroll', onScroll, { passive: true });
    return () => window.removeEventListener('scroll', onScroll);
  }, []);

  const scrollTo = (href: string) => {
    setOpen(false);
    document.querySelector(href)?.scrollIntoView({ behavior: 'smooth' });
  };

  const navItems = [
    { label: t('nav.features'), href: '#features' },
    { label: t('nav.subjects'), href: '#subjects' },
    { label: t('nav.pricing'), href: '#pricing' },
    { label: t('nav.faq'), href: '#faq' },
  ];

  return (
    <nav className={cn(
      'fixed top-0 left-0 right-0 z-[100] transition-all duration-300',
      scrolled
        ? 'bg-white/80 backdrop-blur-xl border-b border-border/60'
        : 'bg-transparent'
    )}>
      <div className="max-w-6xl mx-auto px-6 h-14 flex items-center justify-between">
        <button
          onClick={() => window.scrollTo({ top: 0, behavior: 'smooth' })}
          className="flex items-center gap-2"
        >
          <img src="/Unimind_logo.png" alt="UniMind" className="h-7 w-7 rounded-lg object-contain" />
          <span className="font-extrabold text-base text-foreground tracking-tight">UniMind</span>
          <span className="text-[11px] font-bold text-unimind-text-tertiary hidden sm:inline">.ai</span>
        </button>

        <div className="hidden md:flex items-center gap-7">
          {navItems.map(item => (
            <button
              key={item.href}
              onClick={() => scrollTo(item.href)}
              className="text-[13px] font-medium text-muted-foreground hover:text-foreground transition-colors"
            >
              {item.label}
            </button>
          ))}
        </div>

        <div className="hidden md:flex items-center gap-3">
          <LanguageSwitcher variant="full" />
          {token ? (
            <Button variant="apple" size="sm" onClick={() => navigate('/courses')}>{t('nav.enterConsole')}</Button>
          ) : (
            <>
              <button
                className="text-[13px] font-medium text-muted-foreground hover:text-foreground transition-colors"
                onClick={() => navigate('/login')}
              >
                {t('nav.login')}
              </button>
              <Button variant="apple" size="sm" onClick={() => navigate('/register')}>
                {t('nav.freeTrial')}
              </Button>
            </>
          )}
        </div>

        <button className="md:hidden p-2 text-foreground" onClick={() => setOpen(!open)}>
          {open ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
        </button>
      </div>

      {open && (
        <div className="md:hidden bg-white border-b border-border/60 px-6 pb-6 space-y-3">
          {navItems.map(item => (
            <button
              key={item.href}
              onClick={() => scrollTo(item.href)}
              className="block w-full text-left py-3 text-base font-medium text-muted-foreground hover:text-foreground"
            >
              {item.label}
            </button>
          ))}
          <div className="flex justify-center">
            <LanguageSwitcher variant="full" />
          </div>
          <div className="pt-3 border-t border-border/60 flex gap-3">
            {token ? (
              <Button className="w-full" variant="apple" onClick={() => { setOpen(false); navigate('/courses'); }}>
                {t('nav.enterConsole')}
              </Button>
            ) : (
              <>
                <Button className="flex-1" variant="outline" onClick={() => { setOpen(false); navigate('/login'); }}>
                  {t('nav.login')}
                </Button>
                <Button className="flex-1" variant="apple" onClick={() => { setOpen(false); navigate('/register'); }}>
                  {t('nav.freeTrial')}
                </Button>
              </>
            )}
          </div>
        </div>
      )}
    </nav>
  );
};

/* ────────────────────────────────────────────
   Hero
   ──────────────────────────────────────────── */

const Hero: React.FC = () => {
  const { t } = useTranslation('landing');
  const navigate = useNavigate();

  return (
    <section className="min-h-[95vh] flex flex-col items-center justify-center pt-20 pb-12 px-6">
      <div className="max-w-4xl mx-auto w-full text-center space-y-7">
        <div className="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-full bg-primary/5 border border-primary/10">
          <span className="relative flex h-1.5 w-1.5">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-primary opacity-60" />
            <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-primary" />
          </span>
          <span className="text-[11px] font-extrabold text-primary uppercase tracking-[0.15em]">
            {t('hero.badge')}
          </span>
        </div>

        <h1 className="text-4xl md:text-6xl lg:text-[68px] font-extrabold tracking-tightest text-foreground leading-[1.06]">
          {t('hero.titleLine1')}
          <br />
          <span className="text-primary">
            {t('hero.titleLine2')}
          </span>
        </h1>

        <p className="text-base md:text-lg text-muted-foreground max-w-2xl mx-auto font-medium leading-relaxed">
          {t('hero.subtitle')}
        </p>

        <div className="flex flex-col sm:flex-row items-center justify-center gap-3 pt-4">
          <Button
            variant="apple"
            size="lg"
            className="h-11 px-7 text-sm font-extrabold rounded-xl"
            onClick={() => navigate('/register')}
          >
            {t('hero.cta')}
            <ArrowRight className="ml-1.5 h-4 w-4" />
          </Button>
          <Button
            variant="apple-outline"
            size="lg"
            className="h-11 px-7 text-sm font-bold rounded-xl"
            onClick={() => document.querySelector('#features')?.scrollIntoView({ behavior: 'smooth' })}
          >
            {t('hero.secondary')}
            <ChevronDown className="ml-1 h-4 w-4" />
          </Button>
        </div>

        <p className="text-xs text-unimind-text-quaternary font-medium">
          {t('hero.footnote')}
        </p>

        {/* Hero dashboard preview */}
        <div className="max-w-4xl mx-auto pt-10 reveal">
          <Screenshot
            src="/screenshots/hero-dashboard.png"
            alt="Hero dashboard preview"
            className="w-full"
          />
        </div>
      </div>
    </section>
  );
};

/* ────────────────────────────────────────────
   Stats Bar
   ──────────────────────────────────────────── */

const StatsBar: React.FC = () => {
  const { t } = useTranslation('landing');
  const stats = t('stats', { returnObjects: true }) as Array<{ label: string; value: string; desc: string }>;
  const values = ['10+', '50,000+', '50+', '50×'];

  return (
    <section className="py-14 border-y border-border/60 bg-white">
      <div className="max-w-5xl mx-auto px-6 reveal">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-8 md:gap-12">
          {stats.map((item, i) => (
            <div key={item.label} className="text-center space-y-1">
              <p className="text-[10px] font-extrabold text-unimind-text-quaternary uppercase tracking-[0.25em]">{item.label}</p>
              <p className="text-3xl md:text-4xl font-extrabold text-foreground tracking-tightest">{values[i]}</p>
              <p className="text-[11px] font-medium text-unimind-text-tertiary">{item.desc}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
};

/* ────────────────────────────────────────────
   Pain Points
   ──────────────────────────────────────────── */

const PAIN_ICONS = [Clock, BrainCircuit, TrendingUp];

const PainPoints: React.FC = () => {
  const { t } = useTranslation('landing');
  const items = t('pain.items', { returnObjects: true }) as Array<{ title: string; desc: string }>;

  return (
    <section className="py-24 md:py-32 bg-white">
      <div className="max-w-6xl mx-auto px-6 reveal">
        <SectionHeader
          label={t('pain.label')}
          title={t('pain.title')}
          subtitle={t('pain.subtitle')}
        />
        <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
          {items.map((item, i) => (
            <Card
              key={item.title}
              variant="apple"
              className={cn('p-8 space-y-4 group cursor-default reveal', `reveal-delay-${i + 1}`)}
            >
              <div className="h-11 w-11 rounded-2xl bg-destructive/6 flex items-center justify-center">
                {React.createElement(PAIN_ICONS[i], { className: 'h-5 w-5 text-destructive' })}
              </div>
              <h3 className="font-extrabold text-lg text-foreground tracking-tight">{item.title}</h3>
              <p className="text-[14px] text-muted-foreground leading-relaxed font-medium">{item.desc}</p>
            </Card>
          ))}
        </div>
      </div>
    </section>
  );
};

/* ────────────────────────────────────────────
   Features
   ──────────────────────────────────────────── */

const FEATURE_ICONS = [Cpu, Gauge, BarChart3];

const Features: React.FC = () => {
  const { t } = useTranslation('landing');
  const items = t('features.items', { returnObjects: true }) as Array<{
    title: string; subtitle: string; desc: string; points: string[]; screenshotAlt: string;
  }>;
  const screenshots = ['/screenshots/ai-generate.png', '/screenshots/memorix-review.png', '/screenshots/analytics-dashboard.png'];

  return (
    <section id="features" className="py-24 md:py-32 bg-unimind-bg-secondary border-y border-border/60">
      <div className="max-w-6xl mx-auto px-6 reveal">
        <SectionHeader
          label={t('features.label')}
          title={t('features.title')}
          subtitle={t('features.subtitle')}
        />

        <div className="space-y-20 md:space-y-28">
          {items.map((item, i) => (
            <div
              key={item.title}
              className={cn(
                'flex flex-col md:flex-row gap-12 md:gap-16 items-center reveal',
                `reveal-delay-${i + 1}`,
                i % 2 === 1 ? 'md:flex-row-reverse' : ''
              )}
            >
              <div className="flex-1 w-full">
                <Screenshot
                  src={screenshots[i]}
                  alt={item.screenshotAlt}
                  className="w-full"
                />
              </div>

              <div className="flex-1 space-y-5">
                <div className="h-10 w-10 rounded-2xl bg-primary/8 flex items-center justify-center">
                  {React.createElement(FEATURE_ICONS[i], { className: 'h-5 w-5 text-primary' })}
                </div>
                <h3 className="text-2xl md:text-3xl font-extrabold text-foreground tracking-tight">{item.title}</h3>
                <p className="text-sm font-bold text-primary">{item.subtitle}</p>
                <p className="text-[15px] text-muted-foreground leading-relaxed font-medium">{item.desc}</p>
                <ul className="space-y-2.5">
                  {item.points.map(p => (
                    <li key={p} className="flex items-start gap-3 text-sm font-medium text-foreground/80">
                      <Check className="h-4 w-4 text-unimind-green shrink-0 mt-0.5" />
                      {p}
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
};

/* ────────────────────────────────────────────
   How It Works
   ──────────────────────────────────────────── */

const STEP_ICONS = [Globe, Cpu, BarChart3];

const HowItWorks: React.FC = () => {
  const { t } = useTranslation('landing');
  const steps = t('how.steps', { returnObjects: true }) as Array<{ title: string; desc: string }>;

  return (
    <section className="py-24 md:py-32 bg-white">
      <div className="max-w-6xl mx-auto px-6 reveal">
        <SectionHeader
          label={t('how.label')}
          title={t('how.title')}
          subtitle={t('how.subtitle')}
        />

        <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
          {steps.map((step, i) => (
            <Card key={step.title} variant="apple" className={cn('p-8 space-y-5 relative overflow-hidden group cursor-default reveal', `reveal-delay-${i + 1}`)}>
              <div className="absolute -top-5 -right-5 text-[100px] font-extrabold text-unimind-bg-secondary leading-none select-none group-hover:text-[#E8E8ED] transition-colors">
                {i + 1}
              </div>
              <div className="relative z-10 space-y-4">
                <div className="h-11 w-11 rounded-2xl bg-primary/8 flex items-center justify-center">
                  {React.createElement(STEP_ICONS[i], { className: 'h-5 w-5 text-primary' })}
                </div>
                <h3 className="font-extrabold text-lg text-foreground tracking-tight">{step.title}</h3>
                <p className="text-[14px] text-muted-foreground leading-relaxed font-medium">{step.desc}</p>
              </div>
            </Card>
          ))}
        </div>
      </div>
    </section>
  );
};

/* ────────────────────────────────────────────
   Subjects
   ──────────────────────────────────────────── */

const Subjects: React.FC = () => {
  const { t } = useTranslation('landing');
  const categories = t('subjects.categories', { returnObjects: true }) as Array<{ name: string; tags: string[] }>;

  return (
    <section id="subjects" className="py-24 md:py-32 bg-unimind-bg-secondary border-y border-border/60">
      <div className="max-w-6xl mx-auto px-6 reveal">
        <SectionHeader
          label={t('subjects.label')}
          title={t('subjects.title')}
          subtitle={t('subjects.subtitle')}
        />

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {categories.map((cat, i) => (
            <Card key={cat.name} variant="apple" className={cn('p-6 space-y-4 reveal', `reveal-delay-${i + 1}`)}>
              <h3 className="font-extrabold text-sm text-foreground tracking-tight">{cat.name}</h3>
              <div className="flex flex-wrap gap-1.5">
                {cat.tags.map(tag => (
                  <span key={tag} className="text-[11px] font-bold px-2.5 py-1 rounded-lg bg-unimind-bg-secondary text-muted-foreground">
                    {tag}
                  </span>
                ))}
              </div>
            </Card>
          ))}
        </div>

        <p className="text-center mt-10 text-sm text-unimind-text-quaternary font-medium">
          {t('subjects.footer')}
        </p>
      </div>
    </section>
  );
};

/* ────────────────────────────────────────────
   Pricing
   ──────────────────────────────────────────── */

const Pricing: React.FC = () => {
  const { t } = useTranslation('landing');
  const navigate = useNavigate();
  const [annual, setAnnual] = useState(true);

  const plans = t('pricing.plans', { returnObjects: true }) as Array<{
    label: string; desc: string; cta: string;
  }>;
  const rows = t('pricing.rows', { returnObjects: true }) as string[][];
  const prices = [
    { monthly: '¥0', yearly: '¥0' },
    { monthly: '¥299', yearly: '¥199' },
    { monthly: '¥1,299', yearly: '¥999' },
    { monthly: '¥3,999', yearly: '¥2,999' },
  ];
  const popularIdx = 2; // Plus

  return (
    <section id="pricing" className="py-24 md:py-32 bg-white">
      <div className="max-w-6xl mx-auto px-6 reveal">
        <SectionHeader
          label={t('pricing.label')}
          title={t('pricing.title')}
          subtitle={t('pricing.subtitle')}
        />

        <div className="flex items-center justify-center gap-3 mb-12">
          <span className={cn('text-sm font-bold', !annual ? 'text-foreground' : 'text-unimind-text-quaternary')}>{t('pricing.monthly')}</span>
          <button
            onClick={() => setAnnual(!annual)}
            className={cn(
              'w-11 h-6 rounded-full transition-colors relative',
              annual ? 'bg-primary' : 'bg-unimind-text-quaternary'
            )}
          >
            <div className={cn(
              'absolute top-0.5 h-5 w-5 rounded-full bg-white shadow transition-transform',
              annual ? 'left-[22px]' : 'left-0.5'
            )} />
          </button>
          <span className={cn('text-sm font-bold flex items-center gap-1.5', annual ? 'text-foreground' : 'text-unimind-text-quaternary')}>
            {t('pricing.annually')}
            <Badge variant="apple-green" className="text-[10px]">{t('pricing.saveBadge')}</Badge>
          </span>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 items-start">
          {plans.map((plan, pi) => {
            const price = annual && prices[pi].yearly !== '¥0' ? prices[pi].yearly : prices[pi].monthly;
            const isPopular = pi === popularIdx;
            return (
              <Card
                key={plan.label}
                variant="apple"
                className={cn(
                  'p-6 flex flex-col space-y-5 reveal',
                  `reveal-delay-${pi + 1}`,
                  isPopular && 'ring-2 ring-primary ring-offset-2'
                )}
              >
                <div className="space-y-1">
                  <div className="flex items-center gap-2">
                    <h3 className="font-extrabold text-base text-foreground">{plan.label}</h3>
                    {isPopular && (
                      <Badge variant="apple-blue" className="text-[10px] font-extrabold">{t('pricing.popularBadge')}</Badge>
                    )}
                  </div>
                  <p className="text-[12px] text-unimind-text-tertiary font-medium">{plan.desc}</p>
                </div>

                <div>
                  <span className="text-3xl font-extrabold text-foreground tracking-tightest">{price}</span>
                  {prices[pi].monthly !== '¥0' && <span className="text-sm font-bold text-unimind-text-tertiary">{t('pricing.perMonth')}</span>}
                  {annual && prices[pi].yearly !== '¥0' && (
                    <p className="text-[11px] font-medium text-unimind-text-quaternary mt-1">
                      {t('pricing.annualTotal')}{parseInt(prices[pi].yearly.replace('¥', '')) * 12}
                    </p>
                  )}
                </div>

                <Button
                  variant={isPopular ? 'apple' : 'apple-outline'}
                  className="w-full h-10 rounded-xl text-sm font-extrabold"
                  onClick={() => {
                    if (pi === 3) {
                      document.querySelector('#cta')?.scrollIntoView({ behavior: 'smooth' });
                    } else {
                      navigate('/register');
                    }
                  }}
                >
                  {plan.cta}
                </Button>

                <ul className="space-y-1.5 flex-1">
                  {rows.map((row, ri) => {
                    const text = row[pi];
                    const has = text !== '—';
                    return (
                      <li key={ri} className={cn(
                        'flex items-start gap-2 text-[12px] font-medium',
                        has ? 'text-foreground/70' : 'text-unimind-text-quaternary'
                      )}>
                        {has
                          ? <Check className="h-3.5 w-3.5 text-unimind-green shrink-0 mt-0.5" />
                          : <span className="h-3.5 w-3.5 shrink-0 mt-0.5" />
                        }
                        {has ? text : '—'}
                      </li>
                    );
                  })}
                </ul>
              </Card>
            );
          })}
        </div>

        <p className="text-center mt-8 text-xs text-unimind-text-quaternary font-medium">
          {t('pricing.footer')}
        </p>
      </div>
    </section>
  );
};

/* ────────────────────────────────────────────
   FAQ
   ──────────────────────────────────────────── */

const FAQ: React.FC = () => {
  const { t } = useTranslation('landing');
  const [openIdx, setOpenIdx] = useState<number | null>(null);
  const items = t('faq.items', { returnObjects: true }) as Array<{ q: string; a: string }>;

  return (
    <section id="faq" className="py-24 md:py-32 bg-unimind-bg-secondary border-y border-border/60">
      <div className="max-w-3xl mx-auto px-6 reveal">
        <SectionHeader label={t('faq.label')} title={t('faq.title')} />
        <div className="space-y-2">
          {items.map((faq, i) => (
            <Card key={i} variant="apple" className="overflow-hidden transition-all duration-200">
              <button
                onClick={() => setOpenIdx(openIdx === i ? null : i)}
                className="w-full px-5 py-4 flex items-center justify-between text-left gap-4"
              >
                <span className="font-extrabold text-[14px] text-foreground">{faq.q}</span>
                {openIdx === i
                  ? <ChevronUp className="h-4 w-4 text-unimind-text-quaternary shrink-0" />
                  : <ChevronDown className="h-4 w-4 text-unimind-text-quaternary shrink-0" />
                }
              </button>
              {openIdx === i && (
                <div className="px-5 pb-4">
                  <p className="text-[13px] text-muted-foreground leading-relaxed font-medium">{faq.a}</p>
                </div>
              )}
            </Card>
          ))}
        </div>
      </div>
    </section>
  );
};

/* ────────────────────────────────────────────
   Final CTA
   ──────────────────────────────────────────── */

const FinalCTA: React.FC = () => {
  const { t } = useTranslation('landing');
  const navigate = useNavigate();
  return (
    <section id="cta" className="py-24 md:py-32 bg-white">
      <div className="max-w-3xl mx-auto px-6 text-center space-y-8 reveal">
        <h2 className="text-3xl md:text-5xl font-extrabold tracking-tightest text-foreground leading-[1.12]">
          {t('cta.title')}
        </h2>
        <p className="text-base md:text-lg text-muted-foreground font-medium leading-relaxed max-w-xl mx-auto">
          {t('cta.subtitle')}
        </p>
        <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
          <Button
            variant="apple"
            size="lg"
            className="h-11 px-7 text-sm font-extrabold rounded-xl"
            onClick={() => navigate('/register')}
          >
            {t('cta.button')}
            <ArrowRight className="ml-1.5 h-4 w-4" />
          </Button>
        </div>
        <p className="text-xs text-unimind-text-quaternary font-medium">
          {t('cta.footnote')}
        </p>
      </div>
    </section>
  );
};

/* ────────────────────────────────────────────
   Footer
   ──────────────────────────────────────────── */

const Footer: React.FC = () => {
  const { t } = useTranslation('landing');

  return (
    <footer className="py-12 bg-unimind-bg-secondary border-t border-border/60">
      <div className="max-w-6xl mx-auto px-6 reveal">
        <div className="flex flex-col md:flex-row items-center justify-between gap-6">
          <div className="flex items-center gap-3">
            <img src="/Unimind_logo.png" alt="UniMind" className="h-8 w-8 rounded-lg object-contain" />
            <div className="leading-tight">
              <p className="font-extrabold text-sm text-foreground tracking-tight">UniMind.ai</p>
              <p className="text-[10px] font-bold text-unimind-text-quaternary uppercase tracking-[0.1em]">{t('footer.tagline')}</p>
            </div>
          </div>
          <div className="flex items-center gap-6">
            <a href="#features" className="text-[12px] font-medium text-unimind-text-tertiary hover:text-foreground transition-colors">{t('footer.features')}</a>
            <a href="#pricing" className="text-[12px] font-medium text-unimind-text-tertiary hover:text-foreground transition-colors">{t('footer.pricing')}</a>
            <a href="#faq" className="text-[12px] font-medium text-unimind-text-tertiary hover:text-foreground transition-colors">{t('footer.faq')}</a>
          </div>
          <p className="text-[10px] font-medium text-unimind-text-quaternary">
            © {COPYRIGHT_YEAR} {COPYRIGHT_ENTITY} · {APP_VERSION}
          </p>
        </div>
      </div>
    </footer>
  );
};

/* ────────────────────────────────────────────
   Main Landing
   ──────────────────────────────────────────── */

export const Landing: React.FC = () => {
  const { token } = useAuthStore();

  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            entry.target.classList.add('visible');
          }
        });
      },
      { threshold: 0.1 }
    );

    const timer = setTimeout(() => {
      document.querySelectorAll('.reveal').forEach((el) => observer.observe(el));
    }, 100);

    return () => {
      clearTimeout(timer);
      observer.disconnect();
    };
  }, []);

  return (
    <div className="w-full bg-white font-sans text-left overflow-x-hidden antialiased scroll-smooth">
      <Nav token={token} />
      <Hero />
      <StatsBar />
      <PainPoints />
      <Features />
      <HowItWorks />
      <Subjects />
      <Pricing />
      <FAQ />
      <FinalCTA />
      <Footer />
    </div>
  );
};
