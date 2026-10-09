# 科晟账号第一期交付说明

本期在现有 main 上开发，官网与 UniMind 复用原 Django User，没有另建学生身份库。代码尚未推送、部署，未迁移现有开发库或生产库。

## 已完成范围

官网顶栏和移动导航增加登录／注册入口，登录后显示我的账号。`/account` 提供基础身份、退出官网、账号安全及 UniMind 入口。页面沿用官网纸色、黑色与红色设计变量；昵称和邮箱以文本写入。

统一账号页提供原用户名／邮箱密码登录、邮箱验证注册、找回密码、账号信息与退出全部服务。注册默认为免费学生，无机构、非会员。原账号 ID、密码、平台 Token 和学习记录沿用；遇到原用户名与他人邮箱重名时，原用户名优先。

官网采用 OIDC 授权码、PKCE、RS256 签名和服务端会话。官网 Cookie 与认证中心会话分开，平台长期 Token 不进入官网存储。已有 UniMind 有效 Cookie 可衔接账号中心；两端账号不同时先确认，再通过带 CSRF 的 POST 切换当前浏览器。

有权进入的用户沿用已有平台 Token。React 回调读取实际身份并清除旧账号缓存后进入平台。免费账号在新入口显示服务未开通和联系我们，不自动获得学习权限。这里复用当前会员／机构准入规则，尚未实施新的课程范围授权。

退出官网只结束官网会话。退出全部服务、改密码或停用账号会增加会话版本并撤销旧平台 Token、授权码及 OAuth 凭据。授权码签发和交换包含版本检查，避免旧请求在全端退出后恢复有效登录。

## 本地预览

官网：<http://localhost:4321/account>。认证中心：<http://localhost:8000/accounts/login/>。UniMind 前端：<http://localhost:5173/>。使用同一个 localhost 主机名完成往返，不混用 localhost 与 127.0.0.1 的 Cookie。

账号后端当前使用单独的 `.superpowers/sdd/2026-10-08-korson-account/accounts-local.sqlite3`。现有真实账号未复制进入，因此本地演示需使用示例账号，无法在这个隔离库直接验证你的真实账号密码。

| 示例账号 | 状态 | 本地密码 |
| --- | --- | --- |
| account-local-free | 免费、无机构 | LocalPass12345 |
| account-local-paid | 示例已开通、无机构 | LocalPass12345 |

隔离进程模拟邮件，不发送真实邮件；注册与重置密码演示验证码为 `123456`。只用于此本地进程，正式实现仍生成随机验证码并使用既有 SMTP。重启后模拟验证码缓存清空，需要重新发送。示例账号可进入现有的机构加入引导，但本期没有自动入机构。

重启隔离后端：

```bash
cd /Users/eular/Desktop/科晟开发/UniMind/UniMindCode
bash .superpowers/sdd/2026-10-08-korson-account/run-local.sh
```

UniMind 本地前端：

```bash
cd /Users/eular/Desktop/科晟开发/UniMind/UniMindCode/frontend
node node_modules/vite/bin/vite.js --host 127.0.0.1 --port 5173 --strictPort
```

官网沿用你的现有开发进程，无需切换分支。Astro 开发代理仅覆盖 `/account-api/`，默认指向本机 Django 8000。已有依赖搬迁后缺少执行权限，本次只恢复 esbuild 二进制的执行位；未改你的启动脚本。

## 验证记录

2026 年 10 月 9 日：33 项账号定向检查通过，测试数据库为内存 SQLite。覆盖注册默认状态、验证码用途和消费、锁定、CSRF、禁用开关、独立 Cookie、旧 Token 保留、账号冲突、免费入口、全端撤销和真实 provider 授权码交换。state、PKCE、nonce、issuer、audience 和重放负面检查通过。

官网构建通过，70 个 Astro 文件的最终类型诊断为零错误、零警告。UniMind 前端类型检查和构建通过；回调修复后再次通过类型检查。两处仓库 diff 格式检查通过。只保留一个账号测试文件，未运行整站回归或新增浏览器测试项目。

Chrome 现有官网页面已看到登录／注册入口。为避免打断你的浏览器操作，后续使用同一 localhost 服务的内置浏览器验证：登录返回官网、进入 UniMind 不再输入密码、返回官网保持身份、退出全部服务回到匿名状态，以及免费账号提示暂未开通。移动导航入口也已检查。注册与重置密码通过模块测试验证，未向真实学生邮箱发送邮件。

一次独立只读审查发现的旧用户名冲突、回调重登录地址和未启用时原入口兼容问题已处理。PostgreSQL／Redis 多进程并发尚未实测，不能用 SQLite 测试结果替代生产并发验收。

## 生产启用前

1. 先备份原数据库，运行只读 `audit_account_emails`，人工处理重复已验证邮箱。命令只输出重复组数和用户 ID，不自动合并、删除账号。
2. 安装固定版本依赖，应用 `users/0069` 和 OAuth Toolkit 迁移。新增 User 字段要求随代码升级执行迁移；关闭账号开关不能替代数据库迁移。
3. 配置专用 RSA 私钥、至少 32 字符客户端 secret、确切 issuer／官网 origins／UniMind origin，并使用共享 Redis。私钥与 secret 不进入 Git、浏览器或公开环境变量。
4. 使用 `configure_account_client` 创建固定授权码客户端。命令不会静默覆盖不同的已有配置或轮换密钥。
5. 核实官网到 Django 的真实代理上游、私网或 TLS 连接和受信任代理边界。当前 Nginx 仅有未启用说明块，无生产可用代理。代理须保留官网 Host、真实协议、可信来源 IP，禁止缓存账号响应。
6. 先确保后端、数据库、静态账号资源和代理就绪，再启用后端 `ACCOUNT_ENABLED=true` 并以 `PUBLIC_ACCOUNT_ENABLED=true` 构建官网。生产默认仍保留旧 UniMind 入口，避免单独发布官网时把旧入口改坏。生产前端如认证中心另设域名，配置 `VITE_ACCOUNT_CENTER_ORIGIN`。

收藏、付费权益管理、科晟机构自动加入和课程范围权限不在本期。后续应在 UniMind 管理服务权益，Directus 继续管理官网内容；具体权限与自动加入按已保存设计另行实施。
