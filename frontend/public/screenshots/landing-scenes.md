# Landing 产品截图

这些截图来自当前 React 应用及本地示例数据，不代表真实学员成绩。

开发服务器启动后，打开 `/xiaoyu?preview=1&capture=1`。`capture` 仅隐藏开发预览工具条，界面和功能仍使用真实组件。点击侧栏中的场景会话后截图：

| 文件 | 场景 |
| --- | --- |
| landing-agent-plan.jpg | 把今天学什么，安排清楚 |
| landing-agent-graph.jpg | 让抽象概念，看得见 |
| landing-agent-map.jpg | 找到知识之间的连接 |
| landing-agent-practice.jpg | 从理解，到真正做对 |

Mock 位于 `src/dev/previewApi.ts` 和 `src/dev/agentDemoFixtures.ts`，仅开发模式加载。可继续输入“安排今天的复习”“画出债券价格与利率的关系”“看看知识图谱”“开始练习”体验不同工具调用。

首页游客预览：`/?preview=1&guest=1&capture=1`。回到学生演示请移除 `guest` 并刷新；连接真实后端请使用 `/?preview=0`。

设计参考：[Cursor](https://cursor.com/)、[Claude](https://claude.com/)、[Perplexity Comet](https://www.perplexity.ai/comet)。
