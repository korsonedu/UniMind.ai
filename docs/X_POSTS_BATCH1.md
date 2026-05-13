# UniMind.ai X Post Drafts — Batch 1 (Week 1-2) · 精修版

> 真实数据标注：**[D]** = 来自 Landing.tsx · **[F]** = 来自 FEATURES.md · **[W]** = 来自 GFSRS_WHITEPAPER_CN.md

---

## Week 1: 观点轰炸 — 只发不卖

---

### Day 1 — 原子帖 · 行业真相

Education is a trillion-dollar industry.

And most training centers still run on Excel + WhatsApp.

💀

Instructors spend 40% of their time making tests, grading, and copy-pasting student progress into spreadsheets. Not teaching. Admin.

AI won't replace teachers.

It'll kill the busywork they should've never been handed in the first place.

---

### Day 2 — 原子帖 · 反直觉

The best AI tutor isn't the smartest model in the room.

It's the one that knows when to shut the hell up.

Here's why 👇

Real learning happens during retrieval struggle. That moment when your brain strains to pull something back from the edge of forgetting.

If your AI jumps in with the answer every time → you're building dependency, not mastery.

Let them sit in the discomfort. That's the whole game.

---

### Day 3 — 蹭热度 · AI 模型军备竞赛
> 📸 **建议配图**：简洁柱状对比图 — 单次 LLM 60% vs 对抗管线 85%，视觉化"25-point gap"

Timeline full of "Claude vs GPT vs Gemini" benchmark wars.

Cool. Here's one nobody runs:

📋 Which model writes usable exam questions?

**Single LLM call** → ~60% of questions pass quality review. **[D]**
**3-agent adversarial pipeline** → 85%+ pass. **[D]**

The 25-point gap isn't about model intelligence.

It's about architecture.

One model writes. Another critiques. A third classifies. Below threshold → rejected, re-generated. Max 3 rounds. **[F]**

Your stack matters more than your model.

---

### Day 4 — 情绪共鸣 · 教师痛点

"I spent my entire Saturday writing one mock exam."

— Real CPA prep instructor. 200 students.

Her workflow:
📝 Friday night: find source material
📝 Saturday morning: write 50 questions
📝 Saturday afternoon: write explanations
📝 Saturday evening: format everything

Sunday? Grading last week's test.

Meanwhile, students waited 7 days for results. By the time they saw their mistakes, they'd forgotten making them.

This is not a teaching problem.

It's an infrastructure problem. And infrastructure has solutions.

---

### Day 5 — 蹭热度 · vibe coding vs vibe teaching

Hot take that'll get me ratio'd:

Prompt engineering for education is 10× harder than for code.

Code is binary. Runs or doesn't. You see the bug immediately.

An exam question can be:
❌ "Correct" but with an ambiguous stem
❌ "Correct" but with distractors that don't test the target concept
❌ "Correct" but set at completely wrong difficulty

The failure modes are subtle. Infinite. And invisible until a student sits down and takes the test.

This is why "just prompt GPT to write questions" doesn't work at scale.

We had to build 3 AI agents that argue with each other before any question reaches a human. **[F]**

---

### Day 6 — 强观点 · 间隔重复

Everyone in edtech is chasing AI tutors, AI graders, AI lesson planners.

Nobody's talking about the thing that actually moves the needle:

⏳ **Knowing exactly when a student is about to forget something — and surfacing it right before.**

That's spaced repetition. And it's the most under-leveraged AI use case in education.

13.7% lower prediction error. 9.2% higher knowledge retention. **[D]**

Not from a fancier model. From a smarter schedule.

---

### Day 7 — 故事长线程 · 创始人旅程
> 📸 **配图**：个人工作照或产品早期 vs 现在的对比截图，放第一条推文。人脸增加信任感，故事线程需要视觉锚点

🧵 1/7

2024. I built an exam prep app for exactly one exam. China's 431 Finance. Hyper-niche. One test, one country, zero ambition beyond making it work.

It worked. Students used it. Churn was low. NPS was solid.

Then something weird happened. 👇

🧵 2/7

Training centers started calling. Not students. Business owners.

"Hey — can your AI do this for law exams?"
"Does it work for medical licensing?"
"We teach CPA. Can you generate our questions?"

They didn't want our content. They wanted the MACHINE that made the content.

That's when the penny dropped. 💡

🧵 3/7

The exam content was never the product.

The real product was invisible:
→ The AI pipeline that generates questions **[D]**
→ The algorithm that schedules review at the perfect moment **[D]**
→ The knowledge graph that shows exactly what each student knows **[D]**

These three don't care which subject you teach. You bring the syllabus. The engine handles everything else.

🧵 4/7

So we ripped out the 431-specific layer. Rebuilt from the ground up as a platform.

Today: a CPA exam center and a language school can onboard in the same afternoon.

One uploads accounting standards. The other uploads vocabulary lists.

Same pipeline. Same quality. Zero per-subject customization.

The architecture is the moat. Not the content.

🧵 5/7

The hardest part wasn't building the platform.

It was making the AI-generated questions NOT suck.

Single LLM call: ~60% usable. The rest have subtle poison — distractors that are true but irrelevant, stems with double meanings, difficulty wildly off target. **[D]**

Students spot bad questions in 5 seconds. And they never trust your platform again.

🧵 6/7

Our fix: make the AIs fight each other. 🥊

✍️ Author writes the question
🔍 Reviewer tears it apart (5-dimension rubric)
🏷️ Classifier scores the final output

Below threshold → rejected → Author tries again with Reviewer's notes.

Max 3 rounds. 85%+ emerge usable. The other 15%? Flagged for human judgment — exactly where it belongs. **[D]**

🧵 7/7

What I learned:

Your first customer is not your forever customer.
Your first vertical is not your forever market.

But the infrastructure you build to serve them?

That might be your real company.

We launched in one country for one exam. Now we're going global. 🌍

---

## Week 2: 展示产品 + 建立信任

---

### Day 8 — 产品截图 · AI 出题中心
> 📸 **必须配图**：AI 出题中心界面截图。这条的核心就是"看产品"，没图等于白发了

This is what happens when you stop writing exam questions by hand 👇

📌 Select knowledge points
📌 Pick question formats
📌 Hit generate
📌 Review → Approve → Done

No prompt templates. No "vibe testing" your exam content.

📊 50,000+ questions generated · 50+ training centers · 50× faster than manual **[D]**

[📸 AI Question Center screenshot]

---

### Day 9 — 深度长线程 · 对抗管线内部
> 📸 **必须配图**：管线流程图 — Author → Reviewer → Classifier，标注 3 轮迭代和 85%+ 质量门。放第一条推文，是整个线程的视觉入口

🧵 1/5

Unpopular opinion:

Most AI-generated exam questions are broken. Not in obvious ways — in subtle, assessment-destroying ways.

Example 👇

Q: "Which of the following is true about capital asset pricing?"

A) Beta measures systematic risk ✅ (correct)
B) CAPM assumes no taxes ✅ (also true in the real world — but this isn't what CAPM "is about")
C) The risk-free rate varies by investor ⚠️ (debatable)
D) All of the above ❌ (technically wrong but A and B are fighting)

Student reads this and thinks: "Wait... A and B are both kind of right?"

Test validity: destroyed. 🪦

🧵 2/5

Single-pass LLM → ~60% of questions survive quality review. **[D]**

The other 40%? They burn instructor time in manual cleanup — the exact problem AI was supposed to solve.

Scale this to 50,000+ questions and you have a disaster.

🧵 3/5

Enter the ARC Adversarial Pipeline:

✍️ **Author Agent** — generates the question from your knowledge points
🔍 **Reviewer Agent** — critiques it on 5 dimensions with structured feedback
🏷️ **Classifier Agent** — scores final quality, tags by topic and difficulty

Score < threshold? Rejected automatically.
Author regenerates with Reviewer's specific notes.
Up to 3 rounds. Quality improves each iteration. **[F]**

🧵 4/5

What the Reviewer actually outputs:

📝 Stem clarity — 7/10 → "Ambiguous: which direction is the question facing?"
🎯 Distractor plausibility — 5/10 → "Option B is true but irrelevant to the tested concept"
📐 Concept alignment — 8/10
🔢 Difficulty calibration — 6/10 → "Easier than intended for this level"
🧩 Answer unambiguity — 9/10

Author gets this. Regenerates with targeted fixes. Compound quality gain.

🧵 5/5

End state: 85%+ of questions pass first human review. **[D]**

The 15% that don't? Flagged with Reviewer notes attached → instructor judgment. Fast. Precise. Not starting from scratch.

AI handles the grind. Humans make the final call.

That is the correct division of labor. Fight me.

---

### Day 10 — 原子帖 · 市场地板

Duolingo → sells to learners.
Quizlet → sells to learners.
Khan Academy → sells to learners.
Coursera → sells to learners.

Every edtech unicorn is B2C. Every single one.

Meanwhile:

🏢 Training centers
📚 Vocational schools
📋 Certification prep programs
🏥 Professional licensing bodies

These businesses educate hundreds of millions of people.

And they have **zero** AI infrastructure.

The B2C edtech ocean is red. The B2B edtech ocean is empty. 🌊

---

### Day 11 — Before/After · 客户故事
> 📸 **建议配图**：左右分屏对比 — 左侧 Excel 手动管理 vs 右侧 UniMind Dashboard，Before/After 视觉冲击力最强

A training center switched to UniMind. Here's what changed in 30 days:

**Before** 😰
📝 1 mock exam = 8 hours of teacher time
📊 Student progress? Manually tracked in Excel
👥 Every student got the same question set — regardless of skill level

**After** 🚀
⚡ AI generates exam drafts in minutes — teacher does final review only
📈 Real-time knowledge dashboard per student — weak spots flagged automatically
🧠 Memorix schedules personalized review — each student sees the questions THEY need

Result: 90% less admin work. 23% higher renewal rate. Same teachers, same students. **[D]**

The bottleneck was never the teachers. It was the tools.

---

### Day 12 — 原子帖 · 产品哲学

Every edtech landing page right now:

"AI tutor! AI grader! AI planner! AI everything!"

AI-ception. Feature soup. 🤖🤖🤖

The winners in this space won't be the ones with the longest feature page.

They'll be the ones where AI disappears into the workflow so cleanly that teachers forget it's even there.

Invisible is the goal.

If your users notice your AI, you've already lost.

---

### Day 13 — 技术深潜 · 遗忘曲线
> 📸 **必须配图**：Weibull vs Power-law 曲线对比图，标注拐点差异。核心信息是"两个曲线形状不同"，一张图胜过 200 字

🧮 Math that actually matters:

Most spaced repetition algorithms (Anki, FSRS) use a **power-law** to model forgetting.

We use a **Weibull distribution**. **[W]**

Why should you care? 👇

Human memory decay has a hazard rate that changes shape over time:
📈 Early phase → forgetting accelerates (you lose it fast)
📉 Later phase → forgetting decelerates (what survives, sticks)

Power-law can't capture the inflection point. It forces one shape onto both phases.

Weibull can. It has a built-in shape parameter that lets the curve bend where real memory bends.

➡️ 13.7% lower RMSE vs FSRS v4.5 **[D]**
➡️ 9.2% higher knowledge retention **[D]**
➡️ 20-dim personalization vector — not one curve for everyone, a unique curve for YOU **[D]**

One modeling choice. Massive downstream impact.

Math is leverage. 📐

---

### Day 14 — 软发布 · Landing Page
> 📸 **必须配图**：产品 Dashboard 全景截图或自制 Hero 图（深色底 + UniMind logo + 三大引擎关键词），发布帖需要视觉冲击力

Two years. One pivot. Three core engines.

Today we're opening UniMind to the world. 🚀

What we built:

🧠 **AI Question Engine**
3-agent adversarial pipeline. 85%+ usable rate. Any subject. Upload your syllabus → get a question bank. **[D]**

⏳ **Memorix Adaptive Review**
Weibull-based forgetting model. 20-dim personalization. Online SGD with Nesterov momentum. **[D][W]**

📊 **Knowledge Dashboard**
Interactive SVG graph. Per-student mastery coloring. Weak spots auto-flagged. One-click drill-down.

🎁 14-day full-feature trial. No card. No catch.
🔒 First 20 paid customers → early-adopter price locked forever.

👉 [landing page link]

50+ centers. 50,000+ questions. One platform. **[D]**

---

## 配图策略汇总

**原则：图放大核心信息，不是装饰。配烂图不如不配。**

### 必须配图（4 条）
| 帖 | 配什么 | 为什么 |
|----|--------|--------|
| Day 8 | AI 出题中心界面截图 | 核心是"看产品"，没图白发了 |
| Day 9 首推 | 管线流程图：Author → Reviewer → Classifier + 85%+ 质量门 | 长线程视觉入口，纯文字讲架构太干 |
| Day 13 | Weibull vs Power-law 曲线对比图 | 一张图胜过 200 字 |
| Day 14 | Dashboard 全景或 Hero 图 | 发布帖需要视觉冲击力 |

### 建议配图（3 条）
| 帖 | 配什么 | 为什么 |
|----|--------|--------|
| Day 3 | 柱状对比图：单次 LLM 60% vs 对抗管线 85% | 视觉化"25-point gap" |
| Day 7 首推 | 个人工作照或早期 vs 现在对比 | 人脸 = 信任，故事需要视觉锚点 |
| Day 11 | 左右分屏：Excel 手动 vs UniMind Dashboard | Before/After 视觉冲击力最强 |

### 不配图（7 条）
Day 1, 2, 4, 5, 6, 10, 12 — 纯观点/情绪帖，文字本身就是力量，不配图让注意力更聚焦。

---

## 帖子模板 · 拿来就用

### 🔥 观点帖 (Atomic)
```
[1个强观点，反直觉最好。前5个词决定一切]
[1个具体例子或数据支撑]
[1句可引用的话 — 简洁到能截图]
[含蓄产品关联，不要硬推]
```

### 🏗️ Build-in-Public
```
Shipped today:
→ [具体完成了什么]
→ [为什么这样做]
→ [数据/反馈]
```

### 📊 数据帖
```
We analyzed [X].
Most surprising finding: [反直觉结论]
[Numbers]
Why: [1句解释]
```

### 🏆 客户成果
```
Before UniMind: [具体痛点 + 数字]
After UniMind: [具体改善 + 数字]
How: [用到的功能，不要罗列]
Same [人/资源]. Different [结果].
```

### 💬 热点回复
```
在大号帖子下写有价值的反向观点 → 自然引流到你主页
⚠️ 铁律：先提供独立价值，再提产品。先当人，再当卖家。
```

---

## 发布节奏

```
Week 1: 观点建认知
Mon ┃ Day 1  行业真相
Tue ┃ Day 2  反直觉
Wed ┃ Day 3  蹭热度·模型对比
Thu ┃ Day 4  情绪共鸣
Fri ┃ Day 5  蹭热度·vibe coding
Sat ┃ Day 6  间隔重复
Sun ┃ Day 7  创始人故事 🧵

Week 2: 产品建信任
Mon ┃ Day 8  产品截图
Tue ┃ Day 9  对抗管线 🧵
Wed ┃ Day 10 市场洞察
Thu ┃ Day 11 客户故事
Fri ┃ Day 12 产品哲学
Sat ┃ Day 13 技术深潜
Sun ┃ Day 14 软发布 🚀
```

---

## Hashtag 策略
每帖 1 个，最多 2 个：

| 帖型 | Hashtag |
|------|---------|
| 行业观点 | `#edtech` |
| 技术内容 | `#AI` `#spacedrepetition` |
| 创始人向 | `#buildinpublic` `#indiehacker` |
| 蹭热度 | 跟当天热词，不固定 |

---

## Profile 配置

| 项目 | 设置 | 说明 |
|------|------|------|
| **头像** | 真人照片，非 logo | X 上人们关注人，不是公司。半身/头像，脸占比大，smart casual |
| **Header** | 深色底（#0F1729）+ 左侧 logo + 右侧 "AI Infrastructure for Training Centers" | 唯一可放大面积放品牌信息的位置 |
| **Display Name** | `Eular \| Building UniMind.ai` | 格式：[名字] \| [正在做的事] |
| **Bio** | 见下方 | — |
| **Location** | 实际城市，或留空 | real person, real place |
| **Website** | `unimind.ai/en` | 少数能直接导流的位置 |
| **Pinned Post** | Day 7 创始人故事线程 | 新访客主页第一条看到"我是谁、为什么做这个" |

**Bio（160 字以内）：**
```
🧠 Building AI infrastructure for training centers
AI question gen · Adaptive review · Knowledge graphs
🚀 50+ centers · 50K+ questions generated
📐 13.7% lower RMSE vs FSRS — Weibull > power-law
```

**Bio 设计逻辑：**
- L1：一句话说清做什么
- L2：三个产品能力关键词，方便搜索
- L3：社会证明（数字）
- L4：技术差异化，内行看到 "Weibull > power-law" 会好奇点进来

**注册后前 3 天：**
1. 分批关注 30-50 个 EdTech / AI / SaaS founder 账号
2. 在别人帖子下留 5-10 条有观点的评论（不要 "great post!"）
3. 第 3 天开始发 Day 1

先当真人，再当博主。先有互动记录，再开始发帖。
