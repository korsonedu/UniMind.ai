# 桌面浏览器登录

用户已明确流程：App不进入网页首页，直接显示参考Codex的独立登录页；点击后打开系统浏览器，网页登录后回到App。网页首页与现有网页登录保留。本实现沿用Electron、React和科晟账号服务，不新增身份系统或第三方登录方式。

## 界面

App未登录时显示居中的UniMind标识、欢迎语与单一“通过浏览器登录”主按钮。等待时可重新打开浏览器、取消；失败或超时可重新开始。底部保留协议及隐私入口。已登录且服务端身份有效则进入小宇。使用现有字体和主题，留白、黑白主按钮与细节层级参考桌面原生应用，不复用网页版营销首页和双栏密码表单。

## 固定接口

- `POST /api/users/desktop-auth/start/`：JSON `{state, code_challenge}`，均为32字节base64url（43字符），S256固定。返回`{request_id, expires_in:180}`；不接收重定向地址。
- 系统浏览器打开同源`/accounts/desktop/?request=<request_id>`。未登录使用现有科晟登录页，登录后回到此页；明确展示当前账号，用户确认后才签发授权码。
- 浏览器回调固定为`unimind://auth/callback?code=<code>&state=<state>`。只传短时一次性码，不传Token。网页保留显式“打开UniMind”入口作为浏览器未自动唤起时的回退。
- `POST /api/users/desktop-auth/exchange/`：JSON `{code, code_verifier}`。核对S256、用户有效性及账号会话版本后原子消费授权码，通过HttpOnly平台Cookie给Electron原生会话，不向渲染进程返回Token。
- Native桥接：`DesktopState.auth?: {status:'idle'|'opening'|'waiting'|'completing'|'authenticated'|'error', error?:string, expiresAt?:number}`，`startLogin()`与`cancelLogin()`返回DesktopState。登录页订阅既有`onStateChanged`。
- Native完成Cookie交换并确认`/api/users/me/`后，加载同源`/account-callback?next=/xiaoyu`，复用前端权威身份确认与旧账号缓存清理。

## 安全边界

verifier与state由主进程创建，仅保存在本次登录的内存中。取消、超时、再次登录替换旧请求；未匹配当前state的回调、错误host/path/重复参数拒绝。进程重启后旧回调不能建立登录，重新开始即可。主进程只打开固定同源账号路径，浏览器与资源子窗没有业务IPC权限。

服务端请求有效3分钟，授权码有效60秒；缓存原子add消费防重放，交换前不创建／替换平台凭据。浏览器确认要求CSRF和有效account会话。API仅接受受限JSON、限流并检查账号服务开关；缓存不可用不能降级放行。不把网页会话的旧账号静默带入App，确认页明确展示选用账号。

## 验收与合并

必要冒烟覆盖成功交换、一次性／过期、错误verifier、无浏览器账号／错误账号版本、CSRF、伪造回调及取消后迟到回调。前端／Electron构建、桌面登录UI与网页登录保持原有行为。真实系统浏览器完整回流需要发布匹配服务后再验收，不将stub或本地API测试称为线上通过。

当前无打开的PR；上一提交前端与Windows打包CI通过，后端依赖漏洞扫描失败。因此在本功能完成与安全门槛解决前不建议合并。本轮不合并或部署。

## 分工

- 账号后端：desktop-auth API、账号确认／回流页面及必要冒烟。
- Electron：auth模块、主进程回调／启动、preload桥接；保留既有IPC、下载、恢复与签名边界。
- 主线程：React登录页、App入口、桥接类型、设计整合和可见验收。

## 本轮结果

- 账号后端9项聚焦冒烟通过；新增确认页复用浏览器既有平台Cookie，但GET只展示、POST明确确认，保留CSRF和账号版本边界。
- Electron真实原生会话配合隔离HTTP服务的冒烟通过：PKCE、同会话HttpOnly Cookie到me、重复／伪造回调、等待重开、取消后清理、超时与进程重启旧回调拒绝；该检查未打开真实系统浏览器，不冒充线上端到端。
- React与Electron构建、原3项URL边界冒烟通过。独立只读安全复核未发现确定P1／P2。
- 本地Electron窗口已实际显示新登录页，登录服务未就绪时显示错误并可返回登录。独立网页版验证原密码／验证码登录和首页保留。
- 可见验收使用独立临时Login Preview，仅把本地预览启动路径指定为/login，未改正式包固定线上入口、未修改生产账号／默认协议关联；该临时入口文件打包后已从dist清除。
- 当前源码版本0.1.2；本轮未合并或部署。匹配服务发布后的真实系统浏览器→App回流，以及Windows原生唤起仍需验收；后端CI依赖漏洞扫描门槛仍未解决，不建议合并。
