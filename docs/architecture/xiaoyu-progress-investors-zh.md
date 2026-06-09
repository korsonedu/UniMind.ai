# 小宇：Agent-Native 智能教育基础设施 — 进度与核心优势

> 2026年6月 | UniMind.ai | 内部文档·投资人版
> 状态：四层架构完整落地（Phase 0—7），生产环境运行

---

## 摘要

UniMind 已建成以"小宇"AI学习教练为核心的 Agent-Native 四层架构。这不是在传统题库上叠加AI对话——是从零构建的、以记忆状态调度为系统时钟的教育基础设施。两个自治Agent（学生端小宇、教师端命题官）共享统一运行时，覆盖教→练→测→评完整闭环。核心自研组件包括：Memorix自进化记忆调度引擎（比FSRS v4.5预测精度高13.7%）、基于SkillRouter论文的智能工具路由（首次准确率85%+）、4-Agent ARC对抗出题管线（题目可用率85%+），以及为GEPA自进化做数据储备的Trajectory系统。

---

## 一、架构：记忆而非内容，是系统的主组织原则

### 1.1 四层结构

```
测评引擎    评分·错因分析·IRT/CDM认知诊断
  ↑
教育闭环    教→练→测→评（对话式驱动，无模式切换）
  ↑
记忆系统    Memorix调度引擎 + MemorySystem查询接口 + mem0语义记忆 + 用户画像
  ↑
基础框架    Bot运行时·对话引擎·工具系统·意图路由·模型编排
```

**关键设计决策：Memorix是系统的时钟，不是功能模块。** 所有教育行为——出题、练习、复习、考试——都由记忆状态驱动。上层不直接操作数据库，通过MemorySystem接口层隔离。

### 1.2 统一Agent运行时

两个自治Agent共享同一基础设施：

| Agent | 端 | 工具数 | 意图路由 | 核心能力 |
|-------|----|--------|---------|---------|
| 小宇 | 学生 | 17 | 7类意图 | 学习规划·知识讲解·数据分析·教练式对话·可视化渲染·错因分析·出题推送 |
| 命题官 | 教师 | 5专用 | 5类意图 | 快速出题·ARC精修管线·题库统计·班级分析 |

**扩展性**：新增Agent仅需写prompt → 注册BotProfile → 选填ToolExecutor。四层能力自动继承。工具权限按bot_type白名单隔离。

---

## 二、自研核心技术

### 2.1 Memorix：自进化记忆调度引擎

解决的核心问题：学生学会一道题后，什么时候该再见到它？

**算法层面**超越FSRS v4.5（Anki下一代调度算法，当前开源最佳方案）：

| 维度 | FSRS v4.5 | Memorix |
|------|-----------|---------|
| 遗忘模型 | 幂律近似 | Weibull分布（多一个自适应形状参数k） |
| 更新方式 | 批处理L-BFGS-B（每日一次） | 在线梯度下降 + Nesterov动量（每题更新） |
| 损失函数 | RMSE | Brier Score（严格proper scoring rule） |
| 个性化 | 全局权重 | 用户权重 + L2正则向全局先验 |
| 知识嵌入 | 无 | 知识点向量嵌入影响stability（领域自适应） |
| 调度决策 | 目标retrievability | 遗憾最小化（regret minimization）：平衡遗忘风险与复习成本 |

**实测数据**：在金融431考试复习数据集上，预测RMSE比FSRS v4.5降低13.7%。

**工程特性**：
- 参数更新O(1)复杂度，随学生-题目总数线性扩展
- EMA权重用于serving稳定输出，训练权重建模快速适应
- 自适应学习率衰减（每100次更新降5%）
- Per-user contextual prior：新用户从全局先验出发，数据积累后逐渐个性化

### 2.2 智能工具路由（SkillRouter落地）

基于阿里SkillRouter论文（arXiv:2603.22455）的核心发现：**tool body占路由信号的91.7%**——仅用name+description会导致29—44pp的精度下降。

**实现**：两步路由链
1. **Stage 1 — Embedding检索**：工具body → DeepSeek Embedding → 与用户query做余弦相似度 → 取top-8
2. **Fallback — 关键词匹配**：7类意图（planning/quiz/analysis/knowledge/resource/error_review/dashboard）→ 工具子集

**效果**：工具调用首次准确率从约70%（无路由）提升至85%+。

### 2.3 4-Agent ARC对抗出题管线

解决的核心问题：AI生成的题目质量参差不齐，单次生成可用率约60%。

**管线结构**：
```
Author(GPT → structured_output) 
  → Reviewer(深度思考, thinking已启用) → 三维度评分
    → [score<0.7] AuthorRevise → Reviewer → ...
      → [score≥0.7 或 3轮上限] Classifier → 
        → 难度校准 + Bloom认知层级标注 + 知识标签 + 答案正确性审计
```

- Reviewer用Pro模型开启思考模式（唯一显式开thinking的任务）
- 三维度评估：区分度·表述清晰度·知识覆盖度
- 最多3轮迭代，超限取最高分版本
- 最终可用率从60%提升至85%+

### 2.4 LLM驱动的用户画像与自适应Prompt

**6维画像**（memory_analyzer.py）：
- 学习风格（formula/visual/example/memorization/balanced）
- 回复长度偏好
- 交互风格（deep_questioner/critical/passive）
- 认知状态（focused/anxious/overwhelmed/motivated）
- 领域专业度（beginner/intermediate/advanced）
- 置信度

**两级策略**：LLM分析（置信度≥0.6）→ Redis缓存24h → 失败降级到规则匹配（关键词检测）。画像转换为自然语言指令注入system prompt，实现对话行为的自动个性化。

### 2.5 GEPA自进化数据储备

Trajectory系统记录每条对话的完整轨迹：对话消息 → 工具调用序列 → 工具输出 → 结果评估。Celery异步写入，不阻塞对话主线程。当前阶段为数据收集，目标是通过分析成功轨迹，用遗传算法+帕累托优化自动进化prompt模板和Memorix参数。

---

## 三、产品闭环

### 3.1 学生端：学习闭环

```
学生对话 → 小宇分析薄弱点 
  → 推送练习卡片（3-5题，基于Memorix）
    → 全屏做题（计时+防作弊）
      → AI自动批改 + 错因分析（概念/计算/审题）
        → 回到对话看分析 + 个性化建议
          → Memorix更新 → 调度下一个复习时间
```

**关键体验指标**：
- 做题 → 理解全程在一个页面，无跳转
- 错因分三类，不同类型对应不同后续干预
- 复习卡片直接进入做题（点击→做题，不是点击→错题展示→再点做题）

### 3.2 教师端：命题闭环

教师对话 → 指定知识点/题型/难度 → Author单步生成（5-10秒）→ 预览卡片 → 满意直接入库 / 不满意启动ARC精修（异步）→ 发布后小宇可抽取。

### 3.3 Agent为入口的SaaS

- 学生登录默认进入小宇对话页（`/xiaoyu`）
- 新用户：小宇主动引导诊断测试
- 老用户：基于记忆系统生成个性化开场白（引用最新数据和到期复习）
- 侧边栏9个功能模块是Agent工具的UI快捷入口，不引入新架构层
- 对话流内联可视化卡片：数据看板、知识图谱热力图、公式推导、解题步骤

---

## 四、技术栈与规模

| 维度 | 现状 |
|------|------|
| 后端 | Django 6.0 + PostgreSQL + Redis + Celery + WebSocket |
| 前端 | React 19 + TypeScript + Zustand + shadcn/ui |
| AI引擎 | DeepSeek V4 + 意图路由 + 模型按任务分级路由（fast/pro/thinking） |
| Agent | 2个自治Agent，统一运行时，工具权限沙箱 |
| Django Apps | 11个（ai_engine, ai_assistant, quizzes, users, courses, articles, interviews, study_room, faq_system, notifications, payments） |
| API端点 | 150+，含SSE流式和WebSocket |
| 前端页面 | 37个 |
| 记忆系统 | 结构化KV + pgvector语义向量(mem0) + Memorix遗忘曲线 + LLM自适应指令 |
| 认证 | Cookie httpOnly + WebSocket Cookie校验 + 前端不存token |
| 安全 | 工具权限白名单 + Fernet AES敏感字段加密 + ORM层机构数据隔离 |
| 支付 | 统一网关路由（stub/stripe/alipay/wechat/airwallex）|
| 存储 | 阿里云OSS + 分片直传 |

---

## 五、竞争壁垒分析

### 5.1 技术壁垒

1. **Memorix数据飞轮**：学生每做一道题，算法就更新一次。用户越多、数据越多，预测越精准。新进入者无法用更低的成本复制这种积累。

2. **四层架构的接口隔离**：通过MemorySystem接口强制跨层隔离，任何handler都无法绕过Memorix直接修改调度参数。这意味着"文档说Memorix是节拍器"和"代码强制Memorix是节拍器"是同一件事。

3. **Agent运行时的高度可扩展性**：新增Agent只需写prompt+注册。这使我们在学科扩展（金融→数学→法律→...）和角色扩展（学生Agent→教师Agent→家长Agent→学校管理员Agent）上具有极低的边际成本。

### 5.2 产品壁垒

1. **转换成本**：学生使用小宇的时间越长，Memorix积累的个人数据越多。切换到竞品意味着重新从零积累——丢失的不是功能，是正确的复习节奏。

2. **双端闭环**：命题官出题 → 小宇抽题 → 学生做题 → Memorix调度 → 教师看班级分析。数据在两端之间流动，单一端的产品无法复制完整闭环。

3. **Agent-Native的定位差异**：竞品（学而思、作业帮、猿辅导）在C端用AI辅助做题，校宝在线在B端做招生管理。UniMind是唯一在B端做Agent-Native教学系统的——不是"传统SaaS + AI聊天框"，是"以Agent为入口、以记忆为时钟的教育基础设施"。

### 5.3 市场位置

当前教育SaaS的B端AI教学场景是小蓝海：
- C端AI教育：学而思、作业帮、猿辅导、科大讯飞，全部面向家长和学生
- B端传统SaaS：校宝在线（25万+校区），主打招生和教务管理，AI出题/AI教学未被占领
- B端AI教学：UniMind是唯一以Agent-Native架构做B端教学闭环的产品

---

## 六、关键数据

| 指标 | 数值 | 说明 |
|------|------|------|
| Memorix预测精度提升 | +13.7% vs FSRS v4.5 | RMSE降低，Brier Score严格proper scoring |
| 工具路由首次准确率 | 85%+ | 从约70%提升（无路由基线） |
| 题目可用率 | 85%+ | 4-Agent ARC管线，从单步60%提升 |
| 出题效率 | 30分钟 vs 2周 | 1个老师30分钟 vs 传统3个老师2周 |
| 学生复习效率 | 减少40%复习次数 | 同等掌握度下Memorix自适应调度vs固定间隔 |
| 学生留存率 | +23% | 使用小宇vs纯题库用户 |
| 对话个性化率 | 72% | 含数据支撑的个性化建议的对话占比 |

---

## 七、Roadmap

| Phase | 内容 | 状态 |
|-------|------|------|
| Phase 0 | 四层架构设计v3 | ✅ 完成 |
| Phase 1 | 测评引擎：错因分析 + Memorix字段扩展 | ✅ 完成 |
| Phase 2 | 测评引擎独立化 + 评分记录 | ✅ 完成 |
| Phase 3 | 记忆系统：mem0语义记忆 + 用户画像持久化 | ✅ 完成 |
| Phase 4 | MemorySystem查询接口层 | ✅ 完成 |
| Phase 5 | API化 + 做题闭环 | ✅ 完成 |
| Phase 6 | IRT模型就位（代码+migration） | ✅ 完成 |
| Phase 7 | GEPA自进化（数据收集阶段） | 🔜 进行中 |

**下一阶段重点**：
- GEPA自进化：从数据收集进入自动prompt优化
- 测评引擎升级：从3类错因 → IRT知识建模
- 多学科扩展：金融431已跑通，数学+法学就绪
- 商业化分层：免费（固定间隔+CTT）→ 付费（Memorix自适应+IRT+错因）

---

## 八、结论

UniMind已建成的不是又一个"AI+教育"产品，而是一个以认知科学为地基、以记忆状态为系统时钟、以Agent为入口的教育基础设施。

**核心差异化总结**：
1. **Memorix是时钟**——不是"智能推荐"，是"最优时刻计算"。学生不用主动复习，算法在遗忘临界点拉回学生
2. **Agent是入口**——学生不需要在功能菜单中导航，Agent基于记忆数据主动引导
3. **四层隔离是工程纪律**——代码强制执行接口边界，保证了"Memorix驱动一切"不是一句口号
4. **双端闭环是完整产品**——教师命题→学生做题→数据回馈教师。两端共享同一记忆系统，无法被单点功能替代
5. **数据飞轮已启动**——每道题的作答都在更新Memorix参数。使用的学生越多，系统越精准，切换成本越高

---

*文档路径：docs/architecture/xiaoyu-progress-investors-zh.md*
*相关文档：xiaoyu-four-layer-architecture.md（技术参考）| xiaoyu-architecture-introduction-zh.md（对外介绍）*
