# CLAUDE.md — UniMind.ai

AI 驱动的通用培训机构 SaaS 平台。Django 6.0 + React 19 + DeepSeek V4。

## 硬边界

- **禁止在服务器上直接改代码**。所有修改本地 → git commit → push → 服务器 `git pull`。`.env` 是唯一例外。
- **不要删除/重建 migration 文件**。始终 `python manage.py makemigrations` 追加新 migration。
- **不要改 `backend/ai_service.py`**（8 行 shim，纯 re-export）。新增 AI 能力去 `backend/ai_engine/` 或对应 app 的 `services/`。
- **Prompt 模板唯一来源**：`backend/prompts/`（统一目录），不再用 `backend/core/prompts/` 或 app 内 `templates/` 散落。
- **前端路由**：所有页面在 `frontend/src/App.tsx` 注册，权限 gating 在路由层或 sidebar 层处理。
- **不要裸用 `float('inf')`** 表示无限——用具体大数（如 999999），避免 JSON 序列化问题。

## 项目结构速查

```
backend/
├── school_system/          # Django 配置 (settings, urls, celery, asgi, middleware)
├── ai_engine/              # AI 引擎 (路由、熔断、可观测性、模型配置)
├── ai_assistant/           # AI 助教 (WebSocket 流式对话)
├── quizzes/                # 核心刷题
│   ├── services/           #   出题管线、评分、解析、PDF
│   ├── memorix/            #   Memorix 自进化记忆调度算法
│   └── views_*.py          #   views 已拆分为 6 个文件
├── users/                  # 用户/会员/RBAC/ELO/机构管理
├── courses/                # 课程/专辑/AI大纲/ASR/分片上传
├── articles/               # 深度文章
├── interviews/             # AI 模拟面试
├── study_room/             # 在线自习室
├── faq_system/             # 答疑系统
├── notifications/          # 站内通知
├── core/                   # 基础设施 (邮件、Prompt 管理、限流)
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
| `/` | Landing（未登录）/ `/dashboard`（已登录） |
| `/login` `/register` | 邮箱验证码登录注册 |
| `/intro` | 机构公开首页 |
| `/management` | 管理后台（需管理员） |
| `/api/users/` | 用户/会员/ELO API |
| `/api/quizzes/` | 题库/考试 API |
| `/api/courses/` | 课程/视频 API |
| `/api/ai/` | AI 生成/管线 API |
| `/api/institutions/` | 机构管理 API |
| `/ws/` | WebSocket（自习室/对话） |

## 环境变量速查

```bash
# 必填
DEEPSEEK_API_KEY=sk-xxx          # DeepSeek V4 API key
DJANGO_ENV=production|development
SECRET_KEY=<random-64-chars>
ALLOWED_HOSTS=domain.com

# 数据库
DB_ENGINE=django.db.backends.postgresql
DB_NAME=unimind  DB_USER=unimind  DB_PASSWORD=xxx  DB_HOST=localhost  DB_PORT=5432

# Redis
REDIS_URL=redis://127.0.0.1:6379/0

# AI 模型覆盖 (可选，默认 deepseek-v4-pro)
LLM_MODEL=deepseek-v4-pro
AI_MODEL_CHAT=deepseek-v4-flash
AI_MODEL_GENERATE_AUTHOR=deepseek-v4-pro
AI_MODEL_GENERATE_REVIEWER=deepseek-v4-pro
AI_MODEL_GRADE_SUBJECTIVE=deepseek-v4-pro
AI_MODEL_ESSAY_GRADE=deepseek-v4-pro

# 邮件 (Resend HTTP API)
EMAIL_BACKEND=core.email_service.ResendEmailBackend
RESEND_API_KEY=re_xxx

# 熔断器
AI_CB_FAILURE_THRESHOLD=5  AI_CB_RECOVERY_TIMEOUT=300  AI_CB_WINDOW_TIMEOUT=60

# 其他
AI_BULK_GENERATE_MAX_PER_REQUEST=3  AI_BULK_GENERATE_CONCURRENCY=4
ELO_K_FACTOR=32  USE_MEMORIX=false  ONLINE_USER_ACTIVE_WINDOW_SECONDS=300
```

## 常用命令

```bash
# 开发
cd backend && python manage.py runserver
cd frontend && npm run dev
celery -A school_system worker -l info

# 知识树导入
python manage.py import_knowledge_tree --force

# 机构管理
python manage.py assign_default_institution     # 将无机构用户批量归入宇艺示范学员

# Migration
python manage.py makemigrations && python manage.py migrate

# 生产部署
sudo systemctl restart unimind.service unimind-celery.service unimind-celery-beat.service
sudo journalctl -u unimind.service -f
```

## AI 模型策略

| 任务 | 模型 | 思考 | 原因 |
|------|------|------|------|
| 对话/面试 | v4-flash | 关 | 快速响应 |
| 出题 Author | v4-pro | 关 | 高质量+可控 temp |
| 出题 Reviewer | v4-pro | 开(high) | 深度逻辑检查 |
| 主观题评分 | v4-pro | 开(high) | 精准判断 |
| 作文评分 | v4-pro | 开(max) | 最高强度推理 |
| 解析/分类/修复 | v4-flash | 关 | 轻量任务 |

## 深入文档

| 文档 | 内容 |
|------|------|
| `README.md` | 完整系统介绍、部署指南、环境变量全量参考 |
| `CHANGELOG.md` | 版本更新日志 |
| `docs/MEMORIX_WHITEPAPER.md` | Memorix 算法论文 |
| `docs/FSRS_AUTO_TUNING_ALGORITHM.md` | FSRS 自动调参 |
| `docs/AI_MULTI_AGENT_PIPELINE.md` | 3-Agent 对抗出题管线 |
| `docs/BUSINESS_VERSION_PERMISSION_ARCHITECTURE.md` | 多租户权限架构 |
| `docs/PERSONALIZED_PDF_MOCK_EXAM.md` | PDF 模考（AI 组卷 + 教师发布 + 提交评分） |
| `docs/incidents/` | 历史事故记录 |
| `backend/knowledge_tree.md` | 431 金融知识树 |
| `backend/finance_431.md` | 431 考纲说明 |
