# Changelog

## 1.5.4 · 项目对话右侧栏（2026-11-17）

### Fixed
- 打开学习路径、知识关系、项目资料和任务记录时，当前项目对话进入右侧栏，自动展开并选中小宇标签。
- 切回对话视图后继续在主屏交流，保留原消息与输入草稿。
- 收起侧栏后再次点击当前功能可重新展开，输入框内按 Esc 可收起侧栏。

本轮仅发布网页前端，不涉及后端或数据库迁移，不生成桌面安装包。

## 1.5.3 · 完整空间隔离（2026-11-16）

### Fixed
- 个人与机构 Workspace 各自使用完整功能，切换空间不再只是跳转课程。
- 对话、学习项目、笔记、练习、记录、知识内容、社区与学习偏好分别保存；切换时重建界面与连接。
- 账号 AI 基础额度与加量继续共用，并统一计算两个空间正在使用的额度。
- 机构内容不进入个人空间；空间停用后停止访问，个人空间仍可使用。

新增学习身份映射表；历史个人内容保持原归属。本轮发布网页与后端，不生成桌面安装包。

## 1.5.2 · 个人空间与课程切换（2026-11-16）

### Added
- 左上角切换个人空间与课程 Workspace，返回个人空间时继续个人学习项目。
- 空间菜单显示账号 AI 剩余额度，个人小宇与课程小宇共用额度。

### Changed
- 通过全局导航进入课程时不自动携带个人项目上下文，课程权限沿用现有授权。

本轮仅发布网页，桌面安装包保持现有版本。

## 1.5.1 · 设置与账户整理（2026-11-16）

### Changed
- 设置按常规、通知、外观、学习、个性化和账户分类；桌面通知、快捷键、离线存储和更新按栏目呈现。
- 账户默认展示当前资料、邮箱与身份，点击后再编辑；使用情况与计费仅在账户内提供入口。
- 补充手机端题型提醒与共学广播偏好，沿用现有存储与权限。
- 保留中英文切换、通知总开关折叠分类、简洁文案和原有主题切换。

网页与后端按本次发布部署；桌面菜单源码调整随下次客户端构建分发，本轮不生成安装包。

## 1.5.0 · 中英文学习体验（2026-11-15）

### Added
- 学员端、账号中心和桌面原生界面支持中文与英文，账号语言偏好可跨设备恢复。
- 小宇工作区、课程、练习反馈、笔记、通知和报告导出接入语言；原始学习内容与引用保留原文。
- 首页提供虚构英文示例截图及英文法律参考译文。

### Fixed
- 修正纯日期跨时区偏移、笔记保存状态比较和知识图英文标签截断。

部署需执行 quizzes.0058_exam_ui_language 与 users.0079_preferred_language。桌面原生菜单与离线改造需安装新版生效。安装包继续使用手动安装的受控分发，不启用自动更新；Windows 实机安装、海外支付／网络和真实英文教学质量不由构建冒烟证明。

## 1.4.1 · 请求安全与桌面同步修复（2026-11-11）

### Fixed
- 桌面离线授权和学习记录同步补齐请求来源头，配合服务端 CSRF 校验。
- 站点写请求带上 CSRF token，网络失败不再自动重放写操作；私有 API 不再使用跨账号共享缓存。
- 修正媒体 Range 响应和课程标签接口，停用废弃机构、优惠券及支付入口，移除旧管理端和占位发票任务。

客户端使用正式线上入口，继续提供 Mac ARM64 和 Windows x64 手动安装的受控分发包。Mac 未公证，Windows 未作实机安装验收；不启用自动更新。网页及后端修复已先行部署，桌面主进程修复需安装此版本生效。

## 1.4.0 · 小宇随课问答（2026-11-04）

### Added
- 听课时可直接向小宇提问，结合提问位置所在的一分钟讲稿片段解释概念、补充例子；需要课程具备可用讲稿。
- 回答提供讲稿引用与时间定位，可以点击回看课程，并将回答保存为个人笔记。
- 设置增加“关于 UniMind”，分别展示产品版本与实际安装的客户端版本，技术详情提供产品构建编号。

### Changed
- 产品与桌面客户端开始共用版本序列，以 `frontend/package.json` 为唯一手动维护的版本来源，桌面构建自动同步。旧客户端版本不会随网页更新改变。
- 产品版本不再由最近的 Git 标签推断；发版提醒只提示时机，版本类型按产品变化确定。

安装包继续采用手动安装的受控分发方式。此前桌面版本保留原标签及历史记录；实际部署与分发状态以发布记录为准。

## Desktop 0.1.9 — macOS 菜单栏点击修复（2026-11-04）

### Fixed
- 点击 macOS 菜单栏 UniMind 图标只展开菜单，不再强制唤起主窗口；仍可通过菜单中的“打开 UniMind”进入应用。

桌面包继续采用手动安装的受控分发方式。

## Web 与 Desktop 0.1.8 — macOS 菜单与多窗口（2026-11-03）

### Changed
- 菜单按 UniMind、文件、学习、编辑、显示、窗口排列，补齐应用系统菜单项。
- 文件菜单提供新建窗口、新聊天、新项目、离线课程库、重新连接和关闭窗口；学习菜单提供课程入口和专注操作。
- 新聊天和新项目复用小宇现有流程；菜单操作跟随当前窗口，各窗口独立处理加载与关闭。

桌面包继续采用手动安装的受控分发方式。

## Web 与 Desktop 0.1.7 — 右键菜单（2026-11-01）

### Added
- 桌面主窗口、课程附件与离线课程窗口提供原生文本编辑和链接右键菜单。
- 网页与桌面会话列表支持右键重命名、置顶、移动到项目和删除。
- 笔记列表支持右键打开、重命名、收藏、移动、导出、恢复和删除，保留保存与删除确认流程。
- 业务菜单支持 Shift+F10，并优先于桌面原生右键菜单。

桌面包继续采用手动安装的受控分发方式。

## Web / API 与 Desktop 0.1.6 — 学习体验更新（2026-11-01）

### Added
- 小宇按题型筛选题库；无匹配时在对话内现场出题和反馈，不写入站内练习成绩或掌握度。
- 发布已合并的设备偏好：阅读、对话、练习、在线播放、通知、启动页和专注设置。

### Changed
- 首页缩短首次进场动画，重复访问、慢网络及减少动态效果场景跳过；字体改为本地资源。
- 匿名首页不再等待账号请求，Service Worker 延后到登录后注册，保留离线页面运行资源。
- 桌面客户端升至 0.1.6，以提供新增原生设置；继续使用手动安装的受控分发包。


## Desktop 0.1.5 — 托盘视觉更新（2026-11-01）

### Changed
- macOS 托盘改用 18pt 单色模板图标，提供 1×／2× 资源并适配深浅色菜单栏。
- 专注计时保留标识和紧凑的等宽数字，暂停时显示闭眼标识及明确状态。
- 托盘菜单原位更新倒计时，避免每秒重建菜单。
- Windows／Linux 托盘使用 16px／32px 彩色标识。
- 固定桌面发版流程，区分受控分发候选与签名自动更新发行；版本号与锁文件保持一致。

本次为未取得发行证书的受控分发版，使用正式产品名和线上入口，采用手动安装。网页和后端的其他未提交改动不在本次桌面包中。

## v1.3.2 — 工作台出题稳定性修复 (2026-07-05)

### Fixed
- **出题超时后死循环**：`_run_tool_with_timeout` 超时时返回 `json.dumps` 而非 raw dict，修复下游 `'"error"'` 双引号检测永远漏检导致 LLM 无限重试；新增 `future.cancel()` + `executor.shutdown(wait=False)` 不阻塞等待；timeout 从 30s 提升到 120s
- **quick_generate 运行时间远超声称**：`skip_review=True` 时 `max_windows=1`，避免无意义多轮 Author 生成后被 `questions[:count]` 截断，首轮约 15s 可完成
- **工作台题目面板不渲染 LaTeX**：题干、答案缩略、卡片选项全部改用 `MarkdownContent`（react-markdown + remark-math + rehype-katex），与聊天面板一致
- **题目卡片不能查看详情**：卡片 `onClick` 改为打开 Dialog 详情弹窗，勾选框 `e.stopPropagation()` 保持独立行为；弹窗展示题干/选项/答案/评分要点，全部 LaTeX 渲染
- **评分要点 `.map()` crash**：`_clean_question_data` 中 `isinstance(list)` 时保持 list 不转 string，SSE 直传前端正常 `.map()`；入库时 `'\n'.join()` 转 TextField
- **答案含 LLM 思考过程**：`bulk_generate_prompt.txt` 新增「答案纪律」段落，禁止自我质疑/多轮试探/条件自检等草稿思维出现在 answer 中，要求最终定稿像出版物标准答案
- **非流式路径异常处理漏修**：`call_ai_with_tools` 异常捕获也改为 `json.dumps`，与流式路径一致
- **进度标签硬编码 /2**：`_on_candidates` 标签去掉硬编码分母，改为 `第 N 轮完成`

### Changed
- `quick_generate` 工具描述更新：从"约 5-10 秒"改为"首轮约 15 秒，逐题展示"
- `single_generate_pipeline` 新增 `on_candidates` 回调参数，每轮 author window 完成后通过 SSE 逐步推送候选题目到前端面板

## v1.3.1 — Agent 任务卡片修复 (2026-06-29)

### Fixed
- **Task 卡片死功能**：`batch_start` 后的 SSE 事件因 `return` 误退出 `doSend` 导致全部丢弃，task 永远「进行中」不更新。改为 `continue`，done 事件正常到达前端
- **Task 依次打勾**：并行改串行执行，工具逐个完成，前端收到真实间隔的 progress 事件，自然依次打勾
- **Task 位置**：从消息区顶部移到输入框上方紧贴，不随消息滚动
- **DataCard 去掉 subtitle**：LLM 不再编造「高中数学 · 考研备考中」等无来由文案

### Changed
- **只读工具串行化**：原并行执行白名单工具改为串行，task 列表驱动 agent 逐步执行计划

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
