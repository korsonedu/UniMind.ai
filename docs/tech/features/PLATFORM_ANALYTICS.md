# 平台数据分析

按 2026-10-25 本地源码核对。本次清理保留事件记录、每日平台统计、分析 Dashboard API 与趋势/事件 CSV 导出，移除 NPS 满意度问卷。旧前台分析页面已退出，不据此恢复 `/platform-analytics` 页面或旧维护 Tab。

## 数据与入口

| 职责 | 实现 |
| --- | --- |
| 业务事件 | `backend/core/models.py` 的 `AnalyticsEvent` |
| 记录事件 | `backend/core/analytics.py` 的 `record_event` |
| 每日统计 | `backend/core/models.py` 的 `DailyPlatformStats` |
| 聚合任务 | `backend/core/tasks.py` 的 `aggregate_daily_platform_stats` |
| Dashboard | `backend/users/views.py` 的 `AnalyticsDashboardView` |
| CSV 导出 | `backend/users/views.py` 的 `AnalyticsExportView` |

聚合任务从用户、事件、考试、课程进度和历史使用记录生成昨日快照；留存以登录事件的用户集合计算。`school_system/settings.py` 保留每日任务调度。不要把这些字段直接解释成真实教学效果、付费转化或因果证明，指标口径仍须结合实际数据核对。

## API

以下两个分析接口要求登录及 `IsPlatformAdmin`。管理员身份取决于当前两人映射和账号条件，历史教师、机构所有者不授予分析权限。

| 请求 | 内容 |
| --- | --- |
| `GET /api/users/admin/analytics/dashboard/?days=30` | 汇总、趋势、功能使用计数与历史机构 Top 列表 |
| `GET /api/users/admin/analytics/export/?type=trends&days=90` | 每日统计 CSV |
| `GET /api/users/admin/analytics/export/?type=events&days=90` | 事件 CSV |

Dashboard 返回 `summary`、`trends`、`feature_breakdown`、`institution_top`。没有快照时，用户总量和活跃度有实时查询兜底，不代表完成历史数据回填。

`type=nps` 不再支持，返回无效类型错误。问卷状态、提交接口、展示规则、弹窗和模型已从本地代码移除，`core.0008_remove_npssurvey` 仅生成，尚未在本次清理中执行。本次变更尚未部署，不据此描述当前生产数据或接口状态。

## 相关边界

Agent 消息赞踩仍在 `/api/ai/feedback/`，用于对话反馈；不属于已退出的产品反馈或 NPS 问卷。趋势与事件导出继续使用现有权限与数据范围，不开放新的前台入口。

部署时同时更新 Django、Celery worker 与 Beat，保留备份并按实际发布计划执行迁移。本地构建、迁移状态检查和生产核验应分别记录。
