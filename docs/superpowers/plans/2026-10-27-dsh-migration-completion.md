# DSH 剩余生成能力迁移

> 按 superpowers:executing-plans 在当前隔离 worktree 连续实施，仅必要冒烟；最后一次独立复核。

**Goal:** 完成现有生成能力的 DSH 接入，保留原业务流程、人工确认和可回退开关，明确新增需求与生产前置条件。

**Architecture:** 复用已有结构化 worker、TS collector 和临时网关。内部文本/结构化任务通过同一受限 collector；教研研究工具由短期 loopback 回调复用原执行器，学生凭据不参与。AIEngine 的生成入口按明确开关选择 DSH，开启后失败不落回旧供应商请求。

**Spec:** 完整规划第七、十、十四、十六节及用户“继续至完成”。用户已要求直接实施，不再等待方案确认。未授权生产切流、外部搜索采购和发布。

## 约束与判断

- 复用原 Django/React 产品，不创建另一套教师业务或客户端壳。
- DSH 教研开关覆盖现有 author/reviewer/revise/classifier、批量/配套出题、参考解析和后台聊天；新增生成总开关覆盖笔记理解、课程辅助、经验/画像等零散内部调用。默认均关闭，不改真实 .env。
- 原业务调用的 task/model 路由继续有效；网关硬限制单任务最多 8 次模型请求、8192 输出 tokens、65536 请求 bytes、每次最多 8 个工具；结构化无研究任务只有一次请求。保留已有专用评分/记忆/标题预算。
- 模型只可准备题目、通知及精修确认，不能自动入库、发送通知或修改笔记。后台每次工具回调复核管理员身份和内容范围；禁止任意 render_visual。
- 用户已确认首版暂不接外网搜索，只使用自有课程和题库；外网搜索移出当前交付范围，不把自有知识检索标成联网搜索。
- 正式留存期限、价格、首批年度和生产容量需要产品/真实运行证据，不能由代码改动宣称已完成；本轮提供迁移核对和可执行的本地验证，不擅自清理真实数据。

## Review Focus

- 已撤销管理员或内容范围变化后，原在途教研任务不应继续取数据或产生候选。
- 未注册、越界参数或未确认写工具不能通过回调执行。
- DSH 失败、collector 缺失/重复、无效 Schema 不能触发旧模型重试或半份入库。
- 工具发现和最终 collector 同时注册时，候选不得超过 8；嵌套 quick_generate 共用容量槽。
- 旧功能与入口必须有去向，默认关闭的兼容路径不能被误报为已经退役。

## Tasks

- [x] Task 1：扩展现有 worker/TS collector 支持内部文本、结构化及教研研究工具；定向验证 Schema、回调授权、预算与无旧模型 fallback。
- [x] Task 2：接入现有 AIEngine 公共入口和后台教研；核对文章查询等保留/退出能力；跑实际 SDK/隔离后台与真实模型必要冒烟。
- [x] Task 3：会话及旧功能核对、更新当前迁移表和启用说明；必要检查与一次独立复核，修复后完成本地提交。

## 验收命令

- backend：ACCOUNT_ENABLED=false ACCOUNT_RSA_KEY_PATH='' <现有 backend/.venv/bin/python> -m pytest ai_assistant/tests/test_dsh_generation_smoke.py ai_assistant/tests/test_dsh_teaching_smoke.py -q。
- runtime：.m0-venv/bin/python dsh/generation_smoke.py，使用 loopback 协议夹具验证真实 SDK，断言最终 collector、研究工具与候选上限。
- TypeScript：dsh/node_modules/.bin/tsc --noEmit -p dsh/tsconfig.json。
- 文档和变更：git diff --check；最终记录实际输出和未通过的门槛。

## 实施证据

- 13 项必要后端冒烟通过；原网关 7 项通过，DSH TypeScript 检查通过。
- 原生 SDK/隔离 Django 完成 Author 候选、Reviewer 研究回调、后台聊天工具发现及文本/数组输出：总计 8 次协议请求，每次最多 8 个工具，题库写入为 0。
- 真实 DeepSeek 官方一次 pipeline.author 请求生成一道合成考点的简答题候选，未入库。此证据不代表批量内容质量或真实主观评分已校准。
- SDK 评阅初始化时原生工具未注册，定位为输出 Schema 数值约束兼容问题；降低 wire Schema 后保留后端完整 Schema 校验，原生评阅/研究链路通过。
- 文章旧学生路由已经退出，保留后台 list_articles；没有注册会返回失效链接的学生搜索工具。明确退出三类自由写/展示工具及原文章入口，当前学生有效业务工具均已接入。
- 未新增未经确认的自动留存删除任务；用户已确认暂不接外网搜索，此项不再作为迁移待办。详见 docs/DSH_MIGRATION.md。

## 一次复核修复与最终结果

- P1 撤权覆盖：Reviewer 普通闭包及 quick/parse/ARC/bulk 现在沿用同一教研任务身份/范围检查；每次生成前后、研究回调、进度更新及候选持久化前复核。撤权聚合冒烟先失败，修复后不再调用模型、不保存候选。
- P2 回调清理：生成与嵌套请求共用截止时间，关闭回调设置取消状态，后续请求拒绝；子进程和网关采用同一截止时间。原嵌套边界先失败后通过，实际关闭回调的线程冒烟确认只启动首个请求并完成 join，没有留下下一批生成。
- 清点另发现 backfill_question_kp 直接模型请求，改为既有 AIService；mem0.add 总开关边界关闭旧提取，原温度参数传入服务端网关。直连/温度检查先失败后通过。
- 修复后 16 项相关后端冒烟通过，新增关闭回调与原后台两条确认链路另外 3 项通过；网关 7 项、原生 SDK 8 请求/最多 8 候选/零入库通过；先前 TS 检查通过，未改前端实现。
- 本机仅合成数据的原小宇页面启用生成总开关后，真实 DeepSeek 查询久期课程并显示课程卡片，保留原侧栏和输入区；截图 .m0-state/m0-migration-complete-proof.png。
- 无延期的 minor；未追加复审。保留当前分支与 worktree，本轮不合并主仓库、不 push、不生产切流。
