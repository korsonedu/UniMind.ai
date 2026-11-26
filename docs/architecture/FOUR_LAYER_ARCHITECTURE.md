# UniMind 总体架构：事实—状态—决策—视图

> 规范基线：2026-11-27｜对应 `backend/ai_assistant/services/` 五子包架构与全链路 `trace_id` 观测契约。

## 1．第一性原理：逐层提取与投影 + ULR 纵贯脊柱

UniMind 以 **事实层（Fact）→ 状态层（State）→ 决策层（Decision）→ 视图层（View）** 作为四层纵向信息平面，以 **ULR 运行时内核（`runtime/`）** 作为纵贯四层的受控执行、权限复核与事务脊柱：

- **越往下越客观、确定、慢变、唯一**（L1 事实不可篡改，权限与版本以 L1 为最终裁决）；
- **越往上越个性、生成、快变、多态**（同一份 L2/L3 状态按角色、终端与媒介实时投影为对话、卡片、交互实验、工作区、教研台或外部 Agent MCP 视图）；
- **单向依赖 + 权威穿刺**：`L4 → L3 → L2 → L1`，允许明确确定性指令走 **1 → 4 直编短路（0 模型请求）**，所有视图交互经 ULR 校验后落盘回 L1 形成闭环。

## 2．代码子包映射（`backend/ai_assistant/services/`）

| 子包 | 层级 | 核心职责与代表模块 |
| :--- | :--- | :--- |
| `facts/` | **L1 事实层** | 原始来源、行为事实、披露捕获、修订事务与观测留痕：`source_reader`、`learning_tasks`、`learning_library`、`learning_diagnostics`、`diagnostic_revisions`、`teaching_sidecar`、`course_context`、`chat_images`、`external_video_context` |
| `state/` | **L2 状态层** | 事实的提取与物化：`project_state`、`bep/`（贝叶斯掌握估计）、`sdtm/`（个人条件、任务帧、规范事实）、`prism/`（自分化迁移内核）、`knowledge/`（版本化知识图谱与闭包续延）、`rsi/`（离线影子评测） |
| `decision/` | **L3 决策层** | 目标拆解、阶段规划、教学策略与门禁：`project_learning`、`ulr_teaching`、`prism_gate`、`prism_execution`、`method_adoption`、`public_methods`、`learning_guidance` |
| `views/` | **L4 视图层** | 多端多模态投影（无权威状态）：`cards`、`stream`、`recall_projection`、`step_formatting`、`planner_visuals`、`ulr_artifacts`、`title_generator`、`language`、`guidance_messages` |
| `runtime/` | **ULR 纵贯脊柱** | 执行控制、版本化工具指令编译、领域能力、权限桥接与恢复：`xiaoyu_turn`、`bridge`、`tool_routing`、`ulr_runtime`、`ulr_tool_program`、`ulr_capabilities`、`ulr_outbox`、`ulr_history`、`fixed_tasks`、`scope`、`learning_memory_oauth` |

*(注：旧平铺路径保留 `sys.modules[__name__] = _impl` 同对象别名以兼容存量引用与测试；由 `backend/ai_assistant/tests/test_architecture_layers_smoke.py` 在 CI 中自动守护全部 68 个规范模块、单向依赖边界与禁止新增平铺文件红线。)*

## 3．LLM 与确定性引擎分工

- **L1 事实层**：100% 确定性（哈希快照、版本锁、权限表、幂等结算），模型无直接写权威；
- **L2 状态层**：确定性内核主导（BEP / Memorix / 闭包签名 / PRISM / 时间窗裁决），模型仅作受控 Schema 提取器；
- **L3 决策层**：硬规则与审批闸门由系统把控，模型在受权动作空间内做语义规划；
- **L4 视图层**：结构化卡片/MCP/1→4 直编走确定性通道，讲解/追问/交互实验由模型生成。

## 4．三大跨层硬合同

1. **溯源指针合同**：上层状态、决策与摘录必须携带 `source_id + revision/digest`，支持穿透回查 L1；
2. **全链路 Trace 合同**：由 `ai_engine/observability.py`（`observe_runtime` / `observe_background`）将同一 `trace_id` 贯穿小宇前台、恢复接口、RSI sidecar、后台记忆/标题任务及 MCP 端点；
3. **失效撤权级联合同**：L1 撤权、删笔记、知识实质换版或全端登出时，级联令 L2 失效、L3 停止引用、L4 阻断历史转述。
