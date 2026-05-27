# CLAUDE.md — UniMind.ai

新一代智能教育基础设施（Agent-Native 学习操作系统）。Django 6.0 + React 19 + DeepSeek V4。

## Agent 架构

三个自治 AI Agent 共享统一运行时：

| Agent | bot_type | 工具数 | 职责 |
|-------|----------|--------|------|
| 小宇 | `planner` | 15+ | 学习规划，教练式对话，主动分析数据给建议 |
| 出题助手 | `exam_generator` | 5 专用 | 教研出题，背靠 4-Agent ARC 对抗管线 |
| AI 助教 | `assistant` | 6+ | 学生辅导，跨会话记忆，深度数据钩稽 |

运行时：`Bot → ToolExecutor → AIChatView → call_ai_with_tools`（最多 5 轮自主工具调用）。
新增 Agent 只需：Bot 记录 + ToolExecutor 子类 + 系统提示词。见 `ai_assistant/services/`。

## 硬边界

- **禁止在服务器上直接改代码**。所有修改本地 → git commit → push → 服务器 `git pull`。`.env` 是唯一例外。
- **不要删除/重建 migration 文件**。始终 `python manage.py makemigrations` 追加新 migration。
- **不要改 `backend/ai_service.py`**（8 行 shim，纯 re-export）。新增 AI 能力去 `backend/ai_engine/` 或对应 app 的 `services/`。
- **Prompt 模板唯一来源**：`backend/prompts/`（统一目录），不再用 `backend/core/prompts/` 或 app 内 `templates/` 散落。
- **前端路由**：所有页面在 `frontend/src/App.tsx` 注册，权限 gating 在路由层或 sidebar 层处理。
- **不要裸用 `float('inf')`** 表示无限——用具体大数（如 999999），避免 JSON 序列化问题。
- **Serializer 字段必须显式声明**：禁止 `fields = '__all__'`，所有字段显式列出，防止未来新增 model 字段被自动暴露。
- **敏感字段加密**：支付密钥等用 `core.fields.EncryptedCharField` / `EncryptedTextField`（Fernet AES），加密密钥通过 `ENCRYPTION_KEY` 环境变量设置（默认从 SECRET_KEY 派生）。
- **Token 认证优先 Cookie**：`core.authentication.CookieTokenAuthentication` 先读 httpOnly cookie，fallback 到 Authorization header。前端 `api.ts` 设 `withCredentials:true`。
- **只做被要求的事**：严格按指令执行，不擅自追加额外改动。如果认为某件额外的事确实有用，先询问，不得自行决定。

## 项目结构速查

```
UniMindCode/                  ← git 仓库根目录
├── backend/
│   ├── school_system/          # Django 配置 (settings, urls, celery, asgi, middleware)
│   ├── ai_engine/              # AI 引擎 (路由、熔断、可观测性、模型配置、工具权限沙箱)
│   ├── ai_assistant/           # Agent 运行时（Bot/ToolExecutor/记忆系统/mem0 语义记忆，3 个自治 Agent）
│   ├── quizzes/                # 核心刷题
│   │   ├── services/           #   出题管线、评分、解析、PDF
│   │   ├── memorix/            #   Memorix 自进化记忆调度算法
│   │   ├── management/         #   import_knowledge_tree, seed_questions/demo
│   │   └── views_*.py          #   views 已拆分为 6 个文件（原始 views.py 已删除）
│   ├── users/                  # 用户/会员/RBAC/ELO/机构管理
│   │   └── services/           #   会员服务 (membership.py)
│   ├── courses/                # 课程/专辑/AI大纲/ASR/分片上传
│   ├── articles/               # 深度文章
│   ├── interviews/             # AI 模拟面试
│   ├── study_room/             # 在线自习室
│   ├── faq_system/             # 答疑系统
│   ├── notifications/          # 站内通知
│   ├── payments/               # 支付网关 (Stripe/支付宝/微信)
│   ├── core/                   # 基础设施 (加密字段、Cookie认证、邮件、限流、文件校验、安全审计)
│   └── prompts/                # 统一 Prompt 模板目录
│       ├── quizzes/  ai_assistant/  courses/  pipeline/  grading/  interviews/
├── frontend/
│   ├── src/pages/              # 30+ 页面组件
│   ├── src/components/         # 通用组件 + shadcn/ui
│   ├── src/lib/                # API 客户端、权限、hooks
│   └── src/store/              # Zustand 状态管理
├── Brand/                      # 品牌素材、营销方案、产品介绍（非代码）
├── docs/                       # 技术文档（架构、Memorix 论文、事故记录）
├── scripts/                    # 运维脚本（bootstrap, check, smoke）
└── Makefile                    # make backend-check / frontend-check / qa-smoke
```

## Django Apps (11)

`ai_engine` `ai_assistant` `quizzes` `users` `courses` `articles` `interviews` `study_room` `faq_system` `notifications` `core`

## 关键路由

| 路径 | 说明 |
|------|------|
| `/` | Landing（未登录）/ HomeRedirect（已登录：学生未诊断→/diagnostic, 老师/机构主→/workbench, 其他→/courses） |
| `/login` `/register` | 邮箱验证码登录注册 |
| `/diagnostic` | 学生诊断测试（首次登录强制） |
| `/workbench` | AI 出题工作台 — 对话式 Agent（老师/机构主） |
| `/intro/:slug` | 机构公开首页（无需登录，公开访问） |
| `/management` | 管理后台（需管理员） |
| `/join/:invite_slug` | 邀请链接 → 种 cookie → 302 到 /register |
| `/api/users/` | 用户/会员/ELO API |
| `/api/users/me/diagnostic/generate/` | POST 生成诊断题目 |
| `/api/users/me/diagnostic/submit/` | POST 提交诊断答案 |
| `/api/users/institution/me/analytics/class-performance/` | GET 班级 KP 正确率分析 |
| `/api/users/institution/me/analytics/suggested-topics/` | GET Top 5 薄弱知识点建议 |
| `/api/quizzes/` | 题库/考试 API |
| `/api/quizzes/templates/` | GET/POST 出题模板（系统预设+机构自定义） |
| `/api/quizzes/templates/<id>/` | PATCH/DELETE 模板详情 |
| `/api/quizzes/ai/streaming-generate/` | POST 启动流式出题（返回 task_id） |
| `/api/quizzes/ai/streaming-generate/status/` | GET 轮询出题进度 |
| `/api/courses/` | 课程/视频 API |
| `/api/ai/` | AI 生成/管线 API |
| `/api/ai/memories/` | GET/POST Agent 记忆 CRUD（结构化） |
| `/api/ai/memories/<id>/` | PATCH/DELETE Agent 记忆（结构化） |
| `/api/ai/memories/semantics/` | GET 语义记忆列表（mem0，需 USE_MEM0=true） |
| `/api/ai/memories/semantics/clear/` | DELETE 清空全部语义记忆 |
| `/api/ai/memories/semantics/<memory_id>/` | DELETE 删除单条语义记忆 |
| `/api/ai/workbench-chat/` | POST 工作台 Agent 对话 |
| `/api/institutions/` | 机构管理 API |
| `/api/payments/` | 支付 API（订单/支付配置） |
| `/payments/result` | 支付结果页（前端） |
| `/billing` | 方案账单页（前端） |
| `/checkout` | 结算页（前端） |
| `/ws/ai/chat/<bot_id>/` | WS Agent 对话（出题助手/小宇，多步可见） |
| `/ws/` | WebSocket（自习室/对话） |

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

# Redis
REDIS_URL=redis://127.0.0.1:6379/0

# AI 模型（按任务路由见 ai_engine/config.py，hot-swap 只需改顶部两个常量）
# LLM_MODEL=                    # 全局覆盖（可选）

# 邮件 (Resend HTTP API)
EMAIL_BACKEND=core.email_service.ResendEmailBackend
RESEND_API_KEY=re_xxx

# 熔断器
AI_CB_FAILURE_THRESHOLD=5  AI_CB_RECOVERY_TIMEOUT=300  AI_CB_WINDOW_TIMEOUT=60

# Agent 记忆（mem0 语义记忆，默认关闭）
USE_MEM0=false                    # 启用 mem0 语义记忆（需 pgvector 扩展）
AI_EMBEDDING_MODEL=deepseek-embedding  # Embedding 模型
AI_EMBEDDING_BASE_URL=https://api.deepseek.com/v1  # Embedding API 地址

# 其他
AI_BULK_GENERATE_MAX_PER_REQUEST=3  AI_BULK_GENERATE_CONCURRENCY=4
ELO_K_FACTOR=32  USE_MEMORIX=false  ONLINE_USER_ACTIVE_WINDOW_SECONDS=300
ENCRYPTION_KEY=xxx                # 加密密钥（可选，默认 SECRET_KEY 派生），用于 EncryptedCharField/EncryptedTextField
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
python manage.py seed_exam_agent                # 创建/更新出题助手 Bot
python manage.py seed_xiaoyu                    # 创建/更新小宇学习规划 Bot

# 机构管理
python manage.py assign_default_institution     # 将无机构用户批量归入宇艺示范学员

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

模型路由集中在 `ai_engine/config.py`，顶部 `FALLBACK_FAST` / `FALLBACK_PRO` 两个常量是唯一默认值来源。换供应商只改此处 + `DEFAULT_BASE_URL`。分级覆盖：`AI_MODEL_FAST` / `AI_MODEL_PRO` env var。

| 任务 | 分级 | 思考 | 原因 |
|------|------|------|------|
| 对话/面试 | fast | — | 快速响应 |
| 出题 Author / AuthorRevise | fast | — | structured_output |
| 出题 Reviewer | pro | 开 | 深度逻辑检查，唯一显式开 thinking 的任务 |
| 出题 Classifier | fast | — | 审计+分类，structured_output |
| 主观题判分 | pro | — | 结构化 JSON 输出 |
| 知识树生成 | pro | — | 高质量内容创作 |
| 解析/分类/Schema 修复 | fast | — | 轻量任务 |

> thinking + tool_choice 不冲突。thinking 开启时 tool calls 轮次必须回传 `reasoning_content`（`call_ai_with_tools` 已处理）。

## 深入文档

| 文档 | 内容 |
|------|------|
| `README.md` | 完整系统介绍、部署指南、环境变量全量参考 |
| `CHANGELOG.md` | 版本更新日志 |
| `docs/tech/architecture/PERMISSION_ARCHITECTURE.md` | 三层权限模型、路由守卫、数据隔离、开发规范 |
| `docs/tech/features/MEMORIX_WHITEPAPER.md` | Memorix 算法论文 |
| `docs/tech/features/AI_MULTI_AGENT_PIPELINE.md` | 4-Agent ARC 对抗出题管线（Author→Reviewer→AuthorRevise→Classifier） |
| `docs/tech/features/PERSONALIZED_PDF_MOCK_EXAM.md` | 模拟考试（AI 组卷 + 教师发布 + 提交评分） |
| `docs/tech/features/AGENT_MEMORY.md` | Agent 记忆系统（提取/检索/注入机制） |
| `docs/tech/features/DIAGNOSTIC_TEST.md` | 学生诊断测试（生成/评分/Memorix 初始化） |
| `docs/tech/features/EXAM_WORKBENCH.md` | AI 出题工作台（对话式 Agent/快速出题/ARC 精修） |
| `docs/tech/features/MULTI_STEP_AGENT.md` | 多步可见 Agent（WebSocket 实时步骤 + 流式输出） |
| `docs/tech/features/MULTI_TENANT_AGENT_MEMORY.md` | 多租户 Agent 记忆（mem0+pgvector、工具权限沙箱、机构人格） |
| `docs/tech/incidents/` | 历史事故记录 |
| `backend/knowledge_trees/金融431_完整版.md` | 431 金融知识树（完整版） |
