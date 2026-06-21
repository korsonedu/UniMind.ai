# UniMind 技术架构

## 概述

Agent 驱动的新一代智能教育基础设施。Django 6.0 + React 19 + DeepSeek V4。面向 B 端教育机构，提供学生端 AI 学习教练（小宇）和教师端教研工作台。

## Agent 架构

两个自治 AI Agent 共享统一运行时：

- **小宇**（bot_type: planner, 21 工具, 7 类意图路由）— 学生端唯一 AI 入口：学习规划、知识讲解、数据分析、可视化渲染、教练式对话
- **工作台**（bot_type: exam_generator, 15 工具, 8 类意图路由）— 教师端唯一 AI 入口：出题、查学生数据、作业管理、资产浏览、通知、邀请管理

运行时链路：Bot → BotRegistry → ToolExecutor → chat_dispatch → call_ai_with_tools（最多 5 轮自主工具调用）。

意图路由器按关键词预筛选工具子集。Prompt 自适应基于 mem0 语义记忆检测用户偏好。自进化系统包含 MUTAR 全链路（Measure → Umpire → Think → Adapt → Refine）和用户反馈闭环。

新增 Agent 只需：写 prompt 文件 → bot_registry 加一行 → 可选写 ToolExecutor 子类。

## 技术栈

- 后端：Django 6.0 + Celery + Channels (WebSocket)
- 前端：React 19 + TypeScript + Vite + shadcn/ui + Zustand
- AI：DeepSeek V4（按任务分级路由 fast/pro）
- 数据库：PostgreSQL + Redis
- 存储：阿里云 OSS（分片直传）
- 认证：Cookie httpOnly（REST API + WebSocket）

## 项目结构

11 个 Django App：ai_engine、ai_assistant、quizzes、users、courses、articles、interviews、study_room、faq_system、notifications、core

```
backend/
├── ai_engine/       — AI 引擎：路由、熔断、可观测性、模型配置
├── ai_assistant/    — Agent 运行时：Bot/BotRegistry/ToolExecutor/记忆系统
├── quizzes/         — 刷题核心：出题管线、Memorix 记忆调度算法
├── users/           — 用户/会员/RBAC/ELO/机构管理
├── core/            — 基础设施：加密字段、Cookie认证、邮件、限流
└── prompts/         — 统一 Prompt 模板目录
frontend/
├── src/pages/       — 37 页面组件
├── src/components/  — 通用组件 + shadcn/ui
└── src/store/       — Zustand 状态管理
```

## AI 模型策略

按任务分级路由（集中在 ai_engine/config.py）：

- 对话/面试/出题 Author：fast，快速响应
- 出题 Reviewer：pro + thinking，深度逻辑检查
- 批量出题/模拟考试：pro，高质量批量生成
- 主观题判分/知识树生成：pro，结构化 JSON 输出

换供应商只需改 FALLBACK_FAST / FALLBACK_PRO 两个常量。

## 关键基础设施

- 熔断器：按任务粒度熔断，自动恢复
- Memorix：自研间隔重复调度算法（非 FSRS）
- Memorix-Field：图扩散诊断引擎（Bernoulli-GMRF，18 学科通用）
- 四层权限模型：超管 → 机构所有者 → 教师 → 学生
- 支付网关：统一路由分发（Stripe/Alipay/WeChat/Airwallex）
- 机构隔离：题目、数据全量机构隔离
- MUTAR 自进化：轨迹采集 → 自动评估 → 用户反馈 → 变体路由 → 优化执行

## 部署

- 流程：本地开发 → git push → 服务器 git pull → systemd 重启
- 禁止在服务器直接改代码（.env 除外）
- 常用命令：make backend-check / frontend-check / full-check / qa-smoke

## 硬边界

- 不删除/重建 migration 文件
- Prompt 模板唯一来源：backend/prompts/
- 前端路由统一在 App.tsx 注册
- Serializer 字段必须显式声明
- Cookie 认证为主，不存 token 到 localStorage
- 题目机构隔离，禁止跨机构数据泄露
- 四层权限用 users.permissions 中的 helper 函数判断
