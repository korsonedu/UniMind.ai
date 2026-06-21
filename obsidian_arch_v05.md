# UniMind 四层架构 v0.5.0

> 2026-06-06 · Phase 0-7 全部 commit

## 四层总览

```
测评引擎：评分 + 错因分析(3类) · CTT→IRT→CDM
教育闭环：教·练·测·评（无纠，纠归Memorix）
记忆系统：Memorix 节拍器 + MemorySystem 查询接口层
基础框架：多Agent + 调度执行器 + 对话引擎
```

## 核心设计

- **Memorix 是节拍器**：不做立刻纠错，错题间隔重复自然出现
- **Agent 为入口，SaaS 为画布**：/xiaoyu 学生，/workbench 教师
- **侧边栏 9 模块**：独立页面导航，非 Agent 唤起（商业化安全网）
- **落地页保留原设计**：不激进改 ChatBubble
- **不做模式切换**：小宇自适应
- **免费=固定间隔+CTT，付费=Memorix自适应+错因+IRT**

## v0.5.0 关键修复

- kp_name 替代 kp（API 期望 ID 但 action_cards 传名称）
- memorix_scheduler 文本去重（命题官变式题 63 道重复）
- 卡片持久化（metadata.visual → toolStep.visual 恢复）
- 回 /xiaoyu 自动加载最新 session（不限 24h 窗口）
- practiceDone=1 自动触发判分分析
- 艾宾浩斯→间隔重复/Memorix
- 主观题 prompt 花括号 {{}} 转义

## 待部署

后端：grading_prompt, system_prompt, views_question, tool_router, utils, memorix_scheduler
前端：TestSessionPage, AgentChatLayout, useAgentConversation
需：git pull + restart + npm build

## Migration

0037: UserQuestionStatus + error_type/error_metadata
0038: GradingRecord
0016: UserProfile
0039: ItemParameter, UserAbility, QMatrixEntry
