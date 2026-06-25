# PgBouncer 部署指南

PgBouncer 是轻量级 PostgreSQL 连接池，在 Django `CONN_MAX_AGE` 之上提供连接复用。生产环境建议 **transaction pooling** 模式。

## 为什么需要

| 场景 | 无连接池 | 有 PgBouncer |
|------|---------|-------------|
| 1000 用户 WebSocket | ~200 idle 连接 | ~20 活跃复用 |
| Celery 突发任务 | 每 worker 持连接 | 用完即还 |
| Django + Channels | ASGI 不归还 | transaction 结束归还 |

## 安装

```bash
sudo apt install pgbouncer          # Ubuntu/Debian
brew install pgbouncer              # macOS 开发
```

## 配置

`/etc/pgbouncer/pgbouncer.ini`:

```ini
[databases]
unimind = host=127.0.0.1 port=5432 dbname=unimind

[pgbouncer]
listen_addr = 127.0.0.1
listen_port = 6432
auth_type = scram-sha-256
auth_file = /etc/pgbouncer/userlist.txt

pool_mode = transaction
max_client_conn = 500
default_pool_size = 25
max_db_connections = 50

server_idle_timeout = 600
client_idle_timeout = 0

log_connections = 0
log_disconnections = 0
stats_period = 60
```

## Django 对接

```python
DATABASES = {
    "default": {
        "HOST": os.getenv("DB_HOST", "127.0.0.1"),
        "PORT": os.getenv("DB_PORT", "6432"),  # PgBouncer
        "CONN_MAX_AGE": 120,
        "CONN_HEALTH_CHECKS": True,
    }
}
```

## 验证

```bash
sudo systemctl start pgbouncer
psql -h 127.0.0.1 -p 6432 -U pgbouncer pgbouncer -c "SHOW POOLS;"
python manage.py check --deploy
```

## 注意事项

1. transaction pooling 不支持 prepared statements — Django 默认已关闭
2. Celery worker 建议 `CONN_MAX_AGE=0`
3. migration 建议走直连 PostgreSQL，避免 DDL 受事务池影响
