# DSH 评分任务迁移实施计划

> 使用 superpowers:executing-plans 连续执行，一次独立复核，只做必要冒烟。

**Goal:** 把既有主观评分与客观题解析的模型调用迁入服务端受控 DSH，保留现有作答权限、确定性客观评分、评分归一化和 PracticeSubmission 幂等落库。

**Architecture:** AIService.structured_output 对两个固定 operation 在默认关闭开关开启时路由至 DSH。独立 TS collector 插件只注册一个 schema 工具，成功提交后 concludeTurn，不挂学习工具/记忆/笔记或学生回调。SDK 临时 home 结束删除；Django 校验唯一成功结构化结果再交回原业务处理。失败不回旧 AIEngine、不换评分模型。

**Tech Stack:** 既有 Django/AIService/QuizAITaskService、DSH0.2.1rc2、TS Cordis、现有 jsonschema。

**Spec:** 完整规划 v1.2 第七、十、十一、十二及 M0 主观题/幂等验证。

## Constraints / rulings

- UNIMIND_DSH_GRADING_ENABLED 默认 false，不修改实际 .env，不正式切流或发布。
- 固定 quizzes.grade_question → pro/2500 tokens，quizzes.objective_analysis → fast/2000 tokens；最多1次模型请求，不自动重试/fallback。沿用当前对应模型配置，任务预算独立于聊天周次数，不新增收费规则。
- 学生答案只作为不可信业务数据，模型无额外工具、文件、终端、学生记忆和业务凭据。临时 home/输入不长期保存；审计只记任务标签/模型/状态/用量，不记作答内容。
- schema 复用现有定义；DSH 副本将 error_analysis 的可空类型与既有提示词约定对齐。Django 校验完整 Schema 与有限数字，原评分上限/客观确定性比对仍执行。
- 前端评分提交按题数提供每题 130 秒等待，禁用该写操作的自动网络重试；开启 DSH 时预批改 Celery 时限 150/180 秒，关闭时维持原 60/90 秒。任何父任务中断均先终止 SDK 进程组再清理临时目录。
- 现有 PracticeSubmission 是业务提交事实，本批不新增账本/migration；失败不得写成绩或 Memorix，重复提交不重复计分。评分模型质量未校准前不得宣称正式教学有效。

## Review Focus

- 非法/缺失/多次 collector、非完成 SDK、NaN/坏 Schema 不能落分，失败不走旧模型。
- 固定任务、模型、schema/工具名均由服务端选择，作答不能新增工具或改变来源/级别。
- 临时状态/凭据不泄漏，超时整个进程组终止，SDK 槽位与聊天共用上限。
- 客观分数仍由答案比较决定；主观分数沿用原上限与类型处理。
- 重复/跨用户/跨范围作答保持既有准入，失败/重复不重复落成绩、更新 Memorix。

## Task 1: DSH 结构化评分任务

Files: dsh/structured_plugin.ts、structured.patch.yml、structured_worker.py、gateway.py、worker.py；backend/ai_assistant/services/dsh_tasks.py；AIService、settings。

- [x] 定向冒烟先验证默认旧路径、开启后不触发旧模型、失败不 fallback、无效结果拒绝。
- [x] 实现固定任务模型预算、隔离 SDK 与唯一 collector，复用原评分提示词/Schema/处理。
- [x] 严格 TS 检查与必要后端冒烟。

## Task 2: 实际主观作答闭环

Files: dsh/smoke.py、site_smoke.py；backend/ai_assistant/tests/test_dsh_grading_smoke.py。

- [x] 合成主观题/评分点，fixture 根据唯一 collector 输出结构化分项结果，真实 SDK concludeTurn。
- [x] 通过现有 practice/start/submit 验证首次评分/成绩记录、同请求重放、他人拒绝、失败不落库；客观分数确定性冒烟。
- [x] 一次独立复核及必要修复，文档记录与本地提交；继续明确真实模型质量和正式切流门槛。


## 实施判断与验收

- SDK 的 collector 原生 concludeTurn 已验证：主观任务一次 pro 请求返回 8/10；不依赖 assistant 最终自然语言正文。客观解析另走 fast，分数仍由原答案比较决定。两个任务均为一次模型请求硬上限，评分 profile 显式关闭 llm-retry，不做供应商重试或模型 fallback。
- 实际 SDK 首轮失败定位为不支持 minimum/maximum 与 type 数组；安装版 stderr 经本地任务凭据替换后确认原因。发送给 SDK 的评级使用等价 enum，可空错因使用 oneOf，Django 仍按完整 Schema 与有限数值校验。定向检查先失败后通过。
- 实际 ASGI/临时数据库经既有 practice/start/submit：题目及会话属当前用户；8/10 只落一条 GradingRecord 和 PracticeSubmission；顺序重复提交不增加模型调用；他人拒绝；503 暂态错误只尝试一次且不写成绩；客观错选为 0。聊天周次数保持 [3,1]，评分不冒充第二次聊天扣费。
- 修复旧 PracticeSession 挂载时再次抽新题却提交原 route ID 的问题：新增当前用户的 GET practice/session/<id>/，返回当前会话题目，复核内容范围，恢复本人已完成的练习结果；整卷考试事实不能混作此接口的练习结果。前端显示逐题得分/反馈，区分得分率与达标题数，刷新恢复不伪造用时。API 归属/范围/结果类型检查先失败后通过。
- Cookie 冷启动在根身份查询完成、Store 尚未同步时曾被子路由提前送去登录。RootRedirect 现在等待一致身份后挂载子页面；合成 Cookie 加空客户端快照的浏览器路径已复现并验证。
- 10 项站点/评分聚合冒烟、严格 TS 检查、前端构建通过。实际合成浏览器完成提交、8/10 反馈、刷新恢复；截图 .m0-state/m0-dsh-grading-proof.png。

## 独立复核与边界

一次独立复核发现三项 P2：默认 llm-retry、关闭开关时改变旧客观模型路由、目录权限异常未映射。分别通过本地 503 请求次数、合成模型环境变量和 mkdir 权限异常的检查 RED→GREEN 修复；没有追加复审。没有延期的小项。临时 SDK 目录/槽位、超时与父中断清理分别有源码及 mock 验证；缺失/多次 collector 的拒绝经源码核查，未宣称这些都已通过原生故障注入。

Ruling: 默认关闭开关，保持旧正式入口与旧模型选择；新增 fast 选择只在 DSH adapter 内。代价是生产仍使用既有路径，须真实校准后再开通。复用原评分规则和幂等事务，不在本批重建业务账本；顺序重放已验收，跨节点并发和批量容量不据此推定完成。Cookie 时序与原会话读取属于本批真实作答必要修复，未重构其他认证流程。

2026 年 10 月 26 日 19:59（上海）只读查询用户授权的 DeepSeek 官方来源，HTTP 200、is_available=false；未调用真实生成。本批证明技术链路，不能证明真实主观题评分质量。评分校准、正式题库/人工复核、额度金额及生产交付仍按完整规划处理。

## 2026 年 10 月 27 日真实模型练习冒烟

本机原小宇页面现使用已授权的 DeepSeek 官方配置，保留两个合成学生及隔离 SQLite；Redis 独立进程，Celery 使用进程内 eager/memory，未连接生产队列。原协议夹具仍只证明协议，不用于自然问法验收。

真实问法调用 get_practice_questions 后暴露两处问题：夹具误写了不受支持的 single_choice，已改为题库标准 objective；原页面提交选项正文、评分端按答案字母比对，正确选择被判 0 分。评分入口现使用既有 normalize_options/normalize_objective_answer，把正文与答案统一为字母后再交给解析和确定性评分；保存的原作答不改，模型仍不能决定客观题分数。

定向冒烟先复现失败，再验证列表/字典选项、正文/字母、错选/空答，以及模型错误分数无法覆盖确定性结论。浏览器用真实模型新抽合成题，选择 A 并提交后显示 10/10 和一致反馈；截图 .m0-state/m0-real-deepseek-practice-proof.png。隔离 SQLite 同时读写曾触发锁冲突，本机预览采用 IMMEDIATE 事务和等待超时后提交成功；这不代表生产并发验收。上述仅是一道客观题链路，未完成真实主观题校准或生产发布。
