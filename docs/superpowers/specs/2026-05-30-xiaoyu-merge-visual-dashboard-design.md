# 小宇合并 AI 助教 + 可视化 Dashboard 设计

**日期**：2026-05-30
**状态**：已批准

## 概述

将 AI 助教合并进小宇，学生端只保留一个 AI 入口。同时将 Dashboard 从固定数据卡片升级为动态可视化画布，统一"讲知识"和"看数据"两个场景。

## 决策记录

| 决策 | 结论 |
|------|------|
| 合并方向 | 小宇吸收 AI 助教 |
| `/ai` 页面 | 删除，不重定向 |
| Prompt 策略 | 统一人格 + 情境行为原则 |
| Dashboard 定位 | Chat 的可视化渲染面（第一性原理） |
| 渲染机制 | 单一 `render_visual` 工具 + type 分发 |
| 持久化 | visual 随消息存储，历史会话恢复最后渲染状态 |
| 技能列表 | 扩展，加入知识问答类 |
| Prompt 哲学 | 规定好回答的标准和边界，不过度控制具体回答 |

## 页面状态机

```
Landing（居中） → 用户发消息 → 双栏模式（Dashboard + Chat）
                                     ↑
                 加载历史会话 ─────────┘
```

### 状态 1：Landing（无对话）

居中布局，不显示 Dashboard。

- 主标题：**小宇XiaoYu让学习更具效率。对话即学习。**
- 副标题：**最懂你的学习agent，从数据分析到知识讲解，一个入口搞定**
- 输入框 + 打字机 placeholder（轮播提示语）
- 技能按钮（7-8 个）：
  - 分析薄弱点
  - 制定学习计划
  - 查看复习任务
  - 学习数据总览
  - 推荐课程
  - 解释一个概念
  - 分析一道题
  - 总结知识点
- 历史对话入口（Popover）

### 状态 2：双栏模式（对话已开始）

- **左栏 Dashboard**：可视化画布
  - 空画布为默认状态（新对话）
  - 历史会话恢复该会话最后的 visual 渲染结果
  - 拖拽调整宽度（保持现有交互）
- **右栏 Chat**：对话流
  - 消息气泡（用户 + AI）
  - 工具步骤卡片（AgentStepCard）
  - 输入框 + 技能快捷入口

## 可视化系统

### 渲染工具

小宇通过 `render_visual` 工具触发 Dashboard 渲染。

```
render_visual({
  type: "latex_derivation",
  payload: {
    title: "极限的 ε-δ 定义",
    steps: [
      { latex: "\\lim_{x \\to a} f(x) = L" },
      { latex: "\\forall \\varepsilon > 0, \\exists \\delta > 0" }
    ]
  }
})
```

### 消息协议

每条 assistant 消息可携带 `visual` 字段：

```json
{
  "role": "assistant",
  "content": "下面用 ε-δ 定义来解释极限...",
  "visual": {
    "type": "latex_derivation",
    "payload": { "title": "...", "steps": [...] }
  }
}
```

前端渲染逻辑：
1. 收到消息 → 如果有 `visual` 字段 → 渲染到 Dashboard
2. 加载历史会话 → 找最后一条带 `visual` 的消息 → 渲染到 Dashboard
3. 新对话 → 空画布，等第一条 visual 消息

### 可视化类型（初版）

| type | 用途 | payload 结构 |
|------|------|-------------|
| `data_card` | 数据卡片（现有，统一进来） | `{title, subtitle?, items, cta?}` |
| `latex_derivation` | 数学推导过程 | `{title, steps: [{latex}]}` |
| `step_solution` | 解题步骤 | `{title, steps: [{text, latex?}]}` |
| `knowledge_map` | 知识图谱/关系 | `{nodes, edges, highlights?}` |

扩展方式：前端注册新 renderer 即可，后端零改动。

### Dashboard 默认状态

空画布，显示一行提示文字："小宇会在对话中为你生成可视化内容"。

## Prompt 设计原则

### 核心理念：定标准，不定脚本

Prompt 教小宇"什么是好回答"，而不是"遇到 XX 问题就回答 YY"。

**好回答的标准（已在 system_prompt 中）：**
1. 有数据支撑：引用具体数字
2. 有归因分析：解释"为什么"
3. 有优先级：识别最值得投入的方向
4. 有行动方案：给出可执行的任务
5. 有节奏感：考虑认知负荷
6. 有策略意识：体现学习科学方法

**行为边界（what to do when）：**
- 讲知识时：引导思考 → 卡住时直接讲 → 用例子帮助理解
- 看数据时：调工具拿数据 → 分析归因 → 给行动建议
- 不确定时：诚实说明，不编造
- 超出范围时：建议寻求专业帮助

**不过度控制的部分：**
- 不规定"讲数学题必须用什么格式"
- 不规定"每个概念必须举几个例子"
- 不规定"回答必须多长"
- 不规定"必须调哪个工具"

让 LLM 根据具体问题自主判断最佳回答方式。

### render_visual 使用指南

Prompt 中告诉小宇：
- 什么场景适合渲染可视化（推导、数据、图谱）
- 什么场景不需要（纯文字问答、简单提问）
- 不规定"遇到 XX 必须渲染 YY 类型"

## 后端改动

### 已完成（本次会话前置工作）

- `bot_registry.py`：删除 assistant 条目，fallback 改为 planner
- `tool_executor.py`：AssistantToolExecutor → BaseToolExecutor
- `exam_generator_tool_executor.py`：继承更新
- `chat_service.py` / `chat_dispatch.py` / `views.py`：fallback 更新
- `models.py`：Bot default 改为 planner
- `prompts/bots/xiaoyu/system_prompt.txt`：重写，统一人格
- `prompts/bots/assistant/`：删除
- `management/commands/seed_assistant.py`：删除
- 前端：删除 /ai 路由、AIAssistant.tsx、BotSelector.tsx，更新 MainLayout 导航

### 待实现

1. **后端 `render_visual` 工具**：
   - 在 `ai_engine/tools.py` 的 `get_planner_tools()` 中新增 `render_visual` 工具定义
   - 工具 schema：`{type: string, payload: object}`，type 为枚举
   - 工具执行器：`PlannerToolExecutor` 新增 `_handle_render_visual`，透传 payload 到前端

2. **后端消息模型扩展**：
   - `AIChatMessage` 模型新增 `visual` JSONField（可选），存储 render_visual 的输出
   - 或复用现有 `metadata` 字段

3. **前端 Dashboard 重构**：
   - 替换 `DashboardPanel` 为 `VisualCanvas` 组件
   - 实现 type → renderer 分发
   - 初版 renderer：`data_card`（复用现有）、`latex_derivation`、`step_solution`、`knowledge_map`

4. **前端消息协议**：
   - SSE/WS 消息流支持 `visual` 类型事件
   - 收到 visual 事件时更新 Dashboard 渲染

5. **Prompt 更新**：
   - `tool_guide.txt` 新增 `render_visual` 使用指南
   - 更新 SKILLS 列表和 placeholder 文案

6. **前端 Landing 页更新**：
   - 更新 greeting 文案
   - 扩展 SKILLS 列表（新增知识问答类技能）

## 前端改动

| 文件 | 改动 |
|------|------|
| `XiaoYu.tsx` | Landing 文案更新、SKILLS 扩展、双栏模式 Dashboard 替换为 VisualCanvas |
| `xiaoyu/DashboardPanel.tsx` | 重构为 VisualCanvas，支持 type 分发渲染 |
| 新增 `xiaoyu/visuals/` 目录 | 各类型 renderer（DataCardRenderer、LatexRenderer、StepSolutionRenderer、KnowledgeMapRenderer） |
| `hooks/useAgentChat.ts` | 支持 visual 类型的 SSE/WS 事件 |

## 验证方式

1. 学生在 Landing 页看到新文案和扩展技能列表
2. 发送知识类问题（如"解释极限的定义"）→ 小宇回答 + Dashboard 渲染 LaTeX 推导
3. 发送数据类问题（如"我的薄弱点是什么"）→ 小宇回答 + Dashboard 渲染数据卡片
4. 刷新页面，加载历史会话 → Dashboard 恢复最后的可视化内容
5. 新对话 → Dashboard 空画布
6. TypeScript 编译通过，无报错
