# 正式小宇入口切换与回退

日期：2026 年 10 月 26 日。目标：让 /xiaoyu 可以在新旧两条链路之间切换，默认旧页，任何初始化失败自动回退，不启用生产流量。

## 边界

- 前端构建变量 VITE_DSH_XIAOYU_ENABLED 默认 false；关闭时不请求 DSH 状态，直接渲染旧 XiaoYu。
- 开启后请求 /api/ai/dsh/status/，仅在 200 且 mode 不为 unavailable 时进入 production 模式。
- 404、超时、401/403、网络错误或模型未配置均回退旧页。
- 后端仍由 UNIMIND_DSH_ENABLED 和 UNIMIND_DSH_SITE_ENABLED 双开关控制；任一关闭，status 返回 404，整体回退。
- production 模式隐藏连接状态、身份、记忆、工具候选和网关用量等调试信息；保留发送、停止、恢复、历史会话、结果卡片、导出和删除。
- 不删除旧页代码，不切换生产构建变量。

## 实现

- 新增 XiaoyuRoute：构建开关加 status 探测，旧页与 DshM0 均懒加载。
- DshM0 增加 production 参数，按模式隐藏调试区块并显示正式标题、历史会话和空输入框。
- App 的 /xiaoyu 路由改为 XiaoyuRoute；移除未使用的 XiaoYu lazy 常量。
- frontend/.env.example 增加 VITE_DSH_XIAOYU_ENABLED=false。

## 验证

- 默认构建通过；VITE_DSH_XIAOYU_ENABLED=true 构建通过。
- 后端站点状态测试 7 passed，覆盖双开关关闭 404 和开启后的身份/模式返回。
- 未验收：真实浏览器新旧切换、真实模型质量、生产流量与回滚演练。
