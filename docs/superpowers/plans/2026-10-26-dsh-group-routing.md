# DSH 分组工具选择实施计划

> 使用 superpowers:executing-plans 在当前隔离 worktree 连续执行；用户已要求继续直到完成，不重复询问执行方式。

**Goal:** 每次模型请求最多提供 8 个工具，保留按需发现其他已授权只读能力的路径。

**Architecture:** Django 继续拥有完整鉴权目录和业务执行。沿用旧共享路由作基线，关键词仅选择初始业务分组。DSH TypeScript 插件注册一个 find_learning_tools 控制工具；调用后替换当前分组，通过原生工具变更继续同一轮循环。发现工具不增加权限，不调用旧 AIEngine，也不额外建立分类模型服务。

**Tech Stack:** 现有 Django、TypeScript Cordis 插件、DSH SDK 0.2.1rc2；不升级 SDK。

**Spec:** /Users/eular/Desktop/科晟开发/UniMind/规划/2026-10-25-新UniMind完整规划-v1.2.md，第八节工具路由与 M0 工具选择验证。

## Global Constraints

- 不修改主目录脏文件，不部署，不重试当前不可用的官方模型。
- 每组最多 7 个业务工具，加 1 个发现工具，总计最多 8 个；完整业务许可仍为现有 17 个只读工具。
- 所有业务执行仍由 Django 重新鉴权和校验参数；发现结果、工具调用、业务成功分别记录，不能把模拟当模型质量证据。
- 保留每轮最多 4 次模型请求；复杂跨组请求也遵守该预算，不能悄悄增加次数。
- 只做必要聚合冒烟、真实 SDK 协议与类型/构建核验。

## Review Focus

- 权限少或为零时不能通过发现取得额外工具。
- 组切换不得残留旧组模型 Schema 或突破 8 个上限；已接受调用仍能完成。
- 卡片仅来自本轮许可范围的实际工具结果，包括后来发现的工具。
- 会话恢复、记忆更正与权限收缩仍按完整许可版本失效。
- 无法识别、复合请求及短回复可通过发现恢复；没有真实模型证据时不报告准确率提升。

## Task 1：业务分组和上下文

Files: backend/ai_assistant/services/dsh_routing.py、dsh_service.py；既有 dsh 聚合冒烟。

- [x] 定义 resources、practice、progress、mastery 四组，覆盖当前 17 个业务工具。
- [x] 初始分组复用 classify_intent_keywords；general 只给发现工具，未授权用户仍零工具。
- [x] context 同时给出初始 tools、完整 available_tools 和过滤后的 tool_groups；权限 hash 继续基于完整业务许可。
- [x] 保留旧候选诊断，新增初始组、可见上限和实际 Schema 开销。
- [x] 聚合冒烟验证许可、上限、代表问法及漏选后的可发现能力。

## Task 2：原生工具发现和事件适配

Files: dsh/plugin.ts、gateway.py、cards.py、host.py、smoke.py。

- [x] 插件注册当前组与 find_learning_tools；发现只在已有 tool_groups 内选择并替换组，返回可用工具摘要。
- [x] 网关允许集合由完整业务许可和发现工具组成，仍拒绝其他工具和通用执行能力；记录每请求工具数及 Schema bytes。
- [x] 卡片校验覆盖后来发现的已授权工具，保持原生 meta 与模型内容分离。
- [x] 真实 SDK 验证发现→业务工具→回答的三步链路及每请求上限。
- [x] 八卡片演示在 4 次请求内跨组完成；保留原生恢复和记忆失效验证。

## Task 3：界面、记录与最终审查

Files: frontend/src/pages/DshM0.tsx、dsh/README.md、迁移记录。

- [x] 页面区分旧候选、初始组、当前许可和按需发现，显示实际请求工具数及 Schema。
- [x] 完成插件类型检查、前端构建、浏览器真实可见检查。
- [x] 一次独立代码复核，修复必要问题，记录证据后本地提交。

## Decisions

选择按需发现而非新增单独分类请求，是本次实现判断：它可在已有 4 次请求预算中恢复漏选，并减少首轮 Schema；代价是跨组任务可能多一轮。真实模型的选择质量、时延与成本仍须官方账户恢复后比较，不能仅凭 Schema 变小判定更优。

## 定向结果

4 项后端聚合冒烟通过；必要只读工具仍覆盖，注册用户零业务工具、零发现工具。下表为初始组覆盖与规范化 Schema，不是模型任务完成率。

| 问法场景 | 初始组 | 工具数（含发现） | 初始 Schema bytes |
|---|---|---:|---:|
| 最近练习 | progress | 8 | 4984 |
| 错题讲解 | practice | 7 | 4311 |
| 视频来源 | resources | 4 | 2920 |
| 待复习 | mastery | 7 | 3959 |
| 实际学习记录 | progress | 8 | 4984 |
| 抽题 | practice | 7 | 4311 |
| 课程推荐 | resources | 4 | 2920 |
| 短回复延续 | practice | 7 | 4311 |
| 纯问候 | 按需发现 | 1 | 719 |
| 跨学生诱导 | progress | 8 | 4984 |
| 笔记写入退出 | progress | 8 | 4984 |

独立复核发现立即切组会注销同批后续调用。真实 SDK 的 discovery-first 顺序先复现仅返回 3 张卡片；修复为发现工具暂存选择，在下一次 system-prompt/assemble 中同步替换注册和本次 Schema。旧组本批已接受调用保留，下一次请求只提供新组。

修复记录：pre-step 的初版会使模型声明晚一轮，实际 HTTP 请求检查已复现；最终改为 assembly waterfall。discovery-first 八卡片、三请求发现恢复、13 项边界冒烟、4 项后端聚合冒烟、严格类型检查和前端构建通过。浏览器实际显示 find_learning_tools → search_courses，1/4/4 个工具与 687/2792/2792 bytes；截图 .m0-state/m0-group-discovery-proof.png。真实模型质量未验收。
