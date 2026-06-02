# UniMind 域名切换指南

## 当前状态

| 域名 | 备案 | SSL | 状态 |
|------|------|-----|------|
| korsonedu.com | ✅ 已备案 | ✅ Let's Encrypt | **当前使用** |
| unimind-ai.com | ❌ 未备案 | ✅ Let's Encrypt | 待备案后切换 |

## 快速切换

### 切换到 korsonedu.com（临时方案）

```bash
# 1. 本地配置
./scripts/domain-config.sh korsonedu.com

# 2. 服务器配置
ssh root@47.104.77.217
sed -i 's|^SESSION_COOKIE_DOMAIN=.*|SESSION_COOKIE_DOMAIN=.korsonedu.com|' /opt/unimind/backend/.env
sed -i 's|^CSRF_COOKIE_DOMAIN=.*|CSRF_COOKIE_DOMAIN=.korsonedu.com|' /opt/unimind/backend/.env
systemctl restart unimind.service

# 3. 重新构建前端
cd frontend && npm run build

# 4. 上传到服务器
scp -r dist/* root@47.104.77.217:/opt/unimind/frontend/dist/
```

### 切换到 unimind-ai.com（备案完成后）

```bash
# 1. 本地配置
./scripts/domain-config.sh unimind-ai.com

# 2. 服务器配置
ssh root@47.104.77.217
sed -i 's|^SESSION_COOKIE_DOMAIN=.*|SESSION_COOKIE_DOMAIN=.unimind-ai.com|' /opt/unimind/backend/.env
sed -i 's|^CSRF_COOKIE_DOMAIN=.*|CSRF_COOKIE_DOMAIN=.unimind-ai.com|' /opt/unimind/backend/.env
systemctl restart unimind.service

# 3. 重新构建前端
cd frontend && npm run build

# 4. 上传到服务器
scp -r dist/* root@47.104.77.217:/opt/unimind/frontend/dist/
```

## 配置文件说明

### 本地配置

- `domain.env` - 当前活跃域名配置
- `frontend/.env` - 前端 API 地址（`VITE_API_URL`）

### 服务器配置

- `/opt/unimind/backend/.env` - 后端配置
  - `SESSION_COOKIE_DOMAIN` - Session Cookie 域名
  - `CSRF_COOKIE_DOMAIN` - CSRF Cookie 域名
  - `CORS_ALLOWED_ORIGINS` - 允许的前端域名
  - `CSRF_TRUSTED_ORIGINS` - 信任的 CSRF 来源

### Nginx 配置

- `/etc/nginx/sites-enabled/unimind-ai.com.conf` - unimind-ai.com 配置
- `/etc/nginx/sites-enabled/www.korsonedu.com.conf` - korsonedu.com 配置

两个配置都已指向同一后端应用，无需修改。

## SSL 证书

### korsonedu.com

```bash
# 证书位置
/etc/letsencrypt/live/www.korsonedu.com/fullchain.pem
/etc/letsencrypt/live/www.korsonedu.com/privkey.pem

# 续期
certbot renew
```

### unimind-ai.com

```bash
# 证书位置（包含裸域名和 www）
/etc/letsencrypt/live/unimind-ai.com-0001/fullchain.pem
/etc/letsencrypt/live/unimind-ai.com-0001/privkey.pem

# 续期
certbot renew
```

## DNS 配置

### korsonedu.com

| 主机记录 | 类型 | 记录值 |
|---------|------|--------|
| `@` | A | 47.104.77.217 |
| `www` | A | 47.104.77.217 |

### unimind-ai.com

| 主机记录 | 类型 | 记录值 |
|---------|------|--------|
| `@` | A | 47.104.77.217 |
| `www` | A | 47.104.77.217 |

## 故障排查

### Cookie 不共享

检查 `SESSION_COOKIE_DOMAIN` 是否正确：
```bash
ssh root@47.104.77.217
grep 'SESSION_COOKIE_DOMAIN' /opt/unimind/backend/.env
```

### CORS 错误

检查 `CORS_ALLOWED_ORIGINS` 是否包含当前域名：
```bash
ssh root@47.104.77.217
grep 'CORS_ALLOWED_ORIGINS' /opt/unimind/backend/.env
```

### SSL 证书问题

检查证书是否包含当前域名：
```bash
ssh root@47.104.77.217
openssl x509 -in /etc/letsencrypt/live/www.korsonedu.com/fullchain.pem -noout -text | grep -A5 "Subject Alternative Name"
```

## 后续计划

1. **短期**：使用 korsonedu.com 作为临时方案
2. **中期**：完成 unimind-ai.com 的 ICP 备案
3. **长期**：切换回 unimind-ai.com，保留 korsonedu.com 作为备用

## 联系方式

如有问题，请联系运维团队。
