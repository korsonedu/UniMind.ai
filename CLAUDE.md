# CLAUDE.md — UniMind.ai

科晟教育 Agent 学习平台。当前入口与业务边界以 `README.md`、`admin-extension/README.md` 和 `docs/tech/architecture/SINGLE_PLATFORM_TRANSITION.md` 为准。本地清理不等于生产发布。

## Agent 架构

| 运行时类型 | 入口与职责 |
| --- | --- |
| `planner`（小宇） | 学习端 `/xiaoyu`；普通问答、学习辅助、可视化与本人会话 |
| `exam_generator` | Directus 管理扩展的教学生产；生成、审核、学情与通知，不能作为学生端可选 Bot |

运行时由 BotRegistry、执行器、`chat_service.py`、`ai_engine/tool_run.py` 和模型工具调用组成。两类 Agent 启用意图预筛选；权限和参数校验由服务端执行。当前聊天服务传入的小宇工具轮次上限为 12，教学生产为 8；以实际调用点为准，不能把引擎默认 5 轮当成全部入口上限。

MUTAR 的用户反馈指 Agent 回复赞踩。右下角产品反馈和 NPS 满意度问卷已在本地退出，两者与 Agent 赞踩分别管理。

## 硬边界

- **禁止在服务器上直接改代码**。所有修改本地 → git commit → push → 服务器 `git pull`。`.env` 是唯一例外。
- **不要删除/重建 migration 文件**。始终 `python manage.py makemigrations` 追加新 migration。
- **不要改 `backend/ai_service.py`**（8 行 shim，纯 re-export）。新增 AI 能力去 `backend/ai_engine/` 或对应 app 的 `services/`。
- **Prompt 模板唯一来源**：`backend/prompts/`（统一目录），不再用 `backend/core/prompts/` 或 app 内 `templates/` 散落。
- **前端路由**：所有页面在 `frontend/src/App.tsx` 注册，权限 gating 在路由层或 sidebar 层处理。
- **不要裸用 `float('inf')`** 表示无限——用具体大数（如 999999），避免 JSON 序列化问题。
- **Serializer 字段必须显式声明**：禁止 `fields = '__all__'`，所有字段显式列出，防止未来新增 model 字段被自动暴露。
- **敏感字段加密**：支付密钥等用 `core.fields.EncryptedCharField` / `EncryptedTextField`（Fernet AES），加密密钥通过 `ENCRYPTION_KEY` 环境变量设置（默认从 SECRET_KEY 派生）。
- **Cookie 认证为主**：REST API 用 `core.authentication.CookieTokenAuthentication`（先读 httpOnly cookie，fallback Authorization header），前端 `api.ts` 设 `withCredentials:true`。WebSocket 仅 Cookie 认证（connect 时校验，未认证直接 close 4001），前端不存 token 到 localStorage。
- **单平台内容范围**：内容查询通过 `core.utils.apply_institution_filter` 等既有服务使用显式 `UNIMIND_CONTENT_INSTITUTION_ID`。正整数对应既有内容机构，`global` 对应历史全局分区；未配置拒绝访问。禁止按请求者历史机构猜测归属、扩大到全站或移除过滤。
- **当前权限模型**：学习能力依据 `users.learning.is_course_student` 和逐人功能开关；后台只允许两名 Directus 映射管理员，须同时启用、具有 staff/superuser 身份并无机构归属。历史 owner/teacher 不再授予管理权限。使用 `users.permissions` 的 helper 或 DRF 权限类；`get_effective_plan_for_user` 仅保留历史方案兼容，不能替代当前学习授权。详见 `docs/tech/architecture/SINGLE_PLATFORM_TRANSITION.md`。
- **只做被要求的事**：严格按指令执行，不擅自追加额外改动。如果认为某件额外的事确实有用，先询问，不得自行决定。

## 项目结构速查

```
UniMindCode/                  ← git 仓库根目录
├── backend/
│   ├── school_system/          # Django 配置 (settings, urls, celery, asgi, middleware)
│   ├── ai_engine/              # AI 引擎 (路由、熔断、可观测性、模型配置、工具权限沙箱)
│   ├── ai_assistant/           # Agent 运行时（Bot/BotRegistry/ToolExecutor/记忆系统/mem0 语义记忆，2 个自治 Agent）
│   │   ├── bot_registry.py     #   Bot 注册表：bot_type → (Executor, tools, prompt_dir)
│   │   ├── services/           #   chat_dispatch, memory_analyzer, trajectory_recorder, prompt_adapter
│   │   └── tasks.py            #   Celery tasks: record_trajectory_async, precompute_user_profile
│   ├── quizzes/                # 核心刷题
│   │   ├── services/           #   出题管线、评分、Memorix 调度
│   │   ├── memorix/            #   Memorix 自进化记忆调度算法
│   │   ├── management/         #   import_knowledge_tree, seed_questions/demo
│   │   └── views_*.py          #   views 已拆分为 6 个文件（原始 views.py 已删除）
│   ├── users/                  # 用户/会员/RBAC/ELO/机构管理
│   │   └── services/           #   会员服务 (membership.py)
│   ├── courses/                # 课程/专辑/AI大纲/ASR/OSS分片直传
│   ├── notes/                  # 个人笔记与 Agent 参考
│   ├── backoffice/             # 管理桥接与异步教学任务
│   ├── articles/               # 深度文章
│   ├── study_room/             # 在线自习室
│   ├── faq_system/             # 答疑系统
│   ├── notifications/          # 站内通知
│   ├── payments/               # 支付网关 (gateway_router 统一分发: stub/stripe/alipay/wechat/airwallex)
│   ├── core/                   # 基础设施 (加密字段、Cookie认证、邮件、限流、文件校验、安全审计)
│   └── prompts/                # 统一 Prompt 模板目录
│       ├── quizzes/  ai_assistant/  courses/  pipeline/  grading/
│       └── ai_assistant/bots/  # Bot prompt（每个 bot 一个目录：system_prompt.txt + tool_guide.txt + personality.txt + intent_guide.txt）
│           ├── xiaoyu/           #   小宇学习教练
│           └── exam_generator/   #   工作台教研助手
├── frontend/
│   ├── src/pages/              # 学习端页面（旧管理页面已退出）
│   ├── src/components/         # 通用组件 + shadcn/ui
│   ├── src/lib/                # API 客户端、权限、hooks
│   └── src/store/              # Zustand 状态管理
├── admin-extension/            # Vue / Directus 管理扩展
├── docs/                       # 技术文档（架构、Memorix 论文、事故记录）
├── scripts/                    # 运维脚本（bootstrap, check, smoke）
└── Makefile                    # make backend-check / frontend-check / qa-smoke
```

## Django 业务应用

`ai_assistant` `quizzes` `users` `courses` `articles` `study_room` `faq_system` `notifications` `core` `payments` `notes` `backoffice`。`ai_engine` 是共享引擎模块，安装列表以 `school_system/settings.py` 为准。

## 关键路由

| 路径 | 说明 |
| --- | --- |
| `/` | 未登录首页；已登录进入 `/xiaoyu` |
| `/login`、`/register`、`/account-callback` | 学习端账号入口 |
| `/xiaoyu`、`/notes`、`/notes/:id` | 小宇与个人笔记 |
| `/courses`、`/course/:id` | 课程中心与课程工作区 |
| `/tests`、`/tests/session`、`/tests/review`、`/report-card` | 练习、错题与学习记录 |
| `/community`、`/qa`、`/study` | 答疑与自习室 |
| `/billing`、`/pricing`、`/checkout` | 我的服务、AI 加量目录与结算 |
| `/diagnostic`、`/achievements` | 诊断与成就，实际访问仍受服务端权限限制 |
| Directus `/admin/unimind-admin` | 教学与内容管理 |
| `/api/backoffice/operations/<operation>/` | 签名管理桥接，固定操作名 |
| `/api/ai/chat/`、`/api/ai/chat/stream/`、`/api/ai/history/` | 学习端对话与本人历史 |
| `/api/ai/feedback/` | Agent 回复赞踩，继续保留 |
| `/api/notes/` | 笔记、引用与绑定 API |
| `/api/users/learning/access/`、`/api/users/learning/catalog/` | 学员服务与 AI 加量目录 |
| `/api/users/admin/analytics/dashboard/`、`/api/users/admin/analytics/export/` | 管理分析与 CSV 导出，只保留 trends/events |
| `/api/payments/` | AI 加量订单及历史支付兼容 |
| `/api/legal/` | 内置或数据库法律文档 |
| `/health/` | Django 健康检查；生产核验须确认未命中 SPA 回退 |

旧 `/workbench`、`/management`、`/institution`、`/marketplace` 等学习端地址保留重定向。机构加入/邀请、套餐变更、API Key 和外部 API 等停用接口继续返回 410。`/join/:invite_slug` 的旧页面仍存在，但不能作为有效加入流程。

产品反馈与 NPS 提交/状态接口已从本地路由移除。`core.0007`、`core.0008` 和 `users.0075` 为本次清理生成的待执行迁移，尚未提交或部署。

## 环境变量速查

```bash
# 必填
LLM_API_KEY=sk-xxx              # LLM API key（当前: DeepSeek）
DJANGO_ENV=production|development
SECRET_KEY=<random-64-chars>
ALLOWED_HOSTS=domain.com

# 数据库
DB_ENGINE=django.db.backends.postgresql
DB_NAME=unimind  DB_USER=unimind  DB_PASSWORD=xxx  DB_HOST=localhost  DB_PORT=5432

# Redis（生产环境必须设密码：redis://:password@host:port/db）
REDIS_URL=redis://127.0.0.1:6379/0            # Celery/Channels 共用
CACHE_REDIS_URL=redis://127.0.0.1:6379/1      # Django 缓存用独立 db

# AI 模型（按任务路由见 ai_engine/config.py，hot-swap 只需改顶部两个常量）
# LLM_MODEL=                    # 全局覆盖（可选）

# 邮件 (Resend HTTP API)
EMAIL_BACKEND=core.email_service.ResendEmailBackend
RESEND_API_KEY=re_xxx

# 熔断器
AI_CB_FAILURE_THRESHOLD=5  AI_CB_RECOVERY_TIMEOUT=300  AI_CB_WINDOW_TIMEOUT=60

# Agent 记忆（mem0 语义记忆，默认关闭）
USE_MEM0=false                    # 启用 mem0 语义记忆（需 pgvector 扩展）
AI_EMBEDDING_MODEL=Qwen/Qwen3-Embedding-0.6B  # config.py 默认值
AI_EMBEDDING_BASE_URL=http://127.0.0.1:8012/v1  # 需另行部署对应嵌入服务
AI_EMBEDDING_DIMENSIONS=1024

# 其他
AI_BULK_GENERATE_MAX_PER_REQUEST=3  AI_BULK_GENERATE_CONCURRENCY=4
ELO_K_FACTOR=32  USE_MEMORIX=false  ONLINE_USER_ACTIVE_WINDOW_SECONDS=300
ENCRYPTION_KEY=xxx                # 加密密钥（可选，默认 SECRET_KEY 派生），用于 EncryptedCharField/EncryptedTextField

# 阿里云 OSS 存储（可选，配置后文件存储到 OSS）
OSS_ACCESS_KEY_ID=xxx             # 阿里云 AccessKey ID
OSS_ACCESS_KEY_SECRET=xxx         # 阿里云 AccessKey Secret
OSS_BUCKET_NAME=unimind-courses   # OSS Bucket 名称
OSS_ENDPOINT=oss-cn-beijing.aliyuncs.com  # OSS 访问域名
```

## 常用命令

```bash
# 开发
cd backend && python manage.py runserver
cd frontend && npm run dev
celery -A school_system worker -l info

# 检查
make backend-check     # python manage.py check + makemigrations --check --dry-run
make frontend-check    # npx tsc -b && vite build
make qa-smoke          # API 冒烟测试
make full-check        # 全部检查
make backup            # pg_dump 压缩备份数据库（自动清理 30 天前）

# 知识树导入（全局，示例）
python manage.py import_knowledge_tree backend/knowledge_trees/金融431.md --global --subject=金融431 --force
python manage.py import_knowledge_tree backend/knowledge_trees/高中数学.md --global --subject=高中数学 --force
python manage.py import_knowledge_tree backend/knowledge_trees/高中物理.md --global --subject=高中物理 --force
# AI 生成新学科知识树
python manage.py generate_knowledge_tree --subject=高中数学
# 批量导入所有预设
for f in backend/knowledge_trees/*.md; do subject=$(basename "$f" .md); python manage.py import_knowledge_tree "$f" --global --subject="$subject" --force; done

# Bot 种子
python manage.py seed_exam_agent                # 创建/更新工作台 Bot
python manage.py seed_xiaoyu                    # 创建/更新小宇学习规划 Bot

# 管理接入
# 按 admin-extension/README.md 核对两人映射与内容归属，不批量重写历史机构。

# Migration
python manage.py makemigrations && python manage.py migrate

# 生产部署（服务器上执行）
cd /opt/unimind && git pull
cd frontend && npm run build
sudo systemctl restart unimind.service unimind-celery.service
sudo journalctl -u unimind.service -f

# systemd PATH 须知：unimind.service 的 PATH 必须包含 /usr/bin（ffmpeg 等系统工具），
# 不能只有 venv/bin。遇到 subprocess FileNotFoundError 先检查 systemctl cat unimind.service 的 Environment。
```

## AI 模型策略

模型路由集中在 `ai_engine/config.py`，顶部 `FALLBACK_FAST` / `FALLBACK_PRO` 两个常量是唯一默认值来源。换供应商只改此处 + `DEFAULT_BASE_URL`。分级覆盖：`AI_MODEL_FAST` / `AI_MODEL_PRO` env var。逐任务覆盖：`AI_MODEL_CHAT` / `AI_MODEL_GENERATE_AUTHOR` 等 env var。

| 任务 | 分级 | 思考 | 原因 |
|------|------|------|------|
| 小宇对话 | fast | — | 快速响应 |
| 出题 Author / AuthorRevise | fast | — | structured_output |
| 出题 Reviewer | pro | 开 | 深度逻辑检查，唯一显式开 thinking 的任务 |
| 出题 Classifier | fast | — | 审计+分类，structured_output |
| 批量出题 | fast | — | 以 config.py 的 quizzes.bulk_generate 映射为准 |
| 单管线审核 | pro | — | 深度审核 |
| 主观题判分 | pro | — | 结构化 JSON 输出 |
| 知识树生成 | pro | — | 高质量内容创作 |
| 解析/分类/Schema 修复 | fast | — | 轻量任务 |

> thinking + tool_choice 不冲突。thinking 开启时 tool calls 轮次必须回传 `reasoning_content`（`call_ai_with_tools` 已处理）。

## 深入文档

### 常用（顶层）

| 文档 | 内容 |
|------|------|
| `README.md` | 完整系统介绍、部署指南、环境变量全量参考 |
| `CHANGELOG.md` | 版本更新日志 |
| `admin-extension/README.md` | 当前后台接入、权限、内容与教学任务 |
| `docs/market/02-business-strategy.md` | 历史 B 端商业策略，不能作为当前定价 |
| `docs/market/03-marketing-materials.md` | 历史营销材料，重新对外使用前须核对 |
| `docs/market/04-user-manual.md` | 用户操作手册（场景化组织） |
| `docs/VERSIONING.md` | 版本管理规范（SemVer + Commit 规范 + 发布流程） |
| `docs/enterprise-deployment.md` | 历史企业版部署参考，不代表现行销售承诺 |

### 技术总参考

| 文档 | 内容 |
|------|------|
| `docs/tech/AI_SYSTEM_REFERENCE.md` | AI 系统完整参考（Schema 目录、Prompt 模板、模型路由表） |
| `docs/tech/architecture/SINGLE_PLATFORM_TRANSITION.md` | 当前单平台权限、内容边界与历史依赖 |
| `docs/tech/architecture/PERMISSION_ARCHITECTURE.md` | 历史四层权限设计，不作为现行授权规范 |

### 核心功能文档

| 文档 | 内容 |
|------|------|
| `docs/tech/features/AGENT_MEMORY.md` | Agent 记忆系统（提取/检索/注入机制 + 多租户 + Memorix 联动） |
| `docs/tech/features/EXAM_WORKBENCH.md` | 旧前台工作台历史参考，当前入口见管理扩展 README |
| `docs/tech/features/INTELLIGENT_TOOL_ROUTING.md` | 智能工具路由（SkillRouter 论文落地、impl_summary、意图预筛选） |
| `docs/tech/features/MEMORIX_WHITEPAPER.md` | Memorix 算法论文 |
| `docs/tech/features/MULTI_STEP_AGENT.md` | 多步可见 Agent（逐步气泡展示 + 自定义指标卡片） |
| `docs/tech/features/MUTAR_ENGINE.md` | MUTAR 自进化闭环 |
| `docs/tech/features/PLATFORM_ANALYTICS.md` | 平台数据分析（仅超管可见） |
| `docs/tech/features/archive/mock-interview-simulator.md` | AI 模拟面试（已删除，归档） |
| `docs/tech/features/WOW_MOMENT_TECH_FLOWS.md` | 核心功能技术流程图 |

### 归档

| 文档 | 内容 |
|------|------|
| `docs/tech/features/archive/` | 12 篇功能细节文档（熔断、判分、诊断、OSS 等），不常访问 |
| `docs/architecture/` | 学术论文（Field、Memorix、小宇架构）+ 研究探索 |
| `docs/design/` | 设计规范 + 产品原则 |
| `docs/tech/incidents/` | 历史事故记录 |
| `docs/tech/templates/` | 文档模板 |
| `backend/knowledge_trees/金融431_完整版.md` | 431 金融知识树（完整版） |

## Agent skills

### Domain docs

当前仓库无 `CONTEXT.md`。先读 `README.md`、本文件和单平台过渡清单；日期化设计、历史权限与研究文档不自动代表已实现或已发布。
