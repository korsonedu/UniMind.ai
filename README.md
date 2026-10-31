# UniMind.ai：科晟教育 Agent 学习平台

UniMind 为科晟课程提供学习、练习、复习、笔记与 AI 问答。小宇是学习端的 Agent 入口；教学生产和内容管理集中在 Directus 的 UniMind 管理扩展。课程在线下收费，课程学员身份由管理员调整，平台保留 AI 加量购买。

本文的功能边界按 2026-10-25 本地源码核对。部署模板不代表当前生产拓扑，本地构建与迁移文件也不代表已经发布。

## 当前入口

| 入口 | 地址 | 说明 |
| --- | --- | --- |
| 产品介绍 | `/` | 未登录时展示首页，已登录后进入小宇 |
| 小宇 | `/xiaoyu` | 普通问答、课程学习辅助与本人会话 |
| 我的笔记 | `/notes`、`/notes/:id` | 笔记、笔记本、标签与 Agent 参考 |
| 课程中心 | `/courses`、`/course/:id` | 学科、模块、视频、课件与学习记录 |
| 习题训练 | `/tests` | 练习、考试、错题复盘与 Memorix 调度 |
| 学习记录 | `/report-card` | 本人学习数据与成绩报告 |
| 学习社区 | `/community`、`/qa`、`/study` | 课程答疑与自习室 |
| 我的服务 | `/billing` | 学员状态、周额度、AI 加量与订单 |
| AI 加量 | `/pricing`、`/checkout` | 公开目录与登录后的结算 |
| 账号 | `/login`、`/register`、`/settings` | 登录注册与本人账号设置 |
| 教学管理 | Directus `/admin/unimind-admin` | 两名映射管理员的内容、学员、教学任务与系统管理 |
| Django 管理 | `/admin/` | 受现有管理权限约束的模型配置入口 |

学习功能仍受学员状态和逐人功能开关控制。独立知识地图、旧工作台与前台管理页面已退出，旧地址保留跳转。旧邀请地址已移除，加入机构接口返回 410，不能作为有效入学流程。

## 学员、权限与 AI 次数

- 非课程学员可以体验小宇普通问答、读取本人会话和管理本人账号服务；购买 AI 加量不开放课程或其他学习工具。
- 课程学员取得课程交付所需能力，继续受逐人功能开关和内容访问规则约束。
- 后台仅允许两名 Directus 映射操作者，须同时满足有效账号、staff、superuser 和无机构归属。创建 superuser 或保留历史教师角色均不足以取得管理能力。
- 内容查询使用显式 `UNIMIND_CONTENT_INSTITUTION_ID`；历史 `institution` 字段仍承担内容归属与兼容作用，不能清空字段或移除过滤来代替迁移。
- `users.0073` 初始化非课程学员 20 次／周、课程学员 200 次／周，以及 9.9 元／100 次、90 天有效的 AI 加量包；保留已有人工配置，实际额度和商品以后台配置、页面展示为准。
- 基础额度按上海时间周一 00:00 恢复，未用次数不累计；有效期内的加量不随周恢复清零。一次完整成功答复计一次，失败或取消释放占位，同次请求重试不重复扣次。管理员不限量。

当前不销售机构套餐、课程服务包或激活码，也不自动发放旧套餐试用。历史订单、订阅与权益到期处理保留兼容；旧试用、个人套餐和机构套餐续费提醒已从本地调度中移除。

## 当前能力与实现位置

| 能力 | 实现位置 |
| --- | --- |
| Agent 执行与意图路由 | `backend/ai_assistant/services/chat_service.py`、`backend/ai_engine/tool_run.py`、`backend/ai_engine/tool_router.py` |
| 会话与项目 | `frontend/src/components/AgentChatLayout.tsx`、`backend/ai_assistant/views_projects.py` |
| 笔记与 Agent 参考 | `frontend/src/pages/notes/`、`backend/notes/`；Agent 回答留在聊天中，笔记由用户编辑 |
| 练习、批改与复习 | `backend/quizzes/`、`backend/quizzes/memorix/` |
| 课程与学习记录 | `frontend/src/pages/course-center/`、`backend/courses/`、`backend/users/views_activity.py` |
| 教学管理与 ARC 内容生产 | `admin-extension/src/`、`backend/backoffice/`，生成结果经管理员确认后入库 |
| 平台分析 | `backend/core/analytics.py`、`backend/core/tasks.py`，保留事件、每日统计与 CSV 导出 |

模拟面试、旧 AI 助教和专属学生导师均不作为现行产品功能。右下角产品反馈及 NPS 满意度问卷已在本地移除；Agent 回复赞踩、练习批改反馈继续保留。

## 项目结构

```text
UniMindCode/
├── backend/
│   ├── school_system/          # Django、ASGI、Celery 与路由配置
│   ├── ai_engine/              # 模型、工具、意图路由与执行控制
│   ├── ai_assistant/           # Agent 运行时、会话与记忆
│   ├── users/                 # 账号、学员状态、周额度与历史权益
│   ├── notes/                 # 个人笔记与 Agent 参考
│   ├── courses/               # 课程、模块、资料与媒体
│   ├── quizzes/               # 题库、考试、批改与 Memorix
│   ├── backoffice/            # 管理桥接与教学任务
│   ├── payments/              # AI 加量订单与历史支付兼容
│   ├── articles/              # 文章资源
│   ├── faq_system/            # 课程答疑
│   ├── study_room/            # 自习室
│   ├── notifications/         # 通知与学习提醒
│   ├── core/                  # 认证、限流、审计、分析与内置法律文档
│   └── prompts/               # 提示词模板
├── frontend/src/              # React 学习端与本地预览
├── admin-extension/           # Directus 管理扩展
├── docs/                      # 当前说明、历史方案与研究记录
└── scripts/                   # 运维与研究脚本
```

## 技术栈与架构

后端使用 Django、DRF、Celery、Redis、Channels 与 Daphne；学习端使用 React、TypeScript、Tailwind、Radix、Zustand、TanStack Query、TipTap、KaTeX 与 Recharts。管理扩展使用 Vue 和 Directus。模型路由由 `backend/ai_engine/config.py` 定义，部署环境可以覆盖默认模型与地址。

Bot 注册表连接执行器、工具集和提示词；意图路由缩小工具候选范围，权限与参数检查在服务端执行。小宇与后台教学生产共享运行时，通过各自入口和授权范围访问资源。Memorix-Field 将个人复习状态与知识关系结合；历史论文、仿真和设计中的指标不作为真实用户效果或发布证明。

## 本次本地清理与迁移状态

截至本次文档更新，反馈、旧套餐提醒、不可达前端页面、停用接口旧实现、废弃配置和满意度问卷已在本地清理。以下迁移已生成，尚未在本次清理中执行：

- `core.0007_remove_feedback`：删除产品反馈模型。
- `users.0075_remove_user_trial_ends_at`：删除旧试用到期字段。
- `core.0008_remove_npssurvey`：删除满意度问卷模型。

删表、删字段会移除对应历史数据，发布前须纳入备份和迁移安排。本次清理尚未提交或部署；不能据此宣称生产已经退出这些功能。

## 文档入口

- [用户手册](docs/market/04-user-manual.md)：当前学习端使用方式。
- [管理扩展接入与操作](admin-extension/README.md)：两人映射、内容边界、教学任务与文件上传。
- [单平台权限与历史依赖](docs/tech/architecture/SINGLE_PLATFORM_TRANSITION.md)：现行权限规则及结构保留原因。
- [开发指引](CLAUDE.md)：代码位置、变更约束与常用命令。
- [平台分析](docs/tech/features/PLATFORM_ANALYTICS.md)：当前事件、统计与导出。

旧商业计划、营销文案、四层权限设计和旧前台工作台说明保留为历史参考，不作为当前售卖范围、权限规范或操作入口。

## 快速开始 (本地开发)

### 前置依赖

- Python 3.12+
- Node.js 20+
- Redis (macOS: `brew install redis && brew services start redis`)

### 1. 后端

```bash
cd backend

# 创建虚拟环境
python3 -m venv .venv
source .venv/bin/activate

# 安装依赖
pip install -r requirements.txt

# 成绩报告和试卷 PDF 的浏览器运行依赖，保留其他项目的浏览器缓存
PLAYWRIGHT_SKIP_BROWSER_GC=1 python -m playwright install chromium-headless-shell

# 配置环境变量
cp .env.example .env
# 编辑 .env，填入 LLM_API_KEY

# 数据库迁移
python manage.py migrate

# 启动 Django
python manage.py runserver
```

### 2. 前端

```bash
cd frontend
npm install
npm run dev
```

### 3. Celery Worker (AI 对话/异步任务需要)

```bash
cd backend
source .venv/bin/activate
celery -A school_system worker -l info
```

### 4. Celery Beat (定时任务)

```bash
cd backend
source .venv/bin/activate
celery -A school_system beat -l info
```

---

## 生产部署

### 架构概述

```
                  ┌──────────────┐
                  │    Nginx     │  反向代理 + 静态文件 + SSL 终止
                  └──────┬───────┘
                         │
            ┌────────────┼────────────┐
            ▼            ▼            ▼
     ┌──────────┐ ┌──────────┐ ┌──────────┐
     │  Daphne  │ │  Daphne  │ │  Daphne  │  ASGI (WebSocket + HTTP)
     │  :8001   │ │  :8002   │ │  :8003   │
     └────┬─────┘ └────┬─────┘ └────┬─────┘
          │             │             │
          └─────────────┼─────────────┘
                        │
            ┌───────────┼───────────┐
            ▼           ▼           ▼
     ┌──────────┐ ┌──────────┐ ┌──────────┐
     │  Celery  │ │  Celery  │ │   Beat   │
     │ Worker 1 │ │ Worker 2 │ │Scheduler │
     └────┬─────┘ └────┬─────┘ └────┬─────┘
          │             │             │
          └─────────────┼─────────────┘
                        │
                  ┌─────┴─────┐
                  │   Redis   │  消息队列 + 缓存 + Channel Layer
                  └───────────┘
                        │
                  ┌─────┴─────┐
                  │ PostgreSQL│  数据库
                  └───────────┘
```

### 1. 服务器环境准备

```bash
# Ubuntu/Debian
sudo apt update
sudo apt install -y python3.12 python3.12-venv python3.12-dev \
    nodejs npm redis-server postgresql postgresql-client \
    nginx ffmpeg build-essential libpq-dev

# 启动基础服务
sudo systemctl enable --now redis-server postgresql
```

### 2. 创建项目用户和目录

```bash
sudo useradd -m -s /bin/bash unimind
sudo mkdir -p /opt/unimind
sudo chown unimind:unimind /opt/unimind

# 上传代码到 /opt/unimind
# (通过 git clone 或 rsync)
```

### 3. 配置 PostgreSQL

```bash
sudo -u postgres psql <<SQL
CREATE DATABASE unimind;
CREATE USER unimind WITH PASSWORD '<strong-random-password>';
ALTER ROLE unimind SET client_encoding TO 'utf8';
ALTER ROLE unimind SET default_transaction_isolation TO 'read committed';
ALTER ROLE unimind SET timezone TO 'Asia/Shanghai';
GRANT ALL PRIVILEGES ON DATABASE unimind TO unimind;
\c unimind
GRANT ALL ON SCHEMA public TO unimind;
SQL
```

### 4. 配置环境变量

```bash
cd /opt/unimind/backend
cp .env.example .env
# 编辑 .env，详见下方「环境变量完整参考」章节
# 至少需要配置: DJANGO_ENV, SECRET_KEY, ALLOWED_HOSTS, DB_*, LLM_API_KEY, CORS_*
```

### 5. 安装依赖和初始化

```bash
cd /opt/unimind/backend
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 数据库迁移
python manage.py migrate

# 创建超级用户
python manage.py createsuperuser

# 收集静态文件
python manage.py collectstatic --noinput

# 导入知识树（全局）
python manage.py import_knowledge_tree backend/knowledge_trees/金融431.md --global --subject=金融431 --force

# 导入高中学科知识树
python manage.py import_knowledge_tree backend/knowledge_trees/高中数学.md --global --subject=高中数学 --force
python manage.py import_knowledge_tree backend/knowledge_trees/高中物理.md --global --subject=高中物理 --force

# AI 生成新的学科知识树（自动调用 LLM）
python manage.py generate_knowledge_tree --subject=高中数学

# 导出知识树为 MD
python manage.py export_knowledge_tree --global --subject=金融431
```

### 6. Systemd 服务配置

**Daphne (ASGI 服务)**

```ini
# /etc/systemd/system/unimind.service
[Unit]
Description=UniMind Daphne ASGI
After=network.target redis.service postgresql.service
Wants=redis.service postgresql.service

[Service]
User=unimind
Group=unimind
WorkingDirectory=/opt/unimind/backend
EnvironmentFile=/opt/unimind/backend/.env
ExecStart=/opt/unimind/backend/.venv/bin/daphne \
    -b 127.0.0.1 \
    -p 8001 \
    --websocket_connect_timeout 30 \
    school_system.asgi:application
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

**Celery Worker**

```ini
# /etc/systemd/system/unimind-celery.service
[Unit]
Description=UniMind Celery Worker
After=network.target redis.service postgresql.service
Wants=redis.service postgresql.service

[Service]
User=unimind
Group=unimind
WorkingDirectory=/opt/unimind/backend
EnvironmentFile=/opt/unimind/backend/.env
ExecStart=/opt/unimind/backend/.venv/bin/celery \
    -A school_system worker \
    -l info \
    --concurrency=4 \
    --max-tasks-per-child=100
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

**Celery Beat**

```ini
# /etc/systemd/system/unimind-celery-beat.service
[Unit]
Description=UniMind Celery Beat Scheduler
After=network.target redis.service postgresql.service
Wants=redis.service postgresql.service

[Service]
User=unimind
Group=unimind
WorkingDirectory=/opt/unimind/backend
EnvironmentFile=/opt/unimind/backend/.env
ExecStart=/opt/unimind/backend/.venv/bin/celery \
    -A school_system beat \
    -l info \
    --scheduler django_celery_beat.schedulers:DatabaseScheduler
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

启动所有服务：

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now unimind.service unimind-celery.service unimind-celery-beat.service
```

### 7. Nginx 配置

```nginx
# /etc/nginx/sites-available/unimind
upstream daphne {
    server 127.0.0.1:8001;
    keepalive 32;
}

server {
    listen 80;
    server_name your-domain.com;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name your-domain.com;

    ssl_certificate     /etc/letsencrypt/live/your-domain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/your-domain.com/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_prefer_server_ciphers off;

    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;

    client_max_body_size 200M;
    client_body_timeout 300s;

    root /opt/unimind/frontend/dist;
    index index.html;

    # index.html — 不缓存（保证用户拿到最新版本）
    location = /index.html {
        add_header Cache-Control "no-cache, no-store, must-revalidate";
        add_header Pragma "no-cache";
        add_header Expires "0";
        try_files /index.html =404;
    }

    # 前端静态资源 — 长缓存（文件名带 hash）
    location /assets/ {
        expires 1y;
        add_header Cache-Control "public, immutable";
        try_files $uri =404;
    }

    # SPA fallback — 不缓存
    location / {
        add_header Cache-Control "no-cache";
        try_files $uri $uri/ /index.html;
    }

    # Django 静态文件
    location /static_django/ {
        alias /opt/unimind/backend/staticfiles/;
        expires 30d;
        add_header Cache-Control "public";
    }

    location /media/ {
        alias /opt/unimind/backend/media/;
    }

    # API 代理（keepalive 复用连接）
    location /api/ {
        proxy_pass http://daphne;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Connection "";
        proxy_http_version 1.1;
        proxy_request_buffering off;
        proxy_read_timeout 300s;
        proxy_send_timeout 300s;
    }

    # WebSocket
    location /ws/ {
        proxy_pass http://daphne;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 86400;
        proxy_send_timeout 86400;
    }

    location /admin/ {
        proxy_pass http://daphne;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Connection "";
        proxy_http_version 1.1;
    }

    # 禁止访问隐藏文件
    location ~ /\.(?!well-known) {
        deny all;
    }
}
```

同时确保 `/etc/nginx/nginx.conf` 中启用 gzip：

```nginx
gzip on;
gzip_vary on;
gzip_proxied any;
gzip_comp_level 6;
gzip_buffers 16 8k;
gzip_http_version 1.1;
gzip_types text/plain text/css application/json application/javascript text/xml application/xml application/xml+rss text/javascript application/wasm image/svg+xml;
```

启用配置：

```bash
sudo ln -s /etc/nginx/sites-available/unimind /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx

# SSL 证书 (Let's Encrypt)
sudo certbot --nginx -d your-domain.com
```

### 8. 前端构建

```bash
cd /opt/unimind/frontend
npm ci
VITE_API_URL=https://your-domain.com npx vite build
# 静态文件输出到 frontend/dist/
```

### 9. 部署验证清单

部署完成后逐项检查：

- [ ] PostgreSQL 数据库连接正常
- [ ] Redis 连接正常
- [ ] Django migration 全部执行无报错
- [ ] 静态文件 collectstatic 完成
- [ ] Daphne 启动成功 (`systemctl status unimind`)
- [ ] Celery Worker 启动成功 (`systemctl status unimind-celery`)
- [ ] Celery Beat 启动成功 (`systemctl status unimind-celery-beat`)
- [ ] Nginx 配置语法检查通过 (`nginx -t`)
- [ ] HTTPS 证书有效
- [ ] `DJANGO_ENV=production` 已设置
- [ ] `DEBUG=false` 已设置
- [ ] `SECRET_KEY` 为强随机值（64+ 字符）
- [ ] `ALLOWED_HOSTS` 包含正确的域名
- [ ] `CORS_ALLOW_ALL_ORIGINS=false`
- [ ] `CORS_ALLOWED_ORIGINS` 已配置前端域名
- [ ] API 端点正常响应
- [ ] WebSocket 连接正常
- [ ] 邮件发送正常
- [ ] LLM_API_KEY 有效
- [ ] 日志正常输出到 journald

---

## 环境变量完整参考

### 必填

```bash
# Django 核心
DJANGO_ENV=production                           # development | production
DEBUG=false                                      # 生产环境必须为 false
SECRET_KEY=<generate-with: python -c "import secrets; print(secrets.token_urlsafe(64))">
ALLOWED_HOSTS=your-domain.com,www.your-domain.com

# AI 引擎
LLM_API_KEY=sk-xxx                              # LLM API key
```

### 数据库

```bash
DB_ENGINE=django.db.backends.postgresql
DB_NAME=unimind
DB_USER=unimind
DB_PASSWORD=<db-password>
DB_HOST=localhost
DB_PORT=5432
```

### 缓存 / 消息队列

```bash
REDIS_URL=redis://127.0.0.1:6379/0
CACHE_REDIS_URL=redis://127.0.0.1:6379/1     # Django 缓存（独立 db，避免与 Celery/Channels 冲突）
CHANNEL_LAYER_REDIS_URL=redis://127.0.0.1:6379/0
CELERY_BROKER_URL=redis://127.0.0.1:6379/0
CELERY_RESULT_BACKEND=redis://127.0.0.1:6379/0
```

### CORS / 安全

```bash
CORS_ALLOW_ALL_ORIGINS=false
CORS_ALLOWED_ORIGINS=https://your-domain.com
CORS_ALLOW_CREDENTIALS=true
CSRF_TRUSTED_ORIGINS=https://your-domain.com
USE_X_FORWARDED_PROTO=true
```

### AI 模型配置 (可选)

```bash
# 以下均可选，不设则用 ai_engine/config.py 内置默认值
# LLM_API_KEY=sk-xxx           # API key
# LLM_BASE_URL=                # 覆盖 API 地址
# LLM_MODEL=                   # 全局模型覆盖
# AI_MODEL_FAST=               # 轻量任务分级覆盖
# AI_MODEL_PRO=                # 重量任务分级覆盖
LLM_REQUEST_TIMEOUT_SECONDS=120
LLM_REQUEST_MAX_RETRIES=1
```

### 算法 Feature Flags

```bash
# Memorix 记忆调度
USE_MEMORIX=false                  # Memorix 自进化记忆调度总开关

# Memorix-Field 图扩散调度
MEMORIX_FIELD_ENABLED=true         # 图扩散总开关

# IRT 认知诊断
IRT_MIN_RESPONSES=50               # 题目参数估计最少答题数

# Agent 语义记忆
USE_MEM0=true                      # mem0 语义记忆（需 pgvector 扩展）
```

> **模型路由已收敛至 `ai_engine/config.py`**，顶部 `FALLBACK_FAST` / `FALLBACK_PRO` 两个常量是唯一默认值来源。
> 换供应商只需改这两个常量 + `DEFAULT_BASE_URL`。env var 是可选的覆盖层。

**模型分级速查：**

| 任务 | 分级 | 思考 |
|------|------|------|
| 小宇对话 | fast | — |
| 出题 Author / AuthorRevise | fast | — |
| 出题 Reviewer | pro | 开 |
| 出题 Classifier | fast | — |
| 主观题判分 | pro | — |
| 知识树生成 | pro | — |
| 解析 / 分类 / Schema 修复 | fast | — |

### 邮件

```bash
# Resend HTTP API（生产环境）
EMAIL_BACKEND=core.email_service.ResendEmailBackend
RESEND_API_KEY=re_xxx

# 开发环境可用 console 后端:
# EMAIL_BACKEND=django.core.mail.backends.console.EmailBackend
```

### ASR 语音转文字

```bash
ASR_DEFAULT_PROVIDER=dummy                       # dummy | vosk | whisper_openai | glm_asr

# Vosk 离线（免费，1.4GB 模型下载）
# VOSK_MODEL_PATH=/path/to/vosk-model-cn-0.22

# OpenAI Whisper
# WHISPER_API_KEY=sk-xxx

# GLM ASR
# GLM_ASR_API_KEY=your-key
```

### 其他可选配置

```bash
LOG_LEVEL=INFO
ONLINE_USER_ACTIVE_WINDOW_SECONDS=300

# AI 管线
AI_BULK_GENERATE_MAX_PER_REQUEST=3
AI_BULK_GENERATE_CONCURRENCY=4
AI_DIFFICULTY_CHECK_ENABLED=true
AI_SINGLE_PIPELINE_AUTHOR_WINDOWS=1

# AI 熔断器
AI_CB_FAILURE_THRESHOLD=5                        # 窗口内失败次数阈值
AI_CB_RECOVERY_TIMEOUT=300                       # 熔断恢复超时(秒)
AI_CB_WINDOW_TIMEOUT=60                          # 故障计数窗口(秒)

# ELO
ELO_K_FACTOR=32
ELO_INITIAL_BONUS=200
LEADERBOARD_SIZE=50

# 加密
ENCRYPTION_KEY=                                    # 加密密钥（可选，默认 SECRET_KEY 派生），用于 EncryptedCharField/EncryptedTextField

# GIPHY
GIPHY_API_KEY=                                    # 自习室 GIF 功能

# 阿里云 OSS 对象存储（可选）
OSS_ACCESS_KEY_ID=xxx                             # 阿里云 AccessKey ID
OSS_ACCESS_KEY_SECRET=xxx                         # 阿里云 AccessKey Secret
OSS_BUCKET_NAME=unimind-courses                   # OSS Bucket 名称
OSS_ENDPOINT=oss-cn-beijing.aliyuncs.com          # OSS 访问域名
```

---

## 配置指南

### Prompt 模板管理

所有 AI Prompt 模板以 `.txt` 文件形式存放在 `backend/prompts/` 目录。出题管线 Agent 通过 JSON Schema 定义强制结构化输出（`tool_choice="required"`），从 API 层面杜绝格式偏差。

```
prompts/
├── quizzes/          # 题库生成相关 Prompt
├── ai_assistant/     # Agent 对话 Prompt
│   └── bots/         #   各 Bot 独立 Prompt（小宇/工作台）
├── pipeline/         # 出题管线各 Agent Prompt
├── grading/          # 评分 Prompt
└── courses/          # 课程大纲 Prompt
```

修改方式：
基础提示词以 `backend/prompts/` 源码文件为准，按代码发布流程更新。后台 AI 配置只调整当前提供的助手名称、启停与偏好，不恢复已删除的前台提示词编辑页面。历史 Prompt 模型不代表当前界面提供版本回滚入口。

### 知识点管理

所有功能（题库、课程、文章、知识地图、AI出题）的知识点数据均来自 **`backend/knowledge_trees/`** 目录下的 Markdown 文件。修改后运行导入命令即可更新全系统。

```bash
# 导入指定学科知识树到历史全局分区（访问仍受单平台内容配置约束）
python manage.py import_knowledge_tree backend/knowledge_trees/金融431.md --global --subject=金融431 --force

# 导入到指定内容归属（先核对单平台内容配置）
python manage.py import_knowledge_tree backend/knowledge_trees/金融431.md --institution=<slug> --force

# 批量导入所有预设学科
for f in backend/knowledge_trees/*.md; do
  subject=$(basename "$f" .md)
  python manage.py import_knowledge_tree "$f" --global --subject="$subject" --force
done

# 使用 AI 生成新学科的知识树
python manage.py generate_knowledge_tree --subject=高中数学

# Markdown 格式要求：
#   # [SUB-01] 模块名         → sub 级别（学科模块）
#   ## [CH-01] 篇章名         → ch 级别（篇章）
#   ### [SEC-01] 小节名       → sec 级别（小节）
#   - [MB-1001] 考点名称      → kp 级别（具体考点）
```

名称中的括号说明（如 `货币的起源（常考概念）`）会自动提取到 description 字段供 AI 参考。

### AI 智能大纲

课程视频支持通过 AI 自动生成带时间戳的章节大纲：

```
管理员上传课程（开启「AI 智能大纲」开关）
  → 后端自动提取视频音频 (ffmpeg)
  → ASR 语音转文字（生成完整逐字稿）
  → AI 分析逐字稿生成结构化大纲（含章节标题、时间戳、内容摘要）
  → 学生端展示可折叠大纲，点击时间戳视频跳转
```

| 组件 | 路径 | 说明 |
|------|------|------|
| ASR 抽象层 | `backend/courses/asr/` | 可插拔提供者模式 |
| AI 流水线 | `backend/courses/services/ai_course_service.py` | 转录→大纲→出题编排 |
| 任务分派 | `backend/courses/services/task_dispatcher.py` | Celery + Thread 双重分派 |
| 前端 Store | `frontend/src/store/useCourseAIStore.ts` | 大纲/转录状态管理 |
| 前端组件 | `frontend/src/components/course/OutlinePanel.tsx` | 大纲展示组件 |

**ASR 提供者对比：**

| 提供者 | 费用 | 运行方式 | 时间戳精度 |
|--------|------|---------|-----------|
| Dummy | 免费 | 占位 | 无 |
| Vosk | 免费 | 本地离线 | 逐词（秒级） |
| OpenAI Whisper | API 付费 | 云端 | 逐句 |
| GLM ASR | API 付费 | 云端 | 28秒 粒度 |

---

## 开发指南

- **Django**：`runserver` 自动重载
- **Celery Worker**：需要手动重启
- **前端**：Vite HMR 自动热更新
- **数据库**：开发环境使用 SQLite（`backend/db.sqlite3`），生产环境使用 PostgreSQL

---

## 运维管理

### 查看日志

```bash
journalctl -u unimind.service -f           # 应用日志
journalctl -u unimind-celery.service -f     # Celery Worker
journalctl -u unimind-celery-beat.service -f # Celery Beat
tail -f /var/log/nginx/access.log           # Nginx 访问日志
tail -f /var/log/nginx/error.log            # Nginx 错误日志
```

### 备份数据库

```bash
# PostgreSQL 备份
pg_dump -U unimind unimind > /backup/unimind_$(date +%Y%m%d_%H%M%S).sql

# 定时备份 (crontab)
0 3 * * * pg_dump -U unimind unimind > /backup/unimind_$(date +\%Y\%m\%d).sql
```

### 更新部署

服务器 `git pull` 后的标准操作：

```bash
cd /opt/unimind
git pull origin main

# 后端
cd backend
venv/bin/pip install -r requirements.txt   # 有新增/更新依赖时
venv/bin/python manage.py migrate          # 有新增 migration 时
venv/bin/python manage.py collectstatic --noinput
sudo systemctl restart unimind.service unimind-celery.service

# 前端（前端代码有变更时）
cd ../frontend && npm ci && npm run build
```

没有改依赖可跳过 `pip install`，没有 migration 可跳过 `migrate`，没改前端可跳过前端构建。

---

## 安全注意事项

- **SECRET_KEY**：生产环境必须设置为至少 64 字符的随机值，可用 `python -c "import secrets; print(secrets.token_urlsafe(64))"` 生成
- **API Key**：所有第三方 API Key（LLM、Gmail、GIPHY、ASR）必须通过环境变量注入，不得提交到版本控制
- **数据库密码**：使用强随机密码，不要与其他系统重复
- **HTTPS**：生产环境必须启用 HTTPS，建议使用 Let's Encrypt
- **支付密钥**：支付宝/微信支付私钥等通过 `EncryptedCharField` / `EncryptedTextField`（Fernet AES）加密存储，加密密钥通过 `ENCRYPTION_KEY` 环境变量设置（默认从 SECRET_KEY 派生）
- **认证方式**：Cookie 认证为主（httpOnly cookie + CSRF 保护），REST API 通过 `CookieTokenAuthentication` 读取，WebSocket 仅 Cookie 认证，前端不存储 token 到 localStorage
- **速率限制**：登录、注册、验证码发送端点已启用速率限制，AI 生成端点建议在 Nginx 层额外添加速率限制
- **文件上传**：分片上传已校验分片大小和块数有效性；文件校验通过 `core.file_validation` 模块统一处理
- **XSS 防护**：系统使用 React JSX 转义 + TipTap HTML 过滤，渲染用户生成内容时应注意额外消毒

---

## License

Proprietary. All rights reserved.
