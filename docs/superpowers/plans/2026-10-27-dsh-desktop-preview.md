# 薄桌面与可重复本机预览

> 使用 superpowers:executing-plans 连续执行，仅必要冒烟，最后一次独立复核。

**Goal:** 把现有 Tauri 壳做成可启动的 UniMind 薄客户端，并用仓库中的启动器替代 /tmp 临时预览脚本。

**Architecture:** 桌面加载同源的 UniMind React 网页，共用服务端 API、HttpOnly 登录和 DSH。Rust 不启动 DSH、不传递模型密钥、不添加业务 IPC。生产构建访问代码现有配置的 unimind-ai.com；本地预览构建只访问 loopback 合成服务。预览启动器持久保存合成数据库，隔离 Redis/队列，不修改真实 .env。

**Spec:** 完整规划第六节与用户连续“继续直到完成”；已有 frontend/src-tauri 是现成资产。用户已确认首版不接外网搜索。

## 约束和判断

- Ruling: 复用已有 Tauri，而非新建 Electron。两者均满足薄壳定位；代价是需要实测系统 WebView 的登录/流式兼容，不假设 Chromium 行为。
- 关闭远程页面的原生能力授权；只允许当前受信站点同源导航，拒绝额外窗口和任意 file/javascript 地址。
- 开发 HTTP 只允许 loopback；发布构建要求 HTTPS，不能靠运行时环境变量改为任意站点。
- 不申请摄像头、录音、系统通知或文件系统权限；不新增离线 Agent、更新器或未经授权的生产发布。
- 合成预览数据库必须在忽略目录 .m0-state 下；拒绝符号链接、任意数据库路径或含其他用户的数据库。初始化必须显式 --init，保留已有预览记录。
- 只读已有 DeepSeek 配置，密钥不输出到 URL/日志/命令行或客户端。真实模型模式须显式选择；协议夹具明确不代表自然问法质量。
- Preview App 使用独立名称与标识，避免与未来正式客户端混用缓存。

## Review Focus

- 发布包不能意外加载开发 HTTP 地址或包含模型/数据库配置。
- 远程页面不能用导航、新窗口或 IPC 扩张本机访问。
- 重启预览不能清空合成会话，也不能误连真实数据库、Redis 或 Celery。
- 临时登录入口只能存在于合成预览包装层，生产 Django URL 中不可出现。
- WebView 使用独立 Cookie 存储，必须实际验证登录与原小宇界面恢复。

## Tasks

- [x] Task 1：提交可复用的 dsh/preview.py，保留合成数据库、独立运行环境和本地登录入口；定向冒烟数据库范围/初始化/重启。
- [x] Task 2：调整现有 Tauri 壳、受限导航与预览构建，生成 macOS App 并实际打开合成小宇页面；修复跨端已交卷恢复，原网页不改样式。
- [ ] Task 3：更新规划与启动说明，记录未签名/未生产交付边界，一次独立复核及必要修复、本地提交。

## 验证

- Python：预览路径/合成数据库范围的少量 unittest 冒烟；CLI --help。
- 桌面：cargo test --lib 的 URL 边界冒烟；npm run tauri:build -- --debug --bundles app --config src-tauri/tauri.preview.conf.json。
- 实际运行：重启当前合成预览不丢记录，Preview App 通过临时登录入口显示原小宇历史与卡片；截图记录。
- 生产网站不改，Apple Developer ID/公证和 Windows 签名不在本机凭空生成；无证据不声称可公开分发。

## 实施发现

- 现有前端依赖锁在 Tauri 2.12，而 Rust 锁在 2.11，原构建会拒绝。对齐 Rust 与现有前端到 2.12 并锁定版本；只更新桌面相关锁定依赖，不修改共享 node_modules。
- SDK Python 的 `.resolve()` 绕过虚拟环境，导致实际问答失败。原路径可导入 SDK、解析后的系统 Python 不可导入，已定向确认；保留原虚拟环境路径并在启动时校验，4 项预览冒烟通过。
- Preview App 已实际打开、合成登录、恢复课程卡片，并完成真实服务端 DSH 统计查询，一次成功扣次。Rust 两项导航冒烟及 macOS App 构建通过。
- Ruling: 桌面恢复网页已提交练习时暴露原卡片只保存本地 examId 的缺口，纳入 Task 2 修复。增加本人提交事实读取，以原成绩为准，不重新提交或评分；代价是每张没有本地结果的卡片增加一次本人读取。
- 本人提交恢复接口定向冒烟先404失败，修复后通过：本人读取、匿名401、他人404、旧单题提交404、零新增考试。前端构建通过，桌面实际恢复网页已交卷的10/10，额度仍191次。
- 本机生成macOS arm64 Preview约25 MiB、正式HTTPS入口的发布候选约9 MiB。生产入口只读HTTPS核实200；没有打开正式账号或发布网站。本机签名身份0，产物为ad-hoc/无Team ID，未公证。
