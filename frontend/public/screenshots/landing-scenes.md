# Landing 产品截图

首页保留暗色主调、点线入场与随能力 tabs 变化的线图。Hero 大图直接在原位置切换学习安排、图像讲解、知识关系与练习反馈。桌面端可点击截图里的四个会话名称，也可点击大图循环切换；仅展示预设的 mock 画面。

| 文件 | 内容 | 原始尺寸 |
| --- | --- | --- |
| landing-agent-plan-demo.webp | 学习安排与工具调用 | 3840 × 2640 |
| landing-agent-map-demo.webp | 知识关系与掌握程度 | 3840 × 2640 |
| landing-agent-feedback-demo.webp | 已完成练习的批改与解析 | 3840 × 2640 |
| landing-agent-demo.webp | 小宇工具调用、债券价格图像、历史项目与会话 | 3840 × 2640 |
| landing-workspace-demo.webp | 课程目录、观看进度、课件入口与历史学习活动 | 3840 × 3660 |
| landing-learning-records-demo.webp | 练习表现、知识掌握与历史考试记录 | 3840 × 2400 |

全部截图均来自当前 React 应用中的纯虚构账号“小林 / learner_demo”。演示包含 12 门课程、4 个目录、180 天内的 128 个活跃日、连续学习 18 天与累计 2,460 次答题；姓名、机构、邮箱及历史内容均为虚构值。旧截图已移出公开资源目录，避免继续引用旧身份素材。

图片从真实 DOM、字体和 SVG 以三倍像素密度导出，再无损编码为 WebP，未放大低分辨率图片。开发预览打开目标页面并附加 `?preview=1&capture=hd`，点击「导出完整界面」可重新导出。小宇选择「利率与债券价格」会话；课程门户使用 1280 × 1220 视口，保证课件与进度同屏。高清 PNG 源文件保存在任务产物目录。

Mock 位于 `src/dev/previewApi.ts` 和 `src/dev/agentDemoFixtures.ts`，仅开发模式加载。首页图片切换位于 `src/components/landing/AgentShowcase.tsx`，仅保存当前展示索引，不访问账号、后端或浏览器存储，不包含答题、勾选与滑块操作。

首页游客预览：`/?preview=1&guest=1&capture=1`。学生演示：`/courses?preview=1&capture=hd`、`/report-card?preview=1&capture=hd`、`/xiaoyu?preview=1&capture=hd`。
