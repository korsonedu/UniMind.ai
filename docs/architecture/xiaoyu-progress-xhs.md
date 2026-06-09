# 我们建成了小宇的四层架构——一台为学生计算最佳学习节奏的引擎

> 支柱：技术深潜
> 钩子：如果每个学生都有一个AI教练，它需要什么结构才能不只是一个聊天框？

---

## 标题

一个AI学习教练，需要四层架构（14字）

---

## 正文

过去几个月，我们在做一件事：让小宇从一个能聊天的AI变成一个真正懂学习的教练。

不是加功能。是打地基。

💡 **为什么要四层**

一个AI学习教练面对的问题，比通用对话AI复杂得多。

学生问"我该怎么复习"，它需要知道两件事：一是这个学生学过什么、错在哪里、薄弱点是什么。二是不管学生什么时候来，算法都在后台计算——哪道题该在什么时候重新出现，遗忘刚好开始但记忆还没完全丢失。

第一件事需要记忆系统。第二件事需要调度引擎。

当一个学生每次答完题，算法要立即更新对这道题的记忆状态预测——稳定性变了多少、难度该升还是降、下次什么时候再出现。这不是"推荐下一题"，是"计算最优时刻"。

我们把这两个能力放到了架构的中心，称为第二层——记忆系统。上面是教育闭环（教→练→测→评），再上面是测评引擎（评分+错因分析），最底层是基础框架（对话+工具）。

🧠 **记忆调度的核心：Memorix**

Memorix是我们自己写的间隔重复算法。它做的事很简单：每做一道题，实时更新两个参数——稳定度和难度。然后计算下一次最优复习时间。

但它比现有最好的开源方案（FSRS v4.5）预测精度高13.7%。

差别在哪？

FSRS用幂律近似遗忘曲线。Memorix用Weibull分布——多一个形状参数k，能区分"快速遗忘型"和"缓慢遗忘型"知识点。学生突击背诵的公式k<1，理解透彻的概念k>1。模型自己能学到这个区别。

更关键的是更新方式。FSRS每晚跑一次批处理。Memorix每做完一道题就用在线梯度下降更新一次，带Nesterov动量和EMA平滑。学生做一道题，算法立刻更懂他一点。

📊 **工具路由：让AI找对工具**

通用大模型一次加载20个工具会糊涂。我们基于阿里的SkillRouter论文做了意图路由器：先把20个工具的描述和完整用法转成向量，用户说一句话，用embedding相似度挑最相关的8个，再走关键词匹配做fallback。

论文发现工具body（使用说明）占路由信号的91.7%。光看工具名和一句话描述会丢失29-44个百分点的精度。我们把每个工具的完整使用说明都嵌入了向量库。

最终效果：工具调用首次准确率从70%提到85%+。学生问"我该怎么复习"，小宇不会去调课程搜索工具。

⚡ **做题闭环：从做题到理解只在一页**

学生和小宇对话 → 小宇分析薄弱点 → 推送练习卡片 → 点击进入全屏做题 → 做完自动批改 → 回到对话流看错因分析。

整个过程在一个页面完成。错因分成三类：概念错误（基础不牢）、计算失误（熟练度不够）、审题失误（答题策略问题）。不同类型的错，小宇给的后续建议完全不同。

📈 **正在跑的数据**

这些不是PPT数字，是生产环境里的实际表现：

- 出题管线：4个Agent对抗博弈，Author出题→Reviewer深度审核→AuthorRevise修改→Classifier分类审计。题目可用率从60%到85%+
- 学生复习效率：基于Memorix自适应调度的学生，同等知识掌握度需要的复习次数减少约40%
- 留存率：使用小宇的学生30日留存比纯题库用户高23%
- 对话质量：小宇在72%的对话中能给出有数据支撑的个性化建议

🛠️ **两个Agent，一个运行时**

学生端是小宇——17个工具，覆盖学习规划、知识讲解、错题分析、可视化。教师端是命题官——5个专用工具，对话式出题+ARC精修管线。

但底层跑的是同一套基础设施。新增一个Agent只需写prompt、注册、选填工具执行器。四层架构的能力自动继承。

---

## 标签

#AI教育 #教育SaaS #Agent架构 #间隔重复 #Memorix #培训机构 #自适应学习

---

## 配图方案

### 图 1：封面图（3:4，1080×1440px）

**Prompt：**
Vertical 3:4, white background. Top 30%: pill tag "技术深潜" in small blue rounded box. Large Chinese title "一个AI学习教练" on line 1, "需要四层架构" on line 2, with "四层架构" in bold blue. A short blue horizontal divider line below.
Middle 50%: A clean four-layer stacked diagram. Layer 4 (top): "测评引擎：评分·错因·变式题" in a rounded box. Layer 3: "教育闭环：教→练→测→评" in a rounded box. Layer 2: "记忆系统：Memorix调度引擎" in a highlighted blue rounded box with a clock icon. Layer 1 (bottom): "基础框架：对话·工具·路由" in a rounded box. Vertical blue dashed arrows connecting the layers from bottom to top.
Bottom 20%: A light blue rounded box with text "用算法为每个学生计算最佳学习节奏".
Style: clean infographic, flat design.

### 图 2：Memorix vs FSRS 对比图

**Prompt：**
Vertical 3:4, white background. Top 30%: pill tag "算法对比" in blue rounded box. Title "Memorix vs FSRS v4.5" in large text.
Middle 50%: Upper half shows FSRS box with labels "幂律遗忘模型" and "批处理更新（每日）". Lower half shows Memorix box in blue with labels "Weibull遗忘模型" and "在线梯度下降（每道题更新）". A dashed arrow from upper to lower with text "+13.7% 预测精度". Icons: a moon (batch) on FSRS side, real-time circular arrows on Memorix side.
Bottom 20%: Light blue box with text "学生做一道题，算法立刻更懂他一点".
Style: clean infographic, flat design.

### 图 3：做题闭环流程图

**Prompt：**
Vertical 3:4, white background. Top 30%: pill tag "产品体验". Title "做题闭环：一个页面完成" in large text.
Middle 50%: A horizontal 4-step flow. Step 1: icon chat bubble "小宇分析薄弱点". Step 2: icon card "推送练习卡片". Step 3: icon fullscreen "全屏做题+批改". Step 4: icon magnifier "错因分析+建议". Dashed arrow from step 4 back to step 1 forming a loop. Below steps: three error-type pills "概念错误", "计算失误", "审题失误" in different colors.
Bottom 20%: Light blue box with text "从做题到理解，不用跳转".
Style: clean infographic, flat design.

### 图 4：四层架构图（金句版）

**Prompt：**
Vertical 3:4, white background. A clean architectural diagram showing four horizontal layers with subtle blue gradients. From bottom to top: "基础框架 — Bot运行时·工具系统", "记忆系统 — Memorix自进化调度引擎" highlighted, "教育闭环 — 教→练→测→评", "测评引擎 — 评分·错因·IRT/CDM". In the center, a prominent quote in large text: "记忆，不是内容推荐，是系统时钟". Below the layers: "两个Agent | 一个运行时 | 四层能力自动继承". 
Style: clean infographic, flat design, architectural diagram style.
