# 科晟单平台 Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans for integration. Steps use checkbox (`- [x]`) syntax for tracking. The parent CLAUDE.md requires independent modules to be dispatched in parallel. User authorization on 2026-10-18: “开始做吧”.

**Goal:** 将 UniMind 收敛为科晟课程交付平台，迁入全部现有教学生产能力，统一后台，落实手动学员分类、周额度和独立 AI 加量。

**Architecture:** 保留 Django 业务层、React 学习端及 Directus 的两名管理员桥接。新管理功能通过既有白名单操作接入；不复制数据库、不扩大管理员名单、不直接删除机构外键。未确认的额度和加量销售参数保持未配置，不能编造价格或静默售卖。

**Tech Stack:** Django / DRF / Celery；Vue 3 Directus extension；React / TypeScript。

**Spec:** `docs/superpowers/specs/2026-10-18-korson-single-platform-design.md`

## Global Constraints

- 在当前 checkout 实施，保留他人改动；本轮不推送、部署或执行生产迁移。
- 只做必要的冒烟、类型检查和构建，用户明确要求优先于技能默认的整套 TDD / full-check。
- 两个独立管理员，普通用户只有学生身份；课程学员是服务状态，不是管理角色。
- 教学生产能力全部迁入后再取舍，激活码、机构开户和课程在线销售按已确认规则退出。
- 不让购买 AI 次数改变学员身份或课程权限。
- 周恢复：采用上海时间自然周；手动切换暂不新增自动到期机制。该实现选择可调整。
- 未确认周次数、加量有效期、价格和包次数时保留配置缺失状态；已有历史记录不删除。

## Review Focus

- 非课程用户直接调用 API、工具或文件地址不能访问课程资源。
- 多个并发问答不能超额；失败、取消、同请求重试不重复扣次。
- 管理员能使用全部工作台能力，不受历史机构套餐限制；学生不能伪装管理员。
- 课程线下开通与 AI 加量订单相互独立，支付回调幂等，不把历史订单解释成新商品。
- 暂存机构归属期间不丢失现有题目、学习记录或 Memorix 参数，不暴露其他历史机构数据。

## Task 1: 迁入后台教学工作台与内容任务

**Ownership:** 独立 worker 负责 `backend/backoffice/teaching.py`、必要的新 Celery 任务文件、`admin-extension/src/Teaching.vue` 及其专属辅助文件。不修改共享 Workspace、bridge、backoffice/views、全局 style 或 users 模块。

**Interfaces:** 后端新模块导出 `READS` 和 `WRITES` 操作字典；Vue 默认组件接收 `{ api: Gateway, meta: Meta, view: 'workbench' | 'tasks' }`。共享注册由 Task 3 接入。

- [x] 读取现有工具、工作台、管线服务与模型，列出全部可用操作。
- [x] 复用既有业务服务提供对话、生成、人工审核入库、精修、进度、通知确认、学情与报告、内容浏览、批量生成及任务管理。耗时操作用既有异步任务或短请求轮询，不让 Directus 等待完整长流。
- [x] Vue 页面提供可实际操作的对话、题目面板及任务管理，转义用户和模型内容，历史按实际操作者隔离。
- [x] 覆盖后台内容归属、写确认和最小定向冒烟；不发真实通知、不调用付费模型做验证。

## Task 2: 周额度、学员状态、AI 加量及学生服务页

**Ownership:** 独立 worker 负责 `backend/users/models_learning.py`、`learning.py`、`views_learning.py`、对应新 migrations、必要的 users/models 导出、settings 新额度配置、payments 实现及其迁移、`ai_assistant/views.py` 与 `consumers.py` 的额度生命周期；React `Billing.tsx`、`Pricing.tsx`、`Checkout.tsx`、`types/learning.ts`。不修改 users/permissions、feature_access、backoffice/people 或共享后台 UI。

**Interfaces:** 提供 `is_course_student(user) -> bool` 和保留兼容签名的 `usage_info(user)`（至少 `used, limit, remaining, resets_at, configured`）；`reserve_ai_call` 与成功确认、失败取消释放；学员状态与周额度配置可以通过导出的管理操作注册接入。两名管理员无限。

- [x] 新增最小独立的手动学员状态与周使用数据，旧身份数据在未显式调整前保留兼容解释，不批量猜测历史学员。
- [x] 每周额度高低可设置但不编造默认数；历史月额度数据保留。加量商品与课程服务解绑，未确定销售规则时不上架。
- [x] 接通 polling / SSE / WS 的成功确认、失败取消释放与重试幂等，保留必要的并发约束。
- [x] 只允许 AI 加量新订单，保留历史订单与真实回调核对；停用课程销售和机构订阅新建。
- [x] “我的服务”、AI 加量及结算页改为周口径，取消激活表单、课程销售和虚假免费学习承诺。
- [x] 追加 migration，不运行生产迁移；执行额度边界、失败释放与支付幂等的最小冒烟。

## Task 3: 侧栏、学员管理、配置与共享注册

**Ownership:** 主 agent 负责共享 `admin-extension/src/Workspace.vue`、ModuleRoot、module/index、style、types、bridge、People；`backend/backoffice/views.py`、people.py；学习端导航名称与配置接入。

**Interfaces:** 合并 Task 1 的 `teaching.READS/WRITES` 和 Task 2 的明确管理接口；在根布局使用 Teaching 组件，不把业务逻辑复制进导航。

- [x] 一级入口放 Directus 导航区域或统一侧栏，并使用地址保存当前功能，支持刷新、前进后退。
- [x] 统一工具栏、分页、保存及错误反馈；加入教学工作台、内容任务、状态管理、AI 配置和订单必要入口。
- [x] 学员详情直接切换课程／非课程状态，写审计，不变更后台角色；展示并配置周额度与未上架的加量商品参数。
- [x] 对接新后台操作白名单及审计，保留两名操作者映射。
- [x] 运行 Vue 类型检查与构建。浏览器本地预览被客户端拦截、Directus 容器未启动，真实宿主界面检查未完成，单独保留交付限制。

## Task 4: 单平台访问与退出 B 端

**Ownership:** 主 agent 负责 `backend/users/permissions.py`、feature_access、views_institution、urls、旧激活入口；`backend/ai_engine/tool_permissions.py`、`ai_assistant/services/chat_dispatch.py`、chat_service 中的工具选择；核心内容筛选与必要的迁移盘点命令。

- [x] 学生能力按课程状态授予，非学员只有小宇问答；后端和前端读取同一规则，旧管理员能力不授予普通教师账号。
- [x] AI 工具按实际用户能力过滤，非学员不开放课程检索、诊断、练习等工具；管理员的工作台全量工具以内容归属为边界。
- [x] 关闭激活码、机构创建／加入／切换／角色升级、机构订阅等入口；保留历史数据及必要只读查询。
- [x] 将课程资源查询收敛到配置的科晟内容范围；保留机构字段作为过渡，提供只读依赖与历史机构盘点报告，不擅自合并或删除。
- [x] 对照所有 `institution` 依赖记录仍保留原因及后续数据迁移条件，不宣称已物理删除多租户结构。

## Task 5: 集成与交付

- [x] 合并各 worker 结果，检查共享接口和变更范围，修复实际集成问题。
- [x] Django check / migration drift，管理扩展与学习端类型检查、构建，以及与变更直接相关的冒烟。
- [x] 独立 reviewer 检查权限、计次、支付和完整迁移范围；修复重要问题。
- [x] 更新设计中的实现状态与迁移清单，报告未配置商业参数、未执行迁移、未部署及仍需数据核对的结构性清理。

## Execution ledger

- 2026-10-18：用户已明确授权开始。当前工作区干净，起点 `c559e76`。按当前 checkout 实施，无需再次询问是否开始。
- 2026-10-18：尚未收到具体额度与加量有效期答案；以显式未配置状态实现，不擅自确定商业承诺。优先完成独立且已确认的迁移。

- 2026-10-18：Task 1/2/3/4 本地实现已集成。两名映射管理员、手动学员状态、问答周额度及独立加量商品均已接通；Task 4 的数据库物理删除未执行，属于生产归属核对后的后续工作。
- 2026-10-18：独立审查发现并修复两项重要问题：进程中断后的占位泄漏、无历史机构的新课程学员无法进入教学流程。另修复一级导航草稿保护。
- 2026-10-18：Ruling：过期占位一小时后在用量查询、预留或完成时回收，旧 attempt 不再扣次；恢复时间不依赖定时任务。该策略若需支持超长请求，可后续补心跳，当前模型请求均受既有限时约束。
- 2026-10-18：Ruling：本地 Docker 守护进程未启动，组件预览地址被浏览器客户端拦截。未冒充真实 Directus UI 验证，也不启动生产或修改真实账号补测。
- 2026-10-18：QA 和自习室的内容写入改用配置的科晟内容范围，避免新课程学员无历史机构时写入后无法出现在同一列表。历史机构与学习记录保持原位。

- 2026-10-18：最终验证：Django check 无问题、makemigrations --check 无漂移；管理扩展 vue-tsc / build 与学习端 TypeScript / Vite build 通过；8项后台隔离冒烟、10项权限工具冒烟、独立的额度/支付/三传输模拟脚本通过。未真实收费、发通知、调用付费模型；真实 Directus UI 与 PostgreSQL 并发压测未执行。
- 2026-10-18：商业参数待配置：两类周次数、加量价格/次数/有效期。新商品默认不上架。两项 schema 迁移只在隔离测试库验证，未执行到用户现有库或生产。

- 2026-10-18：用户确认商业参数：非学员 20 次／周，学员 200 次／周；AI 加量仅一档，9.9 元／100 次、购买成功后 90 天有效，跨周保留、基础额度优先。追加 `users.0073_confirmed_ai_service_defaults`，初始化配置与上架商品，保留已有人工配置，不修改已售订单。此前待配置记录已由本次决策解决。未执行现有库或生产迁移。
- 2026-10-18：参数初始化冒烟通过：隔离库从 `users.0072` 空配置迁移至最新版本，验证 20/200 周额度、990 分/100 次/90 天商品、订单快照与实际发放有效期；重复初始化保留人工修改且无重复商品。Django check 与迁移漂移检查通过。
