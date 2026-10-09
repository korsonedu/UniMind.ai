# UniMind 全功能盘点（2026-08-14）

> 盘点范围：backend 11 apps（全部 API 路由/services/Celery 任务/管理命令）+ frontend 62 页面 + 路由注册 + 组件目录。
> 方法：4 个并行探索 agent 核对 urls.py/views/前端调用方 + dev 库数据行数 + git 活跃度。
> 目的：为「功能删除」决策提供完整清单与证据。

## 一、功能全景

### 学生核心学习链路（存活核心）

| 功能 | 路由/入口 | 状态 |
|---|---|---|
| 小宇 AI 教练（Agent 对话+WS/SSE） | `/xiaoyu` `/api/ai/chat|stream/` `ws/ai/chat/` | ✅ 学生主入口 |
| 小宇 Dashboard（打卡/正确率/计划进度/热力图） | `/api/ai/dashboard/` | ✅ |
| 诊断测试（3 阶段+重评估） | `/diagnostic` `/api/users/me/diagnostic/*` | ✅ 首次登录引导 |
| 刷题（TestLadder/TestSession/在线考试） | `/tests` `/exam/:id` `/api/quizzes/*` | ✅ |
| Memorix 遗忘曲线+优化历史 | `/quizzes/memorix/curve|optimization-history/` | ✅ |
| 错题洞察+专项训练 | `/tests/review` `/quizzes/wrong-questions/insights/` | ✅ |
| 个性化模拟卷（错题驱动 PDF） | `/mock-exam` `/quizzes/personalized-mock-exams/` | ✅（dev 库仅 1 条） |
| 收藏/掌握 toggle | `/quizzes/favorite|mastered/toggle/` | ✅ |
| 作业（学生提交+AI 批改） | `/my-assignments` `/api/assignments/*` | ✅ |
| 课程中心/视频课（字幕+AI 大纲+进度） | `/courses` `/course/:id` `/api/courses/*` | ✅ 最活跃模块（8-13 日持续提交） |
| 学习计划（AI 生成+任务管理） | `/plan` `/api/ai/plans/*` | ✅ |
| 练习会话（小宇内发起） | `/xiaoyu/practice/:id` `/api/ai/practice/*` | ✅ |
| 成绩报告卡（雷达图+PDF） | `/report-card` `/users/me/report-card/*` | ✅ |
| 知识图谱（graph/list 双视图+节点训练） | `/knowledge-map` | ✅（KNOWLEDGE_GRAPH 开关） |
| 成就墙+每日签到 | `/achievements` `/users/*/checkin/` `/users/achievements/` | ✅ |
| 深度文章 | `/articles` `/api/articles/` | ✅（43 篇） |

### 教师/机构链路（B 端核心）

| 功能 | 路由/入口 | 状态 |
|---|---|---|
| 工作台（命题官 Agent+ARC 管线） | `/workbench` `/api/ai/chat/stream/` | ✅ |
| 出题管线三套（ARC/批量/单题） | `/quizzes/admin/{adversarial|bulk}-pipeline/` 等 | ✅ |
| 管线任务中心（审核/重试/入库存题） | `/quizzes/admin/pipeline-*` `/quizzes/workbench/*` | ✅ |
| 题库管理+CSV 导入+结构化导出 | `/questions` `/quizzes/admin/questions|import-csv|export-structured/` | ✅（导入/导出无前端） |
| 作业布置+逐份 AI 批改 | `/teacher-assignments` | ✅ |
| 纸质试卷（上传 PDF→学生作答→批改回传） | `/quizzes/teacher-exams/*` | ✅ |
| 在线考试管理 | `/quizzes/online-exams/*` | ⚠️ 管理侧 5 端点无前端 |
| 教学计划（周计划+AI 生成+PDF） | `/lesson-plans` `/courses/teaching-plans/*` | ✅（TEACHING_PLANS 开关） |
| 班级管理+成绩册 | `/institution/students` `/gradebook` | ✅ |
| 机构仪表盘（班级表现/流失风险/商业指标） | `/institution` | ✅ |
| 机构管理（自助设置/SSO/方向/优惠券） | `/institution/admin` | ✅ |
| 学员管理（批量/重置密码/导出） | `/users/institution/me/students/*` | ✅ |
| 邀请链接+审批流 | `/users/institution/me/invites|join-requests/` | ✅ |
| 子校区 CRUD+上下文切换 | `/users/institution/me/children/*` | ⚠️ 前端页面孤儿（CampusManagement 无路由） |
| 内容市场（题库/课程上架购买） | `/marketplace` `/quizzes/marketplace/*` | ⚠️ 学生被 RequireInstitution 重定向，Browse 不可达 |
| API 开放平台（密钥+HMAC 文档+外部 API） | `/api-platform` `/users/institution/me/api-keys/` `/api/v1/*` | ✅（API_ACCESS 开关） |
| 审计日志 | `/institution/audit-logs` | ✅ |
| 站内通知+广播 | `/api/notifications/*` | ✅ |

### 平台/超管

| 功能 | 路由/入口 | 状态 |
|---|---|---|
| 平台仪表盘（DAU/MAU/留存/营收） | `/platform` `/users/admin/analytics/dashboard|revenue/` | ✅ |
| BI 分析（错题热力/完播率/会员率） | `/users/admin/bi/` | ✅ 与 dashboard 数据重叠 |
| 分析导出 CSV | `/users/admin/analytics/export/` | ✅ |
| 全局用户管理+标签+权限组 | `/users/admin/superusers/users/` `/admin/user-tags|permission-groups/` | ✅ |
| 方案邀请码生成 | `/invite-codes` `/users/admin/plan-invite-codes/` | ✅ |
| Prompt 模板管理（文件级+回滚） | `/prompt-templates` `/quizzes/admin/prompt-templates/*` | ✅ |
| Bot 管理（学生/规划师/命题官） | `/api/ai/bots/` | ✅ |
| NPS 问卷 | `/users/nps/*` | ✅（dev 库 2 条） |

### 辅助模块（完整实现，数据少）

| 功能 | 路由/入口 | dev 库数据 | 5 月以来提交 |
|---|---|---|---|
| AI 模拟面试（简历调优+专业面+雷达评分） | backend `interviews/` 全模块 | 8 会话/6 轮 | 12 次 |
| 在线自习室（番茄钟 WS+聊天+Giphy） | `/study` `api/study/*` | 1 会话/87 消息 | 10 次 |
| 答疑社区（提问/回答/点赞/关注） | `/qa` `api/qa/*` | 6 问题/10 回答 | 13 次 |
| 课程专辑 | `/api/courses/albums/*` | 6 专辑 | — |
| 启动资料 | `/api/courses/startup-materials/*` | 8 条 | — |
| 推荐码系统（点击/注册/购买计数） | `/payments/referral/` | — | — |

### 基础设施（不可删）

- `ai_engine/`（模型路由/熔断/可观测/工具沙箱）、`core/`（Cookie 认证/加密字段/限流/文件校验/OSS/邮件/审计）
- 认证全链路（验证码注册/登录/SSO/注销/数据导出——个保法合规）
- 支付（订单/优惠券/网关路由/webhook——虽然订阅半成品，一次性支付是收入命脉）
- Celery 基建（beat 任务：Memorix 扩散/IRT/MUTAR/会员到期/平台聚合）

## 二、删除候选清单（下一步逐项分析）

### Tier 1 — 孤儿代码（无路由/无引用，删除零功能影响）

**前端**
1. `components/interviews/` 整目录（InterviewLobby/ResumeTuner/SessionChat/SessionList/RadarChart）— 全仓库无 import、无路由
2. `pages/CampusManagement.tsx`（11.9K）— 无路由无引用，功能被 InstitutionDashboard 聚合视图部分替代
3. `pages/PlatformAnalytics.tsx`（2.5K）— 无路由；连带 `maintenance/AnalyticsPanel.tsx`（14.4K）失去唯一入口
4. `maintenance/QuizSection.tsx`（15.5K）+ `QuestionBankPanel.tsx`（10.6K）— 无引用，被 TeacherQuestions/TeacherAssignments 取代
5. `maintenance/JoinRequestSection.tsx`（4.4K）— 无引用
6. 薄包装页 ×4（CourseManage 133B / ArticleManage 137B / TeacherKnowledgeTree 329B / PromptTemplatesAdmin 663B）— 可并入 Maintenance tab 或保留（非删除对象，路由在用）

**后端**
7. `quizzes/graph_views.py` — 未挂载任何 url
8. `users/models_commercial_new.py` — 与 models_commercial.py 几乎相同，从未 import
9. `study_room/models.py: StudyTask` — 仅 admin/serializer 引用，无业务逻辑

### Tier 2 — 孤立端点（后端完整实现，前端零调用）

| # | 端点 | 说明 |
|---|---|---|
| 10 | **interviews 全模块后端**（6 路由+WS consumer+services 9.9K） | 前端 components/interviews 孤儿 → 整个 AI 模拟面试对学生/教师实际不可达 |
| 11 | `quizzes/online-exams/create|update|questions|result|results` | 管理侧 5 端点，仅 start/submit 被学生用 |
| 12 | `quizzes/templates/`（ExamTemplate 出题模板 CRUD） | 前端无调用 |
| 13 | `quizzes/ai-parse-raw-text/` + `import-csv/` + `admin/export-structured/` | 无前端（CSV 导入/结构化导出功能不可达） |
| 14 | `quizzes/health-trend|health-detail` | 学情健康度，无前端 |
| 15 | `quizzes/field/diagnose|subjects|invalidate-cache` | Field 引擎仅内部 Celery 用 |
| 16 | `quizzes/knowledge-edges/llm-analyze` + `review/` + `review/action/` | 教师端边审核功能无前端 |
| 17 | `quizzes/workbench/tasks/`（列表端点） | 仅 status 轮询被用 |
| 18 | `/ai/workbench/dashboard/` `/ai/grading/grade/` `/ai/memory/profile|due|stats/` `/ai/reset/` `/ai/conversations/` `/ai/memories/*` | 判分实际走 bot 对话（GradingPreviewCard 调 /ai/chat/），专用端点被绕过 |
| 19 | `users/heartbeat/` | 自习室用 WS 心跳 |
| 20 | `users/institutions/validate-invite-code/` | 无前端 |
| 21 | `users/institution/me/payment-config/` | 写入后**无任何消费方**（payments 网关从不读取） |
| 22 | `users/institution/me/students/<pk>/report-card/` | 教师看学生报告，前端只有学生自查版 |
| 23 | `users/me/class-courses/` | 学生侧班级课程 |
| 24 | `users/admin/feedback/` + `core/admin/feedback/` | 两套管理反馈 API 均无前端 |
| 25 | `interviews/sessions/<id>/` GET + `text-turn/`（非流式） | 前端只用 stream 版 |
| 26 | `notifications/announcements/` 整套 | 公告系统前端零调用 |
| 27 | `payments/invoices/` + `subscriptions/` + `subscriptions/me/` | 订阅仅 stub 网关可用 |
| 28 | notifications WS consumer + interviews WS consumer | 前端无连接 |
| 29 | `payments/orders/<id>/simulate/` | 仅 DEBUG 注册 |

### Tier 3 — 疑似废弃/半成品

30. 英语口语面试类型 — 后端硬编码「语音模型未接入」
31. 订阅体系 — 生产无可用网关实现（仅 stub）
32. 公告系统（announcements）— 完整实现但前端零调用（同 26）
33. `quizzes/services/weekly_report.py` / `study_plan_builder.py` / `review_insights.py` / `knowledge_graph_traversal.py` — 无调用点或仅测试引用
34. ASR dummy 提供方、`debug_title_task` 调试命令

### Tier 4 — 重叠实现（需决策合并，非简单删除）

35. 判分三套：`ai_workflow.run_exam_grading`（主用）/ `QuizAITaskService.grade_question` / `QuestionGenerator.grade_question`
36. 文本解析出题两套：`QuestionGenerator.parse_questions_from_text` vs `QuizAITaskService.parse_questions_from_text`
37. 学习计划两处：ai_assistant.StudyPlan 模型 vs quizzes/study_plan_builder.py + diagnostic_service.build_study_plan
38. 出题入口三套：ARC / Bulk / single_generate_pipeline
39. 记忆三层：AgentMemory（DB）/ mem0 语义记忆 / Experience 经验库
40. task_dispatcher 双份（quizzes 与 courses 各一份）
41. 反馈三套：`/ai/feedback/` `/users/feedback/` + 管理侧两套（users/core）
42. 平台分析四端点：`/admin/bi/` `/admin/analytics/dashboard/` `/admin/revenue/` `/admin/analytics/export/` — BI 与 dashboard 高度重叠
43. 会话标题生成双路径：SSE 内联 vs Celery 异步

### Tier 5 — 低使用完整功能（产品决策级）

44. AI 模拟面试（数据 8 会话 + 前端不可达 → 大概率 Tier 2 处理）
45. 在线自习室（1 会话，10 次提交）
46. 答疑社区（6 问题）
47. 深度文章（43 篇，6-21 后无提交）
48. Marketplace 学生 Browse（路由 gating 矛盾，学生实际不可达）
49. 个性化模拟卷（dev 库 1 条）
50. 子校区体系（后端完整，前端页面孤儿 → Tier 1）

### 附带发现的缺陷（盘点副产品，非删除对象）

- `AccountDeleteView` 导入不存在的 `StudyMessage` → 注销流程 ImportError（潜在线上 bug）
- `ActivateMembershipView` 个人会员激活场景邀请码可能永不被消耗
- XiaoYu 会话侧栏 onDeleteSession/onLoadSession 空实现
- Checkout 默认 gateway 为 'stub'
- `views_question.py: _get_descendant_kp_ids` 标注 deprecated 仍在用

## 三、证据附录

### dev 库数据（sqlite，125 表）

- 数据极少：interviews 8 会话 / study_room 1 会话 / faq 6 问题 / personalized_mockexam 1 / teaching_plan 1 / nps 2
- 数据正常：questions 375 / kp 10265 / edges 9715 / quizattempt 50 / exam 75 / chat 618 / memory 409

### git 活跃度（2026-05-01 以来提交数）

- 活跃（50）：quizzes / courses / users / ai_assistant / ai_engine
- 中等（31）：core；低（10-17）：notifications / payments / faq_system / interviews / articles / study_room
