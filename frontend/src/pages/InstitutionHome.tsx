import React, { useEffect, useRef, useState } from 'react';
import { useParams } from 'react-router-dom';
import { ArrowUpRight, Loader2 } from 'lucide-react';
import { cn } from '@/lib/utils';
import { APP_VERSION, COPYRIGHT_YEAR, COPYRIGHT_ENTITY } from '@/constants/version';
import { useAuthStore } from '@/store/useAuthStore';
import { useInstitutionStore } from '@/store/useInstitutionStore';
import api from '@/lib/api';

interface InstitutionData {
  id: number;
  name: string;
  slug: string;
  description: string;
  logo_url: string | null;
}

/* ──────────────────────────────────────────────────
   BRUTALIST InstitutionHome — 机构课程介绍页
   受众：学生。卖机构课程，不卖 UniMind 平台。
   内容为模板，按机构定制。
   ────────────────────────────────────────────────── */

const useReveal = () => {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const obs = new IntersectionObserver(
      (entries) => entries.forEach(e => { if (e.isIntersecting) e.target.classList.add('on'); }),
      { threshold: 0.08 }
    );
    el.querySelectorAll('.rv').forEach(c => obs.observe(c));
    return () => obs.disconnect();
  }, []);
  return ref;
};

const BrutalLabel: React.FC<{ text: string }> = ({ text }) => (
  <span className="font-mono text-[14px] font-black text-[#FF3333] uppercase tracking-[0.2em] border-b-2 border-[#FF3333] pb-1 inline-block mb-6">
    {text}
  </span>
);

/* ──────────────────────────────────────────────────
   HERO
   ────────────────────────────────────────────────── */
const UNIMIND_BASE = 'https://unimind-ai.com';

const Hero: React.FC<{ institution: InstitutionData }> = ({ institution }) => {
  const registerUrl = `${UNIMIND_BASE}/register?institution=${institution.slug}`;

  return (
    <section className="relative bg-white pt-16 md:pt-28 pb-16 md:pb-24">
      <div className="max-w-[1200px] mx-auto px-6 md:px-12 lg:px-16">
        <div className="flex flex-col lg:flex-row gap-12 lg:gap-0">
          {/* LEFT */}
          <div className="flex-1 lg:pr-16 space-y-8">
            <div className="flex items-center gap-3">
              <span className="h-2 w-2 bg-[#FF3333]" />
              <span className="font-mono text-[14px] font-black text-[#FF3333] uppercase tracking-[0.2em]">
                2027 Enrollment
              </span>
            </div>

            <div className="space-y-2">
              {institution.logo_url && (
                <img src={institution.logo_url} alt={institution.name} className="h-16 md:h-20 w-auto object-contain mb-2" />
              )}
              <h1 className="font-mono text-[clamp(3rem,7vw,5.5rem)] font-black text-black uppercase leading-[0.9]">
                {institution.name}
              </h1>
              {institution.description && (
                <p className="font-mono text-xl md:text-2xl font-bold text-[#999] uppercase tracking-wide">
                  {institution.description}
                </p>
              )}
            </div>

            <p className="font-sans text-base md:text-base text-[#555] max-w-[500px] leading-relaxed font-medium">
              分模块购买 · 自由组合 · 按需选择<br />
              自建 <strong className="text-black font-extrabold border-b-2 border-[#FF3333]">UniMind.ai</strong> ——
              AI 导师 + 自适应学习 + 教研中台
            </p>

            <div className="flex flex-wrap items-end gap-x-12 gap-y-5 pt-2">
              <div>
                <p className="font-mono text-[14px] font-black text-[#999] uppercase tracking-[0.2em] mb-1.5">
                  全科全程班 · 早鸟价
                </p>
                <div className="flex items-baseline gap-3">
                  <span className="font-mono text-lg font-bold text-[#CCC] line-through">¥9,799</span>
                  <span className="font-mono text-[clamp(2.2rem,4.5vw,3.5rem)] font-black text-black leading-none">
                    ¥8,150
                  </span>
                </div>
              </div>
              <div className="flex gap-2.5 pb-0.5">
                <a
                  href={registerUrl}
                  className="font-mono text-sm font-black text-white bg-black border-2 border-black px-7 py-3 uppercase hover:bg-[#FF3333] hover:border-[#FF3333] inline-block"
                >
                  立即报名 <ArrowUpRight className="ml-1.5 h-4 w-4 inline" />
                </a>
                <button
                  onClick={() => document.querySelector('#courses')?.scrollIntoView({ behavior: 'smooth' })}
                  className="font-mono text-sm font-black text-black border-2 border-black px-7 py-3 uppercase hover:bg-black hover:text-white"
                >
                  了解更多
                </button>
              </div>
            </div>
          </div>

          {/* RIGHT — stat cards */}
          <div className="lg:w-[320px] shrink-0">
            <div className="grid grid-cols-2 border-2 border-black">
              {[
                { v: '7 年', l: '连续辅导', sub: '始于 2019', accent: true },
                { v: '200+', l: '累计学员', sub: '全程班' },
                { v: '20+', l: '400+ 高分', sub: '学员' },
                { v: '30+', l: '专业课', sub: '120+ 分' },
              ].map(({ v, l, sub, accent }) => (
                <div key={l} className={cn(
                  'p-5 border-black border-r-2 border-b-2',
                  'even:border-r-0',
                  '[&:nth-child(3)]:border-b-0 [&:nth-child(4)]:border-b-0',
                )}>
                  <p className={cn(
                    'font-mono text-[28px] font-black leading-none',
                    accent ? 'text-[#FF3333]' : 'text-black',
                  )}>{v}</p>
                  <p className="font-mono text-[14px] font-black text-[#999] uppercase tracking-wider mt-1">{l}</p>
                  <p className="font-mono text-[14px] font-bold text-[#BBB] mt-0.5">{sub}</p>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </section>
  );
};

/* ──────────────────────────────────────────────────
   COURSES — 机构课程内容
   ────────────────────────────────────────────────── */
const MODULES = [
  { title: '货币经济学', tag: '约 40% 课时 · 绝对核心',
    items: [
      ['货币金融 / 货币银行学', '黄达、Mishkin、易纲、蒋先玲、胡庆康等经典教材，覆盖 431 全部考点。引入 Dornbusch、Romer、Walsh 进阶内容。'],
      ['国际金融学', '奚君羊、姜波克、Krugman。聚焦实际经济现象的理论分析框架讲授。'],
    ]},
  { title: '金融理论', tag: '约 40% 课时 · 绝对核心',
    items: [
      ['传统金融理论', 'Ross《公司理财》、Bodie《投资学》。原理讲解 + 答题框架梳理，兼顾主客观题。'],
      ['现代金融理论', 'Hull 衍生品定价。聚焦《核心算力》，重点训练几类答题框架。'],
    ]},
  { title: '习题训练', tag: '180+ 题 · Memorix 算法驱动',
    items: [
      ['核心算力 + 独家题库', '历年真题、姜波克习题、Krugman / Ross / Bodie test bank 独家翻译版。'],
      ['UniMind 智能训练', 'Memorix 自适应调度，在 UniMind 或纸质材料完成。'],
    ]},
  { title: '数字化与答疑', tag: 'AI 融入 · UniMind 驱动',
    items: [
      ['AI 实时跟踪', '视频、文章、习题、学习进度由 AI 动态调优学习路径。'],
      ['公开答疑系统', '列表式公开答疑，限时落实，并可沉淀为集体知识。'],
    ]},
];

const CourseContent: React.FC = () => {
  const ref = useReveal();
  return (
    <section id="courses" className="py-20 md:py-28 bg-[#FAFAFA] border-y-2 border-black" ref={ref}>
      <div className="max-w-[1200px] mx-auto px-6 md:px-12 lg:px-16">
        <div className="flex flex-col md:flex-row md:items-end md:justify-between gap-5 mb-12 rv">
          <div className="space-y-3">
            <BrutalLabel text="2027 Curriculum" />
            <h2 className="font-mono text-3xl md:text-4xl font-black text-black uppercase">四大模块</h2>
            <p className="font-sans text-sm text-[#666] font-medium max-w-lg">
              覆盖货币经济学、金融理论两个学科门类及所属四个科目。
            </p>
          </div>

          <div className="border-2 border-[#FF3333] px-4 py-3 max-w-[340px] rv bg-white">
            <div className="flex items-start gap-2">
              <span className="font-mono text-[14px] font-black text-[#FF3333] uppercase tracking-wider shrink-0 mt-0.5">
                NEW
              </span>
              <div>
                <p className="font-mono text-[14px] font-black text-[#FF3333] tracking-[0.15em] uppercase">
                  2027 新增考点
                </p>
                <p className="font-sans text-[14px] text-[#555] mt-0.5 leading-relaxed font-medium">
                  新股发行与配股、租赁与购买、股权回购、认股权证与可转债等。
                </p>
              </div>
            </div>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 border-2 border-black">
          {MODULES.map((mod, i) => (
            <div key={mod.title} className={cn(
              'p-6 flex flex-col gap-4 border-black',
              'border-r-2 last:border-r-0',
              'border-b-2 xl:border-b-0',
              'rv',
            )}>
              <div className="flex items-center justify-between">
                <span className="font-mono text-4xl font-black text-black/5 select-none">
                  0{i + 1}
                </span>
                <span className="font-mono text-[14px] font-black text-[#FF3333] uppercase tracking-wider">
                  {mod.title}
                </span>
              </div>
              <p className="font-mono text-[14px] font-bold text-[#999] uppercase tracking-[0.08em]">
                {mod.tag}
              </p>
              <div className="space-y-3 flex-1">
                {mod.items.map(([name, desc]) => (
                  <div key={name}>
                    <h4 className="font-mono text-[14px] font-black text-black uppercase mb-1">
                      {name}
                    </h4>
                    <p className="font-sans text-[14px] text-[#666] leading-relaxed font-medium">
                      {desc}
                    </p>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
};

/* ──────────────────────────────────────────────────
   ABOUT — 关于机构
   ────────────────────────────────────────────────── */
const About: React.FC<{ institution: InstitutionData }> = ({ institution }) => {
  const ref = useReveal();
  return (
    <section id="about" className="py-20 md:py-28 bg-white border-b-2 border-black" ref={ref}>
      <div className="max-w-[1200px] mx-auto px-6 md:px-12 lg:px-16">
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-14 lg:gap-20 items-start">
          {/* Left */}
          <div className="space-y-8 rv">
            <div className="space-y-3">
              <BrutalLabel text={`About ${institution.name}`} />
              <h2 className="font-mono text-3xl md:text-4xl font-black text-black uppercase leading-[1.1]">
                7 年专注金融硕士
                <br />
                考研辅导
              </h2>
            </div>
            <div className="space-y-4 text-base text-[#555] leading-relaxed font-medium max-w-[520px]">
              <p>
                自 2019 年成立以来，{institution.name}已连续 7 年为金融硕士考生提供系统高效的辅导服务。我们推动学员用<strong className="text-black font-extrabold border-b-2 border-[#FF3333]">最短时间达成专业课掌握</strong>，预留更多时间应对公共课。
              </p>
              <p>
                近 200 位全程班学员中，20 余位斩获 400+，30 余位专业课突破 120+，多名二战生专业课<strong className="text-black font-extrabold">提高 40 分以上</strong>。
              </p>
            </div>

            <div className="grid grid-cols-2 sm:grid-cols-4 border-2 border-black">
              {[
                { v: '7 年', l: '辅导经验' },
                { v: '200+', l: '累计学员' },
                { v: '20+', l: '400+ 分' },
                { v: '30+', l: '120+ 分' },
              ].map(s => (
                <div key={s.l} className="p-4 text-center border-black border-r-2 last:border-r-0">
                  <p className="font-mono text-2xl font-black text-black">{s.v}</p>
                  <p className="font-mono text-[14px] font-black text-[#999] uppercase tracking-wider mt-1">{s.l}</p>
                </div>
              ))}
            </div>
          </div>

          {/* Right */}
          <div className="space-y-4 rv">
            <div className="border-2 border-black p-7 space-y-4 bg-[#FAFAFA]">
              <div className="flex items-center gap-2">
                <span className="font-mono text-[14px] font-black text-[#FF3333] uppercase tracking-[0.2em]">
                  使命
                </span>
              </div>
              <p className="font-mono text-2xl font-black text-black uppercase">
                科技驱动教育公平
              </p>
              <p className="font-sans text-[14px] text-[#555] leading-relaxed font-medium">
                推动人工智能+认知工程发展，实现高等教育智能化、数字化。自主研发 UniMind.ai 系统、KCDS 分发系统。
              </p>
            </div>

            <div className="border-2 border-black p-7 space-y-3">
              <div className="flex items-center gap-2">
                <span className="font-mono text-[14px] font-black text-[#999] uppercase tracking-[0.2em]">
                  获取资料
                </span>
              </div>
              <p className="font-sans text-[14px] text-[#555] font-medium">
                微信：<strong className="font-mono text-black font-extrabold">KORSONEDU</strong>
              </p>
              <p className="font-sans text-[14px] text-[#555] font-medium">
                进入 <strong className="font-mono text-black font-extrabold">UniMind → 启动资料</strong> 获取电子版课本
              </p>
              <p className="font-mono text-[14px] font-bold text-[#BBB] uppercase">
                请使用电脑登录，暂不支持移动端
              </p>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
};

/* ──────────────────────────────────────────────────
   PRICING — 机构定价
   ────────────────────────────────────────────────── */
const PRICING_GROUPS = [
  { cat: '货币经济学 I', items: [
    ['货币银行学核心精讲及配套资料', '1,200'],
    ['货币银行学进阶拓展', '600'],
  ]},
  { cat: '货币经济学 II', items: [
    ['国际金融学核心精讲及配套资料', '1,000'],
    ['国际金融学重点理论应用及分析框架专项提升', '700'],
  ]},
  { cat: '货币经济学 III', items: [
    ['中级宏观经济学提升及增长理论专题突破', '400'],
  ]},
  { cat: '金融理论 I', items: [
    ['公司理财及投资学核心精讲及配套资料', '2,000'],
  ]},
  { cat: '金融理论 II', items: [
    ['投资学及衍生品重点题型及解题框架专项提升', '1,000'],
  ]},
  { cat: '习题训练', items: [
    ['核心算力 180 题及独家题库（UniMind 完成，附赠电子版）', '1,600'],
    ['10 次模拟押题考试（UniMind 完成并批改）', '1,000'],
  ]},
  { cat: '教育科技', items: [
    ['UniMind.ai 全部权限 — AI 导师、自适应学习等', '299', '购买任意模块即赠送'],
  ]},
];

const Pricing: React.FC<{ institution: InstitutionData }> = ({ institution }) => {
  const ref = useReveal();
  const registerUrl = `${UNIMIND_BASE}/register?institution=${institution.slug}`;

  return (
    <section id="pricing" className="py-20 md:py-28 bg-[#FAFAFA] border-b-2 border-black" ref={ref}>
      <div className="max-w-[1200px] mx-auto px-6 md:px-12 lg:px-16">
        <div className="mb-12 rv space-y-3">
          <BrutalLabel text="Pricing" />
          <h2 className="font-mono text-3xl md:text-4xl font-black text-black uppercase">2027 年定价</h2>
          <p className="font-sans text-sm text-[#666] font-medium max-w-lg">
            首次推出分模块购买模式，可根据掌握程度自由选择。
          </p>
        </div>

        {/* Featured */}
        <div className="rv mb-0 border-2 border-black bg-black text-white">
          <div className="p-7 md:p-9 flex flex-col md:flex-row md:items-end md:justify-between gap-6">
            <div className="space-y-3">
              <div className="flex items-center gap-2.5">
                <span className="font-mono text-[14px] font-black text-black bg-[#FF3333] px-2 py-0.5 uppercase">推荐</span>
                <span className="font-mono text-[14px] font-bold text-white/40 uppercase tracking-[0.15em]">最具性价比</span>
              </div>
              <h3 className="font-mono text-xl font-black uppercase">全科全程班</h3>
              <p className="font-sans text-sm text-white/50 font-medium leading-relaxed max-w-lg">
                货币经济学 + 金融理论 + 习题训练 + UniMind 全部权限及服务。一站覆盖。
              </p>
            </div>
            <div className="flex items-end gap-5 shrink-0">
              <div className="text-right">
                <p className="font-mono text-[14px] font-bold text-white/40 uppercase">全价</p>
                <p className="font-mono text-base font-bold text-white/25 line-through">¥9,799</p>
                <p className="font-mono text-[32px] font-black">¥8,150</p>
                <p className="font-mono text-[14px] font-black text-[#FF3333] mt-0.5 uppercase">早鸟优惠价</p>
              </div>
              <a
                href={registerUrl}
                className="font-mono text-sm font-black text-black bg-[#FF3333] border-2 border-[#FF3333] px-6 py-3 uppercase hover:bg-white hover:text-black inline-block"
              >
                立即报名 <ArrowUpRight className="ml-1 h-4 w-4 inline" />
              </a>
            </div>
          </div>
        </div>

        {/* Module table */}
        <div className="rv border-2 border-black border-t-0 bg-white">
          <div className="px-6 py-4 bg-[#FAFAFA] border-b-2 border-black flex items-center justify-between">
            <h4 className="font-mono text-[14px] font-black text-black/55 uppercase tracking-[0.12em]">
              分模块购买（自选组合）
            </h4>
            <span className="font-mono text-[14px] font-bold text-[#BBB] uppercase">
              总计超 ¥8,150 · 建议选全科
            </span>
          </div>
          {PRICING_GROUPS.map((group, gi) => (
            <div key={gi} className="border-b border-black/10 last:border-0">
              {group.items.map(([name, price, note], ii) => (
                <div key={ii} className="flex items-center gap-4 px-6 py-4 hover:bg-[#FAFAFA]">
                  <div className="w-[130px] shrink-0 hidden lg:block">
                    {ii === 0 && (
                      <span className="font-mono text-[14px] font-black text-[#BBB] uppercase tracking-[0.2em]">
                        {group.cat}
                      </span>
                    )}
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="font-sans text-[14px] font-bold text-black/70">{name}</p>
                    {note && <p className="font-mono text-[14px] font-black text-[#FF3333] mt-0.5 uppercase">{note}</p>}
                  </div>
                  <div className="text-right shrink-0 w-[80px]">
                    <p className="font-mono text-base font-black text-black">¥{price}</p>
                  </div>
                </div>
              ))}
            </div>
          ))}
          <div className="px-6 py-4 bg-[#FAFAFA] border-t-2 border-black flex items-center justify-between">
            <span className="font-mono text-[14px] font-black text-black/35 uppercase tracking-[0.12em]">
              模块单独购买总计
            </span>
            <span className="font-mono text-lg font-black text-black/30 mr-[80px]">¥9,799</span>
          </div>
        </div>

        <p className="font-mono text-[14px] font-bold text-[#BBB] mt-5 text-center rv uppercase">
          已购模块可按差价补足升级全科。
        </p>
      </div>
    </section>
  );
};

/* ──────────────────────────────────────────────────
   FAQ — 机构常见问题
   ────────────────────────────────────────────────── */
const FAQS = [
  ['课程有效期是多久？', '视频与课件部署在 UniMind，账号有效期两年。其他服务本年度初试结束后截止，二战考生经申请可延长一年。复试指南及就业服务终身有效。'],
  ['是否有保过班？', '不承诺保过，不开设 VIP 班。课程不能代替你的学习与思考，我们尽最大所能让你掌握更多内容、提高效率。从统计学看，我们的服务显著可靠。'],
  ['能提供定校/定向服务吗？', '不提供定向课程。绝大多数院校考察内容极为类似，单一课程可有效减少信息冗余。我们的课程能做到有效覆盖。'],
  ['只学某一门科目可以吗？', '2027 年首次开放分模块购买。可根据薄弱环节选择单个或多个模块。基础一般建议全科性价比最高，二战或基础好的可按需灵活选择。'],
  ['智能学习系统需要额外付费吗？', '单独购买智能系统附加包为 ¥299。购买全程班及任一模块即赠送 UniMind.ai 全部权限。'],
  ['后续可以升级到全科吗？', '已购模块后可按差价补足升级为全科。系统支持灵活升级。'],
];

const FAQ: React.FC = () => {
  const [openIdx, setOpenIdx] = useState<number | null>(null);
  const ref = useReveal();
  return (
    <section id="faq" className="py-20 md:py-28 bg-white border-b-2 border-black" ref={ref}>
      <div className="max-w-[1200px] mx-auto px-6 md:px-12 lg:px-16">
        <div className="mb-12 rv space-y-3">
          <BrutalLabel text="FAQ" />
          <h2 className="font-mono text-3xl md:text-4xl font-black text-black uppercase">常见问题</h2>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 border-2 border-black">
          {FAQS.map(([q, a], i) => {
            const isOpen = openIdx === i;
            return (
              <div key={i} className={cn(
                'border-black',
                'border-b-2 last:border-b-0 md:[&:nth-child(5)]:border-b-0 md:[&:nth-child(6)]:border-b-0',
                'odd:border-r-0 md:odd:border-r-2',
              )}>
                <button
                  onClick={() => setOpenIdx(isOpen ? null : i)}
                  className="w-full px-5 py-4 flex items-start justify-between text-left gap-3 group hover:bg-black hover:text-white"
                >
                  <span className="font-mono text-[14px] font-black text-black group-hover:text-white uppercase leading-snug flex-1">
                    {q}
                  </span>
                  <span className="font-mono text-lg font-black text-[#FF3333] group-hover:text-white shrink-0 mt-0.5">
                    {isOpen ? '[-]' : '[+]'}
                  </span>
                </button>
                {isOpen && (
                  <div className="px-5 pb-4 -mt-1">
                    <p className="font-sans text-[14px] text-[#555] leading-relaxed font-medium">{a}</p>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
};

/* ──────────────────────────────────────────────────
   FOOTER
   ────────────────────────────────────────────────── */
const Footer: React.FC<{ institution: InstitutionData }> = ({ institution }) => (
  <footer className="py-10 bg-[#FAFAFA] border-t-2 border-black">
    <div className="max-w-[1200px] mx-auto px-6 md:px-12 lg:px-16 flex flex-col md:flex-row items-center justify-between gap-4">
      <div className="flex items-center gap-3">
        <div>
          <p className="font-mono font-black text-sm text-black uppercase">{institution.name}</p>
          <p className="font-mono text-[14px] font-bold text-[#999] uppercase tracking-[0.15em]">
            科技驱动教育公平
          </p>
        </div>
      </div>
      <div className="flex items-center gap-5 font-mono">
        <a href="#courses" className="text-[14px] font-bold text-black/40 hover:text-[#FF3333] uppercase">课程</a>
        <a href="#pricing" className="text-[14px] font-bold text-black/40 hover:text-[#FF3333] uppercase">定价</a>
        <a href="#faq" className="text-[14px] font-bold text-black/40 hover:text-[#FF3333] uppercase">FAQ</a>
      </div>
      <p className="font-mono text-[14px] font-bold text-[#BBB] uppercase">
        &copy; {COPYRIGHT_YEAR} {COPYRIGHT_ENTITY} · {APP_VERSION}
      </p>
    </div>
  </footer>
);

/* ──────────────────────────────────────────────────
   LOADING / ERROR
   ────────────────────────────────────────────────── */
const LoadingState: React.FC = () => (
  <div className="min-h-screen bg-white flex items-center justify-center">
    <div className="text-center space-y-4">
      <Loader2 className="h-8 w-8 animate-spin text-[#FF3333] mx-auto" />
      <p className="font-mono text-[14px] font-black text-[#999] uppercase tracking-[0.2em]">Loading...</p>
    </div>
  </div>
);

const ErrorState: React.FC<{ slug: string }> = ({ slug }) => (
  <div className="min-h-screen bg-white flex items-center justify-center px-6">
    <div className="text-center space-y-6 max-w-md">
      <p className="font-mono text-8xl font-black text-black/5 select-none">404</p>
      <div className="space-y-3">
        <h2 className="font-mono text-2xl font-black text-black uppercase">机构不存在</h2>
        <p className="font-sans text-base text-[#666] font-medium leading-relaxed">
          未找到 <code className="font-mono text-[14px] font-black text-[#FF3333] bg-[#FAFAFA] px-1.5 py-0.5">{slug}</code> 对应的机构，
          请检查链接是否正确。
        </p>
      </div>
      <a
        href="/"
        className="inline-block font-mono text-sm font-black text-white bg-black border-2 border-black px-7 py-3 uppercase hover:bg-[#FF3333] hover:border-[#FF3333]"
      >
        返回 UniMind.ai
      </a>
    </div>
  </div>
);

/* ──────────────────────────────────────────────────
   MAIN
   ────────────────────────────────────────────────── */
const InstitutionHome: React.FC<{ slug?: string }> = ({ slug: propSlug }) => {
  const { slug: paramSlug } = useParams<{ slug: string }>();
  const storeInst = useInstitutionStore(s => s.institution);
  const authInst = useAuthStore(s => s.user?.institution);
  const slug = propSlug || paramSlug || storeInst?.slug || authInst?.slug || '';
  const [institution, setInstitution] = useState<InstitutionData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const { user } = useAuthStore();

  useEffect(() => {
    if (!slug) { setError(true); setLoading(false); return; }
    setLoading(true);
    setError(false);
    api.get(`/users/public/institution/${encodeURIComponent(slug)}/`)
      .then(res => {
        setInstitution(res.data);
        document.title = `${res.data.name} - UniMind.ai - 新一代AI教育基础设施`;
      })
      .catch(() => setError(true))
      .finally(() => setLoading(false));
  }, [slug]);

  useEffect(() => { window.scrollTo(0, 0); }, [slug]);

  if (loading) return <LoadingState />;
  if (error || !institution) return <ErrorState slug={slug || ''} />;

  const registerUrl = `${UNIMIND_BASE}/register?institution=${institution.slug}`;

  return (
    <div className="w-full font-sans antialiased bg-white">
      <style>{`
        .rv{opacity:0;transform:translateY(20px);transition:opacity .6s cubic-bezier(0.3,0,0.2,1),transform .6s cubic-bezier(0.3,0,0.2,1)}
        .rv.on{opacity:1;transform:translateY(0)}
        ::selection{background:#FF3333;color:#fff}
      `}</style>

      {/* 迁移通知顶栏 */}
      <div className="bg-black text-white text-center py-2.5 px-4 font-sans text-[13px]">
        学习系统已迁移至{' '}
        <a href="https://unimind-ai.com" className="text-[#FF3333] font-bold hover:underline">
          UniMind.ai
        </a>
        ，{' '}
        <a href="https://unimind-ai.com/login" className="text-[#FF3333] font-bold hover:underline">
          点击此处
        </a>
        {' '}进入新系统
      </div>

      {user && (
        <div className="bg-black text-white py-2 px-4 flex items-center justify-end gap-4 text-sm font-mono">
          <span className="text-white/60">已登录：{user.nickname || user.username}</span>
          <a href={`${UNIMIND_BASE}/courses`} className="font-black uppercase hover:text-[#FF3333]">进入学习 <ArrowUpRight className="h-3.5 w-3.5 inline" /></a>
        </div>
      )}

      <Hero institution={institution} />
      <CourseContent />
      <About institution={institution} />
      <Pricing institution={institution} />

      {/* CTA */}
      <section className="py-16 bg-white border-b-2 border-black">
        <div className="max-w-[1200px] mx-auto px-6 md:px-12 lg:px-16 text-center space-y-4">
          <h2 className="font-mono text-2xl md:text-3xl font-black text-black uppercase">
            准备好开始了吗
          </h2>
          <p className="font-sans text-base text-[#666] font-medium max-w-md mx-auto">
            2027 全程班现已开放报名。早鸟优惠限时进行中。
          </p>
          <a
            href={registerUrl}
            className="inline-block font-mono text-sm font-black text-white bg-black border-2 border-black px-7 py-3 uppercase hover:bg-[#FF3333] hover:border-[#FF3333]"
          >
            立即报名
          </a>
        </div>
      </section>

      <FAQ />
      <Footer institution={institution} />
    </div>
  );
};

export default InstitutionHome;
