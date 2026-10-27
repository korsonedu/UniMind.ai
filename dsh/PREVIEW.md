# UniMind 网页与薄桌面预览

桌面使用 Electron 薄壳；网页和桌面显示同一份 React，并访问同源 UniMind API。DSH、模型密钥、学生数据和评分任务留在服务端。客户端不包含 DSH SDK，不开放原生业务命令。原 Tauri 壳保留为历史实现，不再作为交付路径。

## 当前本机启动方式

在当前 worktree 根目录，用主仓库已有 Django Python 启动。下面的路径不包含密钥，`.env` 只读取模型来源，不复制或修改：

```sh
/Users/eular/Desktop/科晟开发/UniMind/UniMindCode/backend/.venv/bin/python dsh/preview.py \
  --state-dir .m0-state/live-preview-20261027 \
  --model deepseek \
  --backend-env /Users/eular/Desktop/科晟开发/UniMind/UniMindCode/backend/.env
```

只有首次创建一个新目录时加 `--init`。现有数据库必须仅包含两个合成学生，已有消息、成绩和确认记录不会被清空。SDK 使用 `.m0-venv/bin/python`，启动时验证可导入 harness；保留虚拟环境的 Python 路径，不能解析符号链接后改用系统 Python。

不需要真实模型时省略 `--model deepseek` 和 `--backend-env`，默认使用明确标识的协议夹具。协议夹具不理解自然语言，不能用它判断小宇回答质量。`--port` 默认 8000；Redis 单独启动且退出时关闭，Celery 使用进程内任务和 memory broker。

启动器丢弃继承的业务环境变量并禁止自动加载 `.env`；只有显式指定的 DeepSeek 来源和密钥会进入模型网关。飞书 SMTP 密码为空，Django 邮件使用内存后端，附件写入当前合成目录的 `media/`，不会复用真实邮件或 OSS。数据库、会话和媒体目录拒绝链接逃逸；此启动器只用于隔离预览。

另一个终端在 `frontend` 中启动界面：

```sh
npm run dev -- --host 127.0.0.1 --port 5175 --strictPort
```

已运行同一端口时无需重复启动。打开 `http://127.0.0.1:5175/api/ai/dsh-preview/student-b/` 进入合成课程学员；`student-a` 为合成注册学生，只能观看标为公开的模块。新目录初始化包含一门公开合成课和一门课程学员合成课，只有现有持久预览另放入5秒合成视频与本地课件供播放验证。入口只在 `preview.py` 的包装层存在，不属于生产 Django URL。Cookie 为 HttpOnly，不在 URL 或日志中输出 Token。预览服务只能绑定 loopback，不可作为公开服务。

## Electron 薄壳

桌面壳位于 `frontend/electron`，使用 Electron 45，加载与网页相同的远端 UniMind UI。DSH、模型密钥、学生数据和评分任务留在服务端，客户端不包含 DSH SDK 或 Node 业务命令。

首次安装与构建：

```sh
cd frontend/electron
npm install
npm run build
```

预览（先按上文启动后端和 Vite）：

```sh
npm run preview
```

macOS 预览包：

```sh
npm run dist:preview
```

预期输出 `release-preview/mac-arm64/UniMind Preview.app`。Preview 使用独立应用标识和窗口标题，加载 loopback 合成页面，不代表正式登录或生产服务已交付。

macOS 发布包：

```sh
npm run dist
```

预期输出 `release/` 下的 DMG 和 ZIP，入口为 `https://unimind-ai.com`。本机已生成并校验 `release/UniMind-0.1.0-arm64-mac.zip`；DMG 在下载 dmgbuild/7zip 阶段因网络中断未完成，需重试。发布代码拒绝 HTTP 来源；开发 HTTP 仅允许 loopback。主窗口只能同源导航；课件和附件的新窗口链接使用共享登录会话的受限资源窗口，允许 HTTPS 和开发站点同源 HTTP，拒绝凭据地址、file/javascript 等协议，资源窗口不能继续弹窗。`contextIsolation` 和 `sandbox` 开启，`nodeIntegration` 关闭，没有 preload；权限请求默认拒绝，不提供本地 Agent、插件市场或系统权限。

正式网站仍需完成对应后端发布与开关验收，才能在正式客户端使用新 DSH；桌面壳构建不会改变生产网站。Apple Developer ID 签名、公证及正式更新渠道需要单独交付；此处不声称已可公开分发。

## 实际验收

- 原预览数据从临时脚本迁入仓库启动器后，14 条消息、4 条确认、2 条答疑和4份练习记录保持不变。
- 全新目录以协议夹具初始化、合成 HttpOnly 登录和来源状态检查通过；5 项路径、数据库、SDK 与环境隔离冒烟通过。
- 桌面实际登录合成账号、读取既有会话并显示课程卡片；真实 DeepSeek 查询学习统计后显示卡片和回答，额度由192变191。SDK 路径问题造成的一次失败释放额度，没有扣次。
- 网页已提交练习现在通过本人 submission 查询恢复服务器上的原考试编号和作答，桌面可直接显示原 10/10；恢复没有创建新考试、重新评分或扣次。查询失败时禁用提交并提供重试，不能把读取失败当成“尚未交卷”。
- 截图在忽略目录 `.m0-state/m0-desktop-course-proof.png`、`m0-desktop-chat-proof.png`。

以下为 Tauri 历史证据，保留作对照。

macOS arm64 的 Preview 和 HTTPS 发布构建均已生成，分别约25 MiB和9 MiB；构建产物仅为本机候选。签名检查显示只有 ad-hoc 签名、无 Team ID；本机可用签名身份为0，未做 Developer ID 签名或公证。ZIP 位于 `.m0-state/artifacts/`，跨端成绩截图为 `.m0-state/m0-desktop-practice-restore-proof.png`。

### Electron 迁移验收

- `frontend/electron` 的 `npm run build` 通过：esbuild 编译、TypeScript 类型检查和 3 项 URL 边界测试。
- `npm run pack` 生成 `frontend/electron/release/mac-arm64/UniMind.app`，约 253 MiB，应用标识 `com.korsonedu.unimind.desktop`；实际启动后加载 `https://unimind-ai.com` 落地页，截图 `.m0-state/m0-electron-macos-proof.png`。
- 当前只有 ad-hoc 签名，无 Developer ID；Electron 下的合成登录、课程播放、流式、资源窗口和跨端练习恢复仍待复验；Windows 安装包和实机验收未完成。

网页和桌面使用相同的服务端会话和正式提交事实；客户端草稿仍按用户隔离。实际课程视频、正式账号登录、签名分发和生产并发需要另用授权环境验收，不能用合成数据推定已完成。

一次独立复核发现继承真实邮件/OSS 配置和拒绝所有新窗口两处缺口，已修复。哨兵验证确认 `.env` 不加载、SMTP 不调用、默认存储为本地；重启后原16条消息保留。资源 URL 的3项 Rust 冒烟通过，本人合成课件200、匿名401。解锁后已在修复版 App 实际点击门户课件链接，共享登录的“UniMind · 课程与附件”窗口显示合成SVG正文，截图 `.m0-state/m0-desktop-resource-proof.png`。用户现已确认必须支持Windows，Windows安装包与验收继续推进，不能以当前macOS结果代替。

## 学员批次与 Windows 候选

管理后台学员页可创建多个服务批次，为学员选择当前批次；“我的服务”显示本人届别、服务期、考试日与生效状态。批次不预填正式年度或日期，未设置考试日须明确显示。两个批次并存、改绑、停用及恢复已在独立合成管理库和实际组件验证，未变更生产学员。

Windows x64 为必需交付，沿用同一 Electron HTTPS 薄壳。`.github/workflows/desktop-windows.yml` 在 Windows 2022 上安装 `frontend/electron` 依赖，执行 `npm run dist:win`，生成无签名 NSIS 候选并记录 SHA256；尚未推送或触发。Windows 实际安装、登录、课件播放和会话恢复仍须在真实 Windows 环境验收，不能以 macOS 构建替代。
