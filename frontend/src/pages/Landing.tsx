import React, { useEffect, useState } from 'react';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
  ArrowRight, Check, ChevronDown, ChevronUp,
  BrainCircuit, BarChart3,
  Globe, Clock, TrendingUp,
  Menu, X, Layers, Gauge, Cpu, Image
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { useNavigate } from 'react-router-dom';
import { useAuthStore } from '../store/useAuthStore';
import { APP_VERSION, COPYRIGHT_YEAR, COPYRIGHT_ENTITY } from '@/constants/version';

/* ────────────────────────────────────────────
   Screenshot component
   Placeholder until real screenshots are provided.
   ──────────────────────────────────────────── */

const Screenshot: React.FC<{
  src: string;
  alt: string;
  className?: string;
}> = ({ src, alt, className }) => {
  if (!src) {
    return (
      <div className={cn(
        'flex flex-col items-center justify-center gap-3 rounded-2xl border border-[#E5E5EA] min-h-[200px]',
        className
      )}>
        <Image className="h-8 w-8 text-[#C7C7CC]" />
        <span className="text-xs font-medium text-[#8E8E93] max-w-[200px] text-center leading-relaxed">
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
    <p className="text-[11px] font-extrabold text-[#0071E3] uppercase tracking-[0.25em] mb-4">
      {label}
    </p>
    <h2 className="text-3xl md:text-4xl lg:text-5xl font-extrabold tracking-tight text-[#1D1D1F] leading-[1.12]">
      {title}
    </h2>
    {subtitle && (
      <p className="mt-5 text-[15px] md:text-base text-[#6E6E73] max-w-2xl mx-auto font-medium leading-relaxed">
        {subtitle}
      </p>
    )}
  </div>
);

/* ────────────────────────────────────────────
   Navigation
   ──────────────────────────────────────────── */

const NAV_ITEMS = [
  { label: '功能', href: '#features' },
  { label: '学科', href: '#subjects' },
  { label: '定价', href: '#pricing' },
  { label: '常见问题', href: '#faq' },
];

const Nav: React.FC<{ token: string | null }> = ({ token }) => {
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

  return (
    <nav className={cn(
      'fixed top-0 left-0 right-0 z-[100] transition-all duration-300',
      scrolled
        ? 'bg-white/80 backdrop-blur-xl border-b border-[#E5E5EA]/60'
        : 'bg-transparent'
    )}>
      <div className="max-w-6xl mx-auto px-6 h-14 flex items-center justify-between">
        <button
          onClick={() => window.scrollTo({ top: 0, behavior: 'smooth' })}
          className="flex items-center gap-2"
        >
          <div className="h-7 w-7 rounded-lg bg-[#0071E3] flex items-center justify-center">
            <Layers className="h-3.5 w-3.5 text-white" strokeWidth={2.5} />
          </div>
          <span className="font-extrabold text-base text-[#1D1D1F] tracking-tight">UniMind</span>
          <span className="text-[11px] font-bold text-[#8E8E93] hidden sm:inline">.ai</span>
        </button>

        <div className="hidden md:flex items-center gap-7">
          {NAV_ITEMS.map(item => (
            <button
              key={item.href}
              onClick={() => scrollTo(item.href)}
              className="text-[13px] font-medium text-[#6E6E73] hover:text-[#1D1D1F] transition-colors"
            >
              {item.label}
            </button>
          ))}
        </div>

        <div className="hidden md:flex items-center gap-3">
          {token ? (
            <Button variant="apple" size="sm" onClick={() => navigate('/')}>进入控制台</Button>
          ) : (
            <>
              <button
                className="text-[13px] font-medium text-[#6E6E73] hover:text-[#1D1D1F] transition-colors"
                onClick={() => navigate('/login')}
              >
                登录
              </button>
              <Button variant="apple" size="sm" onClick={() => navigate('/register')}>
                免费试用
              </Button>
            </>
          )}
        </div>

        <button className="md:hidden p-2 text-[#1D1D1F]" onClick={() => setOpen(!open)}>
          {open ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
        </button>
      </div>

      {open && (
        <div className="md:hidden bg-white border-b border-[#E5E5EA]/60 px-6 pb-6 space-y-3">
          {NAV_ITEMS.map(item => (
            <button
              key={item.href}
              onClick={() => scrollTo(item.href)}
              className="block w-full text-left py-3 text-base font-medium text-[#6E6E73] hover:text-[#1D1D1F]"
            >
              {item.label}
            </button>
          ))}
          <div className="pt-3 border-t border-[#E5E5EA]/60 flex gap-3">
            {token ? (
              <Button className="w-full" variant="apple" onClick={() => { setOpen(false); navigate('/'); }}>
                进入控制台
              </Button>
            ) : (
              <>
                <Button className="flex-1" variant="outline" onClick={() => { setOpen(false); navigate('/login'); }}>
                  登录
                </Button>
                <Button className="flex-1" variant="apple" onClick={() => { setOpen(false); navigate('/register'); }}>
                  免费试用
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
  const navigate = useNavigate();

  return (
    <section className="min-h-[95vh] flex flex-col items-center justify-center pt-20 pb-12 px-6">
      <div className="max-w-4xl mx-auto w-full text-center space-y-7">
        <div className="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-full bg-[#0071E3]/5 border border-[#0071E3]/10">
          <span className="relative flex h-1.5 w-1.5">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-[#0071E3] opacity-60" />
            <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-[#0071E3]" />
          </span>
          <span className="text-[11px] font-extrabold text-[#0071E3] uppercase tracking-[0.15em]">
            培训机构的 AI 基础设施
          </span>
        </div>

        <h1 className="text-4xl md:text-6xl lg:text-[68px] font-extrabold tracking-tightest text-[#1D1D1F] leading-[1.06]">
          你的老师只管讲课
          <br />
          <span className="text-[#0071E3]">
            出题和复习交给 UniMind.AI
          </span>
        </h1>

        <p className="text-base md:text-lg text-[#6E6E73] max-w-2xl mx-auto font-medium leading-relaxed">
          UniMind 是培训机构的 AI 基础设施——接入后即可拥有 AI 出题、Memorix 自适应复习、知识工作台三大核心能力。
          不论你教金融、法学、医学、CPA 还是考研公共课，输入考点，AI 自动出题。
        </p>

        <div className="flex flex-col sm:flex-row items-center justify-center gap-3 pt-4">
          <Button
            variant="apple"
            size="lg"
            className="h-11 px-7 text-sm font-extrabold rounded-xl"
            onClick={() => navigate('/register')}
          >
            免费试用 14 天
            <ArrowRight className="ml-1.5 h-4 w-4" />
          </Button>
          <Button
            variant="apple-outline"
            size="lg"
            className="h-11 px-7 text-sm font-bold rounded-xl"
            onClick={() => document.querySelector('#features')?.scrollIntoView({ behavior: 'smooth' })}
          >
            了解功能
            <ChevronDown className="ml-1 h-4 w-4" />
          </Button>
        </div>

        <p className="text-xs text-[#AEAEB2] font-medium">
          无需绑定信用卡 · 14 天全功能试用 · 学科不限
        </p>

        {/* Hero dashboard preview */}
        <div className="max-w-4xl mx-auto pt-10 reveal">
          <Screenshot
            src="/screenshots/hero-dashboard.png"
            alt="课程中心首页或学术天梯页面全景截图，展示平台主界面"
            className="w-full"
          />
        </div>
      </div>
    </section>
  );
};

/* ────────────────────────────────────────────
   Social Proof — logos or stats
   ──────────────────────────────────────────── */

const StatsBar: React.FC = () => (
  <section className="py-14 border-y border-[#E5E5EA]/60 bg-white">
    <div className="max-w-5xl mx-auto px-6 reveal">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-8 md:gap-12">
        {[
          { label: '支持学科', value: '10+', desc: '考研 · 考证 · 语言全覆盖' },
          { label: 'AI 题目已生成', value: '50,000+', desc: '三智能体对抗保证质量' },
          { label: '入驻机构', value: '50+', desc: '从独立教师到连锁品牌' },
          { label: '出题效率提升', value: '50×', desc: '从 30 分钟到 10 秒' },
        ].map(item => (
          <div key={item.label} className="text-center space-y-1">
            <p className="text-[10px] font-extrabold text-[#AEAEB2] uppercase tracking-[0.25em]">{item.label}</p>
            <p className="text-3xl md:text-4xl font-extrabold text-[#1D1D1F] tracking-tightest">{item.value}</p>
            <p className="text-[11px] font-medium text-[#8E8E93]">{item.desc}</p>
          </div>
        ))}
      </div>
    </div>
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
        label="The Problem"
        title="培训机构最大的三个隐性成本"
        subtitle="不是房租，不是获客，而是被忽视的教研效率、复习效果和数据盲区。"
      />
      <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
        {PAINS.map((item, i) => (
          <Card
            key={item.title}
            variant="apple"
            className={cn('p-8 space-y-4 group cursor-default reveal', `reveal-delay-${i + 1}`)}
          >
            <div className="h-11 w-11 rounded-2xl bg-[#FF3B30]/6 flex items-center justify-center">
              <item.icon className="h-5 w-5 text-[#FF3B30]" />
            </div>
            <h3 className="font-extrabold text-lg text-[#1D1D1F] tracking-tight">{item.title}</h3>
            <p className="text-[14px] text-[#6E6E73] leading-relaxed font-medium">{item.desc}</p>
          </Card>
        ))}
      </div>
    </div>
  </section>
);

/* ────────────────────────────────────────────
   Features — with screenshot placeholders
   ──────────────────────────────────────────── */

const FEATURES = [
  {
    icon: Cpu,
    title: 'AI 智能出题',
    subtitle: 'ARC 对抗管线 · 生成即用',
    desc: '我们采用多智能体对抗生成架构——Author（出题者）、Reviewer（审题者）、Classifier（分类者）三个 AI Agent 围绕同一道题目进行迭代博弈。生成不达标的题目自动回退重做，直至质量评分超过阈值。相比单次 LLM 调用，对抗管线将题目可用率从约 60% 提升至 85%+。支持选择题、计算题、案例分析等全题型，学科不限——金融、法学、医学、CPA，AI 均能按对应学术风格生成。',
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
    desc: 'Memorix 是我们自研的记忆调度算法。与传统间隔重复不同，它采用 Weibull 分布替代幂律模型来刻画遗忘曲线——更精确地捕捉"先快后稳"的人类记忆衰减规律。每次作答后，算法通过在线随机梯度下降（SGD with Nesterov Momentum）实时更新 20 维个性化参数，用 Brier 评分校准预测置信度。在我们的 431 金融考试数据集（500+ 用户、12 万条复习日志）上，Memorix 相较 FSRS v4.5 将预测 RMSE 降低了 13.7%，用户知识留存率提升 9.2%。',
    points: [
      'Weibull 遗忘建模 — 比传统幂律模型更贴合真实记忆衰减',
      '在线 SGD + Nesterov 动量 — 每次作答=一次参数自进化',
      'Brier Score 概率校准 — 让"遗忘预测"有数学保证',
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
    points: ['交互式 SVG 知识图谱', '按掌握度着色，薄弱点自动标红', '知识点关联题目、错题、课程一键跳转'],
    screenshot: '/screenshots/analytics-dashboard.png',
    screenshotAlt: '知识工作台页面截图',
  },
];

const Features: React.FC = () => (
  <section id="features" className="py-24 md:py-32 bg-[#F5F5F7] border-y border-[#E5E5EA]/60">
    <div className="max-w-6xl mx-auto px-6 reveal">
      <SectionHeader
        label="Core Features"
        title="三大核心能力"
        subtitle="AI 出题引擎生成内容，Memorix 算法管理复习节奏，知识工作台呈现学情全貌——从内容生产到学习交付的完整闭环。"
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
            {/* Screenshot */}
            <div className="flex-1 w-full">
              <Screenshot
                src={item.screenshot}
                alt={item.screenshotAlt}
                className="w-full"
              />
            </div>

            {/* Text */}
            <div className="flex-1 space-y-5">
              <div className="h-10 w-10 rounded-2xl bg-[#0071E3]/8 flex items-center justify-center">
                <item.icon className="h-5 w-5 text-[#0071E3]" />
              </div>
              <h3 className="text-2xl md:text-3xl font-extrabold text-[#1D1D1F] tracking-tight">{item.title}</h3>
              <p className="text-sm font-bold text-[#0071E3]">{item.subtitle}</p>
              <p className="text-[15px] text-[#6E6E73] leading-relaxed font-medium">{item.desc}</p>
              <ul className="space-y-2.5">
                {item.points.map(p => (
                  <li key={p} className="flex items-start gap-3 text-sm font-medium text-[#1D1D1F]/80">
                    <Check className="h-4 w-4 text-[#34C759] shrink-0 mt-0.5" />
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
        label="How It Works"
        title="三步开始，10 分钟上线"
        subtitle="不需要技术团队，不需要 AI 工程师。注册 → 出题 → 让学生做题。就这三步。"
      />

      <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
        {STEPS.map((step, i) => (
          <Card key={step.num} variant="apple" className={cn('p-8 space-y-5 relative overflow-hidden group cursor-default reveal', `reveal-delay-${i + 1}`)}>
            <div className="absolute -top-5 -right-5 text-[100px] font-extrabold text-[#F5F5F7] leading-none select-none group-hover:text-[#E8E8ED] transition-colors">
              {step.num}
            </div>
            <div className="relative z-10 space-y-4">
              <div className="h-11 w-11 rounded-2xl bg-[#0071E3]/8 flex items-center justify-center">
                <step.icon className="h-5 w-5 text-[#0071E3]" />
              </div>
              <h3 className="font-extrabold text-lg text-[#1D1D1F] tracking-tight">{step.title}</h3>
              <p className="text-[14px] text-[#6E6E73] leading-relaxed font-medium">{step.desc}</p>
            </div>
          </Card>
        ))}
      </div>
    </div>
  </section>
);

/* ────────────────────────────────────────────
   Multi-Subject
   ──────────────────────────────────────────── */

const SUBJECTS = [
  { name: '考研专业课', tags: ['金融 431', '法学', '医学综合', '计算机 408', '教育学 311', '心理学 312'] },
  { name: '职业资格证', tags: ['CPA', 'CFA', '法考', '执业医师', '教资', '一建'] },
  { name: '语言培训', tags: ['雅思', '托福', '四六级', '考研英语', '小语种'] },
  { name: '公考 / 其他', tags: ['行测', '申论', '公基', '军队文职'] },
];

const Subjects: React.FC = () => (
  <section id="subjects" className="py-24 md:py-32 bg-[#F5F5F7] border-y border-[#E5E5EA]/60">
    <div className="max-w-6xl mx-auto px-6 reveal">
      <SectionHeader
        label="All Subjects"
        title="不限于任何一个学科"
        subtitle={`UniMind 的 AI 引擎本质上是"如何出一道好题"的专家——你给它哪个学科的知识点，它就按那个学科的风格出题。`}
      />

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {SUBJECTS.map((cat, i) => (
          <Card key={cat.name} variant="apple" className={cn('p-6 space-y-4 reveal', `reveal-delay-${i + 1}`)}>
            <h3 className="font-extrabold text-sm text-[#1D1D1F] tracking-tight">{cat.name}</h3>
            <div className="flex flex-wrap gap-1.5">
              {cat.tags.map(tag => (
                <span key={tag} className="text-[11px] font-bold px-2.5 py-1 rounded-lg bg-[#F5F5F7] text-[#6E6E73]">
                  {tag}
                </span>
              ))}
            </div>
          </Card>
        ))}
      </div>

      <p className="text-center mt-10 text-sm text-[#AEAEB2] font-medium">
        没有你的学科？自定义知识点树，AI 即刻适配。
      </p>
    </div>
  </section>
);

/* ────────────────────────────────────────────
   Pricing
   ──────────────────────────────────────────── */

// Each row = same capability across tiers. '—' means not included.
const PLAN_ROWS: string[][] = [
  //  Free                    Solo                    Plus（主推）                    Pro
  // ── 全版本通用 ──
  ['AI 出题 20 次/月',       'AI 出题50次/月',        'AI 出题无限制✨',               'AI 出题无限制✨'],
  ['FSRS 4.5 遗忘算法支持',     '新一代Memorix 自适应复习',   '新一代Memorix 自适应复习',          '新一代Memorix 自适应复习'],
  ['题库管理 · 手动组卷',    '题库管理 · 手动组卷',  '题库管理 · 手动+自动组卷',         '题库管理 · 手动+自动组卷'],
  ['错题复盘中心',           '错题复盘中心',         '错题复盘中心',                '错题复盘中心'],
  ['基础学情统计',           '个人完整学情报告',     '班级对比报表 · 数据导出',     '高级学情看板 · AI 建议'],
  ['30 名学员上限',          '50 名学员上限',        '200 名学员上限',              '学员数不限'],
  ['1 名教师 · 1 个学科',   '1 名教师 · 3 个学科',  '5 名教师 · 不限学科',        '教师 · 学科均不限'],
  // ── Plus 解锁（核心竞争力）──
  ['—',                      '—',                    '课程视频 + AI 大纲打点',      '课程视频 + AI 大纲打点'],
  ['—',                      '—',                    '交互式知识图谱',              '交互式知识图谱'],
  ['—',                      '—',                    '在线答疑系统',                '在线答疑系统'],
  ['—',                      '—',                    '多教师协作 · 权限管理',       '多教师协作 · 权限管理'],
  ['—',                      '—',                    '实时学习房间 · 番茄钟',       '实时学习房间 · 番茄钟'],
  ['—',                      '—',                    'AI 助教 · 多 Bot 对话',       'AI 助教 · 多 Bot 对话'],
  ['—',                      '—',                    '模拟考试',              '模拟考试'],
  ['—',                      '—',                    'AI 模拟面试 · 五维雷达图',   'AI 模拟面试 · 五维雷达图'],
  // ── Pro 独占（企业级）──
  ['—',                      '—',                    '—',                           '品牌定制 · 本地白标部署'],
  ['—',                      '—',                    '—',                           '数据私有化'],
  ['—',                      '—',                    '—',                           '个性化设置'],
  ['—',                      '—',                    '—',                           'REST API 对接'],
  ['—',                      '—',                    '—',                           '专属客户经理一对一服务'],
];

const PLANS = [
  { name: 'Free',  label: 'Free',  desc: '个人教师体验入口', monthly: '¥0',    yearly: '¥0',    cta: '免费注册',       popular: false },
  { name: 'Solo',  label: 'Solo',  desc: '独立教师版',       monthly: '¥299',  yearly: '¥199',  cta: '14 天免费试用',  popular: false },
  { name: 'Plus',  label: 'Plus',  desc: '机构版 · 功能最全', monthly: '¥1,299', yearly: '¥999', cta: '14 天免费试用',  popular: true },
  { name: 'Pro',   label: 'Pro',   desc: '企业版 · 品牌定制', monthly: '¥3,999', yearly: '¥2,999', cta: '预约演示',      popular: false },
];

const Pricing: React.FC = () => {
  const navigate = useNavigate();
  const [annual, setAnnual] = useState(true);

  return (
    <section id="pricing" className="py-24 md:py-32 bg-white">
      <div className="max-w-6xl mx-auto px-6 reveal">
        <SectionHeader
          label="Pricing"
          title="选择适合你的方案"
          subtitle="所有方案均包含 14 天免费试用。无需绑定信用卡。"
        />

        {/* Toggle */}
        <div className="flex items-center justify-center gap-3 mb-12">
          <span className={cn('text-sm font-bold', !annual ? 'text-[#1D1D1F]' : 'text-[#AEAEB2]')}>月付</span>
          <button
            onClick={() => setAnnual(!annual)}
            className={cn(
              'w-11 h-6 rounded-full transition-colors relative',
              annual ? 'bg-[#0071E3]' : 'bg-[#C7C7CC]'
            )}
          >
            <div className={cn(
              'absolute top-0.5 h-5 w-5 rounded-full bg-white shadow transition-transform',
              annual ? 'left-[22px]' : 'left-0.5'
            )} />
          </button>
          <span className={cn('text-sm font-bold flex items-center gap-1.5', annual ? 'text-[#1D1D1F]' : 'text-[#AEAEB2]')}>
            年付
            <Badge variant="apple-green" className="text-[10px]">省 23-33%</Badge>
          </span>
        </div>

        {/* Cards */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 items-start">
          {PLANS.map((plan, pi) => {
            const price = annual && plan.yearly !== '—' ? plan.yearly : plan.monthly;
            return (
              <Card
                key={plan.label}
                variant="apple"
                className={cn(
                  'p-6 flex flex-col space-y-5 reveal',
                  `reveal-delay-${pi + 1}`,
                  plan.popular && 'ring-2 ring-[#0071E3] ring-offset-2'
                )}
              >
                <div className="space-y-1">
                  <div className="flex items-center gap-2">
                    <h3 className="font-extrabold text-base text-[#1D1D1F]">{plan.label}</h3>
                    {plan.popular && (
                      <Badge variant="apple-blue" className="text-[10px] font-extrabold">最受欢迎</Badge>
                    )}
                  </div>
                  <p className="text-[12px] text-[#8E8E93] font-medium">{plan.desc}</p>
                </div>

                <div>
                  <span className="text-3xl font-extrabold text-[#1D1D1F] tracking-tightest">{price}</span>
                  {plan.monthly !== '¥0' && <span className="text-sm font-bold text-[#8E8E93]">/月</span>}
                  {annual && plan.yearly !== '—' && (
                    <p className="text-[11px] font-medium text-[#AEAEB2] mt-1">
                      年付总计 ¥{parseInt(plan.yearly.replace('¥', '')) * 12}
                    </p>
                  )}
                </div>

                <Button
                  variant={plan.popular ? 'apple' : 'apple-outline'}
                  className="w-full h-10 rounded-xl text-sm font-extrabold"
                  onClick={() => navigate('/register')}
                >
                  {plan.cta}
                </Button>

                <ul className="space-y-1.5 flex-1">
                  {PLAN_ROWS.map((row, ri) => {
                    const text = row[pi];
                    const has = text !== '—';
                    return (
                      <li key={ri} className={cn(
                        'flex items-start gap-2 text-[12px] font-medium',
                        has ? 'text-[#1D1D1F]/70' : 'text-[#C7C7CC]'
                      )}>
                        {has
                          ? <Check className="h-3.5 w-3.5 text-[#34C759] shrink-0 mt-0.5" />
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

        <p className="text-center mt-8 text-xs text-[#AEAEB2] font-medium">
          前 20 个付费客户锁定早期用户价格，终身不涨价。
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
  { q: '和通用考试工具有什么区别？', a: '通用考试工具是"把纸质考试搬到线上"。UniMind 是"AI 帮你生产和优化教学内容"——出题是 AI 自动生成的、复习是算法个性化的、学情是实时可视化的。我们解决的不是"怎么考"，而是"怎么教和怎么学"。' },
  { q: '我是个人教师，适合哪个版本？', a: '建议从 Free 版开始。30 个学生、每月 50 次 AI 出题足够日常使用。当你学生超过 30 人或需要更多出题次数时，升级到 Solo 版（¥299/月，年付 ¥199/月）。' },
];

const FAQ: React.FC = () => {
  const [openIdx, setOpenIdx] = useState<number | null>(null);

  return (
    <section id="faq" className="py-24 md:py-32 bg-[#F5F5F7] border-y border-[#E5E5EA]/60">
      <div className="max-w-3xl mx-auto px-6 reveal">
        <SectionHeader label="FAQ" title="常见问题" />
        <div className="space-y-2">
          {FAQS.map((faq, i) => (
            <Card key={i} variant="apple" className="overflow-hidden transition-all duration-200">
              <button
                onClick={() => setOpenIdx(openIdx === i ? null : i)}
                className="w-full px-5 py-4 flex items-center justify-between text-left gap-4"
              >
                <span className="font-extrabold text-[14px] text-[#1D1D1F]">{faq.q}</span>
                {openIdx === i
                  ? <ChevronUp className="h-4 w-4 text-[#AEAEB2] shrink-0" />
                  : <ChevronDown className="h-4 w-4 text-[#AEAEB2] shrink-0" />
                }
              </button>
              {openIdx === i && (
                <div className="px-5 pb-4">
                  <p className="text-[13px] text-[#6E6E73] leading-relaxed font-medium">{faq.a}</p>
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
  const navigate = useNavigate();
  return (
    <section className="py-24 md:py-32 bg-white">
      <div className="max-w-3xl mx-auto px-6 text-center space-y-8 reveal">
        <h2 className="text-3xl md:text-5xl font-extrabold tracking-tightest text-[#1D1D1F] leading-[1.12]">
          你的机构准备好 AI 化了吗？
        </h2>
        <p className="text-base md:text-lg text-[#6E6E73] font-medium leading-relaxed max-w-xl mx-auto">
          14 天全功能免费试用。不绑卡，不收费。学科不限。
          看看 AI 能为你的机构省下多少出题时间。
        </p>
        <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
          <Button
            variant="apple"
            size="lg"
            className="h-11 px-7 text-sm font-extrabold rounded-xl"
            onClick={() => navigate('/register')}
          >
            免费试用 14 天
            <ArrowRight className="ml-1.5 h-4 w-4" />
          </Button>
        </div>
        <p className="text-xs text-[#AEAEB2] font-medium">
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
  <footer className="py-12 bg-[#F5F5F7] border-t border-[#E5E5EA]/60">
    <div className="max-w-6xl mx-auto px-6 reveal">
      <div className="flex flex-col md:flex-row items-center justify-between gap-6">
        <div className="flex items-center gap-3">
          <div className="h-8 w-8 rounded-lg bg-[#0071E3] flex items-center justify-center">
            <Layers className="h-4 w-4 text-white" strokeWidth={2.5} />
          </div>
          <div className="leading-tight">
            <p className="font-extrabold text-sm text-[#1D1D1F] tracking-tight">UniMind.ai</p>
            <p className="text-[10px] font-bold text-[#AEAEB2] uppercase tracking-[0.1em]">培训机构的 AI 基础设施</p>
          </div>
        </div>
        <div className="flex items-center gap-6">
          <a href="#features" className="text-[12px] font-medium text-[#8E8E93] hover:text-[#1D1D1F] transition-colors">功能</a>
          <a href="#pricing" className="text-[12px] font-medium text-[#8E8E93] hover:text-[#1D1D1F] transition-colors">定价</a>
          <a href="#faq" className="text-[12px] font-medium text-[#8E8E93] hover:text-[#1D1D1F] transition-colors">常见问题</a>
        </div>
        <p className="text-[10px] font-medium text-[#AEAEB2]">
          © {COPYRIGHT_YEAR} {COPYRIGHT_ENTITY} · {APP_VERSION}
        </p>
      </div>
    </div>
  </footer>
);

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

    // Small delay ensures all DOM nodes are painted before querying
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
