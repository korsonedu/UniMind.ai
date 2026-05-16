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
    { label: '功能', href: '#features' },
    { label: '学科', href: '#subjects' },
    { label: '定价', href: '#pricing' },
    { label: '常见问题', href: '#faq' },
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
            href="/en"
            className="text-sm font-medium text-[#94A3B8] hover:text-[#0F1729] transition-colors p-2 rounded-lg hover:bg-[#F8FAFC]"
            title="Switch to English"
          >
            <Languages className="h-4 w-4" />
          </a>
          {token ? (
            <button
              className="text-sm font-semibold text-white bg-[#0F1729] hover:bg-[#1E293B] px-4 py-2 rounded-xl transition-all shadow-sm"
              onClick={() => navigate('/home')}
            >
              进入控制台
            </button>
          ) : (
            <>
              <button
                className="text-sm font-medium text-[#475569] hover:text-[#0F1729] transition-colors"
                onClick={() => navigate('/login')}
              >
                登录
              </button>
              <button
                className="text-sm font-semibold text-white bg-[#2563EB] hover:bg-[#1D4ED8] px-4 py-2 rounded-xl transition-all shadow-sm shadow-[#2563EB]/20"
                onClick={() => navigate('/register')}
              >
                免费试用
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
            <span className="text-xs font-semibold text-[#94A3B8] uppercase tracking-[0.15em]">中文</span>
            <a
              href="/en"
              className="flex items-center gap-1.5 text-xs font-semibold text-[#2563EB] bg-[#2563EB]/6 px-3 py-1.5 rounded-lg"
            >
              <Languages className="h-3.5 w-3.5" />
              Switch to English
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
                进入控制台
              </button>
            ) : (
              <>
                <button
                  className="flex-1 text-sm font-semibold text-[#0F1729] border border-[#E2E8F0] py-3 rounded-xl"
                  onClick={() => { setOpen(false); navigate('/login'); }}
                >
                  登录
                </button>
                <button
                  className="flex-1 text-sm font-semibold text-white bg-[#2563EB] py-3 rounded-xl shadow-sm"
                  onClick={() => { setOpen(false); navigate('/register'); }}
                >
                  免费试用
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
            培训机构的 AI 运营系统
          </span>
        </div>

        <h1 className="text-4xl md:text-6xl lg:text-[68px] font-bold tracking-tight text-[#0F1729] leading-[1.06]">
          你的老师只管讲课
          <br />
          <span className="bg-gradient-to-r from-[#2563EB] to-[#4F46E5] bg-clip-text text-transparent">
            其他的交给 UniMind.AI
          </span>
        </h1>

        <p className="text-lg text-[#475569] max-w-2xl mx-auto leading-relaxed">
          出题组卷、智能复习、学情分析、在线答疑、自习室、模考、知识图谱——UniMind 是培训机构的 AI 全栈运营系统。老师只需要站上讲台，剩下的我们全包。不论你教金融、法学、医学、CPA 还是考研公共课，一个平台全部搞定。
        </p>

        <div className="flex flex-col sm:flex-row items-center justify-center gap-3 pt-4">
          <button
            className="h-12 px-8 text-sm font-semibold text-white bg-[#2563EB] hover:bg-[#1D4ED8] rounded-xl shadow-lg shadow-[#2563EB]/20 transition-all hover:shadow-xl hover:shadow-[#2563EB]/25 hover:-translate-y-0.5"
            onClick={() => navigate('/register')}
          >
            免费试用 14 天
            <ArrowRight className="ml-1.5 h-4 w-4 inline" />
          </button>
          <button
            className="h-12 px-8 text-sm font-semibold text-[#0F1729] border border-[#E2E8F0] hover:border-[#CBD5E1] hover:bg-[#F8FAFC] rounded-xl transition-all"
            onClick={() => document.querySelector('#features')?.scrollIntoView({ behavior: 'smooth' })}
          >
            了解功能
            <ChevronDown className="ml-1.5 h-4 w-4 inline" />
          </button>
        </div>

        <p className="text-sm text-[#94A3B8] font-medium">
          无需绑定信用卡 · 14 天全功能试用 · 学科不限
        </p>

        <div className="max-w-4xl mx-auto pt-10 reveal">
          <Screenshot
            src="/screenshots/hero-dashboard.png"
            alt="课程中心首页 / 学术天梯页面全景截图"
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
  { label: '支持学科', value: '10+' },
  { label: 'AI 题目已生成', value: '50,000+' },
  { label: '入驻机构', value: '50+' },
  { label: '出题效率提升', value: '50×' },
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
    title: '出题太慢',
    desc: '一道好题 = 选题材 + 编题干 + 写选项 + 写解析。老师一道题花 30 分钟，一套卷子要一整天。',
  },
  {
    icon: BrainCircuit,
    title: '复习太笨',
    desc: '所有学生刷同一套题。学霸浪费时间在已掌握的知识上，薄弱生在新知识面前无效挣扎。',
  },
  {
    icon: TrendingUp,
    title: '数据太盲',
    desc: '月底翻 Excel 才看到正确率。哪个学生在哪个知识点反复出错？不知道。等到发现，考试已过。',
  },
];

const PainPoints: React.FC = () => (
  <section className="py-24 md:py-32 bg-white">
    <div className="max-w-6xl mx-auto px-6 reveal">
      <SectionHeader
        label="痛点"
        title="培训机构最大的三个隐性成本"
        subtitle="不是房租，不是获客，而是被忽视的教研效率、复习效果和数据盲区。"
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
    title: 'AI 智能出题',
    subtitle: 'ARC 对抗管线 · 生成即用',
    desc: '我们采用多智能体对抗生成架构——Author、Reviewer、Classifier 三个 AI Agent 围绕同一道题目进行迭代博弈。生成不达标的题目自动回退重做，直至质量评分超过阈值。相比单次 LLM 调用，对抗管线将题目可用率从约 60% 提升至 85%+。支持选择题、计算题、案例分析等全题型，学科不限。',
    points: [
      'Author → Reviewer → Classifier 三智能体对抗，最多 3 轮迭代',
      '质量阈值自动把关，可用率 85%+',
      '全学科全题型，按学术风格生成',
    ],
    screenshot: '/screenshots/ai-generate.png',
    screenshotAlt: 'AI 出题中心页面截图',
  },
  {
    icon: Gauge,
    title: 'Memorix 自适应复习',
    subtitle: '论文级遗忘建模，在遗忘前精准推送',
    desc: 'Memorix 是我们自研的记忆调度算法。采用 Weibull 分布替代幂律模型来刻画遗忘曲线，更精确地捕捉人类记忆衰减规律。每次作答后，算法通过在线随机梯度下降实时更新 20 维个性化参数，用 Brier 评分校准预测置信度。相较 FSRS v4.5 将预测 RMSE 降低 13.7%，用户知识留存率提升 9.2%。',
    points: [
      'Weibull 遗忘建模 — 比传统幂律模型更贴合真实记忆衰减',
      '在线 SGD + Nesterov 动量 — 每次作答 = 一次参数自进化',
      'Brier Score 概率校准 — 让遗忘预测有数学保证',
      '20 维个性化参数 — 每人独立的记忆画像，而非群体均值',
    ],
    screenshot: '/screenshots/memorix-review.png',
    screenshotAlt: '学术天梯页面截图',
  },
  {
    icon: BarChart3,
    title: '知识工作台',
    subtitle: '可视化知识图谱，掌握度一目了然',
    desc: '每个知识点以彩色节点呈现在交互式知识图谱上——绿色代表已掌握，红色代表薄弱点，灰色代表尚未涉及。点击任意节点即可查看关联题目、错题记录和课程资源。学生能直观看到自己的知识结构，教师能精准定位班级薄弱环节。',
    points: [
      '交互式 SVG 知识图谱',
      '按掌握度着色，薄弱点自动标红',
      '知识点关联题目、错题、课程一键跳转',
    ],
    screenshot: '/screenshots/analytics-dashboard.png',
    screenshotAlt: '知识工作台页面截图',
  },
];

const Features: React.FC = () => (
  <section id="features" className="py-24 md:py-32 bg-[#F8FAFC] border-y border-[#E2E8F0]/60">
    <div className="max-w-6xl mx-auto px-6 reveal">
      <SectionHeader
        label="核心能力"
        title="教学以外，我们全包"
        subtitle="AI 出题、智能组卷、自适应复习、在线答疑、自习室、模考系统、知识图谱——老师只需站上讲台，剩下的全部交给我们。"
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
  { num: '1', icon: Globe, title: '选择学科', desc: '注册机构账号，选择学科方向。系统预置了考研、考证、语言等 10+ 学科的知识点框架，也支持自定义。' },
  { num: '2', icon: Cpu, title: 'AI 出题', desc: '进入 AI 出题中心，选择知识点和题型，AI 三智能体对抗管线自动生成题目。审核通过后一键入库。' },
  { num: '3', icon: BarChart3, title: '学生练习 + 查看学情', desc: '学生通过微信链接即可做题，无需下载 App。作答后自动批改，知识工作台实时更新每个人的掌握度图谱。' },
];

const HowItWorks: React.FC = () => (
  <section className="py-24 md:py-32 bg-white">
    <div className="max-w-6xl mx-auto px-6 reveal">
      <SectionHeader
        label="使用流程"
        title="三步开始，10 分钟上线"
        subtitle="不需要技术团队，不需要 AI 工程师。注册 → 出题 → 让学生做题。就这三步。"
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
  { value: '90%', label: '出题时间节省', desc: '从 30 分钟降至不到 3 分钟' },
  { value: '85%+', label: '题目一次可用率', desc: 'ARC 对抗管线质量把关' },
  { value: '+9.2%', label: '学生知识留存率', desc: 'Memorix 较传统间隔重复' },
  { value: '50+', label: '机构已接入', desc: '从独立教师到连锁品牌' },
];

const INSTITUTION_LOGOS = [
  '金融 431 考研', '法学硕士联考', 'CPA 培训机构', 'CFA 培训机构',
  '医学综合考研', '教资培训', '雅思/托福', '公考培训',
];

const TESTIMONIALS = [
  {
    quote: '以前一套卷子要教研坐一整天。现在 AI 出题 10 分钟搞定初稿，教研只需做最后审校。学生错题数据实时同步，老师第一时间知道班级薄弱点在哪。',
    author: '某金融考研机构教学总监',
    meta: '金融 431 · 200+ 学员',
    highlight: '出题时间节省 90%',
  },
  {
    quote: 'Memorix 的记忆算法是我们选 UniMind 的关键。同样刷 100 道题，用自适应复习的学生知识留存明显更高——续费率就是最好的证明。',
    author: '某连锁考研品牌联合创始人',
    meta: '多学科 · 500+ 学员',
    highlight: '续费率提升 23%',
  },
  {
    quote: '以前管理不同学科老师用一个 Excel 到处发。现在 UniMind 分学科权限、出题、布置作业、看学情——一个平台全搞定。',
    author: '某职业教育机构校长',
    meta: '职业资格证 · 300+ 学员',
    highlight: '管理效率提升 10×',
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
        label="客户成果"
        title="了解我们的解决方案如何带来实际成效"
        subtitle="不是 PPT 数据，来自真实机构的实际使用反馈。"
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
          覆盖学科类型
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
  { name: '考研专业课', tags: ['金融 431', '法学', '医学综合', '计算机 408', '教育学 311', '心理学 312'] },
  { name: '职业资格证', tags: ['CPA', 'CFA', '法考', '执业医师', '教资', '一建'] },
  { name: '语言培训', tags: ['雅思', '托福', '四六级', '考研英语', '小语种'] },
  { name: '公考 / 其他', tags: ['行测', '申论', '公基', '军队文职'] },
];

const Subjects: React.FC = () => (
  <section id="subjects" className="py-24 md:py-32 bg-white">
    <div className="max-w-6xl mx-auto px-6 reveal">
      <SectionHeader
        label="全学科覆盖"
        title="不限于任何一个学科"
        subtitle="UniMind 的 AI 引擎本质上是「如何出一道好题」的专家——你给它哪个学科的知识点，它就按那个学科的风格出题。"
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
        没有你的学科？自定义知识点树，AI 即刻适配。
      </p>
    </div>
  </section>
);

/* ────────────────────────────────────────────
   Pricing — ¥ CNY
   ──────────────────────────────────────────── */

const PLANS = [
  {
    name: 'Free',
    desc: '零成本体验，适合个人教师验证效果',
    monthly: '¥0',
    yearly: '¥0',
    cta: '免费注册',
    popular: false,
    features: [
      'AI 出题 20 次/月',
      '视频课程',
      '基础题库 · 手动组卷',
      '错题复盘中心',
      '基础学情统计',
      '30 名学员 · 1 名教师',
    ],
  },
  {
    name: 'Solo',
    desc: '独立教师的完整 AI 工具箱',
    monthly: '¥299',
    yearly: '¥199',
    cta: '14 天免费试用',
    popular: false,
    features: [
      'AI 出题无限制',
      '智能组卷 · 自动生成',
      'Memorix 自适应复习',
      '交互式知识图谱',
      'AI 学习助手 · 多 Bot',
      'AI 智能大纲生成',
      '个人完整学情报告',
      '50 名学员 · 1 名教师',
    ],
  },
  {
    name: 'Plus',
    desc: '成长型机构的教学管理平台',
    monthly: '¥1,299',
    yearly: '¥999',
    cta: '14 天免费试用',
    popular: true,
    features: [
      '含 Solo 全部功能',
      '在线答疑系统',
      '多教师协作 · 权限管理',
      '实时自习室 · 番茄钟',
      'PDF 个性化模考',
      'AI 模拟面试 · 五维雷达图',
      '班级对比报表 · 数据导出',
      '200 名学员 · 5 名教师',
    ],
  },
  {
    name: 'Pro',
    desc: '企业级旗舰方案，满足规模化与定制需求',
    monthly: '¥3,999',
    yearly: '¥2,999',
    cta: '预约演示',
    popular: false,
    features: [
      '含 Plus 全部功能',
      '学员数不限 · 教师数不限',
      '品牌定制 · 白标部署',
      '私有化部署 · 数据主权',
      'API 接入 · 系统集成',
      '多语言 · 国际化支持',
      '开源组件 · 二次开发',
      'SSO · SAML 单点登录',
      '审计日志 · 合规就绪',
      '专属客户成功经理',
      'SLA 99.9% 可用性保障',
      '学生端收费 · 自主定价',
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
          label="定价"
          title="选择适合你的方案"
          subtitle="所有方案均包含 14 天免费试用。无需绑定信用卡。可随时升级或降级。"
        />

        <div className="flex items-center justify-center gap-4 mb-12">
          <span className={cn('text-sm font-semibold', !annual ? 'text-[#0F1729]' : 'text-[#94A3B8]')}>月付</span>
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
            年付 <span className="text-[#22C55E] text-xs font-bold ml-1">省 23-33%</span>
          </span>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-5 items-stretch">
          {PLANS.map((plan, pi) => {
            const price = annual && plan.yearly !== '¥0' ? plan.yearly : plan.monthly;
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
                    最受欢迎
                  </div>
                )}

                <div className="mb-4 mt-1">
                  <h3 className={cn('text-lg font-bold tracking-tight', plan.popular ? 'text-[#2563EB]' : 'text-[#0F1729]')}>{plan.name}</h3>
                  <p className="text-xs text-[#94A3B8] font-medium mt-1">{plan.desc}</p>
                </div>

                <div className="mb-5">
                  <span className="text-4xl font-bold text-[#0F1729] tracking-tight">{price}</span>
                  {plan.monthly !== '¥0' && <span className="text-sm font-semibold text-[#94A3B8] ml-0.5">/月</span>}
                  {annual && plan.yearly !== '¥0' && (
                    <p className="text-xs text-[#94A3B8] mt-1">
                      年付 ¥{parseInt(plan.yearly.replace('¥', '')) * 12}
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
          所有方案均包含 14 天全功能试用。可随时升级、降级或取消。
        </p>
      </div>
    </section>
  );
};

/* ────────────────────────────────────────────
   FAQ
   ──────────────────────────────────────────── */

const FAQS = [
  { q: '免费版有什么限制？', a: '免费版支持 30 名学员、每月 50 次 AI 出题。你能完整地体验出题→学生做题→看学情数据的闭环，足够一个小班验证产品效果。当需要更多学生或更多出题次数时，升级到 Solo 版即可解锁全部限制。' },
  { q: 'AI 出的题质量能保证吗？', a: '我们采用三智能体对抗机制——一个出题、一个审题、一个分类。质量不达标的题目会自动打回重做。建议机构教研负责人对 AI 生成的题目做最终审阅——AI 帮你省掉 90% 的初稿时间，最后 10% 的审核仍需你的专业判断。' },
  { q: '支持哪些学科？', a: '平台本身不限制学科。我们预置了考研专业课（金融/法学/医学/计算机等）、职业资格证（CPA/CFA/法考/教资等）、语言培训（雅思/托福/四六级）、公考等方向的知识点框架。你也可以自定义学科和知识点树。' },
  { q: '学生怎么使用？需要下载 App 吗？', a: '不需要。学生用微信打开你分享的链接就能做题。我们提供的是 H5/小程序体验，学生端零门槛。' },
  { q: '试用到期后数据还在吗？', a: '在。你所有的题目、学生数据、学习记录都会保留。续费后立即恢复访问。不续费的话数据只读，你不会丢失任何东西。' },
  { q: '可以月付吗？', a: '可以。月付和年付都支持。年付有 23-33% 的折扣。建议先月付一个月深度体验，确认产品适合你的机构后再转年付省钱。' },
  { q: '和通用考试工具有什么区别？', a: '通用考试工具是「把纸质考试搬到线上」。UniMind 是「AI 帮你生产和优化教学内容」——出题是 AI 自动生成的、复习是算法个性化的、学情是实时可视化的。我们解决的不是「怎么考」，而是「怎么教和怎么学」。' },
  { q: '我是个人教师，适合哪个版本？', a: '建议从 Free 版开始。30 个学生、每月 50 次 AI 出题足够日常使用。当你学生超过 30 人或需要更多出题次数时，升级到 Solo 版（¥299/月，年付 ¥199/月）。' },
];

const FAQ: React.FC = () => {
  const [openIdx, setOpenIdx] = useState<number | null>(null);

  return (
    <section id="faq" className="py-24 md:py-32 bg-white">
      <div className="max-w-3xl mx-auto px-6 reveal">
        <SectionHeader label="常见问题" title="常见问题" />
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
          老师只管讲课，剩下的交给我们
        </h2>
        <p className="text-lg text-[#94A3B8] leading-relaxed max-w-xl mx-auto">
          14 天全功能免费试用。不绑卡，不收费。学科不限。出题、组卷、复习、答疑、学情——全部交给 AI，老师只负责教学。
        </p>
        <button
          className="h-12 px-8 text-sm font-semibold text-white bg-[#2563EB] hover:bg-[#1D4ED8] rounded-xl shadow-lg shadow-[#2563EB]/30 transition-all hover:shadow-xl hover:-translate-y-0.5"
          onClick={() => navigate('/register')}
        >
          免费试用 14 天
          <ArrowRight className="ml-1.5 h-4 w-4 inline" />
        </button>
        <p className="text-sm text-[#64748B] font-medium">
          已有 50+ 机构在使用 UniMind
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
            <p className="text-xs font-medium text-[#94A3B8]">培训机构的 AI 运营系统</p>
          </div>
        </div>
        <div className="flex items-center gap-6">
          <a href="#features" className="text-sm font-medium text-[#64748B] hover:text-[#0F1729] transition-colors">功能</a>
          <a href="#pricing" className="text-sm font-medium text-[#64748B] hover:text-[#0F1729] transition-colors">定价</a>
          <a href="#faq" className="text-sm font-medium text-[#64748B] hover:text-[#0F1729] transition-colors">常见问题</a>
        </div>
        <p className="text-xs font-medium text-[#94A3B8]">
          &copy; {COPYRIGHT_YEAR} {COPYRIGHT_ENTITY} · {APP_VERSION}
        </p>
      </div>
    </div>
  </footer>
);

/* ────────────────────────────────────────────
   Main Landing — Chinese
   ──────────────────────────────────────────── */

export const LandingZh: React.FC = () => {
  const { token } = useAuthStore();

  useEffect(() => {
    document.documentElement.lang = 'zh-CN';
    document.title = 'UniMind.ai — 培训机构的 AI 运营系统 | 老师只管讲课，剩下的交给我们';
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
