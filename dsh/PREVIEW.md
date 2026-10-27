# UniMind 网页与薄桌面预览

桌面复用仓库已有 Tauri 壳；网页和桌面显示同一份 React，并访问同源 UniMind API。DSH、模型密钥、学生数据和评分任务留在服务端。客户端不包含 DSH SDK，不开放原生业务命令。

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

## macOS Preview App

在 `frontend` 中执行：

```sh
npm run tauri:build -- --debug --bundles app --config src-tauri/tauri.preview.conf.json
```

构建需要 Rust 1.90 或更新版本；本机使用 Rust 1.94.1。Rust Tauri、前端 API 和 CLI 均已锁定到兼容的 2.12 系列，避免原 2.11/2.12 混用导致构建拒绝。没有修改主仓库共享 node_modules。

输出为 `frontend/src-tauri/target/debug/bundle/macos/UniMind Preview.app`。先启动上述前后端，再打开 App。Preview 使用独立的应用标识和窗口标题，启动时登录合成账号；它访问 loopback 页面，不代表正式登录或生产服务已交付。首次加载期间等待本机服务完成响应。

发布构建使用 `npm run tauri:build -- --bundles app`，入口为后端现有配置中的 `https://unimind-ai.com`。该域名已只读确认 HTTPS 返回 200。发布代码拒绝 HTTP 来源；开发 HTTP 仅允许 loopback。主窗口只能同源导航；课件和附件的现有新窗口链接使用共享登录会话的受限资源窗口，允许 HTTPS 和开发站点同源 HTTP，拒绝凭据地址、file/javascript 等协议，资源窗口不能继续弹窗。原生命令均关闭，不提供本地 Agent、插件市场或系统权限。远程 UI 的配置方式依据 [Tauri 配置说明](https://v2.tauri.app/reference/config/)，权限边界依据 [Capabilities](https://v2.tauri.app/security/capabilities/)。

正式网站仍需完成对应后端发布与开关验收，才能在正式客户端使用新 DSH；桌面壳构建不会改变生产网站。Apple Developer ID 签名、公证及正式更新渠道需要单独交付；此处不声称已可公开分发。Windows 安装包尚未在 Windows 环境构建或验收。

## 实际验收

- 原预览数据从临时脚本迁入仓库启动器后，14 条消息、4 条确认、2 条答疑和4份练习记录保持不变。
- 全新目录以协议夹具初始化、合成 HttpOnly 登录和来源状态检查通过；5 项路径、数据库、SDK 与环境隔离冒烟通过。
- 桌面实际登录合成账号、读取既有会话并显示课程卡片；真实 DeepSeek 查询学习统计后显示卡片和回答，额度由192变191。SDK 路径问题造成的一次失败释放额度，没有扣次。
- 网页已提交练习现在通过本人 submission 查询恢复服务器上的原考试编号和作答，桌面可直接显示原 10/10；恢复没有创建新考试、重新评分或扣次。查询失败时禁用提交并提供重试，不能把读取失败当成“尚未交卷”。
- 截图在忽略目录 `.m0-state/m0-desktop-course-proof.png`、`m0-desktop-chat-proof.png`。

macOS arm64 的 Preview 和 HTTPS 发布构建均已生成，分别约25 MiB和9 MiB；构建产物仅为本机候选。签名检查显示只有 ad-hoc 签名、无 Team ID；本机可用签名身份为0，未做 Developer ID 签名或公证。ZIP 位于 `.m0-state/artifacts/`，跨端成绩截图为 `.m0-state/m0-desktop-practice-restore-proof.png`。

网页和桌面使用相同的服务端会话和正式提交事实；客户端草稿仍按用户隔离。实际课程视频、正式账号登录、签名分发和生产并发需要另用授权环境验收，不能用合成数据推定已完成。

一次独立复核发现继承真实邮件/OSS 配置和拒绝所有新窗口两处缺口，已修复。哨兵验证确认 `.env` 不加载、SMTP 不调用、默认存储为本地；重启后原16条消息保留。资源 URL 的3项 Rust 冒烟通过，本人合成课件200、匿名401。修复版两个 App 已构建；资源窗口的实际点击验证因 Mac 锁屏等待解锁，不把构建或接口结果写成桌面点击已通过。
