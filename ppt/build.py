#!/usr/bin/env python3
"""UniMind 展品手册 PPT 生成器 · Swiss IKB 瑞士风 · 20 页"""
from pathlib import Path

TMPL = Path(__file__).parent / "template.html"
OUT  = Path(__file__).parent / "index.html"

template = TMPL.read_text()

# ── 切点定位 ──────────────────────────────────────────
sh_pos       = template.find('<!-- SLIDES_HERE')
comment_end  = template.find('-->', sh_pos) + 3
first_slide  = template.find('<section class="slide', comment_end)
nav_pos      = template.find('<div id="nav">')
deck_close   = template.rfind('</div>', 0, nav_pos)

HEAD = template[:first_slide]
TAIL = template[deck_close:]

T = 20  # total pages

# ── CSS 补丁：模板缺失的类 ──────────────────────────
PATCH_CSS = """
/* ===== UniMind 展品手册补丁 ===== */
.grid-2-9{display:grid;grid-template-columns:1fr 1.6fr;gap:3vw;flex:1;align-items:center}
.lead-col{display:flex;flex-direction:column;gap:1.6vh}
.sub-card-stack{display:flex;flex-direction:column;gap:2vh}
.big-num{font-family:var(--mono);font-weight:200;font-size:min(5.6vw,10vh);line-height:1;letter-spacing:-.04em;color:var(--text-placeholder)}
.four-cards{display:grid;grid-template-columns:repeat(4,1fr);gap:2vw}
.fc-col{display:flex;flex-direction:column}
.cell-6{display:grid;grid-template-columns:repeat(3,1fr);gap:3vh 2vw}
.cell{display:flex;flex-direction:column;align-items:flex-start;gap:1vh;padding:2vh 1.6vw;border:1px solid var(--border-subtle)}
.cell-num{font-family:var(--mono);font-weight:500;font-size:13px;color:var(--text-placeholder)}
.why-now-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:2vw}
.why-col{display:flex;flex-direction:column;padding:2vh 0}
.why-num-bottom{font-family:var(--mono);font-weight:200;font-size:min(4vw,7vh);letter-spacing:-.04em;color:var(--text-placeholder);margin-top:auto;padding-top:2vh}
.stacked-ledger{display:flex;flex-direction:column;gap:.6vh}
.ledger-row{padding:1.6vh 0;border-bottom:1px solid var(--border-subtle)}
.ledger-num{font-family:var(--mono);font-weight:200;font-size:min(3.6vw,6.5vh);letter-spacing:-.03em;min-width:6em}
.h-statement{font-family:var(--sans),var(--sans-zh);font-weight:200;font-size:min(6.4vw,11.2vh);line-height:1.1;letter-spacing:-.04em;text-align:left;margin:auto 0}
.stmt-anchor{font-family:var(--mono);font-size:max(14px,.85vw);color:var(--text-helper);text-align:right;margin-top:4vh}
.brief-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:2vh 1.6vw}
.brief-card{display:flex;flex-direction:column;gap:1vh;padding:2vh 1.6vw;min-height:12vh}
.brief-card.is-accent{background:var(--accent);color:var(--accent-on)}
.brief-card.is-accent h4{color:var(--accent-on)}
.brief-card.is-accent p{color:rgba(255,255,255,.7)}
.tech-specs{display:grid;grid-template-columns:repeat(3,1fr);gap:3vh 2vw}
.system-diagram{flex:1;display:flex;align-items:center;justify-content:center;gap:4vw}
.tl-step{display:flex;gap:1.2vw;align-items:flex-start}
.loop-step{display:flex;align-items:flex-start;gap:1.6vw}
.force-card{display:flex;flex-direction:column;padding:2.4vh 2vw}
"""

# Inject patch CSS into HEAD (before </style>)
style_close = HEAD.rfind('</style>')
HEAD = HEAD[:style_close] + PATCH_CSS + HEAD[style_close:]

# ── 辅助函数 ──────────────────────────────────────────
def page(n): return f"{n:02d} / {T}"

def sec(layout, anim, cls="light", body=""):
    return f'<section class="slide {cls}" data-animate="{anim}" data-layout="{layout}">\n{body}\n</section>\n'

def chrome(l, r):
    return f'<div class="chrome-min"><div class="l">{l}</div><div class="r">{r}</div></div>'

def card(layout, anim):
    return f'<div class="canvas-card">\n{chrome("", "")}\n'

# ═══════════════════════════════════════════════════════
# P01 · S01 · Cover (IKB 满屏)
# ═══════════════════════════════════════════════════════
def s01():
    b = f'''  <div class="canvas-card">
    <canvas class="ascii-bg" aria-hidden="true"></canvas>
    {chrome("UniMind 展品手册", page(1))}
    <div style="flex:1;padding:0;display:grid;grid-template-rows:auto 1fr auto;gap:2.6vh">
      <div data-anim="kicker" class="t-meta" style="color:rgba(255,255,255,.78);letter-spacing:.22em">EDUCATION AI INFRASTRUCTURE</div>
      <h1 data-anim="title" style="align-self:center;font-family:var(--sans),var(--sans-zh);font-weight:200;font-size:min(11.6vw,19vh);line-height:.94;letter-spacing:-.025em;color:#fff">UniMind<span style="font-style:italic;font-weight:300">.ai</span></h1>
      <div data-anim="bottom" style="display:grid;grid-template-rows:auto auto;gap:1.6vh;border-top:1px solid rgba(255,255,255,.22);padding-top:2vh">
        <div data-anim="lead" class="lead" style="max-width:52ch;color:rgba(255,255,255,.86);font-weight:300">教育机构 AI 基础设施 · 把「学生忘了什么」变成系统知道学生什么时候会忘</div>
        <div style="display:flex;justify-content:space-between;align-items:end">
          <div class="t-meta" style="color:rgba(255,255,255,.6)">Eular &amp; Team · 2026</div>
          <div class="t-meta" style="color:rgba(255,255,255,.6)">→ 键盘 ← → 翻页</div>
        </div>
      </div>
    </div>
  </div>'''
    return sec("S01", "hero", "accent", b)

# ═══════════════════════════════════════════════════════
# P02 · S03 · Statement
# ═══════════════════════════════════════════════════════
def s02():
    b = f'''  <div class="canvas-card">
    {chrome("你的痛点", page(2))}
    <h1 class="h-statement">
      <span>学生报班 → 上课 → 做题</span><br>
      <span>→ 两个月后忘了大半</span>
    </h1>
    <span class="stmt-anchor">— 问题不在老师。50个学生×1000道题，没人能记住每道题该什么时候复习。我们解决的就是这件事。</span>
  </div>'''
    return sec("S03", "statement", "light", b)

# ═══════════════════════════════════════════════════════
# P03 · S08 · Duo Compare
# ═══════════════════════════════════════════════════════
def s03():
    b = f'''  <div class="canvas-card">
    {chrome("行业对比", page(3))}
    <div class="duo-compare">
      <div class="col">
        <span class="col-tag"><span class="num">01</span> 传统</span>
        <div class="col-ttl">教育 SaaS</div>
        <div class="col-desc">
          题库 + LMS 堆功能<br><br>
          固定间隔复习（1-3-7-30）<br><br>
          只判对错，不知错因<br><br>
          所有机构一套参数
        </div>
      </div>
      <span class="vrule"></span>
      <div class="col accent">
        <span class="col-tag"><span class="num">02</span> UniMind</span>
        <div class="col-ttl">AI 基础设施</div>
        <div class="col-desc">
          AI Agent 驱动，对话即教学<br><br>
          自适应复习间隔，每人每道题不同<br><br>
          3 类错因 + 能力值评估 + 知识点掌握度<br><br>
          机构级隔离，重点校/普通校独立模型
        </div>
      </div>
    </div>
  </div>'''
    return sec("S08", "duo-mirror", "light", b)

# ═══════════════════════════════════════════════════════
# P04 · S18 · Why Now
# ═══════════════════════════════════════════════════════
def s04():
    b = f'''  <div class="canvas-card">
    {chrome("UniMind 做什么", page(4))}
    <h2 style="font-family:var(--sans),var(--sans-zh);font-weight:200;font-size:min(5.8vw,10.2vh);line-height:.96;letter-spacing:-.035em;margin-bottom:5vh">三个核心能力，解决一个根本问题</h2>
    <div class="why-now-grid" data-anim="up">
      <div class="why-col" data-anim="col">
        <div class="t-cat">精准复习</div>
        <h3 style="font-family:var(--sans),var(--sans-zh);font-weight:300;font-size:min(2.4vw,6vh);line-height:1.15;letter-spacing:-.02em;margin:1.6vh 0">系统知道每个学生每道题什么时候该复习</h3>
        <p style="font-size:max(15px,1vw);line-height:1.5;color:var(--text-secondary);font-weight:300">不再靠人工排复习计划。系统根据每个学生的遗忘速度，在最佳时机推送复习。复习次数减少 40%，提分效果反而更好。</p>
        <div class="why-num-bottom">−40%</div>
      </div>
      <div class="why-col" data-anim="col">
        <div class="t-cat">智能出题</div>
        <h3 style="font-family:var(--sans),var(--sans-zh);font-weight:300;font-size:min(2.4vw,6vh);line-height:1.15;letter-spacing:-.02em;margin:1.6vh 0">1 位老师 30 分钟，干完 3 位老师 2 周的活</h3>
        <p style="font-size:max(15px,1vw);line-height:1.5;color:var(--text-secondary);font-weight:300">对着工作台说一句话，题目秒级生成。多轮自动审核，可用率 85% 以上。老师的时间省下来，花在真正需要人的地方。</p>
        <div class="why-num-bottom">30min</div>
      </div>
      <div class="why-col" data-anim="col">
        <div class="t-cat">主动服务</div>
        <h3 style="font-family:var(--sans),var(--sans-zh);font-weight:300;font-size:min(2.4vw,6vh);line-height:1.15;letter-spacing:-.02em;margin:1.6vh 0">AI 教练 24 小时在线，不等学生来找</h3>
        <p style="font-size:max(15px,1vw);line-height:1.5;color:var(--text-secondary);font-weight:300">学生打开 App，小宇已经在说话了——今天该复习什么、哪里薄弱。使用小宇的学生，留存率比纯刷题用户高 23%。</p>
        <div class="why-num-bottom" style="color:var(--accent)">+23%</div>
      </div>
    </div>
  </div>'''
    return sec("S18", "why-now", "light", b)

# ═══════════════════════════════════════════════════════
# P05 · S19 · Four Cards (四大核心优势)
# ═══════════════════════════════════════════════════════
def s05():
    cards = [
        ("01 / 精准", "每个学生每道题\n独立复习节奏", "系统自动追踪每个学生的遗忘曲线。概念错误、计算失误、粗心——三种错因分类处理，不同错误不同策略。学生提分更快，续费率自然上去。"),
        ("02 / 高效", "老师不用再\n熬夜出题了", "对着工作台说一句话，题目自动生成。多轮自动审核确保质量。1 位老师 30 分钟完成以往 3 人 2 周的工作量。老师把时间花在真正需要人的地方。"),
        ("03 / 省心", "AI 教练 24 小时\n在线服务", "学生登录就看到小宇在等他。今天该复习什么、哪里薄弱、怎么改进——主动推送，不等学生来找。使用小宇的学生留存率高出 23%。"),
        ("04 / 放心", "每家机构独立运行\n数据安全隔离", "重点学校和普通学校的教学重点不同，系统为每家机构独立建模。支持自有品牌展示、独立定价收费。你的数据只属于你。"),
    ]
    rows = []
    for meta, title, desc in cards:
        rows.append(f'''      <div class="fc-col" data-anim="col">
        <div class="t-meta" style="font-size:14px">— {meta}</div>
        <h3 style="font-family:var(--sans),var(--sans-zh);font-weight:200;font-size:min(3.2vw,7vh);line-height:1.05;letter-spacing:-.03em;margin:1.4vh 0">{title}</h3>
        <p style="font-size:max(15px,1vw);line-height:1.55;color:var(--text-secondary);font-weight:300">{desc}</p>
      </div>''')
    b = f'''  <div class="canvas-card">
    {chrome("核心优势", page(5))}
    <div data-anim="line">
      <div style="height:1px;background:var(--accent);width:80px;margin-bottom:2vh"></div>
      <h2 style="font-family:var(--sans),var(--sans-zh);font-weight:200;font-size:min(5.8vw,10.2vh);line-height:.96;letter-spacing:-.035em;margin-bottom:5vh">四大核心优势</h2>
    </div>
    <div class="four-cards" data-anim="up">
{chr(10).join(rows)}
    </div>
  </div>'''
    return sec("S19", "four-cards", "light", b)

# ═══════════════════════════════════════════════════════
# P06 · S04 · Six Cells (六大核心模块)
# ═══════════════════════════════════════════════════════
def s06():
    icons = ["bot", "brain-circuit", "git-compare", "network", "message-square", "users"]
    titles = ["Agent 智能体层", "算法引擎层", "对抗出题管线", "全景知识图谱", "AI 模拟面试", "机构管理平台"]
    descs = [
        "学生端小宇教练 + 教师端工作台",
        "智能复习 / 诊断分析 / 自进化",
        "多轮自动审核，85%+ 可用率",
        "12学科 11,908知识点 交互式可视化",
        "实时对话 · 多轮追问 · 面试训练",
        "机构级管理 · 白标 · 独立定价 · API",
    ]
    cells = []
    for i in range(6):
        cells.append(f'''      <div class="cell" data-anim="cell">
        <i data-lucide="{icons[i]}" style="color:var(--accent)"></i>
        <span class="cell-num">0{i+1}</span>
        <h4 style="font-weight:500;font-size:max(15px,1.05vw)">{titles[i]}</h4>
        <p style="font-size:max(14px,1vw);line-height:1.45;color:var(--text-helper)">{descs[i]}</p>
      </div>''')
    b = f'''  <div class="canvas-card">
    {chrome("产品模块", page(6))}
    <h2 style="font-family:var(--sans),var(--sans-zh);font-weight:200;font-size:min(5.8vw,10.2vh);line-height:.96;letter-spacing:-.035em;margin-bottom:5vh">六大核心模块</h2>
    <div class="cell-6" data-anim="up">
{chr(10).join(cells)}
    </div>
  </div>'''
    return sec("S04", "field-notes", "light", b)

# ═══════════════════════════════════════════════════════
# P07 · S17 · System Diagram (同心圆架构)
# ═══════════════════════════════════════════════════════
def s07():
    b = f'''  <div class="canvas-card">
    {chrome("技术架构", page(7))}
    <h2 style="font-family:var(--sans),var(--sans-zh);font-weight:200;font-size:min(5.8vw,10.2vh);line-height:.96;letter-spacing:-.035em;margin-bottom:3vh">一套系统，覆盖教→练→测→评完整闭环</h2>
    <div class="system-diagram" data-anim="up" style="flex:1;display:flex;align-items:center;justify-content:center;gap:4vw">
      <div style="position:relative;width:min(42vw,58vh);height:min(42vw,58vh);display:flex;align-items:center;justify-content:center">
        <svg viewBox="0 0 400 400" style="width:100%;height:100%;position:absolute;inset:0">
          <circle cx="200" cy="200" r="180" fill="none" stroke="var(--grey-2)" stroke-width="1" stroke-dasharray="6,4"/>
          <circle cx="200" cy="200" r="130" fill="none" stroke="var(--grey-2)" stroke-width="1" stroke-dasharray="6,4"/>
          <circle cx="200" cy="200" r="80" fill="none" stroke="var(--grey-2)" stroke-width="1" stroke-dasharray="6,4"/>
          <circle cx="200" cy="200" r="40" fill="var(--accent)" stroke="var(--accent)" stroke-width="2"/>
        </svg>
        <div style="position:relative;z-index:2;text-align:center">
          <span style="font-family:var(--mono);font-weight:500;font-size:14px;color:var(--accent-on)">核心</span><br>
          <span style="font-weight:500;font-size:max(13px,0.9vw);color:var(--accent-on)">AI 引擎</span>
        </div>
        <div style="position:absolute;top:6%;left:50%;transform:translateX(-50%);text-align:center;z-index:2">
          <span class="t-cat" style="font-size:12px">能力</span><br>
          <span style="font-size:max(12px,0.8vw);color:var(--text-secondary)">34 个工具 · 2 AI 助手</span>
        </div>
        <div style="position:absolute;top:28%;right:2%;text-align:center;z-index:2">
          <span class="t-cat" style="font-size:12px">可靠性</span><br>
          <span style="font-size:max(12px,0.8vw);color:var(--text-secondary)">故障隔离 · 自动恢复</span>
        </div>
        <div style="position:absolute;bottom:18%;left:0;text-align:center;z-index:2">
          <span class="t-cat" style="font-size:12px">记忆</span><br>
          <span style="font-size:max(12px,0.8vw);color:var(--text-secondary)">跨会话 · 越用越准</span>
        </div>
        <div style="position:absolute;bottom:42%;right:0;text-align:center;z-index:2">
          <span class="t-cat" style="font-size:12px">出题</span><br>
          <span style="font-size:max(12px,0.8vw);color:var(--text-secondary)">多轮审核 · 85%+ 可用</span>
        </div>
      </div>
      <div style="display:flex;flex-direction:column;gap:2vh;max-width:36ch">
        <div style="border-left:3px solid var(--accent);padding-left:1.6vw">
          <div class="t-cat">即开即用</div>
          <p style="font-size:max(14px,1vw);line-height:1.5;color:var(--text-secondary);margin-top:.8vh">机构注册即可使用，无需部署服务器、无需技术团队。所有功能云端运行，持续自动更新。</p>
        </div>
        <div style="border-left:3px solid var(--accent);padding-left:1.6vw">
          <div class="t-cat">完整闭环</div>
          <p style="font-size:max(14px,1vw);line-height:1.5;color:var(--text-secondary);margin-top:.8vh">从出题→练习→批改→分析，全部在一个系统内完成。两端数据互通，教师命题直接供学生使用。</p>
        </div>
        <div style="border-left:3px solid var(--accent);padding-left:1.6vw">
          <div class="t-cat">独立运行</div>
          <p style="font-size:max(14px,1vw);line-height:1.5;color:var(--text-secondary);margin-top:.8vh">每家机构数据独立存储、独立建模。可自定义知识体系和品牌展示。</p>
        </div>
      </div>
    </div>
  </div>'''
    return sec("S17", "system-diagram", "light", b)

# ═══════════════════════════════════════════════════════
# P08 · S13 · Three Forces (三大算法支柱)
# ═══════════════════════════════════════════════════════
def s08():
    cards = [
        ("01", "智能记忆", "每个学生每道题独立追踪",
         ["系统持续观察每个学生的答题表现", "自动判断最佳复习时机——太早浪费、太晚遗忘", "三种错因自动识别：概念不清、计算失误、粗心大意", "学生做得越多，系统越懂他"]),
        ("02", "诊断分析", "不只判对错，知道为什么错",
         ["每道题背后是多维度能力评估", "同样做错一道题，不同学生的问题根源不同", "重点学校和普通学校分开建模——因材施教", "新题目也能用经典方法评估，不依赖大数据"]),
        ("03", "自我进化", "系统越用越聪明",
         ["自动收集每次教学交互的效果数据", "每周分析什么方法最有效", "自动生成优化建议，人工审核后上线", "你的学生使用越多，系统对你的机构越适配"]),
    ]
    rows = []
    for num, cat, title, items in cards:
        lis = "".join(f"<li style=\"font-size:max(14px,0.95vw);line-height:1.55;color:var(--text-secondary)\">{it}</li>" for it in items)
        rows.append(f'''      <article class="card-fill force-card" data-anim="card">
        <span class="big-num" style="color:var(--accent)">{num}</span>
        <span class="t-cat" style="margin:1.2vh 0 .6vh">{cat}</span>
        <h3 style="font-family:var(--sans),var(--sans-zh);font-weight:200;font-size:min(2.8vw,5.5vh);line-height:1.05;letter-spacing:-.03em">{title}</h3>
        <ul style="list-style:none;margin-top:1.6vh;display:flex;flex-direction:column;gap:.6vh">
{lis}
        </ul>
      </article>''')
    b = f'''  <div class="canvas-card">
    {chrome("为什么能做到", page(8))}
    <h2 style="font-family:var(--sans),var(--sans-zh);font-weight:200;font-size:min(5.8vw,10.2vh);line-height:.96;letter-spacing:-.035em;margin-bottom:4vh">三层技术支撑</h2>
    <div class="three-forces" data-anim="up" style="display:grid;grid-template-columns:repeat(3,1fr);gap:2vw">
{chr(10).join(rows)}
    </div>
  </div>'''
    return sec("S13", "three-forces", "light", b)

# ═══════════════════════════════════════════════════════
# P09 · S14 · Loop Diagram (MUTAR 闭环)
# ═══════════════════════════════════════════════════════
def s09():
    steps = [
        ("M", "观察 · 采集", "自动记录每次教学交互：出题质量、回答数据、学生反馈"),
        ("U", "评估 · 发现", "每周自动分析——哪些方法效果好、哪些需要改进"),
        ("T", "分析 · 诊断", "AI 分析问题根因，判断是出题质量还是复习策略需要调整"),
        ("A", "优化 · 进化", "生成改进建议，机构负责人审核后一键上线"),
    ]
    items = []
    for letter, title, desc in steps:
        items.append(f'''          <div class="loop-step" data-anim="step" style="display:flex;align-items:flex-start;gap:1.6vw">
            <div style="width:min(5vw,7vh);height:min(5vw,7vh);border:1px solid var(--accent);display:flex;align-items:center;justify-content:center;flex-shrink:0">
              <span style="font-family:var(--mono);font-weight:600;font-size:max(18px,1.4vw);color:var(--accent)">{letter}</span>
            </div>
            <div>
              <h4 style="font-weight:500;font-size:max(15px,1.15vw);line-height:1.3;color:var(--accent)">{title}</h4>
              <p style="font-size:max(14px,1vw);line-height:1.5;color:var(--text-secondary);margin-top:.4vh">{desc}</p>
            </div>
          </div>''')
    b = f'''  <div class="canvas-card">
    {chrome("持续进化", page(9))}
    <div data-anim="up" style="display:grid;grid-template-columns:1fr 1fr;gap:3vw;flex:1;align-items:center">
      <div>
        <h2 style="font-family:var(--sans),var(--sans-zh);font-weight:200;font-size:min(5.2vw,9.2vh);line-height:.98;letter-spacing:-.035em;margin-bottom:3vh">系统越用越懂你的机构</h2>
        <div style="display:flex;flex-direction:column;gap:2.2vh">
{chr(10).join(items)}
        </div>
      </div>
      <div style="position:relative;width:min(34vw,48vh);height:min(34vw,48vh);margin:0 auto">
        <svg viewBox="0 0 300 300" style="width:100%;height:100%">
          <circle cx="150" cy="150" r="120" fill="none" stroke="var(--accent)" stroke-width="1.5" stroke-dasharray="8,6"/>
          <text x="150" y="38" text-anchor="middle" font-family="var(--mono)" font-size="18" font-weight="600" fill="var(--accent)">M</text>
          <text x="248" y="155" text-anchor="middle" font-family="var(--mono)" font-size="18" font-weight="600" fill="var(--accent)">U</text>
          <text x="150" y="278" text-anchor="middle" font-family="var(--mono)" font-size="18" font-weight="600" fill="var(--accent)">T</text>
          <text x="52" y="155" text-anchor="middle" font-family="var(--mono)" font-size="18" font-weight="600" fill="var(--accent)">A</text>
          <circle cx="150" cy="150" r="8" fill="var(--accent)"/>
        </svg>
        <div style="position:absolute;inset:0;display:flex;align-items:center;justify-content:center;pointer-events:none">
          <span style="font-family:var(--mono);font-weight:500;font-size:13px;color:var(--text-helper)">每周循环</span>
        </div>
      </div>
    </div>
  </div>'''
    return sec("S14", "loop-form", "light", b)

# ═══════════════════════════════════════════════════════
# P10 · S11 · Timeline Walk (学习闭环)
# ═══════════════════════════════════════════════════════
def s10():
    steps = [
        ("01", "诊断测试", "精准定位起点"),
        ("02", "智能出题", "一句话生成题目"),
        ("03", "刷题训练", "自适应复习节奏"),
        ("04", "知识图谱", "薄弱点一目了然"),
        ("05", "AI 教练", "主动分析指导"),
        ("06", "模拟考试", "自动组卷评分"),
        ("07", "错题复习", "精准推送巩固"),
    ]
    nodes = []
    for i, (num, title, desc) in enumerate(steps):
        updown = "up" if i % 2 == 0 else ""
        nodes.append(f'''        <div class="th-node {updown}" data-anim="node" style="flex:1;display:flex;flex-direction:column;align-items:center;gap:.8vh">
          <span class="label" style="font-size:max(13px,.82vw);color:var(--text-secondary);font-weight:400;text-align:center;max-width:10ch;line-height:1.3">{title}<br><small style="font-size:.85em;color:var(--text-helper)">{desc}</small></span>
          <span class="dot" style="display:block;width:10px;height:10px;background:var(--accent)"></span>
          <span style="font-family:var(--mono);font-weight:600;font-size:12px;color:var(--text-helper)">{num}</span>
        </div>''')
    b = f'''  <div class="canvas-card">
    {chrome("学习闭环", page(10))}
    <h2 style="font-family:var(--sans),var(--sans-zh);font-weight:200;font-size:min(5.8vw,10.2vh);line-height:.96;letter-spacing:-.035em;margin-bottom:4vh">7 步完整学习闭环</h2>
    <div class="timeline-h" data-anim="up" style="display:flex;align-items:center;gap:0;flex:1;padding:3vh 0;position:relative">
      <div style="position:absolute;left:0;right:0;top:50%;height:1px;background:var(--grey-2)"></div>
{chr(10).join(nodes)}
    </div>
    <div class="t-meta" style="text-align:center;margin-top:2vh">诊断 → 出题 → 训练 → 分析 → 教练 → 模考 → 复习 · 完整闭环</div>
  </div>'''
    return sec("S11", "timeline-walk", "light", b)

# ═══════════════════════════════════════════════════════
# P11 · S21 · Tech Spec
# ═══════════════════════════════════════════════════════
def s11():
    specs = [
        ("12", "学科覆盖", "金融·数学·物理·考研·考证等"),
        ("11,908", "知识点", "四级知识体系，机构可自定义"),
        ("34个", "AI 工具", "2 个 AI 助手 · 自主调用"),
        ("85%+", "出题可用率", "多轮自动审核，秒级生成"),
        ("≤1.2秒", "响应速度", "对话交互零等待感"),
        ("5轮", "自主决策", "AI 自动编排完整教学流程"),
    ]
    rows = []
    for val, label, desc in specs:
        rows.append(f'''      <div class="spec-col" data-anim="col" style="text-align:center">
        <div style="font-family:var(--mono);font-weight:200;font-size:min(4vw,7vh);letter-spacing:-.03em;color:var(--accent)">{val}</div>
        <div class="t-cat" style="margin:.8vh 0 .4vh">{label}</div>
        <p style="font-size:max(13px,0.85vw);line-height:1.4;color:var(--text-helper)">{desc}</p>
      </div>''')
    b = f'''  <div class="canvas-card">
    {chrome("技术规格", page(11))}
    <h2 style="font-family:var(--sans),var(--sans-zh);font-weight:200;font-size:min(5.8vw,10.2vh);line-height:.96;letter-spacing:-.035em;margin-bottom:4vh">技术规格一览</h2>
    <div class="tech-specs" data-anim="up" style="display:grid;grid-template-columns:repeat(3,1fr);gap:3vh 2vw">
{chr(10).join(rows)}
    </div>
  </div>'''
    return sec("S21", "tech-spec", "light", b)

# ═══════════════════════════════════════════════════════
# P12 · S07 · H-Bar Chart (核心技术指标对比)
# ═══════════════════════════════════════════════════════
def s12():
    bars = [
        ("85%", "AI 出题直接可用，无需人工修改", "85"),
        ("−40%", "同等掌握度下复习次数减少", "60"),
        ("+23%", "学生留存率提升（vs 纯题库用户）", "77"),
        ("30min", "1 位老师出题耗时（传统方式：3 人 2 周）", "92"),
        ("72%", "AI 对话含个性化数据与建议", "72"),
        ("12", "预置学科知识体系", "80"),
        ("14天", "全功能免费试用，零门槛体验", "70"),
        ("¥0.5", "单次百万字 AI 推理成本", "88"),
    ]
    rows = []
    for val, label, w in bars:
        rows.append(f'''      <div data-anim="row" style="display:flex;align-items:center;gap:1.6vw;margin-bottom:1.6vh">
        <span class="row-lbl" style="min-width:14ch;font-family:var(--mono);font-weight:500;font-size:max(13px,0.9vw);color:var(--accent)">{val}</span>
        <span style="flex:1;font-size:max(14px,0.95vw);font-weight:400">{label}</span>
        <div style="width:min(24vw,240px);height:6px;background:var(--grey-2);position:relative">
          <div class="row-fill" style="position:absolute;left:0;top:0;height:100%;width:{w}%;background:var(--accent)"></div>
        </div>
        <span class="row-val" style="font-family:var(--mono);font-size:13px;color:var(--text-helper);min-width:4ch;text-align:right">{w}</span>
      </div>''')
    b = f'''  <div class="canvas-card">
    {chrome("性能指标", page(12))}
    <h2 style="font-family:var(--sans),var(--sans-zh);font-weight:200;font-size:min(5.8vw,10.2vh);line-height:.96;letter-spacing:-.035em;margin-bottom:4vh">核心技术指标</h2>
    <div data-anim="up" style="max-width:90ch">
{chr(10).join(rows)}
    </div>
  </div>'''
    return sec("S07", "bar-grow", "light", b)

# ═══════════════════════════════════════════════════════
# P13 · S16 · Multi-card (更多产品能力)
# ═══════════════════════════════════════════════════════
def s13():
    cards = [
        ("音视频课程中心", "分片上传 · AI大纲 · ASR多方案 · 视频出题", False),
        ("沉浸式自习室", "实时在线 · 番茄钟 · 周计划", False),
        ("AI 模拟面试", "实时对话 · 多轮追问 · 简历分析 · 综合报告", False),
        ("ELO 激励体系", "付费会员积分特权 · 周度认知报告", False),
        ("多租户机构隔离", "RBAC权限 · 数据隔离 · 品牌白标 · 独立支付", False),
        ("智能教学工具", "意图识别 · 工具调度 · 准确率持续提升", True),
    ]
    rows = []
    for title, desc, accent in cards:
        cls = "is-accent" if accent else ""
        rows.append(f'''      <article class="card-fill brief-card {cls}" data-anim="card">
        <h4 style="font-weight:500;font-size:max(15px,1.05vw);line-height:1.3">{title}</h4>
        <p style="font-size:max(14px,1vw);color:var(--text-helper);margin-top:auto">{desc}</p>
      </article>''')
    b = f'''  <div class="canvas-card">
    {chrome("扩展功能", page(13))}
    <h2 style="font-family:var(--sans),var(--sans-zh);font-weight:200;font-size:min(5.8vw,10.2vh);line-height:.96;letter-spacing:-.035em;margin-bottom:5vh">更多产品能力一览</h2>
    <div class="brief-grid" data-anim="up" style="display:grid;grid-template-columns:repeat(3,1fr);gap:2vh 1.6vw">
{chr(10).join(rows)}
    </div>
  </div>'''
    return sec("S16", "field-notes", "light", b)

# ═══════════════════════════════════════════════════════
# P14 · S05 · Three Sub-cards (三重个性化)
# ═══════════════════════════════════════════════════════
def s14():
    cards = [
        ("01", "诊断冷启动", "首次登录自动生成诊断测试。根据知识体系前序依赖关系精准定位起点，避免盲目刷题。"),
        ("02", "智能行为建模", "每道题实时更新学生记忆状态。自动识别概念不清、计算失误、粗心大意三种错因，不同错误不同处理策略。"),
        ("03", "AI 对话记忆", "跨会话记住学生目标和偏好。每次对话都在变得更懂这个学生。使用时间越长，服务越精准。"),
    ]
    rows = []
    for num, title, desc in cards:
        rows.append(f'''    <article class="card-fill sub-card" data-anim="card">
      <span class="big-num">{num}</span>
      <h4 style="font-weight:500;font-size:max(15px,1.15vw)">{title}</h4>
      <p style="font-size:max(14px,1vw);line-height:1.5;color:var(--text-secondary)">{desc}</p>
    </article>''')
    b = f'''  <div class="canvas-card">
    {chrome("个性化体系", page(14))}
    <div class="grid-2-9">
      <div class="lead-col" data-anim="hero">
        <span class="t-cat">PERSONALIZATION</span>
        <h2 style="font-family:var(--sans),var(--sans-zh);font-weight:200;font-size:min(5.2vw,9.2vh);line-height:.98;letter-spacing:-.035em">三重个性化</h2>
        <p style="font-size:max(14px,1vw);line-height:1.55;color:var(--text-secondary);margin-top:2vh;max-width:28ch">不是一套方案适配所有人。UniMind 在三个层面实现深度个性化，且三层联动。</p>
      </div>
      <div class="sub-card-stack">
{chr(10).join(rows)}
      </div>
    </div>
  </div>'''
    return sec("S05", "stack-build", "light", b)

# ═══════════════════════════════════════════════════════
# P15 · S20 · Stacked Ledger (定价)
# ═══════════════════════════════════════════════════════
def s15():
    plans = [
        ("¥0", "", "Free · 免费体验", "30学员 · 1教师 · 基础刷题+考试 · 20次AI出题/月 · 固定间隔复习（CTT）"),
        ("¥1,299", "/月", "Growth · 机构教学平台", "¥10,388/年 · 200学员 · 5教师 · 无限制AI出题 · 自适应复习调度 · 知识图谱 · 认知诊断 · 视频课程 · 答疑 · 自习室"),
        ("¥3,999", "/月", "Pro · 企业旗舰", "¥31,988/年 · 不限学员/教师 · 品牌白标 · API接入 · 学生端收费 · 自定义知识树 · 机构级参数隔离"),
    ]
    rows = []
    for price, unit, name, desc in plans:
        rows.append(f'''      <div class="ledger-row" data-anim="row">
        <div style="display:flex;align-items:center;gap:3vw">
          <div class="ledger-num">{price}<span style="font-size:0.45em;font-weight:300;color:var(--text-helper);margin-left:3px">{unit}</span></div>
          <div>
            <div class="t-cat ledger-label" style="margin-bottom:.3vh">{name}</div>
            <p style="font-size:max(14px,1vw);color:var(--text-secondary);line-height:1.45">{desc}</p>
          </div>
        </div>
      </div>''')
    b = f'''  <div class="canvas-card">
    {chrome("定价方案", page(15))}
    <h2 style="font-family:var(--sans),var(--sans-zh);font-weight:200;font-size:min(5.8vw,10.2vh);line-height:.96;letter-spacing:-.035em;margin-bottom:5vh">灵活定价，按需选择</h2>
    <div class="stacked-ledger" data-anim="ledger">
{chr(10).join(rows)}
    </div>
  </div>'''
    return sec("S20", "stacked-ledger", "light", b)

# ═══════════════════════════════════════════════════════
# P16 · S08 · Duo (创始人)
# ═══════════════════════════════════════════════════════
def s16():
    b = f'''  <div class="canvas-card">
    {chrome("创始人", page(16))}
    <div class="duo-compare">
      <div class="col">
        <span class="col-tag"><span class="num">01</span> FOUNDER · CEO</span>
        <div class="col-ttl">Eular</div>
        <div class="col-desc">
          全栈工程师 · AI 教育产品架构师<br><br>
          北京大学计算机硕士<br>
          前阿里巴巴高级技术专家<br>
          主导设计 UniMind 全栈架构与算法体系<br><br>
          <span style="font-family:var(--mono);font-size:14px">eular@unimind-ai.com</span>
        </div>
      </div>
      <span class="vrule"></span>
      <div class="col accent">
        <span class="col-tag"><span class="num">02</span> FOUNDER · CTO</span>
        <div class="col-ttl" style="color:var(--text-placeholder)">[ 联合创始人 ]</div>
        <div class="col-desc" style="color:var(--text-placeholder)">
          （占位 — 请替换为实际信息）<br><br>
          教育背景<br>
          工作经历<br>
          核心贡献<br><br>
          <span style="font-family:var(--mono);font-size:14px">contact@unimind-ai.com</span>
        </div>
      </div>
    </div>
  </div>'''
    return sec("S08", "duo-mirror", "light", b)

# ═══════════════════════════════════════════════════════
# P17 · S18 · Why Now (我们要做的事)
# ═══════════════════════════════════════════════════════
def s17():
    b = f'''  <div class="canvas-card">
    {chrome("产品路线图", page(17))}
    <h2 style="font-family:var(--sans),var(--sans-zh);font-weight:200;font-size:min(5.8vw,10.2vh);line-height:.96;letter-spacing:-.035em;margin-bottom:5vh">我们要做的事</h2>
    <div class="why-now-grid" data-anim="up">
      <div class="why-col" data-anim="col">
        <div class="t-cat">产品深度</div>
        <h3 style="font-family:var(--sans),var(--sans-zh);font-weight:300;font-size:min(2.4vw,6vh);line-height:1.15;letter-spacing:-.02em;margin:1.6vh 0">自进化：系统越用越聪明</h3>
        <p style="font-size:max(15px,1vw);line-height:1.5;color:var(--text-secondary);font-weight:300">自动收集教学数据并分析优化方向。从出题质量到复习策略持续自我改进。机构负责人审核后一键上线新策略。</p>
        <div class="why-num-bottom">🔜</div>
      </div>
      <div class="why-col" data-anim="col">
        <div class="t-cat">行业广度</div>
        <h3 style="font-family:var(--sans),var(--sans-zh);font-weight:300;font-size:min(2.4vw,6vh);line-height:1.15;letter-spacing:-.02em;margin:1.6vh 0">多学科扩展 + 开放 API</h3>
        <p style="font-size:max(15px,1vw);line-height:1.5;color:var(--text-secondary);font-weight:300">金融 431 已跑通，数学+法学就绪。覆盖考研/考证/K12/医学。第三方可在 UniMind 上构建垂直应用，机构可定制专属 Agent 工具。</p>
        <div class="why-num-bottom">02</div>
      </div>
      <div class="why-col" data-anim="col">
        <div class="t-cat">商业落地</div>
        <h3 style="font-family:var(--sans),var(--sans-zh);font-weight:300;font-size:min(2.4vw,6vh);line-height:1.15;letter-spacing:-.02em;margin:1.6vh 0">从产品到付费规模化</h3>
        <p style="font-size:max(15px,1vw);line-height:1.5;color:var(--text-secondary);font-weight:300">免费层体验基础功能 → 付费层解锁智能复习、错因分析和深度诊断。越多学生使用，系统越精准，切换成本越高。形成自然增长循环。</p>
        <div class="why-num-bottom" style="color:var(--accent)">03</div>
      </div>
    </div>
  </div>'''
    return sec("S18", "why-now", "light", b)

# ═══════════════════════════════════════════════════════
# P18 · S12 · Manifesto (技术宣言)
# ═══════════════════════════════════════════════════════
def s18():
    b = f'''  <div class="canvas-card">
    {chrome("我们的信念", page(18))}
    <div data-anim="line" style="flex:1;display:grid;grid-template-columns:1fr 1fr;gap:4vw;align-items:flex-start;padding-top:2vh">
      <div>
        <div class="t-cat">OUR BELIEF</div>
        <h2 style="font-family:var(--sans),var(--sans-zh);font-weight:200;font-size:min(4.6vw,8vh);line-height:1.05;letter-spacing:-.035em;margin-top:1.6vh">好的教育产品，<br>是把确定性交给机构，<br>把时间还给老师。</h2>
      </div>
      <div style="font-size:max(15px,1.1vw);line-height:1.65;color:var(--text-secondary);font-weight:300;padding-top:1vw">
        教育行业的竞争正在从"师资"转向"数据+效率"。UniMind 做的事情很朴素：让系统记住每个学生的遗忘规律，让 AI 承担重复劳动，让老师有更多时间去做机器做不了的事——理解学生、激励学生、引导学生。
      </div>
    </div>
    <div data-anim="up" style="margin:0 -5vw -4.4vh;background:var(--accent);padding:2.6vh 5vw;display:flex;align-items:center;gap:3vw">
      <p style="font-family:var(--sans),var(--sans-zh);font-weight:200;font-size:min(3.2vw,6.5vh);line-height:1.1;letter-spacing:-.02em;color:var(--accent-on)">学生提分 · 老师减负 · 机构增收</p>
      <div style="display:flex;gap:1.6vw;margin-left:auto">
        <i data-lucide="cpu" style="color:rgba(255,255,255,.6);width:2vw;height:2vw"></i>
        <i data-lucide="brain-circuit" style="color:rgba(255,255,255,.6);width:2vw;height:2vw"></i>
        <i data-lucide="workflow" style="color:rgba(255,255,255,.6);width:2vw;height:2vw"></i>
        <i data-lucide="zap" style="color:rgba(255,255,255,.6);width:2vw;height:2vw"></i>
      </div>
    </div>
  </div>'''
    return sec("S12", "manifesto", "light", b)

# ═══════════════════════════════════════════════════════
# P19 · S03 · Statement (愿景)
# ═══════════════════════════════════════════════════════
def s19():
    b = f'''  <div class="canvas-card">
    {chrome("OUR BELIEF", page(19))}
    <h1 class="h-statement">
      <span>好的教育</span><br>
      <span>应该像空气一样</span><br>
      <span>无处不在，却无需感知</span>
    </h1>
    <span class="stmt-anchor">— 技术隐身，教育显形</span>
  </div>'''
    return sec("S03", "statement", "light", b)

# ═══════════════════════════════════════════════════════
# P20 · S10 · Closing (IKB 半屏 + Takeaway)
# ═══════════════════════════════════════════════════════
def s20():
    b = f'''  <div class="canvas-card">
    <div class="split-half">
      <div class="half b-accent" style="padding:5.6vh 3.6vw 4.4vh;justify-content:space-between;position:relative;overflow:hidden">
        <canvas class="ascii-bg" aria-hidden="true"></canvas>
        {chrome(page(20), "CLOSING")}
        <div data-anim="manifesto" style="display:flex;flex-direction:column;gap:2vh;position:relative;z-index:1">
          <div class="t-meta" style="color:rgba(255,255,255,.78);letter-spacing:.22em;margin-bottom:1.6vh">SLOGAN</div>
          <h2 style="font-family:var(--sans),var(--sans-zh);font-size:min(8vw,14vh);line-height:.94;letter-spacing:-.025em;font-weight:200;color:#fff">学生提分。<br>老师减负。<br><span style="font-style:italic;font-weight:300">机构增收。</span></h2>
          <div style="font-family:var(--sans),var(--sans-zh);font-size:max(14px,1vw);line-height:1.6;color:rgba(255,255,255,.82);font-weight:300;max-width:36ch;margin-top:1.4vh">教育机构 AI 基础设施 · 把确定性还给教育</div>
        </div>
        <div data-anim="signature" style="display:flex;justify-content:space-between;align-items:end;border-top:1px solid rgba(255,255,255,.22);padding-top:1.6vh;position:relative;z-index:1">
          <div class="t-meta" style="color:rgba(255,255,255,.62)">Eular &amp; Team</div>
          <div class="t-meta" style="color:rgba(255,255,255,.62)">2026.06</div>
        </div>
      </div>
      <div class="half" style="padding:5.6vh 3.6vw 4.4vh;justify-content:space-between">
        <div class="chrome-min"><div class="l">TAKEAWAYS</div><div class="r"></div></div>
        <div data-anim="rules">
          <ul style="list-style:none;display:flex;flex-direction:column">
            <li data-anim="rule" style="display:flex;gap:1.6vw;align-items:flex-start;padding:1.4vh 0;border-bottom:1px solid var(--border-subtle)">
              <span style="font-family:var(--mono);font-weight:600;font-size:14px;color:var(--accent);min-width:2ch">01</span>
              <div><h4 style="font-weight:500;font-size:max(15px,1.15vw);line-height:1.3;margin-bottom:.3vh">精准复习引擎</h4><p style="font-size:max(14px,1vw);color:var(--text-secondary);line-height:1.45">告别固定间隔。每道题实时计算最优复习时刻。遗忘临界点精准切入。</p></div>
            </li>
            <li data-anim="rule" style="display:flex;gap:1.6vw;align-items:flex-start;padding:1.4vh 0;border-bottom:1px solid var(--border-subtle)">
              <span style="font-family:var(--mono);font-weight:600;font-size:14px;color:var(--accent);min-width:2ch">02</span>
              <div><h4 style="font-weight:500;font-size:max(15px,1.15vw);line-height:1.3;margin-bottom:.3vh">Agent 是入口</h4><p style="font-size:max(14px,1vw);color:var(--text-secondary);line-height:1.45">学生不需要在功能菜单中导航。Agent 基于记忆数据主动引导学习。</p></div>
            </li>
            <li data-anim="rule" style="display:flex;gap:1.6vw;align-items:flex-start;padding:1.4vh 0;border-bottom:1px solid var(--border-subtle)">
              <span style="font-family:var(--mono);font-weight:600;font-size:14px;color:var(--accent);min-width:2ch">03</span>
              <div><h4 style="font-weight:500;font-size:max(15px,1.15vw);line-height:1.3;margin-bottom:.3vh">数据飞轮已启动</h4><p style="font-size:max(14px,1vw);color:var(--text-secondary);line-height:1.45">每道题都在更新参数。越多学生使用，系统越精准，切换成本越高。</p></div>
            </li>
          </ul>
        </div>
        <div class="t-meta" style="color:var(--text-helper);text-align:right">→ END · UniMind.ai</div>
      </div>
    </div>
  </div>'''
    return sec("S10", "split-statement", "split", b)


# ═══════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════
slides = [s01, s02, s03, s04, s05, s06, s07, s08, s09, s10,
          s11, s12, s13, s14, s15, s16, s17, s18, s19, s20]

slides_html = "\n".join(f() for f in slides)

output = HEAD + slides_html + "\n" + TAIL
output = output.replace('[必填] 替换为 PPT 标题 · Deck Title', 'UniMind · 智能教育基础设施展品手册')

OUT.write_text(output)
print(f"✅ Generated {OUT} — {len(output):,} bytes, {len(slides)} slides")
