import React, { useEffect, useState, useRef } from 'react';
import { Button } from '@/components/ui/button';
import api from '@/lib/api';
import { ArrowRight, List, X, Clock, Repeat, ChartBar } from '@phosphor-icons/react';
import { cn } from '@/lib/utils';
import { useNavigate, Link } from 'react-router-dom';
import { useAuthStore } from '../store/useAuthStore';
import { APP_VERSION, COPYRIGHT_YEAR } from '@/constants/version';

/* ────────────────────────────────────────────
   Palette constants — white-first design
   ──────────────────────────────────────────── */


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
   Nav — adaptive dark/light
   ──────────────────────────────────────────── */

const Nav: React.FC<{ token: string | null }> = ({ token }) => {
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
    { label: '功能', href: '#features' },
    { label: '学科', href: '#subjects' },
    { label: '定价', href: '/pricing' },
  ];

  // Hero is white → transparent nav with dark text; once scrolled → white bar with shadow
  const navBg = scrolled
    ? 'bg-white/90 backdrop-blur-xl border-b border-gray-100 shadow-sm'
    : 'bg-transparent';
  const txtColor = 'text-unimind-text-secondary hover:text-unimind-text';
  const logoColor = 'text-unimind-text';

  return (
    <nav className={cn('fixed top-0 left-0 right-0 z-[var(--z-dropdown)] transition-all duration-500', navBg)}>
      <div className="max-w-6xl mx-auto h-20 flex items-center justify-between">
        <button onClick={() => window.scrollTo({ top: 0, behavior: 'smooth' })} className="flex items-center shrink-0 pl-6">
          <img src="/Unimind_logo_wide.png" alt="UniMind" className="h-9 object-contain mix-blend-multiply" />
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

        <div className="flex items-center gap-3 pr-6">
          {token ? (
            <Button
              size="sm"
              className="text-xiaoyu-500 border-xiaoyu-100 bg-xiaoyu-50 hover:bg-xiaoyu-100"
              onClick={() => navigate('/courses')}
            >
              进入控制台
            </Button>
          ) : (
            <>
              <button
                className={cn('text-[13px] font-medium transition-colors hidden sm:block', txtColor)}
                onClick={() => navigate('/login')}
              >
                登录
              </button>
              <Button
                size="sm"
                className="text-white border-0 font-semibold bg-xiaoyu-500 hover:bg-xiaoyu-600"
                onClick={() => navigate('/register')}
              >
                免费试用
              </Button>
            </>
          )}
          <button className={cn('md:hidden p-1 transition-colors', txtColor)} onClick={() => setOpen(!open)}>
            {open ? <X className="h-5 w-5" /> : <List className="h-5 w-5" />}
          </button>
        </div>
      </div>

      {/* Mobile menu */}
      {open && (
        <div className="md:hidden bg-white/95 backdrop-blur-xl border-b border-gray-100 px-6 pb-5 space-y-1">
          {navItems.map(item => (
            <button
              key={item.href}
              onClick={() => scrollTo(item.href)}
              className="block w-full text-left py-3 text-base font-medium text-unimind-text-secondary hover:text-unimind-text transition-colors"
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
   Hero — white, full viewport
   ──────────────────────────────────────────── */

const Hero: React.FC = () => {
  const navigate = useNavigate();

  return (
    <section className="flex flex-col items-center justify-center min-h-screen px-6 relative overflow-hidden bg-[#fafafa]">

      <div className="max-w-5xl mx-auto w-full text-center relative z-10 space-y-8 pt-32 pb-32 md:pt-44 md:pb-40">
        <div className="reveal space-y-6">
          {/* Memorix-Field announcement — text only, single line */}
          <button
            onClick={() => navigate('/memorix')}
            className="inline-block cursor-pointer group"
          >
            <span className="text-[18px] text-xiaoyu-500 group-hover:underline">
              🎉 <strong>Memorix-Field</strong> 图扩散记忆调度发布 — 遗忘率相比 SOTA 降低 19.9%，现已全面支持 Agent 个性化学习路径 →
            </span>
          </button>

          <h1 className="text-[36px] md:text-[52px] lg:text-[64px] font-extrabold leading-[1.08] text-unimind-text max-w-4xl mx-auto tracking-[-0.03em]">
            你的老师，只管讲课
            <br />
            <span className="text-xiaoyu-500">
              剩下的，UniMind 全包了
            </span>
          </h1>
          <p className="text-base md:text-lg text-unimind-text-secondary max-w-xl mx-auto leading-relaxed">
            出题、刷题、追踪——全链路 Agent 化，开箱即用。
          </p>
        </div>

        <div className="flex items-center justify-center gap-3 pt-2 reveal reveal-delay-2">
          <Button
            size="lg"
            className="h-12 px-8 text-sm font-bold rounded-xl text-white bg-xiaoyu-500 hover:bg-xiaoyu-600"
            onClick={() => navigate('/register')}
          >
            免费开始
            <ArrowRight className="ml-1.5 h-4 w-4" />
          </Button>
        </div>

        {/* Promo badge — capsule below CTA */}
        <div className="reveal reveal-delay-2">
          <button
            onClick={() => navigate('/promo/plus')}
            className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full border border-xiaoyu-100 hover:border-xiaoyu-500 transition-all duration-300 cursor-pointer group bg-xiaoyu-50"
          >
            <span className="text-[11px] font-semibold text-xiaoyu-500">首批机构专享 · Growth 方案免费开放</span>
            <ArrowRight className="h-3 w-3 text-xiaoyu-500 group-hover:translate-x-0.5 transition-transform" />
          </button>
        </div>

        {/* Trust markers */}
        <p className="text-[11px] text-unimind-text-quaternary tracking-wide reveal reveal-delay-2">
          首批机构免费获得 Growth 方案 · 活动截止 2026.6.30
        </p>
      </div>

    </section>
  );
};

/* ────────────────────────────────────────────
   Stats — big numbers, no words
   ──────────────────────────────────────────── */

const StatsBar: React.FC = () => {
  const stats = [
    { label: '支持学科', desc: '金融 · 法学 · 医学 · CPA · CFA · 教资全覆盖' },
    { label: 'AI 题目已生成', desc: '三智能体对抗保证质量' },
    { label: '入驻机构', desc: '从独立教师到连锁品牌' },
    { label: '出题效率提升', desc: '从 30 分钟到 10 秒' },
  ] as Array<{ label: string; value: string; desc: string }>;
  const [visible, setVisible] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const obs = new IntersectionObserver(([e]) => { if (e.isIntersecting) setVisible(true); }, { threshold: 0.6 });
    obs.observe(el);
    return () => obs.disconnect();
  }, []);

  const c0 = useCountUp(12, 1200, visible);
  const c1 = useCountUp(48620, 1800, visible);
  const c2 = useCountUp(47, 1200, visible);
  const c3 = useCountUp(52, 1200, visible);
  const displays = [`${c0}+`, `${(c1 / 1000).toFixed(0)}k+`, `${c2}+`, `${c3}×`];

  return (
    <section ref={ref} className="py-20 border-y border-border bg-background">
      <div className="max-w-5xl mx-auto px-6">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-8 md:gap-16">
          {stats.map((item, i) => (
            <div key={item.label} className="text-center space-y-2">
              <p className="text-5xl md:text-6xl font-bold tracking-tight text-xiaoyu-500" style={{ fontFamily: '"DM Mono", monospace' }}>
                {displays[i]}
              </p>
              <p className="text-[12px] font-medium uppercase tracking-[0.2em] text-muted-foreground">{item.label}</p>
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

const PainPoints: React.FC = () => {
  const pain = {
    label: 'The Problem',
    title: '你最贵的成本，藏在看不见的地方',
    subtitle: '不是房租，不是获客——是教研效率、续费率、数据盲区。',
    items: [
      {
        title: '教研成本吞噬利润',
        desc: '一个全职教研老师月薪 1.5-2 万，60% 的时间花在出题、组卷、写解析上。机构越大，教研人力成本越高——而这些工作 AI 10 秒就能完成。',
      },
      {
        title: '续费率卡在瓶颈',
        desc: '所有学生刷同一套题，学霸觉得没用，薄弱生跟不上。个性化复习是续费的关键驱动力，但手工操作根本做不到——结果就是续费率卡在六七成上不去。',
      },
      {
        title: '决策靠猜不靠数据',
        desc: '哪个知识点全班薄弱？哪个学生快掉队？月底看 Excel 才知道，已经来不及了。没有实时数据，教研调整就是拍脑袋，招生成本越来越高。',
      },
    ],
  } as { label: string; title: string; subtitle: string; items: Array<{ title: string; desc: string }> };
  const icons = [Clock, Repeat, ChartBar];

  return (
    <section className="py-28 md:py-36 px-6 relative overflow-hidden bg-white">
      <div className="max-w-5xl mx-auto">
        <div className="reveal text-center mb-16">
          <p className="text-[10px] font-semibold uppercase tracking-[0.3em] text-unimind-text-tertiary mb-4">{pain.label}</p>
          <h2 className="text-3xl md:text-5xl font-bold tracking-tighter text-unimind-text leading-tight max-w-3xl mx-auto">{pain.title}</h2>
          <p className="text-sm text-unimind-text-secondary max-w-lg mx-auto mt-4">{pain.subtitle}</p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {pain.items.map((item, i) => {
            const Icon = icons[i];
            return (
              <div
                key={item.title}
                className={cn('reveal p-8 rounded-2xl border border-gray-100 bg-gray-50 hover:bg-white hover:border-gray-200 hover:shadow-sm transition-all duration-300 group', `reveal-delay-${i + 1}`)}
              >
                <div className="h-11 w-11 rounded-xl flex items-center justify-center mb-5 bg-red-500/[0.08]">
                  <Icon className="h-5 w-5 text-red-500" />
                </div>
                <h3 className="text-lg font-bold text-unimind-text mb-3 tracking-tight">{item.title}</h3>
                <p className="text-sm leading-relaxed text-unimind-text-secondary">{item.desc}</p>
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
          className="w-full rounded-2xl border border-border"
          style={{ boxShadow: '0 20px 60px rgba(45,43,107,0.06), 0 4px 16px rgba(0,0,0,0.04)' }}
          onError={() => setUseVideo(false)}
        />
      ) : (
        <img
          src={imgSrc}
          alt={alt}
          className="w-full rounded-2xl border border-border"
          style={{ boxShadow: '0 20px 60px rgba(45,43,107,0.06), 0 4px 16px rgba(0,0,0,0.04)' }}
        />
      )}
    </div>
  );
};

/* ────────────────────────────────────────────
   Product Showcase — LIGHT
   ──────────────────────────────────────────── */

const Showcase: React.FC = () => {
  const items = [
    {
      title: 'AI 智能出题',
      subtitle: 'ARC 对抗管线 · 生成即用',
      desc: '我们采用多智能体对抗生成架构——Author（出题者）、Reviewer（审题者）、Classifier（分类者）三个 AI Agent 围绕同一道题目进行迭代博弈。生成不达标的题目自动回退重做，直至质量评分超过阈值。相比单次 LLM 调用，对抗管线将题目可用率从约 60% 提升至 85%+。支持选择题、计算题、案例分析等全题型，学科不限——金融、法学、医学、CPA，AI 均能按对应学术风格生成。',
      points: [
        'Author → Reviewer → Classifier 三智能体对抗，最多 3 轮迭代',
        '质量阈值自动把关，可用率 85%+',
        '全学科全题型，按学术风格生成',
      ],
      screenshotAlt: 'AI 出题中心页面截图',
    },
    {
      title: 'Memorix 自适应复习',
      subtitle: '论文级遗忘建模，在遗忘前精准推送',
      desc: 'Memorix 是我们自研的记忆调度算法。与传统间隔重复不同，它采用 Weibull 分布替代幂律模型来刻画遗忘曲线——更精确地捕捉「先快后稳」的人类记忆衰减规律。每次作答后，算法通过在线随机梯度下降（SGD with Nesterov Momentum）实时更新 20 维个性化参数，用 Brier 评分校准预测置信度。在我们的 431 金融考试数据集（500+ 用户、12 万条复习日志）上，Memorix 相较 FSRS v4.5 将预测 RMSE 降低了 13.7%，用户知识留存率提升 9.2%。',
      points: [
        'Weibull 遗忘建模 — 比传统幂律模型更贴合真实记忆衰减',
        '在线 SGD + Nesterov 动量 — 每次作答=一次参数自进化',
        'Brier Score 概率校准 — 让「遗忘预测」有数学保证',
        '20 维个性化参数 — 每人独立的记忆画像，而非群体均值',
      ],
      screenshotAlt: '学术天梯页面截图',
    },
    {
      title: '知识工作台',
      subtitle: '可视化知识图谱，掌握度一目了然',
      desc: '每个知识点以彩色节点呈现在交互式知识图谱上——绿色代表已掌握，红色代表薄弱点，灰色代表尚未涉及。点击任意节点即可查看关联题目、错题记录和课程资源。学生能直观看到自己的知识结构，教师能精准定位班级薄弱环节。',
      points: [
        '交互式 SVG 知识图谱',
        '按掌握度着色，薄弱点自动标红',
        '知识点关联题目、错题、课程一键跳转',
      ],
      screenshotAlt: '知识工作台页面截图',
    },
  ] as Array<{ title: string; subtitle: string; desc: string; points: string[]; screenshotAlt: string }>;
  const media = [
    { video: '/demos/demo-question-gen.mp4', img: '/screenshots/ai-generate.png' },
    { video: '/demos/demo-memorix.mp4', img: '/screenshots/memorix-review.png' },
    { video: '/demos/demo-knowledge.mp4', img: '/screenshots/analytics-dashboard.png' },
  ];

  const sectionRef = useRef<HTMLDivElement>(null);
  useMouseParallax(sectionRef, 0.015);

  return (
    <section id="features" ref={sectionRef} className="py-28 md:py-36 px-6 relative overflow-hidden bg-background">
      <div className="max-w-6xl mx-auto relative z-10">
        <div className="reveal mb-20 text-center">
          <p className="text-[10px] font-semibold uppercase tracking-[0.3em] text-xiaoyu-500 mb-4">What We Cover</p>
          <h2 className="text-3xl md:text-5xl font-bold tracking-tight text-foreground">讲课之外，AI 全接管</h2>
          <p className="text-base md:text-lg text-muted-foreground max-w-xl mx-auto mt-4">内容生产、学习交付、数据洞察——三大模块开箱即用，系统自动运转，让你的团队专注招生增长。</p>
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
                <p className="text-xs font-semibold uppercase tracking-[0.2em] text-xiaoyu-500 mb-3">{item.subtitle}</p>
                <h3 className="text-2xl md:text-3xl font-bold tracking-tight text-foreground mb-4">{item.title}</h3>
                <p className="text-sm leading-relaxed text-muted-foreground">{item.desc}</p>
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
   Testimonials — infinite scroll
   ──────────────────────────────────────────── */

const Testimonials: React.FC = () => {
  const items = [
    {
      name: '何老师',
      role: '北京 · 金融 431 培训',
      quote: '说实话刚开始不太信 AI 出的题能用。试了一个月，400 多道题里大概 85% 直接能入库，剩下改改也能用。现在我们教研组主要精力放在讲义和课程打磨上了。',
    },
    {
      name: '周校长',
      role: '成都 · 高中数学连锁（3 校区）',
      quote: '最打动我的是学情看板。三个校区 200 多个学生，哪个知识点薄弱一目了然。以前月考完才发现问题，现在每周都能调。续费率确实有提升，从不到七成到现在八成出头。',
    },
    {
      name: '林主任',
      role: '上海 · CPA 培训机构',
      quote: '我们老师不多，出题一直是瓶颈。UniMind 上手很快，注册当天就开始用了。AI 助教答疑这块学生反馈也不错，半夜问问题也能秒回。',
    },
    {
      name: '吴老师',
      role: '广州 · 法考独立讲师',
      quote: '一个人带 60 多个学生，以前批改主观题要花一整天。现在 AI 先判一遍，我再过一遍，效率快了不少。知识图谱学生很喜欢，说终于知道自己哪里弱了。',
    },
  ] as Array<{ name: string; role: string; quote: string }>;
  const doubled = [...items, ...items];

  return (
    <section className="py-28 md:py-36 overflow-hidden bg-white">
      <div className="max-w-5xl mx-auto px-6 mb-14 text-center reveal">
        <p className="text-[10px] font-semibold uppercase tracking-[0.3em] text-unimind-text-tertiary mb-4">Customer Stories</p>
        <h2 className="text-3xl md:text-4xl font-bold tracking-tight text-unimind-text">来自真实机构的反馈</h2>
      </div>

      <div className="relative">
        {/* Fade edges */}
        <div className="absolute left-0 top-0 bottom-0 w-32 z-10" style={{ background: 'linear-gradient(90deg, #fff, transparent)' }} />
        <div className="absolute right-0 top-0 bottom-0 w-32 z-10" style={{ background: 'linear-gradient(270deg, #fff, transparent)' }} />

        <div className="flex animate-scroll-x" style={{ width: 'max-content' }}>
          {doubled.map((item, i) => (
            <div
              key={`${item.name}-${i}`}
              className="flex-shrink-0 w-[340px] mx-3 p-7 rounded-2xl border border-gray-100 bg-gray-50"
            >
              {/* Brand-colored opening quote */}
              <p className="text-3xl font-bold leading-none mb-2 text-xiaoyu-500">"</p>
              <p className="text-sm leading-relaxed text-unimind-text-secondary mb-5">{item.quote}</p>
              <div className="flex items-center gap-3">
                <div className="h-9 w-9 rounded-full flex items-center justify-center text-sm font-bold text-white bg-xiaoyu-500">
                  {item.name[0]}
                </div>
                <div>
                  <p className="text-sm font-semibold text-unimind-text">{item.name}</p>
                  <p className="text-[11px] text-unimind-text-tertiary">{item.role}</p>
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
  const steps = [
    {
      title: '选择学科',
      desc: '注册机构账号，选择学科方向。系统预置了金融、法学、医学、CPA、CFA、教资等 10+ 学科的知识点框架，也支持自定义导入。',
    },
    {
      title: 'AI 出题',
      desc: '进入 AI 出题中心，选择知识点和题型，AI 三智能体对抗管线自动生成题目。教研负责人审核通过后一键入库。',
    },
    {
      title: '学生练习 + 查看学情',
      desc: '学生通过链接/扫码即可做题，无需下载 App。作答后自动批改，知识工作台实时更新每个人的掌握度图谱。',
    },
    {
      title: '个性化模块搭建',
      desc: '语音互动、智能答疑等深度功能，可根据机构需求按需开通。Enterprise 方案支持定制化部署。',
    },
  ] as Array<{ title: string; desc: string }>;

  return (
    <section className="py-28 md:py-36 px-6 bg-card">
      <div className="max-w-4xl mx-auto">
        <div className="reveal text-center mb-20">
          <p className="text-[10px] font-semibold uppercase tracking-[0.3em] text-xiaoyu-500 mb-4">How It Works</p>
          <h2 className="text-3xl md:text-5xl font-bold tracking-tight text-foreground">四步开始，10 分钟上线</h2>
          <p className="text-sm text-muted-foreground max-w-lg mx-auto mt-4">不需要技术团队，开箱即用。注册、出题、学生做题——按需扩展。</p>
        </div>

        <div className="space-y-0">
          {steps.map((step, i) => (
            <div key={step.title} className={cn('reveal', `reveal-delay-${i + 1}`)}>
              <div className="flex items-start gap-8 py-10">
                {/* Big number */}
                <span className="text-6xl md:text-7xl font-bold shrink-0 leading-none select-none text-xiaoyu-500" style={{ fontFamily: '"DM Mono", monospace' }}>
                  {String(i + 1).padStart(2, '0')}
                </span>
                <div className="pt-1">
                  <h3 className="text-xl font-bold text-foreground mb-2">{step.title}</h3>
                  <p className="text-sm leading-relaxed text-muted-foreground max-w-md">{step.desc}</p>
                </div>
              </div>
              {/* Dashed connector line */}
              {i < steps.length - 1 && (
                <div className="ml-10 md:ml-12 border-l border-dashed border-border h-0" />
              )}
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
  const categories = [
    { name: '考研专业课', tags: ['金融 431', '法学', '医学综合', '计算机 408', '教育学 311', '心理学 312'] },
    { name: '职业资格证', tags: ['CPA', 'CFA', '法考', '执业医师', '教资', '一建', 'USMLE'] },
    { name: '中学学科', tags: ['高中数学', '高中物理', '高中化学', '高中生物'] },
    { name: '公考 / 其他', tags: ['行测', '申论', '公基', '军队文职'] },
  ] as Array<{ name: string; tags: string[] }>;
  const allTags = categories.flatMap(cat => cat.tags);

  return (
    <section id="subjects" className="py-28 md:py-36 px-6 bg-white">
      <div className="max-w-4xl mx-auto text-center">
        <div className="reveal space-y-6">
          <h2 className="text-3xl md:text-5xl font-bold tracking-tight text-unimind-text">你要考的，我们都能出</h2>
          <p className="text-sm text-unimind-text-secondary max-w-lg mx-auto">给它任意学科的知识点，AI 按该学科的风格出题。</p>
        </div>
        <div className="mt-14 flex flex-wrap justify-center gap-2.5 reveal reveal-delay-1">
          {allTags.map((tag) => (
            <span
              key={tag}
              className="text-[13px] font-medium px-4 py-2 rounded-full border border-gray-200 text-unimind-text-secondary hover:text-xiaoyu-500 hover:border-xiaoyu-100 hover:bg-xiaoyu-50 transition-all duration-300 cursor-default"
            >
              {tag}
            </span>
          ))}
        </div>
        <p className="mt-8 text-xs text-unimind-text-quaternary reveal reveal-delay-2">没有你的学科？自定义知识点树，AI 即刻适配。</p>
      </div>
    </section>
  );
};

/* ────────────────────────────────────────────
   Final CTA — DARK
   ──────────────────────────────────────────── */

const FinalCTA: React.FC = () => {
  const navigate = useNavigate();

  return (
    <section className="py-28 md:py-36 px-6 relative overflow-hidden bg-[#0e0e1a]">
      {/* Subtle radial accent */}
      <div className="absolute inset-0 pointer-events-none" style={{ background: 'radial-gradient(ellipse 50% 50% at 50% 50%, rgba(45,43,107,0.08) 0%, transparent 70%)' }} />

      <div className="max-w-3xl mx-auto text-center relative z-10 space-y-8">
        <div className="reveal space-y-5">
          <h2 className="text-3xl md:text-5xl font-bold leading-[1.08] text-white tracking-[-0.02em]">
            准备好，进入智能教育新时代
          </h2>
          <p className="text-sm md:text-base text-white/50 max-w-lg mx-auto leading-relaxed">
            首批机构免费获得 Growth 方案。AI 出题、自适应复习、学情分析——开箱即用。
          </p>
        </div>

        <div className="flex flex-col sm:flex-row items-center justify-center gap-4 reveal reveal-delay-1">
          <Button
            size="lg"
            className="h-12 px-8 text-sm font-bold rounded-xl text-white border-0 bg-xiaoyu-500 hover:bg-xiaoyu-600"
            onClick={() => navigate('/register')}
          >
            免费开始
          </Button>
          <button
            className="text-sm font-medium text-white/40 hover:text-white transition-colors"
            onClick={() => navigate('/pricing')}
          >
            查看方案对比 →
          </button>
        </div>

        <p className="text-xs text-white/20 reveal reveal-delay-2">已有 50+ 机构在使用 UniMind · 活动截止 2026.6.30</p>
      </div>
    </section>
  );
};

/* ────────────────────────────────────────────
   Footer — LIGHT
   ──────────────────────────────────────────── */

const Footer: React.FC = () => {
  const navigate = useNavigate();

  return (
    <footer className="py-12 border-t border-border bg-background">
      <div className="max-w-6xl mx-auto px-6">
        <div className="flex flex-col md:flex-row items-start justify-between gap-8 mb-8">
          <div className="space-y-3">
            <div className="flex items-center gap-3">
              <img src="/Unimind_logo.png" alt="UniMind" className="h-7 w-7 rounded-lg object-contain" loading="lazy" />
              <span className="font-bold text-sm text-foreground tracking-tight">UniMind.ai</span>
            </div>
            <p className="text-[12px] text-muted-foreground">Agent 驱动的智能教育基础设施</p>
          </div>
          <div className="flex items-center gap-8">
            <button onClick={() => document.querySelector('#features')?.scrollIntoView({ behavior: 'smooth' })} className="text-[12px] font-medium text-muted-foreground hover:text-foreground transition-colors">功能</button>
            <button onClick={() => navigate('/pricing')} className="text-[12px] font-medium text-muted-foreground hover:text-foreground transition-colors">定价</button>
            <button onClick={() => navigate('/pricing#faq')} className="text-[12px] font-medium text-muted-foreground hover:text-foreground transition-colors">常见问题</button>
          </div>
        </div>
        <div className="border-t border-border pt-6 flex flex-col md:flex-row items-center justify-between gap-4">
          <p className="text-[10px] font-medium text-muted-foreground">
            © {COPYRIGHT_YEAR} 北京融知高科 · UniMind.ai · {APP_VERSION}
          </p>
          <div className="flex items-center gap-4">
            <a href="https://beian.miit.gov.cn/" target="_blank" rel="noopener noreferrer" className="text-[10px] font-medium text-muted-foreground hover:text-foreground transition-colors">京ICP备2023012726号-2</a>
            <Link to="/terms" className="text-[10px] font-medium text-muted-foreground hover:text-foreground transition-colors">用户协议</Link>
            <Link to="/privacy" className="text-[10px] font-medium text-muted-foreground hover:text-foreground transition-colors">隐私政策</Link>
          </div>
        </div>
      </div>
    </footer>
  );
};

/* ────────────────────────────────────────────
   Main — white with FinalCTA dark anchor
   ──────────────────────────────────────────── */

const ReferralBanner: React.FC = () => {
  const [code, setCode] = useState('');
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    api.get('/payments/referral/').then(({ data }) => setCode(data.code)).catch(() => {});
  }, []);

  if (!code) return null;

  const refLink = `https://unimind-ai.com/register?ref=${code}`;
  const handleCopy = () => {
    navigator.clipboard.writeText(refLink).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }).catch(() => {});
  };

  return (
    <section className="py-16 px-6 bg-xiaoyu-50">
      <div className="max-w-2xl mx-auto text-center space-y-4">
        <h3 className="text-xl font-bold text-foreground">邀请朋友，一起学习</h3>
        <p className="text-muted-foreground">复制你的专属推荐链接，朋友注册后双方都将获得奖励</p>
        <div className="flex items-center justify-center gap-2">
          <code className="bg-white border px-4 py-2 rounded-lg text-sm font-mono text-foreground select-all">{refLink}</code>
          <Button size="sm" onClick={handleCopy} variant="outline">
            {copied ? '已复制' : '复制链接'}
          </Button>
        </div>
      </div>
    </section>
  );
};


export const Landing: React.FC = () => {
  const token = useAuthStore(s => s.token);
  useScrollReveal();

  return (
    <div className="w-full min-h-screen font-sans text-left overflow-x-hidden antialiased scroll-smooth bg-white">
      <Nav token={token} />
      <Hero />
      <StatsBar />            {/* white */}
      <PainPoints />          {/* white */}
      <Showcase />            {/* white */}
      {token && <ReferralBanner />}
      <Testimonials />        {/* white */}
      <HowItWorks />          {/* white */}
      <Subjects />            {/* white */}
      <FinalCTA />            {/* dark anchor */}
      <Footer />              {/* white */}
    </div>
  );
};
