# 桌面薄壳从 Tauri 迁移到 Electron

日期：2026 年 10 月 27 日。目标：按用户确认，把桌面交付从 Tauri 切到 Electron，保留远程 UI 薄壳、安全边界和 Windows/macOS 构建能力。Tauri 壳保留为历史实现，不在本轮删除。

## 边界

- Electron 只加载 UniMind 远程 React UI；DSH、模型密钥、学生数据和评分任务留在服务端。
- 客户端不包含 DSH SDK、Node 业务命令、preload 暴露或插件市场。
- `contextIsolation`、`sandbox` 开启，`nodeIntegration` 关闭；权限请求默认拒绝；禁止 webview。
- 主窗口只允许入口同源导航；新窗口只允许 HTTPS 或开发 loopback 的受限资源窗口，资源窗口不能继续弹窗。
- 发布版入口 `https://unimind-ai.com`；预览版入口为 loopback 合成页面；开发入口为 `http://127.0.0.1:5173`。
- 保留 Tauri 代码和依赖，等 Electron 在 Windows 实机验收后再决定清理。
- 不改真实 .env、不发布生产、不把 macOS 构建当作 Windows 验收。

## 实现

- 新增 `frontend/electron` 独立包，避免改动前端共享 node_modules。
- `main.ts`：窗口、同源导航、受限资源窗口、单实例、菜单、权限拒绝。
- `security.ts`：URL 来源、同源和资源边界；`security.test.ts` 覆盖 3 组边界。
- `electron-builder.yml` 和 `electron-builder.preview.yml`：macOS DMG/ZIP、Windows NSIS、预览 .app；使用本地 Electron dist，避免打包时再下载。
- `.github/workflows/desktop-windows.yml` 改为 Windows 2022 上 `npm ci` 和 `npm run dist:win`，生成无签名 NSIS 并记录 SHA256。
- `frontend/package.json` 增加 `electron:*` 转发脚本；Tauri 脚本保留。

## 验证

- `npm run build` 通过：esbuild、tsc、3 项 URL 边界测试。
- `npm run pack` 生成 `release/mac-arm64/UniMind.app`，约 253 MiB，`com.korsonedu.unimind.desktop`；实际启动加载远端落地页，截图 `.m0-state/m0-electron-macos-proof.png`。
- `npm run dist` 生成 `release/UniMind-0.1.0-arm64-mac.zip`，约 112 MiB，`unzip -t` 通过；DMG 构建在下载 dmgbuild/7zip 阶段因网络中断未完成，需重试。
- 未验收：Electron 合成登录、课程播放、流式、资源窗口、跨端练习恢复；Windows NSIS 与实机安装；Developer ID 签名、公证和更新渠道。
