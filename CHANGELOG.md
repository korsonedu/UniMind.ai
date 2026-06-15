# Changelog

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
