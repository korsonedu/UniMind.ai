# Changelog

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
- **GEPA 自进化**：Trajectory 分析骨架 + Celery beat schedule
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
