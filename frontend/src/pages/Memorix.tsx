import { Link } from 'react-router-dom';
import { ArrowRight, ArrowUpRight } from 'lucide-react';

export default function MemorixPage() {
  return (
    <div className="min-h-screen bg-[#0a0a14] text-white font-sans antialiased">
      {/* Hero */}
      <section className="py-28 md:py-36 px-6">
        <div className="max-w-3xl mx-auto text-center space-y-6">
          <p className="text-[10px] font-bold uppercase tracking-[0.3em] text-[#818cf8]">Research</p>
          <h1 className="text-3xl md:text-5xl lg:text-6xl font-bold leading-[1.1] tracking-tight">
            Memorix-Field
            <br />
            <span style={{ background: 'linear-gradient(135deg, #818cf8, #5b5fef)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' }}>
              图扩散记忆调度
            </span>
          </h1>
          <p className="text-base md:text-lg text-white/50 max-w-xl mx-auto leading-relaxed">
            把知识看作图谱上的节点网络，一次复习激活整个区域。
            仿真验证遗忘率降低 19.9% vs FSRS 基线。
          </p>
          <div className="flex items-center justify-center gap-3 pt-4">
            <Link
              to="/register"
              className="inline-flex items-center gap-2 h-11 px-6 rounded-xl text-sm font-bold text-white"
              style={{ background: '#5b5fef' }}
            >
              体验 UniMind <ArrowRight className="h-4 w-4" />
            </Link>
            <a
              href="#"
              className="inline-flex items-center gap-1.5 text-sm font-medium text-white/40 hover:text-white transition-colors"
            >
              arXiv 即将发布 <ArrowUpRight className="h-3.5 w-3.5" />
            </a>
          </div>
        </div>
      </section>

      {/* Problem */}
      <section className="py-20 md:py-28 px-6" style={{ background: '#0e0e1a' }}>
        <div className="max-w-3xl mx-auto space-y-8">
          <h2 className="text-2xl md:text-3xl font-bold tracking-tight">间隔重复，一百年没变过</h2>
          <div className="space-y-4 text-white/50 leading-relaxed">
            <p>
              1885 年，艾宾浩斯画出第一条遗忘曲线。一百多年过去了，间隔重复的数学框架——Leitner 盒子、
              SM-2 算法、FSRS——本质上都在回答同一个问题：<strong className="text-white/70">什么时候该复习？</strong>
            </p>
            <p>
              这个框架有一个盲点：它把每个知识点当作独立的原子。数学题和物理题是分开的、
              微积分和线性代数是分开的。但实际上，知识点之间有线——前提关系、
              相似关系、对立关系。复习一个知识点，会激活它周围的整个网络。
            </p>
            <p>
              Memorix-Field 换了一个问题：<strong className="text-white/70">不是"什么时候复习"，而是"复习哪一个，能激活最多？"</strong>
            </p>
          </div>
        </div>
      </section>

      {/* How it works */}
      <section className="py-20 md:py-28 px-6 bg-[#0a0a14]">
        <div className="max-w-3xl mx-auto space-y-8">
          <h2 className="text-2xl md:text-3xl font-bold tracking-tight">图扩散：记忆是场，不是原子</h2>
          <div className="bg-white/[0.03] border border-white/[0.06] rounded-2xl p-6 md:p-8">
            <p className="font-mono text-sm text-[#818cf8] mb-4">核心方程</p>
            <p className="font-mono text-lg md:text-xl text-white/80">
              <strong className="text-white">du/dt</strong> = −<span className="text-[#f87171]">α</span>u + <span className="text-[#38bdf8]">β</span>L·u + s(t)
            </p>
            <div className="mt-4 space-y-2 text-sm text-white/40">
              <p><span className="text-[#f87171]">α</span> — 自然遗忘速率</p>
              <p><span className="text-[#38bdf8]">β</span> — 知识扩散系数（相邻知识点间的激活传播强度）</p>
              <p><strong>L</strong> — 知识图的拉普拉斯矩阵，编码所有知识点之间的关系</p>
              <p><strong>s(t)</strong> — 复习动作，在特定节点注入能量</p>
            </div>
          </div>
          <p className="text-white/50 leading-relaxed">
            在知识图上，记忆像一个热场。复习 = 在一个节点加热。热通过边扩散到邻居。
            瓶颈节点（被很多知识点依赖的基础概念）天然保持高温——不需要频繁复习。
            叶子节点（孤立知识点）需要更多主动维护。
          </p>
        </div>
      </section>

      {/* Data */}
      <section className="py-20 md:py-28 px-6" style={{ background: '#0e0e1a' }}>
        <div className="max-w-3xl mx-auto space-y-8">
          <h2 className="text-2xl md:text-3xl font-bold tracking-tight">数据：+19.9% vs FSRS</h2>
          <div className="space-y-4 text-white/50 leading-relaxed">
            <p>
              在 400 名学生 × 150 天 × 3 种调度器 × 36 组参数组合的仿真中，
              Memorix-Field 在所有 36 组参数下均优于 FSRS 基线，无一例外。
            </p>
          </div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {[
              { v: '400', l: '学生' },
              { v: '150', l: '天' },
              { v: '36/36', l: '全正' },
              { v: '19.9%', l: '遗忘率降低' },
            ].map(s => (
              <div key={s.l} className="text-center p-4 border border-white/[0.06] rounded-xl bg-white/[0.02]">
                <p className="text-2xl md:text-3xl font-bold text-white">{s.v}</p>
                <p className="text-xs text-white/30 mt-1">{s.l}</p>
              </div>
            ))}
          </div>
          <p className="text-xs text-white/20">
            仿真引擎：Memorix-Sim v0.1 · 知识树：CFA 金融知识图谱（286 节点）· arXiv 论文即将发布
          </p>
        </div>
      </section>

      {/* CTA */}
      <section className="py-20 md:py-28 px-6 bg-[#0a0a14] text-center">
        <div className="max-w-lg mx-auto space-y-6">
          <h2 className="text-2xl md:text-3xl font-bold tracking-tight">亲自试试</h2>
          <p className="text-white/40">注册 UniMind，在真实学习中体验 Memorix-Field 的自适应调度。</p>
          <Link
            to="/register"
            className="inline-flex items-center gap-2 h-12 px-8 rounded-xl text-sm font-bold text-white"
            style={{ background: '#5b5fef' }}
          >
            免费注册 <ArrowRight className="h-4 w-4" />
          </Link>
        </div>
      </section>

      {/* Footer */}
      <footer className="py-10 border-t border-white/[0.04] text-center">
        <p className="text-xs text-white/20">© 2019-2026 北京融知高科 · UniMind.ai</p>
      </footer>
    </div>
  );
}
