import { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { ArrowLeft, ArrowRight, Check, Sparkle } from '@phosphor-icons/react';
import { cn } from '@/lib/utils';
import { APP_VERSION, COPYRIGHT_YEAR, COPYRIGHT_ENTITY } from '@/constants/version';

const PricingPage: React.FC = () => {
  const navigate = useNavigate();
  const [annual, setAnnual] = useState(true);

  const plans = [
    {
      label: 'Free',
      desc: '体验版 · 验证 AI 教学效果',
      persona: '零成本体验 AI 出题、题库管理、基础学情统计，快速验证产品是否适合你的机构。',
      cta: '免费注册',
      features: [
        '全部 Agent 能力（小宇 AI 助手、AI 出题、ARC 管线）— 受 AI 调用配额限制',
        '100 次/月 AI 调用',
        '30 名学员 · 1 名教师 · 1 门学科',
        '习题训练 · 考试 · 错题复盘',
        '诊断测试 · 错题洞察 · 每日签到',
        '课程视频 · 答疑系统 · 自习室 · 知识图谱',
        '5 GB 存储 · 题库 200 题',
        '基础统计',
      ],
    },
    {
      label: 'Starter',
      desc: '成长型机构 · 1-2 名教师 · AI 提效',
      persona: '适合起步期培训机构，AI 出题 + Memorix 复习 + 完整学情报告，用 AI 替代重复性教研工作。',
      cta: '7 天免费试用',
      features: [
        '全部 Agent 能力 — 受 AI 调用配额限制',
        '500 次/月 AI 调用',
        '50 名学员 · 1 名教师 · 3 门学科',
        'Free 全部功能',
        '完整学情报告 · 诊断测试 · 错题洞察',
        '50 GB 存储 · 题库 2,000 题',
      ],
    },
    {
      label: 'Growth',
      desc: '规模化机构 · 多教师协作 · 系统化管理',
      persona: '适合成长中的培训机构，多教师协作、知识图谱、模拟考试、在线答疑，系统化提升教学管理效率。',
      cta: '7 天免费试用',
      features: [
        '全部 Agent 能力 — 受 AI 调用配额限制',
        '3,000 次/月 AI 调用',
        '200 名学员 · 5 名教师 · 10 门学科',
        'Starter 全部功能',
        'Memorix 图扩散记忆调度 · 知识图谱',
        '视频 AI 大纲 · 多教师协作',
        '班级对比 · 数据导出 · 学生端收费',
        '500 GB 存储 · 题库 10,000 题',
      ],
    },
    {
      label: 'Enterprise',
      desc: '连锁品牌 · 数据主权 · 深度定制',
      persona: '适合连锁机构或企业培训，白标部署、数据私有化、API 对接、SSO 单点登录。',
      cta: '预约演示',
      features: [
        'AI 调用无限制',
        '学员 · 教师 · 学科均不限',
        'Growth 全部功能',
        'AI Bot 自定义',
        '品牌白标 · API 接入 · 私有化部署',
        '存储 · 题库均不限',
      ],
    },
  ] as Array<{ label: string; desc: string; persona?: string; cta: string; features: string[] }>;
  const prices = [
    { monthly: '¥0', yearly: '¥0' },
    { monthly: '¥499', yearly: '¥416' },
    { monthly: '¥1,299', yearly: '¥1,083' },
    { monthly: '¥3,999', yearly: '¥3,333' },
  ];
  const popularIdx = 2;

  return (
    <div className="min-h-screen font-sans antialiased" style={{ background: '#0a0a0d', color: '#f0f0ed' }}>
      {/* Ambient bg */}
      <div className="fixed inset-0 pointer-events-none overflow-hidden" style={{ zIndex: 0 }}>
        <div className="absolute top-1/4 -left-32 w-[500px] h-[500px] rounded-full blur-[120px] opacity-[0.06]" style={{ background: '#5b5fef' }} />
        <div className="absolute bottom-1/4 -right-32 w-[400px] h-[400px] rounded-full blur-[100px] opacity-[0.04]" style={{ background: '#38bdf8' }} />
      </div>

      <div className="relative z-10">
        {/* Nav */}
        <nav className="max-w-6xl mx-auto px-6 h-16 flex items-center justify-between">
          <button onClick={() => navigate('/')} className="flex items-center gap-2">
            <img src="/Unimind_logo.png" alt="UniMind" className="h-7 w-7 rounded-lg object-contain" />
            <span className="font-bold text-base tracking-tight text-white">UniMind</span>
          </button>
          <button onClick={() => navigate('/')} className="inline-flex items-center gap-1.5 text-sm font-medium text-white/60 hover:text-white transition-colors">
            <ArrowLeft className="h-3.5 w-3.5" />
            回首页
          </button>
        </nav>

        {/* Header */}
        <section className="py-16 md:py-24 text-center px-6">
          <h1 className="text-4xl md:text-6xl lg:text-7xl font-bold tracking-tight text-white max-w-3xl mx-auto leading-[1.08]">
            选择适合你的方案
          </h1>
          <p className="mt-5 text-base md:text-lg max-w-xl mx-auto leading-relaxed text-white/65">
            试用码解锁 7 天全功能 · 无需绑定信用卡 · 随时取消
          </p>

          {/* Trial banner removed — moved below pricing grid */}
        </section>

        {/* Toggle */}
        <section className="max-w-6xl mx-auto px-6 pb-8">
          <div className="flex items-center justify-center gap-3">
            <span className={cn('text-sm font-semibold', annual ? 'text-white/50' : 'text-white')}>
              月付
            </span>
            <button
              onClick={() => setAnnual(!annual)}
              className="w-11 h-6 rounded-full transition-all relative"
              style={{ background: annual ? '#5b5fef' : '#333' }}
            >
              <div className={cn('absolute top-0.5 h-5 w-5 rounded-full bg-white shadow transition-all', annual ? 'left-[22px]' : 'left-0.5')} />
            </button>
            <span className={cn('text-sm font-semibold flex items-center gap-1.5', annual ? 'text-white' : 'text-white/50')}>
              年付
              <span className="text-[10px] font-bold px-1.5 py-0.5 rounded-full" style={{ background: 'rgba(34,197,94,0.15)', color: '#4ade80' }}>省 23-33%</span>
            </span>
          </div>
        </section>

        {/* Plans */}
        <section className="max-w-6xl mx-auto px-6 pb-24">
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 items-stretch">
            {plans.map((plan, pi) => {
              const isFree = prices[pi].monthly === '¥0';
              const price = annual && !isFree ? prices[pi].yearly : prices[pi].monthly;
              const isPopular = pi === popularIdx;
              const isPro = pi === 3;

              return (
                <div
                  key={plan.label}
                  className={cn('p-6 rounded-2xl border flex flex-col', isPopular && 'ring-1')}
                  style={{
                    borderColor: isPopular ? 'rgba(91,95,239,0.4)' : 'rgba(255,255,255,0.06)',
                    background: isPopular ? 'rgba(91,95,239,0.06)' : 'rgba(255,255,255,0.02)',
                    ...(isPopular ? { boxShadow: '0 0 40px rgba(91,95,239,0.08)' } : {}),
                  }}
                >
                  <div className="mb-5" style={{ minHeight: '100px' }}>
                    <div className="flex items-center gap-2 mb-1">
                      <h3 className="font-bold text-base text-white">{plan.label}</h3>
                      {isPopular && (
                        <span className="text-[10px] font-bold px-2 py-0.5 rounded-full text-white" style={{ background: '#5b5fef' }}>
                          最受欢迎
                        </span>
                      )}
                    </div>
                    <p className="text-[12px] text-white/55">{plan.desc}</p>
                    {plan.persona && <p className="text-[11px] mt-1.5 leading-relaxed text-white/45 line-clamp-2">{plan.persona}</p>}
                  </div>

                  <div className="mb-5" style={{ minHeight: '62px' }}>
                    <div className="flex items-baseline gap-1">
                      <span className="text-3xl font-bold tracking-tight text-white" style={{ fontFamily: '"DM Mono", monospace' }}>
                        {price}
                      </span>
                      {!isFree && <span className="text-sm text-white/55">/月</span>}
                    </div>
                    <p className="text-[11px] mt-1 h-4" style={{ color: isFree ? '#4ade80' : 'rgba(255,255,255,0.45)' }}>
                      {!isFree && annual ? `年付总计 ¥${parseInt(prices[pi].yearly.replace('¥', '').replace(',', '')) * 12}` : isFree ? '永久免费' : ''}
                    </p>
                  </div>

                  <Button
                    className="w-full h-10 rounded-xl text-sm font-bold mb-5"
                    style={isPopular
                      ? { background: '#5b5fef', color: '#fff' }
                      : isPro
                        ? { background: 'transparent', border: '1px solid rgba(255,255,255,0.1)', color: '#fff' }
                        : { background: 'rgba(255,255,255,0.04)', color: '#fff' }
                    }
                    onClick={() => {
                      if (isPro) {
                        document.querySelector('#pricing-faq')?.scrollIntoView({ behavior: 'smooth' });
                      } else {
                        navigate('/register');
                      }
                    }}
                  >
                    {isPopular && <Sparkle className="h-3.5 w-3.5 mr-1.5" />}
                    {plan.cta}
                  </Button>

                  <ul className="space-y-2 flex-1">
                    {plan.features.map((f, fi) => (
                      <li key={fi} className="flex items-start gap-2 text-[12px]" style={{ color: 'rgba(255,255,255,0.7)' }}>
                        <Check className="h-3.5 w-3.5 shrink-0 mt-0.5 text-green-400" />
                        <span>{f}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              );
            })}
          </div>
          <p className="text-center mt-8 text-xs text-white/40">前 20 个付费客户锁定早期用户价格，终身不涨价。</p>

          {/* Trial info — plain text, no card */}
          <div className="max-w-2xl mx-auto mt-8 text-center space-y-2">
            <p className="text-sm font-semibold text-white/80">统一试用策略 — 零风险体验</p>
            <p className="text-[13px] leading-relaxed text-white/50">获取试用码即可解锁 7 天全功能体验（Growth 级别）。试用期内无任何限制。到期后自动切换至初始版（永久免费），数据全部保留。随时可升级。</p>
          </div>
        </section>

        {/* FAQ */}
        <section id="pricing-faq" className="max-w-3xl mx-auto px-6 pb-24">
          <h2 className="text-2xl md:text-3xl font-bold tracking-tight text-center mb-10 text-white">FAQ</h2>
          <div className="space-y-2">
            {([
              { q: '免费版有什么限制？', a: '免费版支持 30 名学员、每月 100 次 AI 调用。你能完整地体验出题→学生做题→看学情数据的闭环，足够一个小班验证产品效果。当需要更多学生或更多 AI 调用次数时，升级到 Starter 版即可解锁全部功能。' },
              { q: 'AI 出的题质量能保证吗？', a: '我们采用三智能体对抗机制——一个出题、一个审题、一个分类。质量不达标的题目会自动打回重做。建议机构教研负责人对 AI 生成的题目做最终审阅——AI 帮你省掉 90% 的初稿时间，最后 10% 的审核仍需你的专业判断。' },
              { q: '支持哪些学科和题型？', a: '平台本身不限制学科。我们预置了考研专业课（金融/法学/医学/计算机等）、职业资格证（CPA/CFA/法考/USMLE/教资等）、中学学科（数学/物理/化学/生物）、公考等方向的知识点框架。题型支持选择题、填空题、计算题、案例分析、作文等。你也可以自定义学科和知识点树。' },
              { q: '学生怎么使用？需要下载 App 吗？', a: '不需要。学生通过你分享的链接或扫码就能做题，手机/电脑均可。我们提供的是 Web/H5 体验，学生端零门槛。' },
              { q: '试用到期后数据还在吗？', a: '在。你所有的题目、学生数据、学习记录都会保留。续费后立即恢复访问。不续费的话数据只读，你不会丢失任何东西。' },
              { q: '可以月付吗？', a: '可以。月付和年付都支持。年付有 23-33% 的折扣。建议先月付一个月深度体验，确认产品适合你的机构后再转年付省钱。' },
              { q: '和通用考试工具有什么区别？', a: '通用考试工具是「把纸质考试搬到线上」。UniMind 是「AI 帮你生产和优化教学内容」——出题是 AI 自动生成的、复习是算法个性化的、学情是实时可视化的。我们解决的不是「怎么考」，而是「怎么教和怎么学」。' },
              { q: '我是个人教师，适合哪个版本？', a: '建议从 Free 版开始。30 个学生、每月 100 次 AI 调用足够日常使用。当你需要更多配额或高级功能时，升级到 Starter 版（¥499/月）。' },
              { q: '可以和我的网站或 LMS 系统集成吗？', a: 'Enterprise 方案包含 REST API 对接权限，你可以将 UniMind 的出题引擎和复习系统嵌入现有的平台中。如需超出 API 范围的自定义集成，请联系我们的解决方案团队——通过预约演示即可对接。' },
            ] as Array<{ q: string; a: string }>).filter((_, i) => [0, 4, 5, 7].includes(i)).map((faq, i) => (
              <div key={i} className="rounded-xl border p-5" style={{ borderColor: 'rgba(255,255,255,0.06)', background: 'rgba(255,255,255,0.02)' }}>
                <p className="font-semibold text-sm text-white mb-2">{faq.q}</p>
                <p className="text-sm leading-relaxed text-white/65">{faq.a}</p>
              </div>
            ))}
          </div>
        </section>

        {/* Bottom CTA */}
        <section className="max-w-3xl mx-auto px-6 pb-24 text-center space-y-6">
          <h2 className="text-3xl md:text-4xl font-bold tracking-tight text-white leading-[1.12]">让你的机构，今天就 AI 接管</h2>
          <p className="text-base max-w-xl mx-auto leading-relaxed text-white/60">7 天全功能试用。到期可继续使用初始版。不绑卡。</p>
          <Button
            size="lg"
            className="h-12 px-8 text-sm font-bold rounded-xl text-white border-0"
            style={{ background: '#5b5fef' }}
            onClick={() => navigate('/register')}
          >
            免费开始
            <ArrowRight className="ml-1.5 h-4 w-4" />
          </Button>
        </section>

        {/* Footer */}
        <footer className="py-10 border-t border-white/[0.06]">
          <div className="max-w-6xl mx-auto px-6 flex flex-col md:flex-row items-center justify-between gap-4">
            <div className="flex items-center gap-3">
              <img src="/Unimind_logo.png" alt="UniMind" className="h-7 w-7 rounded-lg object-contain" loading="lazy" />
              <span className="font-bold text-sm tracking-tight text-white/70">UniMind.ai</span>
            </div>
            <div className="flex items-center gap-4 text-[11px] text-white/40">
              <Link to="/privacy" className="hover:text-white/70 transition-colors">隐私政策</Link>
              <Link to="/terms" className="hover:text-white/70 transition-colors">用户协议</Link>
              <a href="https://beian.miit.gov.cn/" target="_blank" rel="noopener noreferrer" className="hover:text-white/70 transition-colors">京ICP备2023012726号-2</a>
              <span>© {COPYRIGHT_YEAR} {COPYRIGHT_ENTITY} · {APP_VERSION}</span>
            </div>
          </div>
        </footer>
      </div>
    </div>
  );
};

export default PricingPage;
