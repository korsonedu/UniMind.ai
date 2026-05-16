import React, { useEffect, useState } from 'react';
import {
  ArrowRight, Check, ChevronDown, ChevronUp,
  BrainCircuit, BarChart3,
  Globe, Clock, TrendingUp,
  Menu, X, Gauge, Cpu, Image, Languages,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { useNavigate } from 'react-router-dom';
import { useAuthStore } from '../store/useAuthStore';
import { APP_VERSION, COPYRIGHT_YEAR, COPYRIGHT_ENTITY } from '@/constants/version';

/* ────────────────────────────────────────────
   Screenshot placeholder
   ──────────────────────────────────────────── */

const Screenshot: React.FC<{
  src: string;
  alt: string;
  className?: string;
}> = ({ src, alt, className }) => {
  if (!src) {
    return (
      <div className={cn(
        'flex flex-col items-center justify-center gap-3 rounded-2xl border border-[#E2E8F0] bg-[#F8FAFC] min-h-[200px]',
        className
      )}>
        <Image className="h-8 w-8 text-[#CBD5E1]" />
        <span className="text-xs font-medium text-[#94A3B8] max-w-[200px] text-center leading-relaxed">
          {alt}
        </span>
      </div>
    );
  }
  return <img src={src} alt={alt} className={cn('rounded-2xl border border-[#E2E8F0] shadow-lg', className)} />;
};

/* ────────────────────────────────────────────
   Section Header
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
    <span className="inline-block text-xs font-semibold text-[#2563EB] uppercase tracking-[0.2em] mb-4 bg-[#2563EB]/6 px-3 py-1 rounded-full">
      {label}
    </span>
    <h2 className="text-3xl md:text-4xl lg:text-5xl font-bold tracking-tight text-[#0F1729] leading-[1.12]">
      {title}
    </h2>
    {subtitle && (
      <p className="mt-5 text-base text-[#475569] max-w-2xl mx-auto leading-relaxed">
        {subtitle}
      </p>
    )}
  </div>
);

/* ────────────────────────────────────────────
   Navigation
   ──────────────────────────────────────────── */

const Nav: React.FC<{ token: string | null }> = ({ token }) => {
  const [open, setOpen] = useState(false);
  const [scrolled, setScrolled] = useState(false);
  const navigate = useNavigate();
  const NAV_ITEMS = [
    { label: 'Features', href: '#features' },
    { label: 'Subjects', href: '#subjects' },
    { label: 'Pricing', href: '#pricing' },
    { label: 'FAQ', href: '#faq' },
  ];

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 20);
    window.addEventListener('scroll', onScroll, { passive: true });
    return () => window.removeEventListener('scroll', onScroll);
  }, []);

  const scrollTo = (href: string) => {
    setOpen(false);
    document.querySelector(href)?.scrollIntoView({ behavior: 'smooth' });
  };

  return (
    <nav className={cn(
      'fixed top-0 left-0 right-0 z-[100] transition-all duration-300',
      scrolled
        ? 'bg-white/90 backdrop-blur-xl border-b border-[#E2E8F0]/60 shadow-sm'
        : 'bg-transparent'
    )}>
      <div className="max-w-6xl mx-auto px-6 h-16 flex items-center justify-between">
        <button
          onClick={() => window.scrollTo({ top: 0, behavior: 'smooth' })}
          className="flex items-center gap-2"
        >
          <img src="/Unimind_logo.png" alt="UniMind" className="h-8 w-auto" />
        </button>

        <div className="hidden md:flex items-center gap-8">
          {NAV_ITEMS.map(item => (
            <button
              key={item.href}
              onClick={() => scrollTo(item.href)}
              className="text-sm font-medium text-[#475569] hover:text-[#0F1729] transition-colors"
            >
              {item.label}
            </button>
          ))}
        </div>

        <div className="hidden md:flex items-center gap-3">
          <a
            href="/zh"
            className="text-sm font-medium text-[#94A3B8] hover:text-[#0F1729] transition-colors p-2 rounded-lg hover:bg-[#F8FAFC]"
            title="切换到中文"
          >
            <Languages className="h-4 w-4" />
          </a>
          {token ? (
            <button
              className="text-sm font-semibold text-white bg-[#0F1729] hover:bg-[#1E293B] px-4 py-2 rounded-xl transition-all shadow-sm"
              onClick={() => navigate('/home')}
            >
              Dashboard
            </button>
          ) : (
            <>
              <button
                className="text-sm font-medium text-[#475569] hover:text-[#0F1729] transition-colors"
                onClick={() => navigate('/login')}
              >
                Log in
              </button>
              <button
                className="text-sm font-semibold text-white bg-[#2563EB] hover:bg-[#1D4ED8] px-4 py-2 rounded-xl transition-all shadow-sm shadow-[#2563EB]/20"
                onClick={() => navigate('/register')}
              >
                Free Trial
              </button>
            </>
          )}
        </div>

        <button className="md:hidden p-2 text-[#0F1729]" onClick={() => setOpen(!open)}>
          {open ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
        </button>
      </div>

      {open && (
        <div className="md:hidden bg-white border-b border-[#E2E8F0]/60 px-6 pb-6 space-y-3 shadow-lg">
          <div className="flex items-center justify-between pt-3 pb-1">
            <span className="text-xs font-semibold text-[#94A3B8] uppercase tracking-[0.15em]">English</span>
            <a
              href="/zh"
              className="flex items-center gap-1.5 text-xs font-semibold text-[#2563EB] bg-[#2563EB]/6 px-3 py-1.5 rounded-lg"
            >
              <Languages className="h-3.5 w-3.5" />
              切换到中文
            </a>
          </div>
          {NAV_ITEMS.map(item => (
            <button
              key={item.href}
              onClick={() => scrollTo(item.href)}
              className="block w-full text-left py-3 text-base font-medium text-[#475569] hover:text-[#0F1729]"
            >
              {item.label}
            </button>
          ))}
          <div className="pt-3 border-t border-[#E2E8F0]/60 flex gap-3">
            {token ? (
              <button
                className="w-full text-sm font-semibold text-white bg-[#0F1729] py-3 rounded-xl"
                onClick={() => { setOpen(false); navigate('/home'); }}
              >
                Dashboard
              </button>
            ) : (
              <>
                <button
                  className="flex-1 text-sm font-semibold text-[#0F1729] border border-[#E2E8F0] py-3 rounded-xl"
                  onClick={() => { setOpen(false); navigate('/login'); }}
                >
                  Log in
                </button>
                <button
                  className="flex-1 text-sm font-semibold text-white bg-[#2563EB] py-3 rounded-xl shadow-sm"
                  onClick={() => { setOpen(false); navigate('/register'); }}
                >
                  Free Trial
                </button>
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
  const navigate = useNavigate();

  return (
    <section className="relative min-h-[95vh] flex flex-col items-center justify-center pt-20 pb-12 px-6 overflow-hidden">
      <div className="absolute inset-0 pointer-events-none">
        <div className="absolute top-0 right-0 w-[600px] h-[600px] bg-[#2563EB]/[0.03] rounded-full blur-3xl translate-x-1/3 -translate-y-1/3" />
        <div className="absolute bottom-0 left-0 w-[500px] h-[500px] bg-[#4F46E5]/[0.03] rounded-full blur-3xl -translate-x-1/3 translate-y-1/3" />
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_center,rgba(37,99,235,0.02)_0%,transparent_70%)]" />
        <div className="absolute inset-0 opacity-[0.015]"
          style={{
            backgroundImage: 'linear-gradient(#0F1729 1px, transparent 1px), linear-gradient(90deg, #0F1729 1px, transparent 1px)',
            backgroundSize: '64px 64px',
          }}
        />
      </div>

      <div className="relative max-w-4xl mx-auto w-full text-center space-y-8">
        <div className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full bg-[#2563EB]/6 border border-[#2563EB]/10">
          <span className="relative flex h-2 w-2">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-[#2563EB] opacity-50" />
            <span className="relative inline-flex rounded-full h-2 w-2 bg-[#2563EB]" />
          </span>
          <span className="text-xs font-bold text-[#2563EB] uppercase tracking-[0.15em]">
            AI Operations System for Tutoring Institutions
          </span>
        </div>

        <h1 className="text-4xl md:text-6xl lg:text-[68px] font-bold tracking-tight text-[#0F1729] leading-[1.06]">
          Your teachers teach.
          <br />
          <span className="bg-gradient-to-r from-[#2563EB] to-[#4F46E5] bg-clip-text text-transparent">
            We handle the rest.
          </span>
        </h1>

        <p className="text-lg text-[#475569] max-w-2xl mx-auto leading-relaxed">
          AI question generation, smart exam assembly, adaptive review, real-time analytics, online Q&A, virtual study rooms, mock exams, interactive knowledge graphs — UniMind is the AI operations layer that runs your entire tutoring business. Your teachers do what they do best: teach. We automate everything else. SAT, MCAT, GRE, LSAT, CFA, bar exams, language certifications — if it has a syllabus, our AI masters it.
        </p>

        <div className="flex flex-col sm:flex-row items-center justify-center gap-3 pt-4">
          <button
            className="h-12 px-8 text-sm font-semibold text-white bg-[#2563EB] hover:bg-[#1D4ED8] rounded-xl shadow-lg shadow-[#2563EB]/20 transition-all hover:shadow-xl hover:shadow-[#2563EB]/25 hover:-translate-y-0.5"
            onClick={() => navigate('/register')}
          >
            Start 14-Day Free Trial
            <ArrowRight className="ml-1.5 h-4 w-4 inline" />
          </button>
          <button
            className="h-12 px-8 text-sm font-semibold text-[#0F1729] border border-[#E2E8F0] hover:border-[#CBD5E1] hover:bg-[#F8FAFC] rounded-xl transition-all"
            onClick={() => document.querySelector('#features')?.scrollIntoView({ behavior: 'smooth' })}
          >
            Learn More
            <ChevronDown className="ml-1.5 h-4 w-4 inline" />
          </button>
        </div>

        <p className="text-sm text-[#94A3B8] font-medium">
          No credit card required · 14-day full-feature trial · All subjects
        </p>

        <div className="max-w-4xl mx-auto pt-10 reveal">
          <Screenshot
            src="/screenshots/hero-dashboard.png"
            alt="Course Center and Study Ladder dashboard screenshot"
            className="w-full"
          />
        </div>
      </div>
    </section>
  );
};

/* ────────────────────────────────────────────
   Infinite Marquee
   ──────────────────────────────────────────── */

const Marquee: React.FC<{ children: React.ReactNode; speed?: number; className?: string }> = ({
  children,
  speed = 30,
  className,
}) => (
  <div className={cn('overflow-hidden', className)}>
    <div
      className="flex gap-0 hover:[animation-play-state:paused]"
      style={{
        animation: `marquee ${speed}s linear infinite`,
        width: 'max-content',
      }}
    >
      {children}
      {children}
    </div>
  </div>
);

/* ────────────────────────────────────────────
   Stats Bar
   ──────────────────────────────────────────── */

const STATS = [
  { label: 'Subjects Supported', value: '30+' },
  { label: 'AI Questions Generated', value: '100,000+' },
  { label: 'Institutions Worldwide', value: '50+' },
  { label: 'Avg. Time Savings', value: '50×' },
];

const StatsBar: React.FC = () => (
  <section className="py-12 border-y border-[#E2E8F0]/60 bg-white overflow-hidden">
    <Marquee speed={40}>
      {STATS.map((item, i) => (
        <div key={i} className="inline-flex items-center gap-4 px-10 py-2 shrink-0">
          <span className="text-xs font-semibold text-[#94A3B8] uppercase tracking-[0.2em]">{item.label}</span>
          <span className="text-3xl font-bold text-[#0F1729] tracking-tight">{item.value}</span>
        </div>
      ))}
    </Marquee>
  </section>
);

/* ────────────────────────────────────────────
   Pain Points
   ──────────────────────────────────────────── */

const PAINS = [
  {
    icon: Clock,
    title: 'Your Best Teachers Waste Hours on Admin',
    desc: 'Writing questions, assembling exams, grading papers, compiling reports — your most valuable people spend 70% of their week on busywork instead of teaching. That\'s not what you hired them for.',
  },
  {
    icon: BrainCircuit,
    title: 'One-Size-Fits-All Review Doesn\'t Work',
    desc: 'Every student gets the same worksheet. Top performers coast through material they already know. Struggling students fall further behind. Neither group is getting what they actually need — and your retention numbers show it.',
  },
  {
    icon: TrendingUp,
    title: 'You\'re Flying Blind on Student Progress',
    desc: 'By the time you spot a problem — a failing student, a weak topic area, a class falling behind — it\'s already too late. Without real-time insight into every student\'s mastery, you\'re making decisions in the dark.',
  },
];

const PainPoints: React.FC = () => (
  <section className="py-24 md:py-32 bg-white">
    <div className="max-w-6xl mx-auto px-6 reveal">
      <SectionHeader
        label="The Problem"
        title="Running a Tutoring Business Shouldn't Mean Running Yourself Ragged"
        subtitle="The real cost isn't rent or marketing. It's your teachers burning out on busywork, students slipping through the cracks, and decisions made without data."
      />
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {PAINS.map((item, i) => (
          <div
            key={item.title}
            className={cn(
              'p-8 rounded-2xl border border-[#E2E8F0] bg-white hover:shadow-lg hover:shadow-[#0F1729]/4 hover:-translate-y-1 transition-all duration-300 reveal group',
              `reveal-delay-${i + 1}`
            )}
          >
            <div className="h-11 w-11 rounded-xl bg-red-50 flex items-center justify-center mb-5">
              <item.icon className="h-5 w-5 text-red-500" />
            </div>
            <h3 className="text-xl font-bold text-[#0F1729] tracking-tight mb-3">{item.title}</h3>
            <p className="text-[15px] text-[#64748B] leading-relaxed">{item.desc}</p>
          </div>
        ))}
      </div>
    </div>
  </section>
);

/* ────────────────────────────────────────────
   Features
   ──────────────────────────────────────────── */

const FEATURES = [
  {
    icon: Cpu,
    title: 'AI Question Engine',
    subtitle: 'Generate, review, and deploy exam-quality questions in minutes — not days.',
    desc: 'A multi-agent adversarial pipeline — Author, Reviewer, and Classifier — iterates on every question. Substandard output is automatically rejected and regenerated until it meets the quality threshold. The result: 85%+ first-pass usability vs. ~60% with single-shot LLM generation. Multiple choice, calculation, case analysis — any format, any subject, academic-style output every time.',
    points: [
      '3-agent adversarial pipeline with up to 3 refinement iterations',
      'Automatic quality gating — 85%+ questions ready to use immediately',
      'All question formats supported across unlimited subjects',
    ],
    screenshot: '/screenshots/ai-generate.png',
    screenshotAlt: 'AI Question Generation Center screenshot',
  },
  {
    icon: Gauge,
    title: 'Memorix Adaptive Review',
    subtitle: 'Every student gets their own personalized review schedule — like a private tutor for each of them.',
    desc: 'Memorix builds a 20-dimension memory profile for every student using Weibull-distribution forgetting curves — far more accurate than traditional spaced repetition. After each answer, online stochastic gradient descent updates the profile in real time. The result: 13.7% lower prediction error than FSRS v4.5, and 9.2% higher knowledge retention. Students review what they\'re about to forget, exactly when they need to see it.',
    points: [
      'Weibull forgetting model — captures real human memory decay patterns',
      'Online SGD + Nesterov — every answer refines the student\'s memory profile',
      'Brier Score calibration — mathematically guarantees prediction accuracy',
      '20 personal parameters per student — individual memory portraits, not group averages',
    ],
    screenshot: '/screenshots/memorix-review.png',
    screenshotAlt: 'Memorix adaptive review interface',
  },
  {
    icon: BarChart3,
    title: 'Knowledge Workbench',
    subtitle: 'See exactly what every student knows, what they\'re struggling with, and what to do about it.',
    desc: 'An interactive knowledge graph where every concept is a colored node — green for mastered, red for weak, gray for not yet covered. Click any node to jump to related questions, mistake history, and course materials. Students visualize their own knowledge structure. Teachers pinpoint class-wide weak spots in seconds and adjust instruction accordingly.',
    points: [
      'Interactive SVG knowledge graph with real-time mastery coloring',
      'One-click drill-down from concept → questions → mistakes → resources',
      'Class-wide heatmaps for targeted group instruction',
    ],
    screenshot: '/screenshots/analytics-dashboard.png',
    screenshotAlt: 'Knowledge Workbench analytics dashboard',
  },
  {
    icon: Globe,
    title: 'Complete Operations Suite',
    subtitle: 'One platform. Every tool your institution needs to run, scale, and grow.',
    desc: 'Beyond question generation and review — UniMind includes built-in video courses with AI-generated outlines, a live Q&A system for student support, virtual study rooms with Pomodoro timers, mock exam generation, multi-teacher role-based permissions, white-label branding, and API access for custom integrations. Stop paying for 6 different tools. Run everything from one dashboard.',
    points: [
      'Video courses + AI outlines, online Q&A, virtual study rooms',
      'Multi-teacher permissions, white-label deployment, API access',
      'Student-side payments — monetize your content directly',
    ],
    screenshot: '/screenshots/hero-dashboard.png',
    screenshotAlt: 'UniMind operations dashboard overview',
  },
];

const Features: React.FC = () => (
  <section id="features" className="py-24 md:py-32 bg-[#F8FAFC] border-y border-[#E2E8F0]/60">
    <div className="max-w-6xl mx-auto px-6 reveal">
      <SectionHeader
        label="Core Capabilities"
        title="Everything That Isn't Teaching, Automated"
        subtitle="Stop stitching together a dozen tools. UniMind replaces your question bank, review scheduler, analytics dashboard, LMS, and operations stack — so your teachers can focus on the one thing AI can't do: inspire students."
      />

      <div className="space-y-20 md:space-y-28">
        {FEATURES.map((item, i) => (
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
                src={item.screenshot}
                alt={item.screenshotAlt}
                className="w-full"
              />
            </div>

            <div className="flex-1 space-y-5">
              <div className="h-10 w-10 rounded-xl bg-[#2563EB]/8 flex items-center justify-center">
                <item.icon className="h-5 w-5 text-[#2563EB]" />
              </div>
              <h3 className="text-2xl md:text-3xl font-bold text-[#0F1729] tracking-tight">{item.title}</h3>
              <p className="text-sm font-semibold text-[#2563EB]">{item.subtitle}</p>
              <p className="text-[15px] text-[#64748B] leading-relaxed">{item.desc}</p>
              <ul className="space-y-2.5">
                {item.points.map(p => (
                  <li key={p} className="flex items-start gap-3 text-sm font-medium text-[#334155]">
                    <Check className="h-4 w-4 text-[#22C55E] shrink-0 mt-0.5" />
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

/* ────────────────────────────────────────────
   How It Works
   ──────────────────────────────────────────── */

const STEPS = [
  { num: '1', icon: Globe, title: 'Upload Your Curriculum', desc: 'Register in 60 seconds. Import your syllabus, knowledge points, or existing question bank. Our AI maps your subject structure and is ready to generate content immediately. Works with any subject, any format.' },
  { num: '2', icon: Cpu, title: 'AI Generates Content', desc: 'Select topics and question types. Our three-agent adversarial pipeline auto-generates exam-quality content. Review, approve with one click, and your question bank is live. New content in minutes, not weeks.' },
  { num: '3', icon: BarChart3, title: 'Students Learn. You Get Insights.', desc: 'Share a link — students practice instantly via browser, no app to install. Every answer is auto-graded. Your knowledge dashboard updates in real time, showing you exactly who needs help and where.' },
];

const HowItWorks: React.FC = () => (
  <section className="py-24 md:py-32 bg-white">
    <div className="max-w-6xl mx-auto px-6 reveal">
      <SectionHeader
        label="How It Works"
        title="From Zero to Live in Under 10 Minutes"
        subtitle="No engineering team. No AI expertise. No training required. If you can upload a syllabus, you can run UniMind."
      />

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {STEPS.map((step, i) => (
          <div
            key={step.num}
            className={cn(
              'relative p-8 rounded-2xl border border-[#E2E8F0] bg-white hover:shadow-lg hover:-translate-y-1 transition-all duration-300 overflow-hidden group reveal',
              `reveal-delay-${i + 1}`
            )}
          >
            <div className="absolute -top-5 -right-5 text-[120px] font-bold text-[#F1F5F9] leading-none select-none group-hover:text-[#E2E8F0] transition-colors">
              {step.num}
            </div>
            <div className="relative z-10 space-y-4">
              <div className="h-11 w-11 rounded-xl bg-[#2563EB]/8 flex items-center justify-center">
                <step.icon className="h-5 w-5 text-[#2563EB]" />
              </div>
              <h3 className="text-lg font-bold text-[#0F1729] tracking-tight">{step.title}</h3>
              <p className="text-[14px] text-[#64748B] leading-relaxed">{step.desc}</p>
            </div>
          </div>
        ))}
      </div>
    </div>
  </section>
);

/* ────────────────────────────────────────────
   Customer Results
   ──────────────────────────────────────────── */

const RESULT_METRICS = [
  { value: '90%', label: 'Less Time on Content Creation', desc: 'From hours per exam to minutes' },
  { value: '85%+', label: 'AI-First-Pass Acceptance Rate', desc: 'Questions ready with minimal review' },
  { value: '+9.2%', label: 'Knowledge Retention Lift', desc: 'Memorix vs. standard spaced repetition' },
  { value: '50+', label: 'Active Institutions', desc: 'From independent tutors to enterprise brands' },
];

const INSTITUTION_LOGOS = [
  'SAT / ACT Prep', 'MCAT Prep', 'LSAT Prep', 'GRE / GMAT Prep',
  'USMLE Step 1 & 2', 'Bar Exam Prep', 'CFA Exam Prep', 'Language Schools',
];

const TESTIMONIALS = [
  {
    quote: 'Before UniMind, our curriculum team spent 20+ hours per week just writing and reviewing questions. Now the AI produces a full practice set in minutes, our team does a quick quality check, and we\'re done. We\'ve doubled our course offerings without hiring a single person.',
    author: 'Dr. Sarah Chen',
    meta: 'Director of Curriculum, MedPrep Academy · Boston, MA',
    highlight: 'Doubled output with same team',
  },
  {
    quote: 'We evaluated five platforms. Memorix was the differentiator. Our students using adaptive review scored 12 percentile points higher on the actual exam than the control group. That\'s not incremental improvement — that\'s transformational. Our enrollment is up 40% because outcomes sell.',
    author: 'Marcus Williams',
    meta: 'Founder, Williams Test Prep · Austin, TX',
    highlight: '12-point score improvement',
  },
  {
    quote: 'We used to juggle Google Classroom, Quizlet, a separate testing platform, and spreadsheets to track everything. UniMind consolidated it all. One login, one dashboard, one place where our 40+ tutors collaborate. The operational overhead savings alone paid for the subscription in month one.',
    author: 'James Harrington',
    meta: 'CEO, Harrington Education Group · London, UK',
    highlight: 'Consolidated 5 tools into 1',
  },
];

const TestimonialCarousel: React.FC = () => {
  const [active, setActive] = useState(0);
  const len = TESTIMONIALS.length;

  useEffect(() => {
    const timer = setInterval(() => setActive(prev => (prev + 1) % len), 5000);
    return () => clearInterval(timer);
  }, [len]);

  return (
    <div className="reveal">
      <div className="overflow-hidden rounded-2xl border border-[#E2E8F0] bg-white">
        <div
          className="flex transition-transform duration-500 ease-in-out"
          style={{ transform: `translateX(-${active * 100}%)` }}
        >
          {TESTIMONIALS.map((tm, i) => (
            <div key={i} className="w-full shrink-0 p-8 md:p-10 flex flex-col">
              <span className="text-5xl font-serif text-[#2563EB]/12 leading-none select-none mb-4">&ldquo;</span>
              <blockquote className="text-[15px] md:text-base text-[#475569] leading-relaxed flex-1 mb-8 max-w-2xl">
                {tm.quote}
              </blockquote>
              <div className="flex items-center gap-3">
                <div className="h-9 w-9 rounded-full bg-[#2563EB]/8 flex items-center justify-center">
                  <span className="text-xs font-bold text-[#2563EB]">{tm.author.charAt(0)}</span>
                </div>
                <div>
                  <p className="text-sm font-semibold text-[#0F1729]">{tm.author}</p>
                  <p className="text-xs text-[#94A3B8]">{tm.meta}</p>
                </div>
                <span className="ml-auto text-xs font-semibold text-[#2563EB] bg-[#2563EB]/6 px-3 py-1 rounded-full">
                  {tm.highlight}
                </span>
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="flex items-center justify-center gap-2 mt-6">
        {TESTIMONIALS.map((_, i) => (
          <button
            key={i}
            onClick={() => setActive(i)}
            className={cn(
              'h-2 rounded-full transition-all duration-300',
              i === active ? 'w-6 bg-[#2563EB]' : 'w-2 bg-[#CBD5E1] hover:bg-[#94A3B8]',
            )}
          />
        ))}
      </div>
    </div>
  );
};

const CustomerResults: React.FC = () => (
  <section className="py-24 md:py-32 bg-[#F8FAFC] border-y border-[#E2E8F0]/60 overflow-hidden">
    <div className="max-w-6xl mx-auto px-6">
      <SectionHeader
        label="Customer Results"
        title="Trusted by Tutoring Businesses Worldwide"
        subtitle="From solo tutors to multi-location brands — here's what our customers are achieving."
      />

      <div className="mb-16 reveal">
        <Marquee speed={35}>
          {RESULT_METRICS.map((item, i) => (
            <div
              key={i}
              className="inline-flex items-center gap-6 px-8 py-5 mx-2 rounded-2xl border border-[#E2E8F0] bg-white shrink-0 min-w-[200px]"
            >
              <p className="text-2xl font-bold text-[#0F1729] tracking-tight tabular-nums">{item.value}</p>
              <div className="text-left">
                <p className="text-xs font-semibold text-[#2563EB]">{item.label}</p>
                <p className="text-[11px] text-[#94A3B8]">{item.desc}</p>
              </div>
            </div>
          ))}
        </Marquee>
      </div>

      <div className="mb-20 reveal">
        <p className="text-xs font-semibold text-[#94A3B8] uppercase tracking-[0.2em] mb-6 text-center">
          Disciplines Covered
        </p>
        <Marquee speed={50}>
          {INSTITUTION_LOGOS.map((name, i) => (
            <span
              key={i}
              className="inline-flex mx-1.5 px-5 py-2.5 rounded-xl bg-white border border-[#E2E8F0] text-sm font-medium text-[#475569] hover:border-[#CBD5E1] hover:shadow-sm transition-all cursor-default shrink-0"
            >
              {name}
            </span>
          ))}
        </Marquee>
      </div>

      <TestimonialCarousel />
    </div>
  </section>
);

/* ────────────────────────────────────────────
   Subjects
   ──────────────────────────────────────────── */

const SUBJECTS = [
  { name: 'College Admissions', tags: ['SAT', 'ACT', 'AP Biology', 'AP Calculus', 'AP History', 'College Essays'] },
  { name: 'Graduate Exams', tags: ['MCAT', 'LSAT', 'GRE', 'GMAT', 'DAT', 'PCAT'] },
  { name: 'Professional Licensing', tags: ['USMLE', 'Bar Exam', 'CFA', 'CPA', 'PMP', 'NCLEX'] },
  { name: 'Language & K-12', tags: ['IELTS', 'TOEFL', 'Cambridge', 'GCSE', 'A-Levels', 'IB Diploma'] },
];

const Subjects: React.FC = () => (
  <section id="subjects" className="py-24 md:py-32 bg-white">
    <div className="max-w-6xl mx-auto px-6 reveal">
      <SectionHeader
        label="All Subjects"
        title="If It Has a Syllabus, We Can Teach It"
        subtitle={'UniMind\'s AI isn\'t pre-loaded with specific subjects — it\'s an expert at "how to write a great question" in any domain. Upload your curriculum once, and it generates discipline-specific content that matches your teaching style.'}
      />

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-5">
        {SUBJECTS.map((cat, i) => (
          <div
            key={cat.name}
            className={cn(
              'p-6 rounded-2xl border border-[#E2E8F0] bg-white hover:shadow-md transition-all duration-300 reveal',
              `reveal-delay-${i + 1}`
            )}
          >
            <h3 className="text-sm font-bold text-[#0F1729] tracking-tight mb-4">{cat.name}</h3>
            <div className="flex flex-wrap gap-1.5">
              {cat.tags.map(tag => (
                <span key={tag} className="text-xs font-medium px-2.5 py-1 rounded-lg bg-[#F8FAFC] text-[#64748B] border border-[#E2E8F0]/60">
                  {tag}
                </span>
              ))}
            </div>
          </div>
        ))}
      </div>

      <p className="text-center mt-10 text-sm text-[#94A3B8] font-medium">
        Don't see your subject? Customize your knowledge tree — AI adapts instantly.
      </p>
    </div>
  </section>
);

/* ────────────────────────────────────────────
   Pricing — $ USD
   ──────────────────────────────────────────── */

const PLANS = [
  {
    name: 'Free',
    desc: 'For solo tutors validating the product',
    monthly: '$0',
    yearly: '$0',
    cta: 'Get Started Free',
    popular: false,
    features: [
      'AI generation 20/month',
      'Video courses',
      'Basic question bank',
      'Mistake review center',
      'Basic analytics',
      '30 students · 1 teacher',
    ],
  },
  {
    name: 'Solo',
    desc: 'Complete AI toolkit for independent tutors',
    monthly: '$39',
    yearly: '$29',
    cta: 'Start Free Trial',
    popular: false,
    features: [
      'Unlimited AI generation',
      'Smart exam assembly',
      'Memorix adaptive review',
      'Interactive knowledge graph',
      'AI assistant · Multi-bot',
      'AI outline generator',
      'Full personal analytics',
      '50 students · 1 teacher',
    ],
  },
  {
    name: 'Plus',
    desc: 'All-in-one platform for growing businesses',
    monthly: '$189',
    yearly: '$149',
    cta: 'Start Free Trial',
    popular: true,
    features: [
      'Everything in Solo',
      'Online Q&A system',
      'Multi-teacher · Permissions',
      'Study room · Pomodoro timer',
      'Mock exam generator',
      'Class comparison · Data export',
      '200 students · 5 teachers',
    ],
  },
  {
    name: 'Pro',
    desc: 'Enterprise flagship — built for scale & customization',
    monthly: '$599',
    yearly: '$449',
    cta: 'Book a Demo',
    popular: false,
    features: [
      'Everything in Plus',
      'Unlimited students & teachers',
      'White-label · Custom branding',
      'Private deployment · Data sovereignty',
      'API access · System integration',
      'Multi-language · i18n support',
      'Open-source SDK · Extendability',
      'SSO · SAML single sign-on',
      'Audit logs · Compliance ready',
      'Dedicated customer success manager',
      'SLA 99.9% uptime guarantee',
      'Student-side payments',
    ],
  },
];

const Pricing: React.FC = () => {
  const navigate = useNavigate();
  const [annual, setAnnual] = useState(true);

  return (
    <section id="pricing" className="py-24 md:py-32 bg-[#F8FAFC] border-y border-[#E2E8F0]/60">
      <div className="max-w-6xl mx-auto px-6 reveal">
        <SectionHeader
          label="Pricing"
          title="Start Small. Scale at Your Own Pace."
          subtitle="Every plan includes a 14-day full-feature trial. No credit card. Upgrade, downgrade, or cancel anytime."
        />

        <div className="flex items-center justify-center gap-4 mb-12">
          <span className={cn('text-sm font-semibold', !annual ? 'text-[#0F1729]' : 'text-[#94A3B8]')}>Monthly</span>
          <button
            onClick={() => setAnnual(!annual)}
            className="w-12 h-7 rounded-full bg-[#E2E8F0] relative transition-colors"
          >
            <div className={cn(
              'absolute top-0.5 h-6 w-6 rounded-full bg-white shadow-md transition-all',
              annual ? 'left-6 bg-[#2563EB]' : 'left-0.5'
            )} />
          </button>
          <span className={cn('text-sm font-semibold', annual ? 'text-[#0F1729]' : 'text-[#94A3B8]')}>
            Annual <span className="text-[#22C55E] text-xs font-bold ml-1">Save 23–33%</span>
          </span>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-5 items-stretch">
          {PLANS.map((plan, pi) => {
            const price = annual && plan.yearly !== '$0' ? plan.yearly : plan.monthly;
            return (
              <div
                key={plan.name}
                className={cn(
                  'p-6 rounded-2xl border bg-white flex flex-col reveal transition-all duration-300 hover:shadow-lg relative',
                  `reveal-delay-${pi + 1}`,
                  plan.popular
                    ? 'border-[#2563EB] ring-2 ring-[#2563EB]/20 shadow-xl shadow-[#2563EB]/8 scale-[1.02]'
                    : 'border-[#E2E8F0] hover:border-[#CBD5E1]'
                )}
              >
                {plan.popular && (
                  <div className="absolute -top-3 left-1/2 -translate-x-1/2 bg-[#2563EB] text-white text-[10px] font-bold px-4 py-1 rounded-full tracking-wide">
                    Most Popular
                  </div>
                )}

                <div className="mb-4 mt-1">
                  <h3 className={cn('text-lg font-bold tracking-tight', plan.popular ? 'text-[#2563EB]' : 'text-[#0F1729]')}>{plan.name}</h3>
                  <p className="text-xs text-[#94A3B8] font-medium mt-1">{plan.desc}</p>
                </div>

                <div className="mb-5">
                  <span className="text-4xl font-bold text-[#0F1729] tracking-tight">{price}</span>
                  {plan.monthly !== '$0' && <span className="text-sm font-semibold text-[#94A3B8] ml-0.5">/mo</span>}
                  {annual && plan.yearly !== '$0' && (
                    <p className="text-xs text-[#94A3B8] mt-1">
                      ${parseInt(plan.yearly.replace('$', '')) * 12}/year
                    </p>
                  )}
                </div>

                <button
                  className={cn(
                    'w-full h-11 rounded-xl text-sm font-semibold transition-all mb-6',
                    plan.popular
                      ? 'bg-[#2563EB] text-white hover:bg-[#1D4ED8] shadow-md shadow-[#2563EB]/20'
                      : 'bg-[#0F1729] text-white hover:bg-[#1E293B]'
                  )}
                  onClick={() => navigate('/register')}
                >
                  {plan.cta}
                </button>

                <ul className="space-y-2 flex-1 border-t border-[#F1F5F9] pt-4">
                  {plan.features.map((feat, fi) => (
                    <li key={fi} className="flex items-start gap-2.5 text-[13px] font-medium text-[#334155] leading-relaxed">
                      <Check className="h-4 w-4 text-[#22C55E] shrink-0 mt-0.5" />
                      {feat}
                    </li>
                  ))}
                </ul>
              </div>
            );
          })}
        </div>

        <p className="text-center mt-10 text-sm text-[#94A3B8] font-medium">
          All plans include a 14-day full-feature trial. Upgrade, downgrade, or cancel anytime.
        </p>
      </div>
    </section>
  );
};

/* ────────────────────────────────────────────
   FAQ
   ──────────────────────────────────────────── */

const FAQS = [
  { q: 'What are the limits of the free plan?', a: 'The Free plan supports 30 students and 50 AI question generations per month — enough to run a full pilot with a small class. You get access to the complete product: AI generation, adaptive review, analytics, and knowledge graphs. No time limit. No credit card.' },
  { q: 'Can AI-generated questions match the quality of our expert-written content?', a: 'Our three-agent adversarial pipeline — Author, Reviewer, Classifier — iterates on every question until it passes a quality threshold. In head-to-head comparisons, AI-generated questions matched or exceeded human-written quality in 85%+ of cases. We recommend a quick final review by your subject experts — the AI handles the heavy lifting, your team provides professional judgment on the last 10%.' },
  { q: 'Which subjects and exams does UniMind support?', a: 'The platform is completely subject-agnostic. We have pre-built frameworks for SAT/ACT, MCAT, LSAT, GRE/GMAT, USMLE, bar exams, CFA/CPA, language certifications (IELTS/TOEFL/Cambridge), and K-12 (GCSE/A-Levels/IB). Teaching something else? Upload your own syllabus and knowledge tree — the AI adapts within minutes.' },
  { q: 'How do students access the platform?', a: 'Students access everything through a web browser — no app download, no installation. Share a link via email, messaging app, or your LMS, and students start practicing instantly. The experience is fully mobile-responsive and works on any device.' },
  { q: 'What payment methods do you accept?', a: 'We accept all major credit and debit cards (Visa, Mastercard, Amex) via Stripe. For annual Plus and Pro plans, we also support invoicing and bank transfers. All payments are processed in USD.' },
  { q: 'What happens to my data if I cancel?', a: 'Your data is yours — always. All questions, student records, and learning data are preserved and exportable. If you cancel, your account becomes read-only. Resubscribe at any time to restore full access. No data lock-in, no surprises.' },
  { q: 'How is UniMind different from a regular LMS or quiz maker?', a: 'An LMS hosts content. UniMind creates it. Quizlet gives you flashcards. UniMind builds the flashcards, schedules when each student should review them, and tells you who\'s struggling. We\'re not a testing tool — we\'re an AI operations layer that automates content creation, personalizes learning, and surfaces insights so you can scale your tutoring business without scaling your headcount.' },
  { q: 'I\'m a solo tutor. Is this for me or just for large institutions?', a: 'Both. Our Free and Solo plans are built for independent tutors and small practices. Start free, get your first 30 students onboard, and upgrade when you grow. Many of our Pro customers started as solo users. The platform scales with you — from 5 students to 5,000.' },
];

const FAQ: React.FC = () => {
  const [openIdx, setOpenIdx] = useState<number | null>(null);

  return (
    <section id="faq" className="py-24 md:py-32 bg-white">
      <div className="max-w-3xl mx-auto px-6 reveal">
        <SectionHeader label="FAQ" title="Frequently Asked Questions" />
        <div className="space-y-3">
          {FAQS.map((faq, i) => (
            <div
              key={i}
              className="rounded-2xl border border-[#E2E8F0] overflow-hidden transition-all duration-200"
            >
              <button
                onClick={() => setOpenIdx(openIdx === i ? null : i)}
                className="w-full px-6 py-4 flex items-center justify-between text-left gap-4 hover:bg-[#F8FAFC]"
              >
                <span className="text-sm font-semibold text-[#0F1729]">{faq.q}</span>
                {openIdx === i
                  ? <ChevronUp className="h-4 w-4 text-[#94A3B8] shrink-0" />
                  : <ChevronDown className="h-4 w-4 text-[#94A3B8] shrink-0" />
                }
              </button>
              {openIdx === i && (
                <div className="px-6 pb-5">
                  <p className="text-sm text-[#64748B] leading-relaxed">{faq.a}</p>
                </div>
              )}
            </div>
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
  const navigate = useNavigate();
  return (
    <section className="relative py-24 md:py-32 bg-[#0F1729] overflow-hidden">
      <div className="absolute inset-0 pointer-events-none">
        <div className="absolute top-0 right-0 w-[500px] h-[500px] bg-[#2563EB]/10 rounded-full blur-3xl translate-x-1/3 -translate-y-1/3" />
        <div className="absolute bottom-0 left-0 w-[400px] h-[400px] bg-[#4F46E5]/8 rounded-full blur-3xl -translate-x-1/3 translate-y-1/3" />
      </div>
      <div className="relative max-w-3xl mx-auto px-6 text-center space-y-8 reveal">
        <h2 className="text-3xl md:text-5xl font-bold tracking-tight text-white leading-[1.12]">
          Stop running operations. Start running a school.
        </h2>
        <p className="text-lg text-[#94A3B8] leading-relaxed max-w-xl mx-auto">
          14-day full-feature trial. No credit card. No setup fee. Every feature included. See how much time your team gets back when AI handles the busywork and you focus on what matters: student outcomes.
        </p>
        <button
          className="h-12 px-8 text-sm font-semibold text-white bg-[#2563EB] hover:bg-[#1D4ED8] rounded-xl shadow-lg shadow-[#2563EB]/30 transition-all hover:shadow-xl hover:-translate-y-0.5"
          onClick={() => navigate('/register')}
        >
          Start 14-Day Free Trial
          <ArrowRight className="ml-1.5 h-4 w-4 inline" />
        </button>
        <p className="text-sm text-[#64748B] font-medium">
          Trusted by 50+ institutions across 12 countries
        </p>
      </div>
    </section>
  );
};

/* ────────────────────────────────────────────
   Footer
   ──────────────────────────────────────────── */

const Footer: React.FC = () => (
  <footer className="py-12 bg-[#F8FAFC] border-t border-[#E2E8F0]/60">
    <div className="max-w-6xl mx-auto px-6 reveal">
      <div className="flex flex-col md:flex-row items-center justify-between gap-6">
        <div className="flex items-center gap-3">
          <img src="/Unimind_logo.png" alt="UniMind" className="h-6 w-auto" />
          <div className="leading-tight">
            <p className="font-bold text-sm text-[#0F1729] tracking-tight">UniMind.ai</p>
            <p className="text-xs font-medium text-[#94A3B8]">AI Operations System for Tutoring Institutions</p>
          </div>
        </div>
        <div className="flex items-center gap-6">
          <a href="#features" className="text-sm font-medium text-[#64748B] hover:text-[#0F1729] transition-colors">Features</a>
          <a href="#pricing" className="text-sm font-medium text-[#64748B] hover:text-[#0F1729] transition-colors">Pricing</a>
          <a href="#faq" className="text-sm font-medium text-[#64748B] hover:text-[#0F1729] transition-colors">FAQ</a>
        </div>
        <p className="text-xs font-medium text-[#94A3B8]">
          &copy; {COPYRIGHT_YEAR} {COPYRIGHT_ENTITY} · {APP_VERSION}
        </p>
      </div>
    </div>
  </footer>
);

/* ────────────────────────────────────────────
   Main Landing — English
   ──────────────────────────────────────────── */

export const LandingEn: React.FC = () => {
  const { token } = useAuthStore();

  useEffect(() => {
    document.documentElement.lang = 'en';
    document.title = 'UniMind.ai — AI Operations System for Tutoring Institutions | Teachers Teach. We Handle the Rest.';
  }, []);

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
    <div className="w-full bg-white font-sans text-left antialiased">
      <style>{`
        @keyframes marquee {
          0% { transform: translateX(0); }
          100% { transform: translateX(-50%); }
        }
      `}</style>
      <Nav token={token} />
      <Hero />
      <StatsBar />
      <PainPoints />
      <Features />
      <HowItWorks />
      <CustomerResults />
      <Subjects />
      <Pricing />
      <FAQ />
      <FinalCTA />
      <Footer />
    </div>
  );
};
