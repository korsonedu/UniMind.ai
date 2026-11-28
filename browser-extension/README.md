# UniMind 随堂学浏览器插件（Chrome / Edge MV3）

面向 B 站与 YouTube 公开课的 AI 伴学侧边栏。插件接入 UniMind 主站的小宇流式对话、项目、随堂练习和个人笔记。

## 构建和加载

在仓库根目录运行以下命令。需要 Node.js 22.12+ 或 24。

```bash
cd browser-extension
npm ci
npm run build
npm run build:edge
```

- **Chrome 116+**：打开 `chrome://extensions`，启用「开发者模式」，点击「加载已解压的扩展程序」，选择 `browser-extension/.output/chrome-mv3`。
- **Edge**：打开 `edge://extensions`，启用「开发人员模式」，点击「加载解压缩的扩展」，选择 `browser-extension/.output/edge-mv3`。

扩展默认连接 `https://unimind-ai.com`。本地联调时，可以在扩展设置中切换到本地 UniMind 服务。视频伴学和短音频转写使用本仓库的配套后端接口。

## 开发和验证

在 `browser-extension` 目录运行：

```bash
npm run dev
npm run typecheck
npm test
```
