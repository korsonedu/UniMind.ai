# UniMind.ai — AI 驱动的全球考试学习系统

基于 Django + React 的全栈 AI 学习平台，集成 DeepSeek V4 智能引擎、FSRS 记忆调度算法、ELO 学术天梯和沉浸式共学社区。

## 项目结构

```
官网0215/
├── backend/                     # Django 后端 (Python 3.12+)
│   ├── school_system/           # 项目配置 (settings, urls, celery, asgi, middleware)
│   ├── ai_engine/               # AI 引擎 (路由、熔断、可观测性、模型配置)
│   ├── ai_assistant/            # AI 助教对话 (多 Bot、WebSocket 流式)
│   ├── quizzes/                 # 核心刷题系统
│   │   ├── services/            #   出题管线、评分、解析、PDF 生成
│   │   ├── memorix/             #   Memorix 自进化记忆调度算法
│   │   └── templates/           #   AI 出题 Prompt 模板
│   ├── users/                   # 用户/会员/RBAC 权限/ELO 积分/机构管理
│   ├── courses/                 # 课程/专辑/导学资料/AI智能大纲/ASR/分片上传
│   ├── articles/                # 深度文章
│   ├── interviews/              # AI 模拟面试 (WebSocket)
│   ├── study_room/              # 在线自习室 (番茄钟/GIPHY/周计划)
│   ├── faq_system/              # 答疑系统
│   ├── notifications/           # 站内通知
│   ├── core/                    # 基础设施 (邮件、Prompt 管理、限流)
│   ├── prompts/                 # 统一 Prompt 模板目录
│   │   ├── quizzes/             #   题库生成 Prompt
│   │   ├── ai_assistant/        #   助教对话 Prompt
│   │   ├── courses/             #   课程大纲 Prompt
│   │   ├── pipeline/            #   出题管线各 Agent Prompt
│   │   ├── grading/             #   评分 Prompt
│   │   └── interviews/          #   面试 Prompt
│   ├── .env.example             # 环境变量模板
│   ├── requirements.txt         # Python 依赖
│   └── manage.py
├── frontend/                    # React 前端 (TypeScript + Tailwind)
│   ├── src/
│   │   ├── pages/               # 21 个页面组件
│   │   ├── components/          # 通用组件 + shadcn/ui
│   │   ├── lib/                 # 工具库 (API 客户端、权限、hooks)
│   │   └── store/               # Zustand 状态管理
│   ├── vite.config.ts
│   └── package.json
├── docs/                        # 项目文档
├── scripts/                     # 运维脚本
├── .github/workflows/           # CI/CD
└── README.md
```

## 页面入口

| 页面 | URL | 说明 |
|------|-----|------|
| **产品介绍页** | `/`（未登录） | Landing 页，含功能展示、定价、FAQ。登录后 pro→机构主页，其他→课程中心 |
| **机构首页** | `/intro/:slug` | 公开的机构首页，无需登录 |
| **登录** | `/login` | 邮箱验证码登录 |
| **注册** | `/register` | 邮箱验证码注册，自动开启 7 天全功能试用 |
| **邀请链接** | `/join/:invite_slug` | 邀请链接 → 种 cookie → 302 到 /register |
| **管理后台** | `/management` | 题库管理、用户权限、系统配置（需管理员） |

---

## 系统功能

### 1. AI 学术导师矩阵

不只聊天，是真正懂学生的专属导师。

- **多 Bot 架构**：管理员可部署具有不同性格和学术背景的 AI 助教，学生自由切换
- **专属导师模式**：AI 深度钩稽学生个人数据——ELO 积分、错题记录、知识图谱掌握度——提供定制化辅导。学生说"检查错题"时，AI 直接调出最近错题并分析思维误区
- **DeepSeek V4 驱动**：出题审核、作文评分启用深度思考模式（Chain-of-Thought）；判分、对话使用高速响应模式；按任务难度智能分配 v4-pro / v4-flash 算力
- **LaTeX 原生渲染**：数学公式、经济学模型完美展示（KaTeX）

### 2. FSRS 智能天梯

拒绝题海战术，千人千面的自适应学习系统。

- **FSRS v4.5 记忆算法**：精准计算每道题的遗忘临界点，在最该复习的时刻推给你
- **Memorix 自进化算法**：基于 Weibull 遗忘曲线 + 贝叶斯校准 + 在线 SGD 学习，越用越准
- **ELO 学术段位**：每次答题影响竞技积分，全站实时排名
- **AI 自动评分**：主观题（名词解释、简答、论述、计算）由 AI 精准判分
- **错题归因引擎**：自动分类错误原因（概念混淆/计算失误/逻辑错误/记忆遗漏/表达不清），生成针对性复习建议

### 3. AI 工业级出题中心

教研效率提升 100 倍的内容生产流水线。

- **3-Agent 对抗性管线**：Author（出题者）→ Reviewer（审核者，四维质量评分，最多 3 轮迭代）→ Classifier（自动打标分类）→ 管理员审核入库
- **全题型覆盖**：单选题、名词解释、简答题、论述题、计算题
- **超长文本解析**：支持 5-10 万字语料的并行分片解析，Word/文本拖入即出题
- **难度自适应**：自动估计题目难度（entry → extreme 五档），按目标难度生成
- **题型比例控制**：支持按目标题型配比生成（如 40% 客观 + 30% 简答 + 30% 论述）

### 4. 全景知识拓扑地图

不是孤立的题目，是网状的知识体系。

- **4 级树状结构**：学科(Sub) → 篇章(Ch) → 小节(Sec) → 考点(KP)
- **类 Obsidian 思维图谱**：基于 D3.js 的可视化探索，节点间自由跳转
- **多维资源挂载**：视频课程、深度文章、题库全量挂载至知识节点
- **掌握度热力图**：按知识点展示掌握程度，一眼定位薄弱环节
- **自定义标注**：学生可对知识点添加笔记、优先级、掌握度标记

### 5. AI 模拟面试

还原真实面试场景的智能对话训练。

- **WebSocket 实时对话**：低延迟双向语音/文字交互
- **多轮追问**：AI 根据回答质量自动调整追问深度
- **简历分析**：上传简历，AI 提取关键经历并针对性提问
- **面试报告**：结束后生成综合评估（语言表达、专业深度、逻辑清晰度等维度评分）

### 6. 沉浸式自习室

天涯若比邻的共学空间。

- **实时在线同步**：WebSocket 广播全站学友的专注状态
- **番茄钟**：可配置的专注计时 + 任务管理
- **GIPHY 集成**：学习间隙的轻松互动
- **周度学习计划**：AI 自动生成每周复习计划，Celery 定时推送

### 7. 音视频课程中心

从上传到内化的完整学习闭环。

- **分片上传**：支持 100MB+ 视频文件，断点续传，进度追踪
- **AI 智能大纲**：ASR 语音转文字 → AI 生成结构化大纲 → 点击时间戳视频跳转
- **多 ASR 提供者**：OpenAI Whisper / Vosk 离线 / GLM ASR，可插拔架构，按需接入
- **视频出题**：基于视频内容 AI 自动生成配套习题
- **课程管理**：专辑组织、导学资料、学习进度追踪

### 8. 会员与激励体系

- **四档方案**：Free / Solo / Plus / Pro，覆盖个人到企业
- **7 天全功能试用**：新用户注册自动开启
- **激活码系统**：灵活的批量会员开通方式
- **ELO 积分特权**：付费会员 ELO 永不衰减
- **周度认知报告**：转化率、ELO 百分位、每日准确率/专注度/课时趋势

### 9. 机构管理平台 (B2B)

面向培训机构的全套教学管理系统。

- **多教师协作**：教师角色分配，权限隔离
- **学生管理**：学生列表、学习进度追踪、数据导出
- **班级对比**：跨班级学习效果对比分析
- **品牌定制**：Pro 方案支持白标，机构自有品牌展示
- **独立定价**：机构可自定义对学生的收费标准
- **收款集成**：支付宝/微信支付，机构自有商户号配置

---

## 技术栈

| 层 | 技术 |
|----|------|
| 后端框架 | Django 6.0 + Django REST Framework 3.16 |
| 异步任务 | Celery 5.4 + Redis |
| WebSocket | Django Channels 4.3 + Daphne 4.2 |
| AI 引擎 | DeepSeek V4 (v4-pro / v4-flash) 原生 API，思考模式 + 按任务路由 |
| 前端框架 | React 19 + TypeScript |
| UI 组件 | shadcn/ui (Radix) + Tailwind CSS 4 |
| 状态管理 | Zustand 5 |
| 数学渲染 | KaTeX + remark-math + rehype-katex |
| 富文本 | TipTap + react-markdown |
| 图表 | Recharts 3 |
| 国际化 | i18next (中英双语) |
| 数据库 | SQLite (开发) / PostgreSQL (生产) |

## 版本方案

| | Free | Solo | Plus | Pro |
|------|------|------|------|------|
| **定位** | 免费体验 | AI 智能学习 | 机构教学平台 | 企业旗舰 · 含学生收费 |
| **价格** | ¥0 | ¥299/月 | ¥1,299/月 | ¥3,999/月 |
| **学员上限** | 30 | 50 | 200 | 不限 |
| **教师数** | 1 | 1 | 5 | 不限 |
| 习题训练 · 考试 | ✓ | ✓ | ✓ | ✓ |
| 错题复盘 | ✓ | ✓ | ✓ | ✓ |
| 基础统计 | ✓ | ✓ | ✓ | ✓ |
| AI 生成题目 | 20次/月 | 无限制 | 无限制 | 无限制 |
| Memorix 记忆复习 | — | ✓ | ✓ | ✓ |
| 完整学情报告 | — | ✓ | ✓ | ✓ |
| 知识图谱 | — | ✓ | ✓ | ✓ |
| AI 学习助手 | — | ✓ | ✓ | ✓ |
| 视频课程 + AI 大纲 | — | — | ✓ | ✓ |
| 答疑系统 | — | — | ✓ | ✓ |
| 多教师协作 | — | — | ✓ | ✓ |
| 自习室 | — | — | ✓ | ✓ |
| 模拟考试 | — | — | ✓ | ✓ |
| 班级对比 · 数据导出 | — | — | ✓ | ✓ |
| 品牌定制 · 白标 | — | — | — | ✓ |
| API 接入 | — | — | — | ✓ |
| 学生端收费 · 自主定价 | — | — | — | ✓ |

---

## 技术亮点

| 特性 | 技术实现 |
|------|---------|
| AI 引擎 | DeepSeek V4 原生 API，按任务智能分配 v4-pro(思考)/v4-flash(快速) |
| 思考模式 | Reviewer/Grader 任务开启 Chain-of-Thought，effort 可调(high/max) |
| 熔断保护 | 按任务类型粒度熔断，单模型故障不扩散 |
| 记忆算法 | FSRS v4.5 + Memorix 双轨，Weibull 遗忘曲线 + 在线 SGD |
| 出题管线 | 3-Agent 对抗性博弈，支持迭代改进与人工审核 |
| Prompt 管理 | 统一文件系统 + 数据库版本历史，支持一键回滚 |
| 大文件上传 | 分片上传 + 断点续传，支持 100MB+ 视频文件 |
| 实时通信 | Django Channels + Redis，WebSocket 毫秒级推送 |
| 异步任务 | Celery 分布式任务队列，自动重试 + Celery Beat 定时调度 |
| 智能大纲 | ASR 可插拔架构 (Vosk/Whisper/GLM)，离线至云端多方案覆盖 |
| 对抗出题 | 3-Agent 管线博弈，Reviewer 四维质量评分，最多 3 轮迭代修改 |
| 权限体系 | RBAC + 细粒度功能权限 + 机构数据隔离 |

---

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

# 配置环境变量
cp .env.example .env
# 编辑 .env，填入 DEEPSEEK_API_KEY

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
     │  :8000   │ │  :8001   │ │  :8002   │
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
# 至少需要配置: DJANGO_ENV, SECRET_KEY, ALLOWED_HOSTS, DB_*, DEEPSEEK_API_KEY, CORS_*
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

# 导入知识树
python manage.py import_knowledge_tree --force
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
    -p 8000 \
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
upstream unimind_backend {
    least_conn;
    server 127.0.0.1:8000;
    # 如需多进程负载均衡，添加更多 upstream server
    # server 127.0.0.1:8001;
    # server 127.0.0.1:8002;
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
    ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256;
    ssl_prefer_server_ciphers off;

    # 安全响应头
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains; preload" always;
    add_header X-Frame-Options "DENY" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;

    # 文件上传限制
    client_max_body_size 200M;
    client_body_timeout 300s;

    # 静态文件
    location /static/ {
        alias /opt/unimind/backend/staticfiles/;
        expires 30d;
        add_header Cache-Control "public, immutable";
    }

    location /media/ {
        alias /opt/unimind/backend/media/;
        expires 7d;
    }

    # 前端构建产物
    location /assets/ {
        alias /opt/unimind/frontend/dist/assets/;
        expires 30d;
        add_header Cache-Control "public, immutable";
    }

    # 前端入口
    location / {
        root /opt/unimind/frontend/dist;
        try_files $uri $uri/ /index.html;
    }

    # API 代理 (HTTP + WebSocket)
    location /api/ {
        proxy_pass http://unimind_backend;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 120s;
        proxy_send_timeout 120s;
    }

    # WebSocket 专用路径
    location /ws/ {
        proxy_pass http://unimind_backend;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 3600s;
        proxy_send_timeout 3600s;
    }

    # 禁止访问隐藏文件
    location ~ /\.(?!well-known) {
        deny all;
    }
}
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
- [ ] DEEPSEEK_API_KEY 有效
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
DEEPSEEK_API_KEY=sk-xxx                          # 从 https://platform.deepseek.com/api_keys 获取
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
# 全局模型覆盖 — 不设置则使用 ai_engine/config.py 中的按任务路由默认值
LLM_MODEL=deepseek-v4-pro
LLM_BASE_URL=https://api.deepseek.com
LLM_REQUEST_TIMEOUT_SECONDS=120
LLM_REQUEST_MAX_RETRIES=1
```

> **模型路由已收敛至 `ai_engine/config.py`**，按 operation 名称逐段匹配，决定 flash / pro / thinking。
> 只需设置 `LLM_MODEL` 即可全局覆盖所有任务的默认模型；如无特殊需求，无需其他配置。

**模型策略速查：**

| 任务 | 默认模型 | 思考 | 原因 |
|------|---------|------|------|
| 对话 / 面试 | v4-flash | 关 | 快速响应 |
| 出题 Author / 生成 | v4-pro | 关 | 高质量内容创作 |
| 出题 Author Revise | v4-pro | 开(medium) | 基于审题反馈修订 |
| 出题 Reviewer | v4-pro | 开(high) | 深度逻辑检查 |
| 主观题判分 | v4-pro | 关 | 结构化 JSON 输出，无需链式推理 |
| 作文评分 | v4-pro | 开(max) | 最高强度多维推理 |
| 解析 / 分类 | v4-flash | 关 | 轻量文本处理 |
| Schema 修复 | v4-flash | 关 | JSON 格式修复 |

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

# Memorix (设为 true 启用)
USE_MEMORIX=false

# GIPHY
GIPHY_API_KEY=                                    # 自习室 GIF 功能
```

---

## 配置指南

### Prompt 模板管理

所有 AI Prompt 模板以 `.txt` 文件形式存放在 `backend/prompts/` 目录：

```
prompts/
├── quizzes/          # 题库生成相关 Prompt
├── ai_assistant/     # AI 助教对话 Prompt
│   └── bots/         #   各 Bot 独立 Prompt
├── pipeline/         # 出题管线 Agent Prompt
│   ├── author_generate.txt
│   ├── reviewer_single.txt
│   ├── reviewer_adversarial.txt
│   ├── classifier.txt
│   └── distractor.txt
├── grading/          # 评分 Prompt
└── interviews/       # 面试 Prompt
```

修改方式：
1. **管理后台** → Prompt模板 → 选择命名空间 → 编辑 → 保存（自动生成版本历史）
2. **直接编辑文件** → 重启后端生效

版本历史通过 `PromptTemplateVersion` 数据库表追踪，支持一键回滚。

### 知识点管理

所有功能（题库、课程、文章、知识地图、AI出题）的知识点数据均来自 **`backend/knowledge_tree.md`**。修改后运行导入命令即可更新全系统。

```bash
# 修改 knowledge_tree.md 后，运行此命令更新所有功能
python manage.py import_knowledge_tree --force

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

### 重启服务

```bash
sudo systemctl restart unimind.service unimind-celery.service
```

### 查看日志

```bash
sudo journalctl -u unimind.service -f       # Daphne 日志
sudo journalctl -u unimind-celery.service -f # Celery 日志
```

---

## 安全注意事项

- **SECRET_KEY**：生产环境必须设置为至少 64 字符的随机值，可用 `python -c "import secrets; print(secrets.token_urlsafe(64))"` 生成
- **API Key**：所有第三方 API Key（DeepSeek、Gmail、GIPHY、ASR）必须通过环境变量注入，不得提交到版本控制
- **数据库密码**：使用强随机密码，不要与其他系统重复
- **HTTPS**：生产环境必须启用 HTTPS，建议使用 Let's Encrypt
- **支付密钥**：支付宝/微信支付私钥属于高敏感信息，建议生产环境使用密钥管理服务（如 HashiCorp Vault），`.env` 文件权限设为 `600`
- **令牌管理**：当前使用 DRF Token Authentication，生产环境建议迁移到 JWT (`djangorestframework-simplejwt`) 实现令牌过期和刷新机制
- **速率限制**：登录、注册、验证码发送端点已启用速率限制（基于 Django cache 的滑动窗口算法），AI 生成端点建议在 Nginx 层额外添加速率限制
- **文件上传**：分片上传已校验分片大小和块数有效性，生产环境建议在反向代理层添加文件类型白名单
- **XSS 防护**：系统使用 React JSX 转义 + TipTap HTML 过滤，渲染用户生成内容时应注意额外消毒

---

## License

Proprietary. All rights reserved.
