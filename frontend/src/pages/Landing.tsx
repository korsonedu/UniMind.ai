import { useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowRight, ArrowUpRight } from '@phosphor-icons/react';
import { useAuthStore } from '@/store/useAuthStore';
import { APP_VERSION, COPYRIGHT_YEAR } from '@/constants/version';
import '@/styles/landing.css';

const scenes = [
  { id: 'plan', label: '找到学习方向', prompt: '看看我的学习情况，今天先学什么？', tools: ['读取学习记录', '分析薄弱知识点', '给出下一步建议'], detail: '把学习记录变成有依据的建议，从你当前的进度出发。', alt: '小宇调用学习统计和知识掌握工具，展示学习数据与行动建议' },
  { id: 'graph', label: '看懂公式与图像', prompt: '为什么利率上升，债券价格反而下降？画图帮我理解。', tools: ['检索知识点', '绘制价格曲线', '展开折现公式'], detail: '让抽象的变化看得见，把推导过程和函数图像放在一起理解。', alt: '小宇在对话中展示债券价格与收益率曲线' },
  { id: 'map', label: '串起知识关系', prompt: '帮我把这些知识点串起来。', tools: ['梳理知识结构', '生成知识图谱', '标记知识关系'], detail: '从一个概念走向一张知识网络，知道它从哪里来，又能用在哪里。', alt: '小宇在对话中生成知识图谱，展示概念之间的联系' },
  { id: 'practice', label: '在练习中掌握', prompt: '围绕债券定价出道题，看看我是否真的懂了。', tools: ['匹配针对性练习', '提交并批改', '解释解题步骤'], detail: '把“听懂了”落到一次作答里，及时看见自己卡在哪一步。', alt: '小宇根据薄弱点匹配可作答练习，支持提交批改' },
];

const stories = [
  { scene: scenes[1], eyebrow: '01 / MAKE IT VISIBLE', title: <>公式不必<br />只停留在纸上。</>, text: '一个问题，可以用文字解释，也可以展开推导、画出图像。小宇把不同的表达方式放回同一段对话，让你顺着思路继续追问。' },
  { scene: scenes[2], eyebrow: '02 / CONNECT THE DOTS', title: <>从记住一个点，<br />到理解一张网。</>, text: '概念之间的关系同样值得学。让小宇帮你整理知识结构，把分散的知识点串起来，再回到需要补上的地方。' },
  { scene: scenes[3], eyebrow: '03 / LEARN BY DOING', title: <>学到哪里，<br />就练到哪里。</>, text: '在对话中做一道题，提交答案、查看批改、追问解题步骤。从理解到作答，不必把正在进行的思考打断。' },
];

export function Landing() {
  const user = useAuthStore(state => state.user);
  const entry = user ? '/xiaoyu' : '/register';
  const [activeScene, setActiveScene] = useState(0);
  const scene = scenes[activeScene];

  return <div className="um-landing">
    <header className="landing-header landing-wrap">
      <Link to="/" aria-label="UniMind 首页" className="landing-brand"><img src="/Unimind_logo_wide.png" alt="UniMind.ai" width="150" height="34" /></Link>
      <nav aria-label="首页导航">
        <a href="#agent">认识小宇</a><a href="#tools">工具与能力</a>
        <Link to="/pricing" className="landing-nav-pricing">AI 加量</Link>
        {!user && <Link to="/login">登录</Link>}
        <Link to={entry} className="landing-nav-entry">{user ? '进入学习空间' : '开始体验'}<ArrowUpRight size={16} /></Link>
      </nav>
    </header>

    <main>
      <section className="landing-hero landing-wrap" id="agent">
        <div className="landing-eyebrow"><span className="landing-status" /> XIAOYU / YOUR LEARNING AGENT</div>
        <div className="landing-hero-copy">
          <h1>学习这件事，<br />和<span>小宇</span>一起推进。</h1>
          <div className="landing-hero-aside"><p>一个会用工具的学习 Agent。<br />理解你的进度，拆解眼前的问题，<br />把下一步学习真正展开。</p><Link to={entry} className="landing-button">和小宇开始<ArrowUpRight size={19} /></Link></div>
        </div>
        <div className="landing-scene-tabs" aria-label="选择 Agent 展示场景">
          {scenes.map((item, index) => <button key={item.id} type="button" aria-pressed={activeScene === index} onClick={() => setActiveScene(index)}><span>0{index + 1}</span>{item.label}<ArrowUpRight size={15} /></button>)}
        </div>
        <div className="landing-demo" aria-live="polite">
          <div className="landing-demo-caption"><span className="landing-demo-label">YOU → XIAOYU</span><p>{scene.prompt}</p><span className="landing-demo-note">演示数据 · 真实产品界面</span></div>
          <a className="landing-product-shot" href={`/screenshots/landing-agent-${scene.id}.jpg`} target="_blank" rel="noopener noreferrer" aria-label={`查看大图：${scene.alt}`}><img key={scene.id} src={`/screenshots/landing-agent-${scene.id}.jpg`} alt={scene.alt} width="1280" height="720" fetchPriority="high" /></a>
          <div className="landing-tool-chain">{scene.tools.map((tool, index) => <span key={tool}><small>0{index + 1}</small>{tool}{index < scene.tools.length - 1 && <ArrowRight size={14} aria-hidden="true" />}</span>)}</div>
        </div>
        <div className="landing-under-demo"><span>FROM A QUESTION TO A NEXT STEP.</span><p>{scene.detail}</p></div>
      </section>

      <section className="landing-tools-intro landing-wrap" id="tools">
        <div className="landing-eyebrow">AN AGENT. MANY WAYS TO LEARN.</div>
        <h2>不止于回答。<br /><span>让每一种工具，接住你的问题。</span></h2>
        <p>查学习记录、找课程、画图、梳理知识、出题与批改。小宇根据问题调用工具，让对话有过程，也有可以继续的下一步。</p>
      </section>

      <div className="landing-stories">
        {stories.map(({ scene: item, eyebrow, title, text }, index) => <section key={item.id} className={`landing-story landing-wrap ${index === 1 ? 'landing-story-reverse' : ''}`}>
          <div className="landing-story-copy"><div className="landing-eyebrow">{eyebrow}</div><h2>{title}</h2><p>{text}</p><div className="landing-story-tools">{item.tools.map(tool => <span key={tool}>{tool}</span>)}</div></div>
          <a className="landing-story-image" href={`/screenshots/landing-agent-${item.id}.jpg`} target="_blank" rel="noopener noreferrer" aria-label={`查看大图：${item.alt}`}><img src={`/screenshots/landing-agent-${item.id}.jpg`} alt={item.alt} width="1280" height="720" loading="lazy" /><span>探索真实界面 <ArrowUpRight size={15} /></span></a>
        </section>)}
      </div>

      <section className="landing-workspace landing-wrap">
        <div className="landing-eyebrow">ONE CONNECTED LEARNING SPACE</div>
        <div className="landing-workspace-heading"><h2>小宇身后，<br />是你的整个学习空间。</h2><p>课程、练习、复习与交流各有位置。<br />把学习留下来，也把它接起来。</p></div>
        <div className="landing-workspace-list">
          {[['课程与资料', '按进度学习课程，查找配套资料。'], ['练习与 Memorix', '围绕知识点练习，回到错题与待复习内容。'], ['学习记录与社区', '查看自己的学习足迹，交流正在遇到的问题。']].map(([title, text], index) => <div key={title}><span>0{index + 1}</span><h3>{title}</h3><p>{text}</p></div>)}
        </div>
      </section>

      <section className="landing-start">
        <div className="landing-wrap"><div className="landing-eyebrow">YOUR NEXT QUESTION STARTS HERE.</div><h2>带着问题来。<br />带着下一步继续。</h2><Link to={entry} className="landing-button">{user ? '回到小宇' : '免费开始体验'}<ArrowUpRight size={20} /></Link><p>未报名课程，也可以先体验每周有限的问答服务。</p></div>
      </section>
      <section className="landing-service landing-wrap" aria-label="服务说明"><p>课程在线下报名和付费，由管理员开通课程与配套功能。课程学员享有更多问答额度。</p><p>AI 加量只增加问答次数，不会开放课程访问权限。付费服务到期后，学习记录仍会保留，基础学习可以继续使用。<Link to="/pricing">了解 AI 加量 <ArrowUpRight size={12} /></Link></p></section>
    </main>

    <footer className="landing-footer landing-wrap"><span>© {COPYRIGHT_YEAR} 北京融知高科 · UniMind.ai · {APP_VERSION}</span><div><a href="https://beian.miit.gov.cn/" target="_blank" rel="noopener noreferrer">京ICP备2023012726号-2</a><Link to="/terms">用户协议</Link><Link to="/privacy">隐私政策</Link></div></footer>
  </div>;
}
