import React from 'react';
import { Button } from '@/components/ui/button';
import { ArrowLeft, Envelope, Buildings, Target, Sparkle, Clock, Users, CheckCircle, ArrowRight } from '@phosphor-icons/react';
import { useNavigate } from 'react-router-dom';

const PromoPlus: React.FC = () => {
  const navigate = useNavigate();

  return (
    <div className="w-full min-h-screen font-sans text-left overflow-x-hidden antialiased scroll-smooth" style={{ background: '#ffffff' }}>
      {/* Nav */}
      <nav className="sticky top-0 z-[var(--z-dropdown)] bg-white/80 backdrop-blur-xl border-b border-[#e5e7eb]">
        <div className="max-w-4xl mx-auto px-6 h-14 flex items-center justify-between">
          <button onClick={() => navigate('/')} className="flex items-center gap-2 text-[#5a5a7a] hover:text-[#1a1a2e] transition-colors">
            <ArrowLeft className="h-4 w-4" />
            <span className="text-[13px] font-medium">返回首页</span>
          </button>
          <button onClick={() => window.scrollTo({ top: 0, behavior: 'smooth' })} className="flex items-center gap-2">
            <img src="/Unimind_logo.png" alt="UniMind" className="h-7 w-7 rounded-lg object-contain" />
            <span className="font-bold text-base tracking-tight text-[#1a1a2e]">UniMind</span>
          </button>
          <Button
            size="sm"
            className="text-white border-0 font-semibold"
            style={{ background: '#2d2b6b' }}
            onClick={() => navigate('/register')}
          >
            免费注册
          </Button>
        </div>
      </nav>

      {/* Hero */}
      <section className="pt-20 pb-16 px-6" style={{ background: 'linear-gradient(180deg, #f8f9fb 0%, #ffffff 100%)' }}>
        <div className="max-w-3xl mx-auto text-center space-y-6">
          <div className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full border border-[#2d2b6b]/20" style={{ background: 'rgba(45,43,107,0.06)' }}>
            <Sparkle className="h-3.5 w-3.5 text-[#2d2b6b]" />
            <span className="text-[12px] font-semibold text-[#2d2b6b]">限时活动</span>
          </div>
          <h1 className="text-4xl md:text-5xl font-bold tracking-tight text-[#1a1a2e] leading-tight">
            首批机构专享<br />Growth 方案免费开放
          </h1>
          <p className="text-lg text-[#5a5a7a] max-w-xl mx-auto leading-relaxed">
            我们正在寻找首批合作伙伴，共同探索 AI 驱动的教育新模式。入选机构将免费获得 Growth 方案全部功能，为期 6 个月（原价 ¥1,299/月）。
          </p>
          <div className="flex items-center justify-center gap-4 text-sm">
            <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full font-semibold text-[#FF3B30]" style={{ background: 'rgba(255,59,48,0.08)' }}>
              <span className="h-1.5 w-1.5 rounded-full bg-[#FF3B30] animate-pulse" />
              首批 20 个名额
            </span>
          </div>
          <div className="flex items-center justify-center gap-2 text-sm text-[#9ca3af]">
            <Clock className="h-4 w-4" />
            <span>活动截止：2026 年 6 月 30 日</span>
          </div>
        </div>
      </section>

      {/* What is UniMind */}
      <section className="py-20 px-6" style={{ background: '#ffffff' }}>
        <div className="max-w-3xl mx-auto space-y-16">
          <div className="space-y-6">
            <p className="text-[10px] font-semibold uppercase tracking-[0.3em] text-[#2d2b6b]">What is UniMind</p>
            <h2 className="text-3xl md:text-4xl font-bold tracking-tight text-[#1a1a2e]">什么是 UniMind？</h2>
            <div className="space-y-4 text-[15px] leading-[1.8] text-[#4a4a6a]">
              <p>
                UniMind 不是又一个题库、网课平台或教育管理系统。它是<strong className="text-[#1a1a2e]">Agent 驱动的新一代智能教育基础设施</strong>——
                从出题、刷题到知识追踪，全链路 Agent 化。
              </p>
              <p>
                核心是两个自治 AI Agent：<strong className="text-[#1a1a2e]">小宇</strong>（学习教练，主动分析学生数据、制定个性化计划）
                和<strong className="text-[#1a1a2e]">出题助手</strong>（教研搭档，背后 4 个 AI 对抗博弈，出题可用率从 60% 提升至 85%+）。
                底层是自研的 <strong className="text-[#1a1a2e]">Memorix 自进化记忆调度算法</strong>，比 FSRS v4.5 预测精度高 13.7%，每个学生的记忆模型都在实时进化。
              </p>
              <p>
                已支持考研、CPA、法考、高中数理等 10+ 学科，50+ 机构正在使用。
                对话即学习，Agent 即基建。
              </p>
            </div>
          </div>

          {/* Plus plan highlights */}
          <div className="space-y-8">
            <p className="text-[10px] font-semibold uppercase tracking-[0.3em] text-[#2d2b6b]">Growth Plan Includes</p>
            <h2 className="text-3xl md:text-4xl font-bold tracking-tight text-[#1a1a2e]">Growth 方案包含</h2>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {[
                'AI 出题无限制',
                '200 名学员上限',
                '5 名教师 · 不限学科',
                'Memorix 自适应复习',
                '班级对比报表 · 数据导出',
                '交互式知识图谱',
                '课程视频 + AI 大纲打点',
                '在线答疑系统',
                '模拟考试',
                'AI 助教 3000 次/月',
                'PDF 导出 100 次/月',
                '多教师协作 · 权限管理',
              ].map((feature) => (
                <div key={feature} className="flex items-start gap-3 p-4 rounded-xl border border-[#e5e7eb] bg-[#f8f9fb]">
                  <CheckCircle className="h-4.5 w-4.5 text-[#2d2b6b] mt-0.5 shrink-0" />
                  <span className="text-sm text-[#1a1a2e] font-medium">{feature}</span>
                </div>
              ))}
            </div>
          </div>

          {/* Two paths */}
          <div className="space-y-6">
            <p className="text-[10px] font-semibold uppercase tracking-[0.3em] text-[#2d2b6b]">Getting Started</p>
            <h2 className="text-3xl md:text-4xl font-bold tracking-tight text-[#1a1a2e]">两种方式，你选</h2>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="p-6 rounded-2xl border border-[#e5e7eb] bg-white space-y-3">
                <p className="text-sm font-bold text-[#1a1a2e]">直接注册</p>
                <p className="text-[13px] text-[#5a5a7a] leading-relaxed">
                  注册后输入试用码即可体验 7 天全功能，到期后自动切换至免费版，数据全部保留。适合快速了解产品。
                </p>
                <button
                  onClick={() => navigate('/register')}
                  className="text-[13px] font-medium text-[#5a5a7a] hover:text-[#2d2b6b] transition-colors inline-flex items-center gap-1"
                >
                  注册体验 <ArrowRight className="h-3 w-3" />
                </button>
              </div>
              <div className="p-6 rounded-2xl border border-[#2d2b6b]/30 space-y-3" style={{ background: 'rgba(45,43,107,0.04)' }}>
                <div className="flex items-center gap-2">
                  <p className="text-sm font-bold text-[#1a1a2e]">申请入选首批机构</p>
                  <span className="text-[10px] font-bold px-2 py-0.5 rounded-full text-white" style={{ background: '#2d2b6b' }}>推荐</span>
                </div>
                <p className="text-[13px] text-[#5a5a7a] leading-relaxed">
                  通过邮件申请，入选后免费使用 Growth 方案 6 个月，充分验证 AI 驱动的教学效果。名额有限。
                </p>
                <a
                  href="mailto:eular@unimind-ai.com"
                  className="text-[13px] font-semibold text-[#2d2b6b] hover:underline inline-flex items-center gap-1"
                >
                  发送邮件申请 <ArrowRight className="h-3 w-3" />
                </a>
              </div>
            </div>
          </div>

          {/* Eligibility */}
          <div className="space-y-6">
            <p className="text-[10px] font-semibold uppercase tracking-[0.3em] text-[#2d2b6b]">Eligibility</p>
            <h2 className="text-3xl md:text-4xl font-bold tracking-tight text-[#1a1a2e]">参与资格</h2>
            <div className="space-y-4 text-[15px] leading-[1.8] text-[#4a4a6a]">
              <p>我们欢迎以下类型的机构申请：</p>
              <ul className="space-y-3 ml-1">
                {[
                  '正在运营的培训机构（线上/线下均可）',
                  '独立讲师或教育工作室',
                  '有明确的学科方向和学员群体',
                  '愿意提供使用反馈，帮助我们迭代产品',
                ].map((item) => (
                  <li key={item} className="flex items-start gap-3">
                    <span className="h-1.5 w-1.5 rounded-full bg-[#2d2b6b] mt-2.5 shrink-0" />
                    <span>{item}</span>
                  </li>
                ))}
              </ul>
              <p className="text-[#9ca3af] text-sm pt-2">
                首批名额有限，我们将根据机构情况择优入选。活动截止日期为 2026 年 6 月 30 日。
              </p>
            </div>
          </div>

          {/* How to join */}
          <div className="space-y-6" id="apply">
            <p className="text-[10px] font-semibold uppercase tracking-[0.3em] text-[#2d2b6b]">How to Join</p>
            <h2 className="text-3xl md:text-4xl font-bold tracking-tight text-[#1a1a2e]">如何加入</h2>
            <div className="space-y-6">
              <p className="text-[15px] leading-[1.8] text-[#4a4a6a]">
                发送邮件至以下地址，我们会在一个工作日内回复：
              </p>

              <div className="p-6 rounded-2xl border border-[#e5e7eb] bg-[#f8f9fb] space-y-5">
                <div className="flex items-center gap-3">
                  <div className="h-10 w-10 rounded-xl flex items-center justify-center" style={{ background: 'rgba(45,43,107,0.08)' }}>
                    <Envelope className="h-5 w-5 text-[#2d2b6b]" />
                  </div>
                  <a href="mailto:eular@unimind-ai.com" className="text-lg font-bold text-[#2d2b6b] hover:underline">
                    eular@unimind-ai.com
                  </a>
                </div>

                <div className="border-t border-[#e5e7eb] pt-5 space-y-4">
                  <p className="text-sm font-semibold text-[#1a1a2e]">邮件请包含以下信息：</p>
                  <div className="space-y-3">
                    {[
                      { icon: Buildings, label: '机构名称', desc: '你的培训机构或工作室名称' },
                      { icon: Users, label: '主要业务', desc: '教授的学科、学员规模、运营模式' },
                      { icon: Target, label: 'AI 驱动的具体成果', desc: '你希望 AI 帮你解决什么问题、达到什么效果' },
                    ].map(({ icon: Icon, label, desc }) => (
                      <div key={label} className="flex items-start gap-3">
                        <Icon className="h-4 w-4 text-[#5a5a7a] mt-1 shrink-0" />
                        <div>
                          <p className="text-sm font-semibold text-[#1a1a2e]">{label}</p>
                          <p className="text-xs text-[#9ca3af]">{desc}</p>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </div>

              <p className="text-[13px] text-[#9ca3af] leading-relaxed">
                你也可以附上机构介绍、网站链接或任何有助于我们了解你的材料。我们会在审核后通过邮件告知结果，并协助你完成部署。
              </p>
            </div>
          </div>

          {/* Bottom CTA */}
          <div className="text-center space-y-6 pt-8 pb-12">
            <h2 className="text-3xl md:text-4xl font-bold tracking-tight text-[#1a1a2e]">
              准备好，进入智能教育新时代
            </h2>
            <p className="text-[#5a5a7a]">发送邮件，或直接注册开始体验</p>
            <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
              <Button
                size="lg"
                className="h-12 px-8 text-sm font-bold rounded-xl text-white border-0"
                style={{ background: '#2d2b6b' }}
                onClick={() => navigate('/register')}
              >
                免费注册
              </Button>
              <a
                href="mailto:eular@unimind-ai.com"
                className="text-sm font-medium text-[#5a5a7a] hover:text-[#2d2b6b] transition-colors"
              >
                发送邮件申请 →
              </a>
            </div>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="py-8 border-t border-[#e5e7eb]" style={{ background: '#f8f9fb' }}>
        <div className="max-w-4xl mx-auto px-6 flex flex-col md:flex-row items-center justify-between gap-4">
          <div className="flex items-center gap-2">
            <img src="/Unimind_logo.png" alt="UniMind" className="h-5 w-5 rounded-md object-contain" />
            <span className="text-[12px] font-medium text-[#9ca3af]">UniMind.ai</span>
          </div>
          <p className="text-[10px] text-[#9ca3af]">© 2019-2026 北京融知高科 · UniMind.ai</p>
        </div>
      </footer>
    </div>
  );
};

export default PromoPlus;
