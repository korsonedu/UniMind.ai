# X 出海商业化打法 — 从做号到收钱

> 你现在的状态：内容在发了，号在做。下一步不是发更多内容，是**把流量变成客户**。

---

## 先搞清楚：你在 X 上卖的是什么

不是一个产品。是三个东西，分阶段卖：

| 阶段 | 卖什么 | 客户状态 | 你的动作 |
|------|--------|----------|----------|
| 1 | **一个有意思的 idea** | 路人 → 关注者 | 你已经在做了 |
| 2 | **一个他想了解的产品** | 关注者 → 潜在客户 | 👈 你现在在这里 |
| 3 | **一个他愿意付钱的东西** | 潜在客户 → 付费客户 | 目标是这里 |

你现在做号阶段搞定的是 1。接下来要做的是 2→3。

---

## 你的客户在 X 上的真实画像

不是"教育培训机构老板"这么笼统。具体点：

**会刷 X 的培训机构创始人长这样：**
- 大概率不是传统培训机构（传统老板不用 X）
- 更可能是：EdTech 创始人、在线教育创业者、职业培训赛道 founder
- 年龄 25-40，英语流利，有技术认知但不一定自己写代码
- 他们的痛点：内容生产成本高、老师效率低、规模化困难
- 他们的语言：「course creation」「assessment pipeline」「student retention」「scaling content」

**他们不在传统培训机构的圈子里混，他们在：**
- `#buildinpublic` `#indiehacker` `#edtech` `#saas` 这些标签下
- 关注 Pieter Levels、Marc Lou、Danny Postma 这些 indie hacker 大号
- 可能在 Product Hunt 上投过自己的产品

---

## 漏斗设计：X 上的内容不是终点，是入口

你现在的帖子是往天上撒种子。现在需要修一条路，让感兴趣的人能走进来。

### 你的漏斗应该长这样：

```
X 帖子（每天）
    ↓ 好奇心被勾起来
个人主页 Bio 链接
    ↓ 想了解更多
英文 Landing Page / Waitlist
    ↓ 看到产品价值
免费试用 / Demo
    ↓ 用上了觉得好
付费
```

**你现在缺的是中间两层。**

---

## 第零步：想清楚你的差异化叙事——你在 X 上到底在讲什么故事

做号之前先想明白一件事：你跟其他 EdTech 产品的**本质区别**是什么。不是功能列表，是那个让你一开口就跟别人不一样的东西。

你有三个别人没有的硬核故事：

### 故事 A：Memorix 算法 — 数学才是护城河

全世界的间隔重复系统都在用 FSRS（Anki 也是）。FSRS 用幂律分布建模遗忘——幂律意味着遗忘速度只能递减。但真实人脑遗忘先加速后减速，有个拐点。

你换了 Weibull 分布。多了一个形状参数 k，曲线可以折弯。RMSE 比 FSRS v4.5 低 13.7%，知识留存率高 9.2%。数学模型层面的差异，不是调参调出来的。

**怎么讲：** "Everyone uses the same forgetting model. We rebuilt it from the math up." 这不是功能对比，这是方法论层面的降维打击。

### 故事 B：闭环学习系统 — 竞品只是单点工具

大部分 AI 教育产品是单点功能：要么只出题、要么只判分、要么只排日程。你的是完整闭 loop：**做题 → AI 判分 → 输出 fsrs_rating → 喂入 Memorix 调度器 → 更新遗忘参数 → 自适应选题 → 再做下一轮**。

每一步都是一个数据契约，中间断一环就不转。花了一年才跑通这个数据链条。

**怎么讲：** "We don't just grade. We close the loop." 闭环 = 数据沉淀 = 迁移成本 = 客户走不了。

### 故事 C：防作弊和离线考试 — 网页做不到的事

这是 Tauri 桌面 App 的差异化。网页端的防作弊基本是"请自觉"——机构老板听了想笑。桌面 App 可以锁屏、禁止切窗口、检测截屏、强制全屏、进程检测（检测到微信/浏览器弹警告）。

离线考试同理：题库本地缓存 → 断网作答 → 交卷同步。机房场景的硬刚需。

**怎么讲：** "Your students are cheating. Your browser-based exam can't stop them. We can." 这是销售话术，不是产品话术。

### 在 X 上怎么分配这三个故事的曝光

| 故事 | 面向 | 内容类型 | 出现频率 |
|------|------|----------|----------|
| Memorix 算法 | 技术型 founder、投资人 | 数学/数据帖、build in public | 每 3-4 条出现 1 次 |
| 闭环系统 | 培训机构 owner | 产品帖、客户案例 | 每 2-3 条出现 1 次 |
| 防作弊/离线 | 培训机构的决策者 | 痛点帖、CTA 帖 | 每 5-6 条出现 1 次 |

---

## 第一步：立即把 X 主页链接换成能承接流量的东西

你现在 Bio 里的链接指向哪？

如果指向一个空的 landing page 或者直接是 unimind.ai（中文的），那所有流量都在漏。

**你需要一个英文 landing page，至少包含：**
- 一句话说清你是谁（"AI infrastructure for training centers. Any subject, any exam."）
- 三个核心能力（AI Question Engine / Adaptive Review / Knowledge Dashboard）
- 一个 60 秒产品 demo 视频（录屏就行，别做动画）
- 一个 action：填邮箱加入 waitlist / 预约 demo / 直接注册试用
- 社会证明：50+ centers, 50K+ questions（你现在帖子里已经用的数字）
- **可选但推荐：桌面 App 下载按钮**（"Download for Windows/macOS" —— 即使目前只是一个 Tauri webview 壳，有个独立窗口的 demo 比 URL 链接有说服力十倍）

**不需要复杂。** 用 Carrd 或者直接在你现有前端项目里开一个 `/en` 路由，一个下午能搞定。

**做完这个之前先别急着搞下面的。这是第一优先级。**

---

## 第二步：把内容策略从「建立认知」调整为「驱动行动」

你现在发的内容是按 Week 1-2 计划走的——观点轰炸 → 展示产品 → 软发布。这个方向是对的。但从第 3 周开始，内容要有明确的目的性。

### 第 3 周起的内容框架：

| 类型 | 占比 | 目的 | 例子 |
|------|------|------|------|
| 客户案例/见证 | 30% | 证明有人在用、有人付钱 | "A CPA training center in [country] switched to UniMind. Here's what happened in 30 days." |
| Build in public | 30% | 让人觉得你在实打实干 | "Just shipped [X feature]. Took 3 days because [technical constraint]. Here's what I learned." |
| 观点/争议 | 20% | 保持曝光和讨论 | "The reason most AI tutoring products fail isn't the AI. It's that they're building for students, not for teachers." |
| 直接 CTA | 20% | 明确要求行动 | "We're looking for 5 more training centers to pilot our AI question engine. Free for 3 months. DM me 'pilot' if interested." |

**关键变化：新增了「直接 CTA」类型。** 你现在没有这种内容，全是认知型。没有 ask 就没有 conversion。

---

## 第三步：从等的模式切换到找的模式

你现在是在等人来找你。不够。

### 你的主动获客流程：

**1. 列名单**
- 在 X 上搜索 "edtech founder" "course creator" "training platform" "exam prep" "certification prep" "online academy"
- 找人，不是找公司号。找那些在简介里写 "building X for Y" 的个人
- 目标：每周找到 20-30 个潜在客户账号，关注他们

**2. 互动养熟（3-7 天）**
- 关注后，在他们帖子下留真实评论。不是 "great post"。是观点。
- 比如他发了一条关于学员流失的帖子，你回："we saw the same thing. In our data, personalized review scheduling alone cut churn by ~20%. Have you tried spaced repetition?"
- 别提你的产品。先建立存在感。

**3. DM（时机成熟后）**

时机成熟的信号：他回复了你两次以上，或者他主动来看了你的主页、给你的帖子点过赞。

DM 模板（核心：不推销，请教 + 提供价值）：

> "Hey [name], been following your work on [topic]. I'm building in a similar space — AI infrastructure for training centers. Quick question: what's your biggest headache with content/assessment creation right now? I might be able to share something useful from what we've learned."

为什么这样写：
- 不是"看看我的产品"
- 是在请教 + 暗示你可能能帮上忙
- 他回复后你才知道他是不是你的目标客户

**如果他回复了真实痛点 → 你提供你产品怎么解决这个痛点的信息 → 邀请 demo。**

---

## 第四步：把 DM 对话变成一个可复用的流程

你不可能同时跟 50 个人 DM。但 X 上的效果在于你的帖子本身就在帮你销售。

### 每一条帖子都应该有一个「下一步动作」

发完帖子的最后一句话（或者 comment 区自己追评），引导行动：

- 如果这条讲产品能力 → 「If you run a training center and this resonates, DM me "questions" — happy to show you how it works.」
- 如果这条讲行业观点 → 「What's your take? Is AI going to replace teachers or just kill the admin work?」
- 如果这条讲客户案例 → 「Want to see what this looks like for your subject? Drop your subject in the replies.」
- 如果这条讲 build in public → 「Building something similar? Would love to compare notes.」

**每一条帖子都是一条钓鱼线。**

---

## 第五步：产品 Demo 流程

当有人表示兴趣，从 DM 到 Demo 的流程：

**DM 阶段：**
- 不要发 Calendly 链接让人预约。太冷。
- 问他：「What subject do you teach? How many students?」
- 听完他说，简短告诉他：「For [his subject], our pipeline could generate [具体] in [具体时间]. Want me to do a quick 15-min screen share?」

**Demo 阶段（15-20 分钟，不是 60 分钟）：**

**用什么演示：**
- **优先用桌面 App demo**。双击打开一个独立窗口，比在浏览器里敲 URL 专业十倍。机构决策者看到的是一个"系统"，不是一个"网址"。
- 如果桌面 App 还没准备好，浏览器全屏 F11 凑合。但长期目标是所有 demo 都用桌面 App 做。

**Demo 流程：**
- 10 分钟：打开产品，用他的学科实时演示——出题、判分、知识图。真实操作，不做 PPT。
  - **关键 demo 点**：演示防作弊锁屏（如果有桌面 App）→ 演示 AI 出题管线 → 演示 Memorix 自适应选题 → 演示知识图谱热力图
- 5 分钟：他问问题。
- 结束：「If you want to try it yourself, I'll give you full access. Free for [X] weeks. No card. Just feedback.」

**桌面 App demo 的特殊优势：**
- 你可以说"Download our desktop app"——这听起来像一个正经产品
- 有桌面 App 的 SaaS 在 EdTech 赛道极其罕见——本身就是差异化
- 防作弊功能只能在桌面 App 里 demo——这是一个网页端竞品无法复现的 demo 环节

**Demo 后的跟进：**
- 如果他说要试试 → 当场发邀请码。别等。
- 如果他说考虑 → 三天后发一条：「Saw this article about [his industry pain point], thought of our chat. Here's the link. No pressure.」
- 如果他不回 → 两周后再 follow up 一次。两次不回就停。

---

## 第六步：定价和付款（海外版）

海外客户和国际支付，比国内简单：

**定价建议（先别定死，试）：**
- Starter: $99/month — 1 subject, up to 500 students
- Pro: $299/month — 5 subjects, up to 2,000 students
- 定制报价 — 大机构单独谈

**收款用 Stripe，不要用国内支付。** Stripe 有个 Payment Links 功能，不用 coding，创建一个链接发过去就能收款。海外客户看到 Stripe 才觉得正规。

**先不要设免费试用 14 天，改成「前 20 个客户锁定创始价」。** 因为 B2B 试用 14 天太短，机构来不及用出感觉。有限数量的创始价制造稀缺感。

**定价要体现桌面 App 的附加值：** 防作弊锁屏和离线考试作为 Pro/Enterprise 层的差异化功能，不要放在 Starter 里。让高级版有"网页做不到的事"。

---

## 第八步：桌面 App——不是产品，是销售武器

前面提到了桌面 App 在 demo 中的价值。这里展开讲战略层面的意义。

### 桌面 App 在 B2B EdTech 的定位

Figma、Slack、Notion 都做了桌面 App。不是因为"公司做大了就可以做"，而是因为桌面 App 本身就是 B2B 商业模型的必要组件：

1. **独立窗口 = 独立心智空间**。机构管理员一天开几十个 tab，浏览器里的 SaaS 会被淹没。桌面 App 在 dock 栏有个图标，点一下就开——就像微信之于聊天，浏览器 tab 永远做不到。
2. **防作弊是签单杀手锏**。机构最大的痛点之一是"学生在系统里刷题，旁边开着百度/Google 搜答案"。桌面 App 可以做锁屏、禁止切窗口、禁截屏、进程检测（检测到浏览器/微信弹警告）。Demo 这个功能，机构负责人眼睛会亮——因为竞品做不到。
3. **离线考试 = 机房场景的刚需**。很多培训机构机房断网考试，或故意断网防作弊。桌面 App 本地缓存题库 + 离线作答 + 交卷一键同步，网页无解。
4. **"Download our app" > "Here's a URL"**。机构决策者感受到的是一个"系统"而不是一个"工具"。年费上万的产品需要一个看得见摸得着的载体。

### 节奏：什么时候做

| 阶段 | 做什么 | 目的 |
|------|--------|------|
| 现在 → 第一个付费客户 | Tauri webview 壳，能跑完整流程 | Demo 时双击打开独立窗口 |
| 第一个付费客户上线后 | 接 3 个 native 能力：防作弊锁屏、离线刷题、系统通知 | 变成续费理由 |
| 5+ 付费机构后 | 投移动端（小程序/PWA），桌面 App 只维护 | 学生碎片时间覆盖 |

### 在 X 上怎么聊桌面 App

不要把它当成"我们有桌面 App"来宣传。要在正确的上下文中提到：
- 聊考试诚信时 → "我们的桌面 App 支持防作弊锁屏"
- 聊机房考试时 → "题库本地缓存，离线作答，交卷同步"
- Build in public 时 → "今天给桌面 App 加了进程检测，测了微信和 Chrome，稳定"

**桌面 App 永远不是主推点。它是你讲其他故事时的"证据"。**

不要用粉丝数衡量。用这三个数：

| 指标 | 冷启动 | 跑通 | 说明 |
|------|--------|------|------|
| 每周 DM 发起数 | 5-10 个 | 持续产出 | 你在主动出击 |
| 每月 Demo 数 | 2-4 个 | 10+ | 有人在看产品 |
| 付费转化 | 0 | 3+ 个海外付费客户 | 真金白银 |

**不要等到有很多粉丝才做商业转化。** 10 个精准关注者里有 1 个客户就够了。Indie hacker 圈子里几百个关注、月入几万美金的人遍地都是。

---

## 现在就做的三件事

1. **今天：检查 X Bio 链接指向哪**。如果还指向空页面或者中文首页，花一个下午搞个英文 landing page。加一个桌面 App 下载按钮——现阶段只是 Tauri 壳，但"有 App 下载"这件事本身就是信号。
2. **今天+本周：开始列名单。** 搜 #edtech #buildinpublic，找 30 个在做在线教育/培训相关产品的人，关注 + 互动。
3. **明天开始：你的帖子末尾加 CTA。** 每一条。不要求大行动（"注册"），求小行动（"DM 我" "回复你的学科"）。

---

## 不要做的事

- 不要等有了 1000 个粉丝才想着变现。10 个粉丝的时候就可以开始聊客户了。
- 不要在帖子里放购买链接。X 上的 B2B 销售是 DM → Demo → Close，没有自助买单。
- 不要发冷冰冰的 DM 模板。先互动，再 DM。先做人，再卖东西。
- 不要把 demo 做成一小时产品演示。15 分钟。重点是让他看到自己的学科在你的系统里跑起来。
