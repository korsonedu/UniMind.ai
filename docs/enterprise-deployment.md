# UniMind 企业版本地部署指南

> 企业版 = 源码交付 + 客户自行部署运维 + 可选付费技术支持。
> 核心引擎（Memorix、AI 管线、Agent 运行时）与 SaaS 版共享同一代码库。

## 硬件要求

| 环境 | CPU | 内存 | 磁盘 | 说明 |
|------|-----|------|------|------|
| 最小部署 | 2 核 | 4 GB | 20 GB | 适合小团队（<50 学员） |
| 推荐部署 | 4 核 | 8 GB | 50 GB | 适合中型机构（50-500 学员） |
| 大规模 | 8 核+ | 16 GB+ | 100 GB+ | 500+ 学员，建议扩展 Worker |

## 依赖服务

- **PostgreSQL** 14+
- **Redis** 6+
- LLM API Key（DeepSeek / OpenAI 兼容接口）

## 部署步骤

### 1. 获取源码

```bash
git clone <repo-url> /opt/unimind
cd /opt/unimind/UniMindCode
```

### 2. 环境变量

复制并编辑 `.env`：

```bash
cp .env.example .env
```

必填项：

```bash
DJANGO_ENV=production
SECRET_KEY=<生成 64 位随机字符串>
ALLOWED_HOSTS=your-domain.com
LLM_API_KEY=sk-xxx

DB_ENGINE=django.db.backends.postgresql
DB_NAME=unimind
DB_USER=unimind
DB_PASSWORD=<strong-password>
DB_HOST=localhost
DB_PORT=5432

REDIS_URL=redis://:password@localhost:6379/0
CACHE_REDIS_URL=redis://:password@localhost:6379/1
```

### 3. 模块开关

通过 `ENABLED_APPS` 环境变量控制启用哪些 Django app：

```bash
# 全部启用（默认）
ENABLED_APPS=all

# 仅启用核心模块
ENABLED_APPS=users,quizzes,courses,ai_assistant,ai_engine

# 企业版精简（不要支付、自习室、文章、面试、FAQ）
ENABLED_APPS=core,users,quizzes,courses,ai_assistant,ai_engine,notifications
```

### 4. 数据库初始化

```bash
cd backend
python3 manage.py migrate
python3 manage.py seed_xiaoyu
python3 manage.py seed_exam_agent
```

### 5. 静态文件 & 前端构建

```bash
cd frontend
npm install
npm run build

cd ../backend
python3 manage.py collectstatic --noinput
```

### 6. 启动服务

**Docker Compose（推荐）：**

```yaml
# docker-compose.yml
version: '3.8'
services:
  db:
    image: postgres:15
    environment:
      POSTGRES_DB: unimind
      POSTGRES_USER: unimind
      POSTGRES_PASSWORD: ${DB_PASSWORD}
    volumes:
      - pgdata:/var/lib/postgresql/data

  redis:
    image: redis:7-alpine
    command: redis-server --requirepass ${REDIS_PASSWORD}

  web:
    build: .
    ports:
      - "8000:8000"
    env_file: .env
    depends_on: [db, redis]

  celery:
    build: .
    command: celery -A school_system worker -l info
    env_file: .env
    depends_on: [db, redis]

volumes:
  pgdata:
```

**Systemd（备选）：**

```ini
# /etc/systemd/system/unimind.service
[Unit]
Description=UniMind Django
After=network.target postgresql.service redis.service

[Service]
User=unimind
WorkingDirectory=/opt/unimind/UniMindCode/backend
Environment=PATH=/opt/unimind/venv/bin:/usr/bin
ExecStart=/opt/unimind/venv/bin/gunicorn school_system.wsgi:application -b 127.0.0.1:8000
Restart=always

[Install]
WantedBy=multi-user.target
```

### 7. Nginx 反向代理

```nginx
server {
    listen 443 ssl;
    server_name your-domain.com;

    ssl_certificate /etc/ssl/certs/your-domain.crt;
    ssl_certificate_key /etc/ssl/private/your-domain.key;

    location /static/ {
        alias /opt/unimind/UniMindCode/backend/staticfiles/;
    }

    location /media/ {
        alias /opt/unimind/UniMindCode/backend/media/;
    }

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

## 备份策略

```bash
# 每日自动备份（crontab）
0 3 * * * cd /opt/unimind/UniMindCode && make backup

# 手动备份
pg_dump -U unimind unimind | gzip > backup_$(date +%Y%m%d).sql.gz

# 恢复
gunzip -c backup_20260101.sql.gz | psql -U unimind unimind
```

备份保留策略：自动清理 30 天前的备份文件。

## 升级步骤

```bash
cd /opt/unimind/UniMindCode
git pull origin main
cd frontend && npm install && npm run build
cd ../backend
python3 manage.py migrate
python3 manage.py collectstatic --noinput
sudo systemctl restart unimind.service unimind-celery.service
```

## 品牌定制

登录机构管理后台 → 品牌设置：
- **Logo**: 上传机构 Logo（方形，建议 256×256）
- **主题色**: 选择品牌主色（默认 `#6366f1`）
- **机构名称**: 显示在页面标题和邮件中
- **自定义域名**（企业版专属）: 绑定 `your-domain.com`，配置 DNS CNAME 指向部署服务器

## Agent 扩展开发

新增自定义 Bot（三步法，详见 CLAUDE.md）：

1. 写 prompt 文件到 `backend/prompts/ai_assistant/bots/{name}/`（至少含 `system_prompt.txt` + `tool_guide.txt`）
2. 在 `backend/ai_assistant/bot_registry.py` 的 `BOT_REGISTRY` 注册
3. （可选）写 `ToolExecutor` 子类

## 故障排查

| 问题 | 检查项 |
|------|--------|
| 502 Bad Gateway | `systemctl status unimind`；检查 Gunicorn 是否启动 |
| 数据库连接失败 | `pg_isready -U unimind`；检查 `DB_HOST`/`DB_PASSWORD` |
| AI 调用失败 | 检查 `LLM_API_KEY`；查看 Celery worker 日志 |
| 静态文件 404 | 检查 `STATIC_ROOT` 路径；重新 `collectstatic` |

## 安全注意事项

- **禁止在生产环境使用 `DJANGO_ENV=development`**
- `SECRET_KEY` 必须随机生成，不得用默认值
- Redis 必须设置密码
- PostgreSQL 使用强密码，限制 IP 访问
- 定期更新依赖：`pip install --upgrade -r requirements.txt`
- 开启 HTTPS，禁止 HTTP 明文传输 Cookie

## 从 SaaS 迁移到企业版

SaaS 版数据可通过 Django dumpdata/loaddata 导出导入。联系技术支持获取迁移脚本。
