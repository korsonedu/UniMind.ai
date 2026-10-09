# 科晟统一账号 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 官网注册、登录和管理账号复用现有 UniMind 用户，有效会话跨站进入时免再次输入密码，新注册账号不自动获得学习权限。

**Architecture:** UniMind 的 Django 用户表继续作为唯一身份来源，在现有后端提供独立的“科晟账号”页面和 OIDC 授权服务。官网保留 Astro 静态发布，通过 `/account-api/` 接入服务端授权码回调和官网会话；UniMind 同一后端复用认证中心会话，兼容现有 HttpOnly Cookie。两个域名各自保存会话，不共享域 Cookie，不建设第二套用户库。

**Tech Stack:** Django 6.0.2、DRF、Django OAuth Toolkit 3.4.1、Authlib 1.8.0、Astro、React、现有数据库和共享缓存。

**Spec:** `docs/superpowers/specs/2026-10-07-korson-student-access-design.md` 的“第二项：统一登录衔接”。本次按用户“开始做账号”调整交付顺序，先做账号，权益管理和收藏分别交付。

状态：待用户审阅。本文件为实施计划，尚未修改认证代码、安装依赖、执行迁移或接通登录。

## Global Constraints

- 代码只在现有 main 上修改，保留当前所有用户改动，不创建工作树或功能分支。
- 不在生产数据库上执行未经确认的迁移或批量变更。
- 官网新注册用户不自动入机构，不开通会员，不改变机构套餐。
- 已有 UniMind 用户继续使用原用户 ID、密码与学习记录，不创建第二套账号。
- 官网会话只服务官网身份与收藏，不把 UniMind 长期 Token 放进 URL 或浏览器 localStorage。
- 学生、机构、课程及权益管理放在 UniMind 管理端。Directus 只维护官网内容与择校资料。
- 仅做与账号、权益和机构变更直接相关的验证，不运行整站反复回归，不新增临时测试页面。
- 本次不实现收藏、支付、服务包、学员权益后台或自动加入机构，不推送 GitHub，不部署。
- 不改官网当前未提交的 `src/pages/about.astro`、`src/components/Footer.astro`；不改 UniMind 当前未提交的 `backend/manage.py`、`scripts/`、品牌资料和产品手册。

## Review Focus

1. 同一浏览器使用 localhost 的不同端口，官网会话 Cookie 与认证中心 Cookie 必须保持独立。
2. 已有两个用户具有同一已验证邮箱时，不自动合并，不擅自选其中一个，不修改学习记录。
3. 同时打开两个登录页、刷新回调和重复点击注册时，不串账号，不重复消费授权码或邮箱验证码。
4. 已有 UniMind Cookie 与认证中心属于不同账号时，不默默覆盖身份，需要明确选择账号。
5. 密码重置、停用账号及“退出全部服务”后，另一端旧会话和待消费授权码不能恢复登录。

以上五项分别由任务 1、2、3、4、5 的定向检查覆盖。

## 固定入口与页面范围

官网新增 `/account`，顶栏和移动导航增加“登录／注册”，登录后显示“我的账号”。公开择校页保持免登录。

认证中心暂挂在现有 UniMind 后端 `/accounts/` 下，页面统一标注“科晟账号”，只展示登录、注册、找回密码和账号信息，不展示学习首页。生产独立账号域名不在本次设置；浏览器登录时会短暂跳转至现有 UniMind 域名的账号页面，完成后返回官网。

| 路径 | 方法 | 职责 |
| --- | --- | --- |
| 官网 `/account-api/login/` | GET | 发起授权，保存 state、nonce、PKCE 与返回页 |
| 官网 `/account-api/callback/` | GET | 校验授权响应，建立官网会话，再跳转至原页 |
| 官网 `/account-api/session/` | GET | 返回本人基础信息与 CSRF Token，不返回平台 Token |
| 官网 `/account-api/logout/` | POST | 仅清除官网会话，保留其他服务会话 |
| 认证中心 `/accounts/login/` | GET、POST | 邮箱或原用户名加密码，建立认证中心会话 |
| 认证中心 `/accounts/register/` | GET、POST | 邮箱验证、密码、昵称和协议同意 |
| 认证中心 `/accounts/send-code/` | POST | 只允许 register、reset_password 两种用途 |
| 认证中心 `/accounts/reset-password/` | GET、POST | 邮箱验证码重置密码，撤销旧会话 |
| 认证中心 `/accounts/profile/` | GET | 本人账号信息及退出全部服务入口 |
| 认证中心 `/accounts/logout-all/` | POST | 撤销该用户全部账号会话及令牌 |
| 认证中心 `/accounts/unimind/` | GET、POST | 进入 UniMind 的账号确认与兼容 Cookie 建立 |
| 认证中心 `/accounts/o/` | 按协议 | OIDC discovery、JWKS、authorize、token、userinfo |
| UniMind `/account-callback` | GET | 重新获取 `/api/users/me/`，更新前端用户状态 |

写请求均要求 CSRF。登录后的返回页只接受站内相对路径；授权回调地址从服务端配置读取，不能由请求者指定。身份响应和账号页使用 `Cache-Control: no-store`，回调页使用 `Referrer-Policy: no-referrer`。

## 文件与职责

UniMind 根目录：`/Users/eular/Desktop/科晟开发/UniMind/UniMindCode`。

- `backend/users/accounts/__init__.py`：账号模块。
- `backend/users/accounts/forms.py`：邮箱、密码、协议及重定向字段校验。
- `backend/users/accounts/services.py`：验证码、账号创建、认证及会话撤销；不操作机构和会员。
- `backend/users/accounts/views.py`、`urls.py`：中性账号页面与官网会话接口。
- `backend/users/accounts/middleware.py`：按固定路径选择会话 Cookie，检查会话版本和来源边界。
- `backend/users/accounts/oidc.py`：身份声明、官网 OAuth 客户端及固定回调。
- `backend/users/accounts/signals.py`：密码变更和账号停用时撤销认证凭据。
- `backend/users/templates/users/accounts/base.html`、`form.html`、`profile.html`：账号界面，沿用科晟文字与视觉，不放学习导航。
- `backend/users/static/users/accounts.css`：账号页面样式。
- `backend/users/test_accounts.py`：集中保存账号定向检查，不生成临时页面。
- `backend/users/management/commands/audit_account_emails.py`：只读检查已验证邮箱重复情况。
- `backend/users/management/commands/configure_account_client.py`：幂等配置官网授权客户端，凭据从环境读取。
- `backend/users/models.py`、新增 migration：会话版本和已验证邮箱唯一约束。
- `backend/users/apps.py`：注册账号安全信号。
- `backend/users/views.py`：仅处理旧注册和验证码建号路径的邮箱唯一冲突，不重构整个文件。
- `backend/school_system/settings.py`、`urls.py`、`backend/requirements.txt`：认证库、受信任来源、路由与功能开关。
- `frontend/src/pages/AccountCallback.tsx`、`frontend/src/App.tsx`：建立会话后的前端身份刷新。

官网根目录：`/Users/eular/Desktop/科晟开发/官网`。

- `src/pages/account.astro`：官网账号页。
- `src/components/Header.astro`：账号入口；保留现有导航与咨询入口。
- `src/lib/account.ts`：会话读取、退出官网和登录跳转，不保存长期令牌。
- `src/styles/account.css`：沿用现有颜色、字体、圆角和间距。
- `astro.config.mjs`：仅增加本地 `/account-api/` 代理，不改静态输出。
- `deploy/nginx.conf`：官网账号 API 的代理模板，不直接修改生产 Nginx。

## Task 1：认证配置、会话隔离与安全开关

**Files:** requirements、settings、urls、models、新增 migration、accounts/middleware.py、accounts/oidc.py、test_accounts.py、两个管理命令。

**Interfaces:**

- `User.account_session_version: int`，默认 0，只用于撤销会话，不表示权限。
- 会话记录 `account_user_id`、`account_session_version`、`account_audience`，audience 为 `website` 或 `account`。
- `begin_account_session(request, user, *, audience: str) -> None`：使用 Django `login()` 轮换会话 ID，再保存版本与 audience。
- `account_is_current(request, *, audience: str) -> bool`：要求活跃用户、匹配 audience、匹配数据库版本。
- `KorsonOAuth2Validator`：继承库的验证器，身份主键使用现有用户 ID。

- [ ] Step 1：增加定向检查，账号安全开关关闭时原路由和 Cookie 行为保持；官网 Cookie 不可作为认证中心会话使用。

```python
def test_website_cookie_is_not_account_cookie(self):
    user = User.objects.create_user(username="existing", password="Pass12345")
    self.client.force_login(user)
    original = self.client.cookies["sessionid"].value
    response = self.client.get("/account-api/session/")
    self.assertEqual(response.json()["user"], None)
    self.assertEqual(self.client.cookies["sessionid"].value, original)
```

- [ ] Step 2：先运行该检查，确认缺少新路由时失败。新增依赖保持显式版本，启用 `oauth2_provider` 时在企业模块裁剪中保留它；账号开关默认关闭，开关开启且配置缺失时直接报告配置错误。

```python
OAUTH2_PROVIDER = {
    "OIDC_ENABLED": True,
    "OIDC_RSA_PRIVATE_KEY": os.getenv("ACCOUNT_OIDC_RSA_PRIVATE_KEY"),
    "OIDC_ISS_ENDPOINT": os.getenv("ACCOUNT_ISSUER_URL"),
    "OAUTH2_VALIDATOR_CLASS": "users.accounts.oidc.KorsonOAuth2Validator",
    "PKCE_REQUIRED": True,
    "SCOPES": {"openid": "账号身份", "profile": "账号基础信息", "email": "邮箱"},
    "AUTHORIZATION_CODE_EXPIRE_SECONDS": 60,
    "ACCESS_TOKEN_EXPIRE_SECONDS": 300,
}
```

- [ ] Step 3：增加仅针对 `/account-api/` 的会话 Cookie `korson_account_session`，其他路径沿用 `sessionid`。Cookie host-only、HttpOnly、SameSite=Lax，生产 Secure；官网 Cookie Path 为 `/account-api/`。中间件按照 Django 6.0 SessionMiddleware 的读取、保存、删除和并发删除处理实现，不修改全局 settings，不绕过 CSRF，不把 Django session 签进浏览器 Cookie。来源只接受配置中官网 origin，开发支持 localhost 和 127.0.0.1，但不混用二者的授权回调。

```python
def begin_account_session(request, user, *, audience):
    login(request, user, backend="django.contrib.auth.backends.ModelBackend")
    request.session["account_user_id"] = user.pk
    request.session["account_session_version"] = user.account_session_version
    request.session["account_audience"] = audience
```

- [ ] Step 4：增加只读邮箱审计，输出重复组数量和用户 ID，不输出密码或令牌。唯一约束仅覆盖非空且已验证的邮箱，使用 `Lower("email")`。发现旧重复记录时，停止约束迁移和上线，不自动合并或删除。数据库迁移不在本计划审阅阶段执行。

```python
models.UniqueConstraint(
    Lower("email"),
    condition=models.Q(email_verified=True) & ~models.Q(email=""),
    name="users_verified_email_ci_unique",
)
```

- [ ] Step 5：配置命令只建立一个可信官网客户端，类型 confidential、grant authorization-code、algorithm RS256；仅登记固定 callback，无通配符，无开放客户端注册。客户端 secret 从环境读取且按库默认哈希保存；注册只读命令不打印 secret，重复执行不轮换 secret、不扩展回调地址。完成此任务的定向检查后保存明确列出的文件，不使用 `git add -A`。

## Task 2：注册、密码登录与找回密码

**Files:** accounts/forms.py、services.py、views.py、urls.py、三个模板、accounts.css、test_accounts.py；users/views.py 的旧注册和验证码建号路径。

**Interfaces:**

- `send_account_code(email: str, *, purpose: str) -> None`：仅 register、reset_password，10 分钟有效。
- `consume_account_code(email: str, code: str, *, purpose: str) -> None`：正确且未消费时返回；否则抛 `ValidationError`。
- `register_account(*, email: str, code: str, password: str, nickname: str, agreed_to_terms: bool) -> User`。
- `authenticate_account(request, identifier: str, password: str) -> User`：兼容已存在的用户名，邮箱查询存在歧义时拒绝登录。
- `reset_account_password(*, email: str, code: str, password: str) -> None`。

- [ ] Step 1：注册检查固定学生角色、未入机构、未开通会员，原用户名登录仍返回同一个 ID。给重置、用途混用、重复验证码和重复注册分别写断言。

```python
def test_registration_does_not_grant_learning(self):
    with patch("users.accounts.services.consume_account_code"):
        user = register_account(
            email="student@example.com", code="123456", password="Pass12345",
            nickname="同学", agreed_to_terms=True,
        )
    self.assertIsNone(user.institution_id)
    self.assertFalse(user.is_member)
    self.assertEqual(user.personal_plan, "free")
    self.assertEqual(user.role, "student")
```

- [ ] Step 2：新验证码缓存使用独立命名空间，不能接受旧 `verification_code:{email}` 下未校验用途的验证码。缓存记录包括 purpose、密码散列、随机 record ID 和发送时间；生产要求共享缓存。验证成功后用 `cache.add()` 原子标记 record ID 已消费，再删除记录；失败次数原子累计，5 次失败清除验证码。邮件发送失败清除缓存，所有失败不生成会话。

```python
key = f"account_code:{purpose}:{email}"
record = cache.get(key)
if not record or record["purpose"] != purpose:
    raise ValidationError("验证码错误或已过期")
if not check_password(code, record["code_hash"]):
    raise ValidationError("验证码错误或已过期")
if not cache.add(f"account_code_used:{record['id']}", True, timeout=600):
    raise ValidationError("验证码错误或已过期")
cache.delete(key)
```

- [ ] Step 3：邮箱使用 Django `EmailField` 校验并标准化。新密码沿用现有 8 位、大写字母和数字要求，并调用 Django 密码校验；协议值必须是真正布尔值或表单 checkbox 的合法值。注册使用 `create_user()`，不使用可能把首用户设为管理员的 serializer 创建路径。数据库唯一冲突转为可理解的注册失败，不覆盖已存在用户。

```python
with transaction.atomic():
    user = User.objects.create_user(username=username, email=email, password=password)
    user.nickname = nickname
    user.email_verified = True
    user.agreed_to_terms = True
    user.agreed_to_terms_at = timezone.now()
    user.save(update_fields=["nickname", "email_verified", "agreed_to_terms", "agreed_to_terms_at"])
```

旧注册和验证码建号路径同样在创建或验证邮箱的局部事务外捕获该唯一约束冲突，返回“该邮箱已有账号，请直接登录”，不以 500 响应退出。对旧注册成功、已有账号验证码登录各运行一次定向检查，证明原有用户 ID、密码和机构未改变。仅捕获对应已验证邮箱唯一冲突，其他数据库异常继续上报。

- [ ] Step 4：新登录复用现有锁定规则：5 次密码错误锁定 15 分钟，停用账号不可登录；建立 Django 认证中心会话，不删除或重建现有 UniMind Token。注册成功可建立同样会话并返回原授权流程。找回密码的发送响应统一，找不到已验证账号时不发邮件，不泄露存在状态。

```html
<form method="post">
  {% csrf_token %}
  {{ form.non_field_errors }}
  {{ form.as_div }}
  <button type="submit">{{ submit_label }}</button>
</form>
```

- [ ] Step 5：登录 10 次／5 分钟、注册 5 次／小时、验证码按 IP 3 次／10 分钟且按邮箱 60 秒冷却、重置 5 次／10 分钟。沿用现有 `rate_limit`，不真实发送测试邮件。页面支持错误提示、提交中状态、邮箱自动填充和移动端；不得出现学习导航或默认付费承诺。通过账号定向检查后保存本任务文件。

## Task 3：官网授权码登录及独立会话

**Files:** accounts/oidc.py、views.py、urls.py、test_accounts.py。

**Interfaces:**

- `safe_site_return_path(value: str) -> str`：合法站内路径原样返回，其余返回 `/account`。
- `site_login(request) -> HttpResponse`、`site_callback(request) -> HttpResponse`。
- `site_session(request) -> JsonResponse`：`{"user": null | {"id", "nickname", "email", "email_verified"}, "csrf_token": str}`。
- `site_logout(request) -> JsonResponse`：仅 POST，仅清官网会话。
- `KorsonOAuth2Validator.get_additional_claims()` 返回邮箱、验证状态、昵称与会话版本，scope 映射明确；不输出角色、课程或付费承诺。

```python
class KorsonOAuth2Validator(OAuth2Validator):
    oidc_claim_scope = {
        **OAuth2Validator.oidc_claim_scope,
        "account_session_version": "openid",
    }

    def get_additional_claims(self):
        return {
            "email": lambda request: request.user.email,
            "email_verified": lambda request: request.user.email_verified,
            "name": lambda request: request.user.nickname,
            "account_session_version": lambda request: request.user.account_session_version,
        }
```

- [ ] Step 1：state 错误、缺失 nonce、错误 audience／issuer、授权码重放、恶意 return_to 分别拒绝建立会话。两次并行发起登录使用各自 state 对应的返回页，不使用会被覆盖的单个 `next` 字段。

```python
def test_external_return_is_rejected(self):
    for value in ["https://evil.example/", "//evil.example/", "/\\evil.example/"]:
        self.assertEqual(safe_site_return_path(value), "/account")
    self.assertEqual(safe_site_return_path("/schools/de?province=北京"), "/schools/de?province=北京")
```

- [ ] Step 2：使用 Authlib Django 客户端，不自行实现 JWT、授权码或签名校验。服务端固定 issuer、discovery URL 和 callback，客户端仅 openid、profile、email，PKCE 只用 S256；拒绝 plain，ID Token 仅 RS256。客户端请求使用超时，不按浏览器提供的地址下载 discovery 或 JWKS。

```python
oauth = OAuth()
oauth.register(
    "korson",
    client_id=settings.ACCOUNT_WEBSITE_CLIENT_ID,
    client_secret=settings.ACCOUNT_WEBSITE_CLIENT_SECRET,
    server_metadata_url=settings.ACCOUNT_DISCOVERY_URL,
    client_kwargs={"scope": "openid profile email", "code_challenge_method": "S256"},
)
```

- [ ] Step 3：`authorize_redirect()` 保存 state、nonce、PKCE 到服务端 session。授权成功后 `authorize_access_token()` 完成协议校验；只根据验证后的 sub 查询现有 User，不按邮箱重新创建用户。ID Token 的会话版本必须等于数据库当前版本，再调用 `begin_account_session(..., audience="website")`。令牌不写前端，不返回 JSON，服务端不需要长期刷新令牌时不保存它。

```python
token = oauth.korson.authorize_access_token(request)
identity = token["userinfo"]
user = User.objects.get(pk=identity["sub"], is_active=True)
if identity["account_session_version"] != user.account_session_version:
    raise PermissionDenied("登录已失效，请重新登录")
begin_account_session(request, user, audience="website")
```

- [ ] Step 4：`session/` 每次读取当前数据库用户与会话版本，并返回 `get_token(request)`；无登录正常返回 user null。`logout/` 要求 CSRF，只 `logout(request)` 当前官网 session，不删除原 UniMind Token，不增加全局会话版本。

```python
@require_POST
@csrf_protect
def site_logout(request):
    logout(request)
    response = JsonResponse({"status": "ok"})
    response["Cache-Control"] = "no-store"
    return response
```

- [ ] Step 5：对真实授权码交换做一个完整的本地定向集成检查，其余负面输入用库验证器或 mock 检查，不创建临时登录页面，不运行全站 E2E。确认“网页登录不会撤销已存在平台 Token”后保存本任务文件。

## Task 4：UniMind 旧账号衔接和前端身份刷新

**Files:** accounts/middleware.py、views.py、test_accounts.py、AccountCallback.tsx、App.tsx。

**Interfaces:**

- `unimind_entry(request) -> HttpResponse`：认证中心会话存在时进入平台；否则引导账号登录，再返回此入口。
- 只在账号入口读取现有 `auth_token`，核验数据库 Token、活跃用户和锁定状态后衔接原用户；不读取 URL Token，不以 localStorage 用户对象作为认证证明。
- 平台 Cookie 沿用现有名字和安全属性，Token 使用 `get_or_create()`，不轮换已有 Token。
- `AccountCallback` 获取 `/api/users/me/` 后执行 `setAuth(user, null)`，再按现有方式刷新机构与功能状态。

- [ ] Step 1：已有平台 Token 登录官网时保持 Token 值不变；从官网进入平台后仍为同一用户 ID。账号冲突先展示两个账号的确认信息，GET 不切换身份，确认 POST 要求 CSRF。

```python
def test_account_login_keeps_existing_platform_token(self):
    user = User.objects.create_user(username="paid", password="Pass12345")
    original = Token.objects.create(user=user).key
    self.client.post("/accounts/login/", {"identifier": "paid", "password": "Pass12345"})
    self.assertEqual(Token.objects.get(user=user).key, original)
```

- [ ] Step 2：平台入口复用现有 `is_member_or_admin()`，这里只维持当前入口准入，不声称已经实施新的付费课程权限。新注册用户默认 false，显示“学习服务暂未开通”和联系我们，不加入机构。旧有效会员、教师、负责人和平台管理员按现有规则进入，其他机构归属不改变。

```python
if not is_member_or_admin(request.user):
    return render(request, "users/accounts/profile.html", {"learning_available": False})
token, _ = Token.objects.get_or_create(user=request.user)
```

- [ ] Step 3：设置兼容 HttpOnly 平台 Cookie 后，只重定向至服务端固定 `UNIMIND_ORIGIN + '/account-callback'`。React 回调先显示加载状态，不信任持久化旧用户，不把 Token 写入存储，加载失败显示重试或重新登录，不进入其他账号工作台。

```tsx
const { data: user } = await api.get('/users/me/');
useAuthStore.getState().setAuth(user, null);
window.location.replace('/');
```

- [ ] Step 4：App 的新 callback 路由放在登录保护之外，实际权限仍由后端保证。保留旧登录、邀请码、飞书机构 SSO 路由，不改机构加入接口。本地只检查旧账号往返、新免费账号和账号冲突三条路径，通过后保存本任务文件。

## Task 5：会话撤销与官网可见入口

**Files:** accounts/services.py、signals.py、views.py、users/apps.py、test_accounts.py；官网 Header.astro、account.astro、account.ts、account.css、astro.config.mjs、deploy/nginx.conf。

**Interfaces:**

- `revoke_account_sessions(user_id: int) -> None`：原子增加会话版本，删除该用户平台 Token、OAuth grants、access／refresh／ID tokens；不删账号、机构、课程和学习记录。
- 密码修改或用户从活跃变为停用时触发该服务，新建账号不触发；钩子不递归保存 User。
- `readAccountSession() -> Promise<AccountSession>`、`logoutWebsite(csrfToken: string) -> Promise<void>`，只调用官网同源接口。

```ts
export interface AccountSession {
  user: { id: number; nickname: string; email: string; email_verified: boolean } | null;
  csrf_token: string;
}
```

- [ ] Step 1：针对密码重置、普通修改密码、管理员修改密码、停用账号和退出全部服务检查旧官网会话失效、旧平台 Token 无效、旧授权码不能换取新会话。官网单独退出检查另一端仍可用。

```python
def test_revoke_invalidates_legacy_token(self):
    user = User.objects.create_user(username="existing", password="Pass12345")
    Token.objects.create(user=user)
    version = user.account_session_version
    revoke_account_sessions(user.pk)
    user.refresh_from_db()
    self.assertEqual(user.account_session_version, version + 1)
    self.assertFalse(Token.objects.filter(user=user).exists())
```

- [ ] Step 2：撤销服务在 transaction.atomic 中锁定用户，然后以 F 表达式更新版本和删除凭据。安全钩子比较保存前的密码与 active 状态，密码未变不触发。现有修改密码接口如需为当前平台重新发 Cookie，保留其已有行为，但其他旧会话全部失效。退出全部服务是 CSRF POST，不由 GET 查询触发。

```python
with transaction.atomic():
    user = User.objects.select_for_update().get(pk=user_id)
    User.objects.filter(pk=user.pk).update(account_session_version=F("account_session_version") + 1)
    Token.objects.filter(user_id=user.pk).delete()
    Grant.objects.filter(user_id=user.pk).delete()
    AccessToken.objects.filter(user_id=user.pk).delete()
    RefreshToken.objects.filter(user_id=user.pk).delete()
    IDToken.objects.filter(user_id=user.pk).delete()
```

- [ ] Step 3：官网 `/account` 沿用 Layout 和现有设计变量。匿名显示登录、注册、找回密码；登录后显示昵称、邮箱、退出官网和账号安全入口。昵称以 textContent 写入，不插入 HTML。desktop 和 mobile 入口同时增加，“进入 UniMind”指向认证中心入口，用户不会找不到账号入口。

```ts
export async function readAccountSession() {
  const response = await fetch('/account-api/session/', { credentials: 'same-origin', cache: 'no-store' });
  if (!response.ok) throw new Error('账号服务暂时不可用');
  return response.json();
}
export async function logoutWebsite(csrfToken: string) {
  const response = await fetch('/account-api/logout/', {
    method: 'POST', credentials: 'same-origin', headers: { 'X-CSRFToken': csrfToken },
  });
  if (!response.ok) throw new Error('退出失败，请重试');
}
```

- [ ] Step 4：Astro 仅对 `/account-api/` 设置开发代理，后端目标由环境配置，默认本地 Django 8000。生产代理模板保留 `/account-api/` 路径，转发真实 Host、协议和由受信任代理提供的 X-Real-IP，关闭缓存，不跨公网明文发送账号会话。实际生产上游与 HTTPS 连接方式在部署时核实，本次不将未知端口写为可直接上线的配置。

```js
vite: {
  server: {
    proxy: {
      '/account-api/': {
        target: process.env.ACCOUNT_API_UPSTREAM || 'http://127.0.0.1:8000',
        changeOrigin: false,
      },
    },
  },
},
```

- [ ] Step 5：本地打开实际官网 4321，检查顶栏入口、匿名状态、注册后返回、两端免重复输入密码、退出官网和免费账号不进入学习平台。只运行本模块自动检查、两端相关类型检查及各一次构建；测试数据库必须与用户开发数据库分开，邮件用 mock，不运行现有 scripts/check_all.sh，不新增浏览器自动化回归项目。

从 UniMind 根目录运行定向检查，显式使用内存测试数据库，不能通过默认 `.env` 连接用户开发数据库：

```bash
DB_ENGINE=django.db.backends.sqlite3 DB_NAME=:memory: backend/.venv/bin/python -m pytest backend/users/test_accounts.py -q
```

检查文件使用 Django TestCase，测试构造的账号只进入测试数据库。邮件发送、外部 HTTP 和后台任务分别 mock；完整授权码交换用本地 provider 与测试客户端完成。

## 执行与交付

按任务 1 至 5 在现有 main 原地开发，任务依赖共享身份和会话接口，不并行改认证代码。只暂存本计划列出的实际修改，提交前重新检查用户未提交文件；代码提交不等于推送，推送和部署另等指令。

本地验证成功标准：

- Chrome 的官网 4321 顶栏和移动导航可看到账号入口。
- 注册创建一个原 UniMind User，默认学生、free、无机构、非会员。
- 旧账号使用原密码和原用户 ID，两端往返不需要重复输入密码，不重置平台旧 Token。
- 匿名用户仍可以查询择校库；免费账号不会由新的进入入口自动取得学习服务。
- 官网会话不被 UniMind 学习 API 当作平台认证凭据；账号入口不授予机构或管理权限。
- state、PKCE、nonce、issuer、audience、回调及 CSRF 的负面检查通过。
- 官网退出与全部退出有明确区别，重置密码和停用账号使旧会话失效。
- 用户现有开发数据和未提交代码保持，已执行的迁移、安装及验证分别如实记录。

生产尚需确认：账号签名密钥、客户端 secret、issuer 与回调、共享缓存、旧邮箱审计、数据库备份、账号 API 受信任代理连接、后端与官网发布顺序。未确认这些条件前不启用生产账号开关。新权益管理、自动入机构和课程范围授权仍按独立设计实施，不能用本次登录验收替代权限验收。

技术依据：[Django OAuth Toolkit OIDC 文档](https://django-oauth-toolkit.readthedocs.io/en/latest/oidc.html)、[Authlib Django 客户端](https://docs.authlib.org/en/stable/oauth2/client/web/django.html)、[OAuth 2.0 安全最佳实践](https://www.rfc-editor.org/rfc/rfc9700.html)。
