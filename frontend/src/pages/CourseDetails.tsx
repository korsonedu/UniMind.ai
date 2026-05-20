import React, { useEffect } from 'react';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { 
  CheckCircle2, Play, BookOpen, 
  ClipboardList, Cpu, MessageSquare, Users, 
  Trophy, GraduationCap, Zap
} from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { APP_VERSION, COPYRIGHT_YEAR, COPYRIGHT_ENTITY, BRAND_DESC } from '@/constants/version';

const FeatureItem = ({ icon: Icon, title, description }: any) => (
  <div className="flex gap-6 p-8 rounded-[2.5rem] bg-slate-50 dark:bg-white/[0.02] border border-slate-100 dark:border-white/5 transition-all hover:shadow-lg">
    <div className="h-12 w-12 rounded-2xl bg-white dark:bg-slate-900 flex items-center justify-center shadow-sm shrink-0">
      <Icon className="h-6 w-6 text-pink-500" />
    </div>
    <div className="space-y-2">
      <h4 className="font-bold text-slate-900 dark:text-white text-base">{title}</h4>
      <p className="text-slate-500 dark:text-slate-400 text-sm leading-relaxed font-medium">{description}</p>
    </div>
  </div>
);

export const CourseDetails: React.FC = () => {
  const navigate = useNavigate();

  useEffect(() => {
    window.scrollTo(0, 0);
  }, []);

  return (
    <div className="w-full bg-white dark:bg-[#0F1115] font-sans selection:bg-pink-500 selection:text-white antialiased">
      
      {/* Apple Style Hero */}
      <section className="pt-20 pb-20 px-6 text-center overflow-hidden min-h-[80vh] flex flex-col justify-center relative">
        <div className="max-w-5xl mx-auto space-y-10">
          <div className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full bg-slate-50 dark:bg-white/5 border border-slate-100 dark:border-white/10">
            <Zap className="h-4 w-4 text-amber-500" />
            <span className="text-[11px] font-bold text-slate-500 dark:text-slate-400 uppercase tracking-[0.3em]">2026 全程班 · 深度重构</span>
          </div>
          
          <div className="space-y-4">
            <h1 className="text-4xl md:text-6xl lg:text-[80px] font-black tracking-tighter text-slate-900 dark:text-white leading-[1.1]">
              重构金融应试<br />
              <span className="text-primary font-black">定义效率极致</span>
            </h1>
            
            <div className="flex flex-col items-center pt-6">
              <div className="flex items-baseline gap-4">
                <span className="text-xl md:text-2xl font-bold text-slate-200 dark:text-slate-800 line-through">¥9,799</span>
                <span className="text-5xl md:text-[64px] font-black tracking-tighter text-slate-900 dark:text-white leading-none">¥8,150</span>
              </div>
              <p className="text-sm font-bold text-pink-500 uppercase tracking-[0.3em] mt-4">K2 全程班计划 · 限时优惠</p>
            </div>
          </div>

          <p className="text-base md:text-lg text-slate-500 dark:text-slate-400 max-w-3xl mx-auto font-medium leading-relaxed">
            体系越精简，复习越高效。在高保真的前提下压缩时长，让大家用最短的时间掌握抵达高分目标的能力。我们的目标是让每一分钟的努力都清晰可见。
          </p>

          <div className="pt-6 flex justify-center gap-4">
             <Button size="lg" className="rounded-full px-10 h-14 bg-slate-900 dark:bg-white text-white dark:text-slate-900 font-bold text-base shadow-lg hover:scale-105 transition-all" onClick={() => navigate('/register')}>
                立即开启学习
              </Button>
              <Button size="lg" variant="ghost" className="rounded-full px-10 h-14 font-bold text-base" onClick={() => navigate('/')}>
                返回主页
              </Button>
          </div>
        </div>
      </section>

      {/* Course Introduction Section */}
      <section className="py-24 bg-white dark:bg-[#0F1115]">
        <div className="max-w-5xl mx-auto px-6 space-y-20">
          <div className="space-y-6 text-center md:text-left">
            <h2 className="text-4xl md:text-5xl font-black tracking-tight text-slate-900 dark:text-white uppercase">本课程深度解析</h2>
            <div className="h-2 w-20 bg-pink-500 rounded-full mx-auto md:mx-0" />
            <p className="text-slate-500 dark:text-slate-400 text-base md:text-lg max-w-2xl font-medium leading-relaxed">
              我们深入研究了近十年金融 431 的考试趋势，为你打造了这套兼具理论深度与实战效率的课程体系。
            </p>
          </div>
          
          <div className="grid grid-cols-1 gap-16 text-left">
            <div className="space-y-6">
              <h3 className="text-2xl font-bold text-slate-900 dark:text-white flex items-center gap-4">
                <div className="h-8 w-1.5 bg-indigo-500 rounded-full" />
                权威课本覆盖
              </h3>
              <p className="text-slate-500 dark:text-slate-400 leading-relaxed text-lg md:text-xl font-medium">
                课程内容深度覆盖 <span className="text-slate-900 dark:text-white font-black underline decoration-indigo-500/30 underline-offset-8 text-xl">黄达、Mishkin、易纲、蒋先玲、胡庆康</span> 等核心教材。我们不仅停留于基础教材，更引入了 <span className="italic text-slate-700 dark:text-slate-300 font-semibold">Dornbusch《宏观经济学》、Romer《高级宏观经济学》、Walsh《Monetary Theory and Policy》</span> 等进阶内容，确保学员在应对人大、复旦等名校高难度考题时具有压制性的理论视野。
              </p>
            </div>

            <div className="space-y-6">
              <h3 className="text-2xl font-bold text-slate-900 dark:text-white flex items-center gap-4">
                <div className="h-8 w-1.5 bg-pink-500 rounded-full" />
                AMR 核心战略优势
              </h3>
              <p className="text-slate-500 dark:text-slate-400 leading-relaxed text-lg md:text-xl font-medium">
                突破传统基础、提高、冲刺的多阶段冗余模式，采取一轮全程班授课。在 <span className="text-pink-500 font-black">加速阶段</span> 让学生以最高效率掌握全面知识点，随后进入 <span className="text-indigo-500 font-black">保持阶段</span>，通过 300+ 核心习题训练将知识点编织成网，确保每一位学员都能在考场上游刃有余。
              </p>
            </div>

            <div className="space-y-6">
              <h3 className="text-2xl font-bold text-slate-900 dark:text-white flex items-center gap-4">
                <div className="h-8 w-1.5 bg-emerald-500 rounded-full" />
                讲义来源与增补
              </h3>
              <p className="text-slate-500 dark:text-slate-400 leading-relaxed text-lg md:text-xl font-medium">
                讲义针对近两年考试思路进行了体系化重构。特别增补了 <span className="text-slate-900 dark:text-white font-black underline decoration-emerald-500/30 underline-offset-8 text-xl">新股发行与配股、租赁与购买、股权回购、认股权证与可转债</span> 等过去冷门但如今高频考察的知识点。国际金融部分则着重于对真实世界经济现象的理论分析框架讲解，让你的备考既有广度又有深度。
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* Core Features Grid */}
      <section className="py-32 bg-slate-50 dark:bg-[#0A0A0B]">
        <div className="max-w-7xl mx-auto px-6">
          <div className="text-center mb-24 space-y-6">
            <h2 className="text-5xl font-bold tracking-tight text-slate-900 dark:text-white">全程班核心权益</h2>
            <p className="text-2xl text-slate-500 dark:text-slate-400 font-medium">八大维度深层赋能，全方位护航你的 431 考研之路</p>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-10">
            <FeatureItem 
              icon={BookOpen} 
              title="专业课讲义" 
              description="深度整合核心书目，增补高级教材进阶理论与答题框架。"
            />
            <FeatureItem 
              icon={Play} 
              title="全模块视频" 
              description="200+ 小时录播，支持倍速播放与 24 个月超长回放有效期。"
            />
            <FeatureItem 
              icon={ClipboardList} 
              title="核心题库" 
              description="300+ 核心习题，包含独家翻译的顶级金融考研系统题库。"
            />
            <FeatureItem 
              icon={Cpu} 
              title="宇艺引擎" 
              description="集成 AI 判分、ELO 学力追踪与赛博助教，赋能数字化学习。"
            />
            <FeatureItem 
              icon={MessageSquare} 
              title="及时答疑" 
              description="社群 + 赛博助教 + 主讲亲答，确保每一个疑惑不过夜。"
            />
            <FeatureItem 
              icon={Users} 
              title="一对一服务" 
              description="根据学员背景提供个性化建议，拒绝任何形式的流水线化教学。"
            />
            <FeatureItem 
              icon={Trophy} 
              title="模拟考试" 
              description="包含 4 次阶段考、3 次模拟考及 1 次冲刺考，对标真实环境。"
            />
            <FeatureItem 
              icon={GraduationCap} 
              title="复试辅导" 
              description="无缝衔接复试指导，提供终身有效的就业联盟与实操资源。"
            />
          </div>
        </div>
      </section>

      {/* Bottom CTA Card */}
      <section className="py-32 bg-white dark:bg-[#0F1115]">
        <div className="max-w-5xl mx-auto px-6">
          <Card className="p-16 md:p-24 rounded-[4rem] bg-slate-900 text-white border-slate-800 shadow-lg relative overflow-hidden">
            <div className="relative z-10 space-y-12 text-center">
              <div className="space-y-6">
                <h3 className="text-5xl font-black uppercase tracking-tight">K2 全程班计划</h3>
                <p className="text-emerald-400 text-lg font-bold uppercase tracking-[0.4em]">Ready to Start Your Journey?</p>
              </div>
              
              <div className="grid grid-cols-1 md:grid-cols-2 gap-8 text-left max-w-3xl mx-auto">
                {[
                  '全套 AMR 视频课程与配套讲义',
                  '300+ 习题与 8 次全真模拟考测',
                  '宇艺系统 AI 判分与赛博助教权限',
                  '复试指导与终身就业联盟席位'
                ].map(item => (
                  <div key={item} className="flex items-center gap-4 text-base font-medium text-slate-300">
                    <CheckCircle2 className="h-6 w-6 text-emerald-400 shrink-0" />
                    {item}
                  </div>
                ))}
              </div>

              <div className="pt-6">
                <Button size="lg" className="w-full md:w-auto px-20 h-20 rounded-full bg-white text-slate-900 font-bold text-2xl hover:bg-slate-100 shadow" onClick={() => navigate('/register')}>
                  开始学习 · ¥8150
                </Button>
              </div>
            </div>
          </Card>
        </div>
      </section>

      {/* Footer */}
      <footer className="py-20 border-t border-slate-100 dark:border-slate-900 text-center space-y-2">
        <p className="text-slate-400 text-sm">© {COPYRIGHT_YEAR} {COPYRIGHT_ENTITY}</p>
        <p className="text-[11px] font-bold text-slate-200 dark:text-slate-800 uppercase tracking-[0.3em]">{APP_VERSION} · {BRAND_DESC}</p>
      </footer>
    </div>
  );
};
