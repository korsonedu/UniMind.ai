# Changelog

## v1.3.0 — AI 对话页会话侧栏 (2026-06-29)

### Added
- **AI 对话页左侧会话侧栏**：小宇页新增可拖动收起的会话侧栏，展示历史对话列表，随时切换
- **后端轻量会话列表 API**：`GET /api/ai/conversations/?bot_id=xxx`，返回会话元数据 + 消息数，避免加载全量消息
- **侧栏拖动吸附**：右边缘可拖拽调整宽度，拖到阈值以下自动收起到 48px，以上展开到 224px
- **工作台会话切换优化**：保留 header 中「N 个对话」pill 按钮（无侧栏时），可见性从 `muted-foreground/55` 纯文字提升为 `bg-muted/50` 药丸按钮

### Changed
- **小宇页 edge-to-edge**：`/xiaoyu` 加入 `isEdgeToEdge`，去除 MainLayout 默认的 `px-4 py-4` padding，侧栏贴边
- **「新对话」按钮强化**：从 `ghost muted-foreground/40` 改为 `bg-muted/60 rounded-full` pill 按钮
- **对话标题来源统一**：chat header 和侧栏标题走同一套 fallback 逻辑（消息 → session.title → session.label），新对话无标题时为空
- **侧栏收起方式**：从底部按钮切换改为右边缘拖拽吸附，无蓝色 hover 提示线

### Fixed
- **卡片不因刷新消失**：`handleRefreshSessions` 补充 `metadata.visual → toolStep.visual` 转换，侧栏切会话后 action card 不丢
- **新对话标题残留**：`handleReset` 后 `activeSessionId === null` 时直接返回空标题，不再 fallback 到旧 session
- **拖动时文字挤压**：副标题加 `whitespace-nowrap`，列表区拖动时禁用 overflow

## v1.2.2 — 页面 UI 一致性 (2026-06-28)

### Changed
- **统一入场动画方向**：所有页面卡片/编辑区动画统一为 `slide-in-from-bottom`（自下而上），消除 `zoom-in`（中心扩张）和 `slide-in-from-top`（自上而下）的方向混乱
- **统一页面边距**：Achievements / StudyPlan / ReportCard 去除多余 `px-4`，与 CourseCenter / Gradebook 对齐
- **消除双重动画**：PageWrapper 已提供入场动画，MyAssignments / QASystem 内层不再叠加
- **Loading 状态一致性**：TeacherAssignments / Gradebook loading 包裹 PageWrapper，与其他页面一致

## v1.2.1 — ARC 精修管线修复 (2026-06-28)

### Fixed
- **ARC 管线进度轮询停止**：`setTimeout` + state 驱动模式导致只轮询一次，进度永远卡在 5%。重写为递归 setTimeout + useRef
- **ARC 结果不展示**：管线完成后 questions 困在 `task.result`，前端无感知。状态端点 completed 时附加 questions，前端自动注入题目面板
- **管线进度写入不可靠**：`_update_task` 原地修改 JSONField dict 导致 Django 变更检测失效，后续阶段进度不写入 DB。改为每次创建新 dict
- **Agent 查询管线状态不同步**：小宇 `check_pipeline_status` 返回过期进度（同上 JSONField 问题）

### Changed
- **管线进度文字精细化**：Reviewer/Author/Classifier 逐题显示「评审第 2/6 题「一元二次方程」...」
- **防重复提交**：管线运行中 ARC 精修按钮禁用
- **精修题不再精修**：ARC 生成题目（source=arc_refine）不可再次触发 ARC
- **题目来源徽章**：一键生成（蓝色）/ ARC 精修（紫色），按 KP 自然关联
- **轮询空状态**：管线运行中显示实时进度文字和百分比

## v1.2.0 — 产品引导系统 (2026-06-28)

### Added
- **GuidedTour 引导系统**：新用户首次进入工作台/小宇时，遮罩式三步布局引导（输入框 → 侧栏 → 顶栏账号区），走完/跳过即记录，不再重复弹出
- **面板引导（Phase 2）**：教师首次对话后左栏面板出现时，单独引导 CopilotOverview 工作区
- 数据库持久化 `tour_dismissed_at` / `tour_panel_dismissed_at`，换设备不重复
- 移动端 <768px 自动跳过引导

### Changed
- 头像下拉菜单纳入 header-right 高亮区域

## v1.1.1 — 性能与体验优化 (2026-06-26)

### Changed
- **ErrorBoundary 路由级隔离**：`lazyPage()` 内包 ErrorBoundary，单页崩溃不再导致全白屏
- **AI Assistant 查询优化**：5 处 queryset 加 `select_related('user', 'bot')`，消除 N+1
- **Celery 任务超时保护**：20 个早期任务全部补 `soft_time_limit` + `time_limit`
- **Institution plan 缓存**：`get_effective_plan_for_user()` 加 Redis 缓存 300s，减少每次请求的递归查询
- **热点接口迁移 React Query**：机构 features、课程列表、学科列表改用 `useQuery`/`fetchQuery`，支持缓存去重
- **TestLadder 骨架屏**：数据加载时渲染全页 Skeleton，替代内容逐块弹出

### Added
- `AIChatMessage` 联合索引 `(user, bot, timestamp)` — 优化高频查询
- 共享 `queryClient` 模块 (`frontend/src/lib/queryClient.ts`)

## v1.1.0 — 双层熔断器 (2026-06-25)

### Added
- **双层熔断器（operation + model_tier）**：断路器支持操作层 + 模型分层独立熔断，pro 模型阈值 3 次（vs fast 5 次），更快隔离故障。操作层 key 向后兼容旧格式，部署时状态不丢失。

### Changed
- ai_engine 13 处调用点传入 model_tier 参数
- config.py 新增 `get_model_tier_for_operation()`

### Docs
- PgBouncer 部署指南（transaction pooling 模式）

## v1.0.4 — 版本号自动注入 (2026-06-25)

### Added
- **Footer 版本号从 git tag 自动注入**：vite build 时执行 `git describe --tags`，通过 `define` 注入 `__APP_VERSION__`，不再需要手改 version.ts。

## v1.0.3 — CHANGELOG + 前端版本号 (2026-06-25)

### Changed
- 更新 CHANGELOG + 前端版本号 v1.0.2

## v1.0.2 — OSS URL 修复 (2026-06-25)

### Fixed
- **RelativeImageField 错误拼接 OSS 绝对 URL**：`RelativeImageField` 在 `https://` 开头的 OSS URL 前拼接 `/`，产生 `//https://...` 破损链接，导致封面图和视频文件均加载失败。改为识别绝对 URL 直接透传，不再补前缀。

## v1.0.1 — OSS 签名 URL (2026-06-25)

### Fixed
- **OSS 私有 Bucket 返回 403**：`OssMediaStorage.url()` 返回未签名 URL，私有 OSS Bucket 直接返回 403，课程封面图和视频全部无法加载。改为返回带 24h 有效期的签名 URL，加 Redis 缓存避免每次 `url()` 调用都发 OSS API 请求。

## v1.0.0 — 首个版本化发布 (2026-06-25)

### Added
- **Git 版本化治理**：GitHub Flow 分支策略、SemVer 版本号、commit 规范、CHANGELOG 联动
- **Field 诊断引擎**：知识图谱诊断服务（`field_service.py`）+ API 端点（`views_field.py`）
- **语义边分析器**：KnowledgeEdge 语义关系分析（`semantic_edge_analyzer.py`）
- **知识树服务**：知识树 CRUD 服务层（`knowledge_tree.py`）
- **学生健康诊断扩展**：健康分计算 + 趋势分析 + 机构健康概览
- **前端 TaskList 组件**：任务列表 UI + `queryKeys` 统一管理
- **AgentChat hooks 重构**：`useAgentChat` + `useAgentConversation` 提取
- **Migration 0052**：KnowledgePoint code/level 字段调整

### Changed
- **AI 引擎重构**：`ai_engine/service.py` 大幅重构（+462/-?）
- Memorix 优化（field/optimizer/service）
- 前端 AgentChatLayout、课程、支付等多个页面改进

## v0.5.1 — MUTAR 自进化闭环 + 用户反馈 (2026-06-13)

### 架构
- **MUTAR 全链路打通**：采集→评估→分析→建议→变体路由→优化执行
- **Trajectory 记录激活**：SSE/Polling/WS 三条路径对话结束时自动调用 `record_trajectory`
- **Prompt Variant 框架**：文件驱动的变体管理（`mutar_variants.py`），按流量比例 A/B 路由
- **用户反馈体系**：AI 回复 hover 赞/踩 → `AIChatMessage.feedback` → `AITrajectory.outcome`

### 新功能
- **AI 回复反馈**（👍👎）：hover 显示，静默记录，再次点击取消，失败回滚
- **轨迹自动评估**（`_auto_evaluate_trajectory`）：启发式评估 outcome（无反馈时也能用）
  - AI 错误消息 → failure(0.95) | 工具全成功 → success(0.75) | 部分失败 → partial(0.65)
- **反馈→轨迹联动**：用户赞/踩同步覆盖 `AITrajectory.outcome`，标记 `feedback_source: user`
- **变体路由**：`get_variant_for_request(bot)` 按 `traffic_split` 加权随机选择 variant
- **变体 CRUD**：`create_variant / retire_variant / update_traffic`，JSON 文件存储，零 migration
- **`optimize_prompt_task`** 从 `pass` → 完整框架（读建议→分派 3 类 handler）
- Celery beat 新增 `optimize-prompt-weekly`（每周一 3am，跟在 analyze 之后）

### 修复
- ChatBubble 反馈按钮折叠导致 layout shift → 固定 `h-5` 占位 + `opacity` 切换
- 对话间距增大（`space-y-3`/`space-y-4`），hover 不再挤动下方内容

### Migration
- `ai_assistant/0018_add_feedback_to_message.py` — `AIChatMessage.feedback` (BooleanField, nullable)

## v0.5.0 — 闭环 MVP + 测评引擎升级 (2026-06-06)

### 架构
- 四层架构完整落地：基础框架 → 记忆系统 → 教育闭环 → 测评引擎
- MemorySystem 查询接口层（6 query + 2 write + 1 context）
- GradingEngine 独立评分服务
- 多 Agent 运行时（小宇 20 tools + 命题官 5 tools）

### 新功能
- **错因分析**：评分同时输出错因类型（概念错误/计算失误/审题失误）
- **做题闭环**：小宇推送练习 → 做题 → 回到小宇看分析
- **复习闭环**：点击复习卡片直接进做题（`preference=review_first`）
- **GradingRecord**：评分历史持久化
- **UserProfile**：6 维用户画像持久化
- **IRT 模型**：ItemParameter / UserAbility / QMatrixEntry 数据模型就位
- **API 化**：4 个 API 端点（grade / profile / due / stats）
- **MUTAR 自进化**：Trajectory 分析骨架 + Celery beat schedule
- **HomeRedirect**：学生默认进 /xiaoyu（Agent 为入口）

### 修复
- action_cards URL 加 `source=xiaoyu` 参数，做题后回到小宇
- 复习卡片直接进做题页，不再跳错题展示页
- 批改步骤卡片显示错因标签
- 卡片刷新后持久化（metadata.visual 恢复）
- question.question → question.text 字段名 bug（原始代码）
- 主观题评分 prompt 花括号转义
- review_first 无错题时 fallback 到 balanced

### Migration
- 0037: UserQuestionStatus + error_type / error_metadata
- 0038: GradingRecord
- 0016: UserProfile
- 0039: ItemParameter / UserAbility / QMatrixEntry

---

## v0.4.x — 小宇基础能力 (pre-2026-06-06)

- 小宇学习教练 Agent（20 个工具）
- 命题官教研 Agent（5 个工具）
- Memorix 间隔重复调度引擎
- 自适应 Prompt 系统（memory_analyzer + prompt_adapter）
- 对话流内联视觉卡片（InlineVisualCard）
- 侧边栏 9 模块（MainLayout）
- 诊断测试（DiagnosticTest）
- 命题官工作台（Workbench + split-view）
- SSE 流式对话
- 机构多租户隔离
