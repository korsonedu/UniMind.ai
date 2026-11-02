# UniMind 登录会话

UniMind 网页和 App 每次登录分别签发 `LoginSession`，通过原有 HttpOnly `auth_token` Cookie 传递，最长有效期为 30 天。退出仅删除当前凭据。官网仍使用独立的 `/account-api/` 会话，通过 UniMind 账号的 OIDC 流程登录。

浏览器中的账号会话可用于展示已有账号卡片。用户点击卡片后，才为本次请求的产品完成登录。官网退出不会清除 UniMind 会话；账号选择不再顺带改写 UniMind 网页凭据。修改密码和停用账号仍撤销相关会话。

## 发布

1. 备份并执行 `python manage.py migrate`，新增 `users.0077_login_session` 表。
2. 发布匹配的后端、账号静态资源和 UniMind 前端。App 的现有登录桥接可直接使用，不需要更换安装包。
3. 官网的 `fix/website-unimind-account-entry` 分支在独立检出目录 `.worktrees/korson-independent-login`。发布该变更后，官网的登录、注册入口统一走 `/account-api/`，不再受构建开关控制。确认官网代理可用。

旧版本的共享 DRF Token 不再接受为浏览器 Cookie。旧网页和 App 会需要重新登录一次，以获得独立会话；既有 OIDC 官网会话保留。授权头的旧 DRF Token 兼容路径保留，不会被普通网页或 App 的登录覆盖。

发布后检查：两个端同时登录、单端退出后另一个端仍可访问、官网退出后刷新仍为未登录、账号卡片点击后的官网回跳及 App 回流。
