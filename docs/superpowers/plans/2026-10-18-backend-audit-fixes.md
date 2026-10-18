# Backend audit fixes implementation plan

**Goal:** 修复两轮静态审计的 19 个 bug，并落实 6 项性能改进。

**Architecture:** 保持既有 Django/DRF/Channels/Celery 结构，在业务入口固定内容边界；用短事务和持久化结果保证学习数据原子更新；外部 AI/文件处理在数据库写事务外执行。

**Spec:** 本聊天两轮审计报告 B01–B19、P01–P06。

## Constraints

- 保留已有对话置顶、课程管理等脏改动；只修改必要代码。
- 用户明确要求不测试：不新增或执行测试，仅语法和 diff 静态检查。
- 不提交、不推送、不部署、不操作真实账号或生产数据。

## Tasks

- [x] Learning: B01–B04、P03。交卷校验范围，不提前写复习时间；按用户锁持久化优化器状态并写 ReviewLog；移除逐次 worker 探测。
- [x] Courses: B10、B14、B15、B19、P01、P04、P05。统一受管归属；批量加载列表；保留旧文件及旧转录直到新内容完整保存；流式存储、单进程分段。
- [x] Boundaries and reliability: B08、B11、B13、B17、B18、P02、P06。媒体/答疑外键鉴权；自习状态完整持久化和异步隔离；支付后续补偿、Token 轮换串行；答疑兼容分页及批量作者状态。
- [x] Practice and infrastructure: B05、B06、B07、B09、B12、B16。答案指纹缓存；批改先完成再短事务写入；持久化可重放提交结果；修复装饰器、原生 Redis 连接和失联任务回收。
- [x] Integration: 核对全部审计编号、迁移依赖、前端响应兼容；语法与 diff 检查；独立静态代码复核；记录未运行测试及部署边界。

## Shared interface

`quizzes.models.PracticeSubmission`: user FK、session_id UUID unique、answers_hash CharField(64)、response JSONField、created_at。只记录完成提交，与学习写入同事务提交；重复提交重放结果，答案不同则拒绝。

`MemorixService.update_status(user_id, status, rating)` 保持签名，自己锁用户及最新 status、保存优化器状态和 ReviewLog；调用方可在同一用户锁事务内安全嵌套调用。

## Review focus

- 新答案不得复用旧批改；服务失败不得写成答错。
- worker 重投和重复交卷不得重复应用学习结果。
- 内容外键及媒体对象必须在明确范围内；公开图片保持可访问。
- 外部 AI/OSS 调用失败必须保留已提交的旧内容。
- 新列表响应必须与当前前端读取方式匹配。

## Progress

- 已保存初始脏差异到 `/tmp/unimind-audit-fix-initial.diff`，用于区分并行变更。

- 两轮审计项已完成本地代码修复，并对学习事务、课程并发替换、媒体鉴权、答疑分页兼容进行了交叉静态复核。
- 静态检查：46 个变更/新增 Python 文件 AST 解析通过；QASystem.tsx 语法解析通过；git diff --check 通过。
- 新增 quizzes/0054、courses/0028 两个迁移，未执行；未运行测试、提交、推送或部署。
- 已知边界与逐项结果见 docs/tech/backend-audit-fixes-2026-10-18.md。
