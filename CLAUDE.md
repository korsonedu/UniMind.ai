# CLAUDE.md — UniMind.ai

AI 驱动的通用培训机构 SaaS 平台。Django 6.0 + React 19 + MiMo V2.5。

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
backend/
├── school_system/          # Django 配置 (settings, urls, celery, asgi, middleware)
├── ai_engine/              # AI 引擎 (路由、熔断、可观测性、模型配置)
├── ai_assistant/           # AI 助教 (WebSocket 流式对话)
├── quizzes/                # 核心刷题
│   ├── services/           #   出题管线、评分、解析、PDF
│   ├── memorix/            #   Memorix 自进化记忆调度算法
│   ├── management/         #   import_knowledge_tree, seed_questions/demo
│   └── views_*.py          #   views 已拆分为 6 个文件（原始 views.py 已删除）
├── users/                  # 用户/会员/RBAC/ELO/机构管理
│   └── services/           #   会员服务 (membership.py)
├── courses/                # 课程/专辑/AI大纲/ASR/分片上传
├── articles/               # 深度文章
├── interviews/             # AI 模拟面试
├── study_room/             # 在线自习室
├── faq_system/             # 答疑系统
├── notifications/          # 站内通知
├── payments/               # 支付网关 (Stripe/支付宝/微信)
├── core/                   # 基础设施 (加密字段、Cookie认证、邮件、限流、Prompt管理)
└── prompts/                # 统一 Prompt 模板目录
    ├── quizzes/  ai_assistant/  courses/  pipeline/  grading/  interviews/

frontend/
├── src/pages/              # 21 个页面组件
├── src/components/         # 通用组件 + shadcn/ui
├── src/lib/                # API 客户端、权限、hooks
└── src/store/              # Zustand 状态管理
```

## Django Apps (11)

`ai_engine` `ai_assistant` `quizzes` `users` `courses` `articles` `interviews` `study_room` `faq_system` `notifications` `core`

## 关键路由

| 路径 | 说明 |
|------|------|
| `/` | Landing（未登录）/ HomeRedirect（已登录：pro→机构主页, 其他→课程中心） |
| `/login` `/register` | 邮箱验证码登录注册 |
| `/intro/:slug` | 机构公开首页（无需登录，公开访问） |
| `/management` | 管理后台（需管理员） |
| `/join/:invite_slug` | 邀请链接 → 种 cookie → 302 到 /register |
| `/api/users/` | 用户/会员/ELO API |
| `/api/quizzes/` | 题库/考试 API |
| `/api/courses/` | 课程/视频 API |
| `/api/ai/` | AI 生成/管线 API |
| `/api/institutions/` | 机构管理 API |
| `/api/payments/` | 支付 API（订单/支付配置） |
| `/payments/result` | 支付结果页（前端） |
| `/billing` | 方案账单页（前端） |
| `/checkout` | 结算页（前端） |
| `/ws/` | WebSocket（自习室/对话） |

## 环境变量速查

```bash
# 必填
LLM_API_KEY=sk-xxx              # LLM API key（当前: MiMo）
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

# 知识树导入（全局，示例）
python manage.py import_knowledge_tree backend/knowledge_trees/金融431.md --global --subject=金融431 --force
python manage.py import_knowledge_tree backend/knowledge_trees/高中数学.md --global --subject=高中数学 --force
python manage.py import_knowledge_tree backend/knowledge_trees/高中物理.md --global --subject=高中物理 --force
# AI 生成新学科知识树
python manage.py generate_knowledge_tree --subject=高中数学
# 批量导入所有预设
for f in backend/knowledge_trees/*.md; do subject=$(basename "$f" .md); python manage.py import_knowledge_tree "$f" --global --subject="$subject" --force; done

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

| 任务 | 分级 | 思考 | 原因 |
|------|------|------|------|
| 对话/面试 | fast | — | 快速响应 |
| 出题 Author / AuthorRevise | fast | — | structured_output |
| 出题 Reviewer | pro | 开 | 深度逻辑检查，唯一显式开 thinking 的任务 |
| 出题 Classifier | fast | — | 审计+分类，structured_output |
| 主观题判分 | pro | — | 结构化 JSON 输出 |
| 知识树生成 | pro | — | 高质量内容创作 |
| 解析/分类/Schema 修复 | fast | — | 轻量任务 |

> 路由来源：`ai_engine/config.py`。模型 ID 集中在文件顶部 `FALLBACK_FAST` / `FALLBACK_PRO` 两个常量。
> 换供应商只改此处 + `DEFAULT_BASE_URL`。分级覆盖：`AI_MODEL_FAST` / `AI_MODEL_PRO` env var。
> DeepSeek thinking + tool_choice 不冲突。thinking 开启时 tool calls 轮次必须回传 `reasoning_content`（`call_ai_with_tools` 已处理）。

## 深入文档

| 文档 | 内容 |
|------|------|
| `README.md` | 完整系统介绍、部署指南、环境变量全量参考 |
| `CHANGELOG.md` | 版本更新日志 |
| `docs/tech/architecture/PERMISSION_ARCHITECTURE.md` | 三层权限模型、路由守卫、数据隔离、开发规范 |
| `docs/tech/features/MEMORIX_WHITEPAPER.md` | Memorix 算法论文 |
| `docs/tech/features/AI_MULTI_AGENT_PIPELINE.md` | 4-Agent ARC 对抗出题管线（Author→Reviewer→AuthorRevise→Classifier） |
| `docs/tech/features/PERSONALIZED_PDF_MOCK_EXAM.md` | 模拟考试（AI 组卷 + 教师发布 + 提交评分） |
| `docs/tech/incidents/` | 历史事故记录 |
| `backend/knowledge_trees/金融431_完整版.md` | 431 金融知识树（完整版） |
