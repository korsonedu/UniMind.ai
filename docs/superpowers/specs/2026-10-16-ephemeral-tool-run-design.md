# UniMind 临时工具任务系统设计

## 背景

UniMind 的 planner 和 exam generator 已支持多轮工具调用，但工具解析、执行、权限、错误处理和 Task 事件都集中在 `AIEngine.call_ai_with_streaming_tools()` 中。当前 Task 清单以模型单轮工具批次为边界，新一轮会覆盖前一轮，并且只有 `running` 和 `done` 两种状态。工具返回错误时，前端仍可能显示为完成。

本设计只处理单次聊天请求内的临时任务。不引入数据库持久化，不改造 Celery 或 Pipeline 任务，不恢复页面刷新前的执行过程。

## 目标

1. 一次用户请求对应一个临时 Tool Run，多轮工具调用累计到同一张 Task 清单。
2. Task 只展示模型已经返回、即将执行的真实工具调用，不生成预测性计划。
3. 工具名称、套餐权限和参数在执行前统一校验。
4. 工具失败被标记为失败，并将结构化错误返回模型，允许模型改参数后重试。
5. 同一轮的纯只读工具可最多 4 个并行执行。含写操作的批次按原始顺序串行执行。
6. SSE 和 WebSocket 使用同一套状态协议。

## 非目标

- 不增加模型生成的未来步骤计划。
- 不引入外部 Agent 编排框架。
- 不将临时 Task 写入数据库、Redis 或聊天消息 metadata。
- 不改造 `ContentPipelineTask` 和相关 Celery 任务。
- 不重新设计 TaskList 的视觉样式。

## 总体架构

新增 `ai_engine/tool_run.py`，定义一个请求级 `ToolRunCoordinator`。

### AIEngine

`AIEngine` 继续负责：

- 向模型发起流式请求。
- 累积标准 `tool_calls` 或文本工具协议。
- 将工具结果追加回多轮 messages。
- 在无工具调用时返回最终文本。

`AIEngine` 不再维护 Task 列表，也不再分别实现并行和串行工具的事件组装。

### ToolRunCoordinator

协调层负责：

- 为单次请求生成 `run_id`。
- 规范化每轮的工具调用，确保 `call_id` 在整个 Tool Run 内唯一。
- 根据套餐过滤后、意图路由前的 tool definitions 建立完整许可 Schema 注册表。
- 校验工具存在性、执行权限、必填参数、参数基本类型和 `additionalProperties: false`。
- 按只读白名单决定并行或串行。
- 识别超时、异常和工具返回的 `error` 对象。
- 生成唯一的 step 状态事件。
- 保留每个工具结果的原始顺序，供 `AIEngine` 追加 tool messages。

### ToolExecutor

`ToolExecutor` 保留业务 handler、套餐权限边界和轨迹日志。调度层在意图路由前把完整的套餐许可工具定义保存到 executor，协调层从中读取 Schema。`ToolExecutor` 不组装 Task 事件，不决定并发策略。

## 事件协议

工具调用统一使用 `step` 事件：

```json
{
  "type": "step",
  "run_id": "run_...",
  "call_id": "call_...",
  "round": 1,
  "name": "get_learning_stats",
  "label": "获取学习统计数据",
  "status": "queued",
  "duration_ms": null,
  "result_summary": null,
  "retry_of": null,
  "error": null
}
```

`status` 只允许：

- `queued`：已确认工具调用，等待执行。
- `running`：已开始执行。
- `succeeded`：执行完成且结果不含工具错误。
- `failed`：名称、权限、参数、超时或执行结果失败。

`error.code` 只允许：

- `unknown_tool`
- `permission_denied`
- `invalid_arguments`
- `timeout`
- `execution_error`

最终 `done` 事件增加 `run_id`，前端用它将运行中任务结束并计算成功与失败数。不再发送 `batch_start` 和嵌套 `task_list.update`。

## 工具调用规范化

1. 标准 API `tool_calls` 保留上游 ID，若 ID 为空或与本 Tool Run 内已有 ID 重复，则生成新 ID。
2. DSML 和 `<function_calls>` 文本协议始终生成新 ID。
3. `arguments` 无法解析为 JSON 对象时，记录 `invalid_arguments`，不执行 handler。
4. 工具不在当前套餐许可集时，记录 `permission_denied`，不执行 handler。
5. 路由预选未包含某工具，但工具仍在套餐许可集时，允许现有的自愈放行。

参数校验只实现项目当前 Schema 使用的范围：object、array、string、integer、number、boolean、required 和 `additionalProperties`。不引入新依赖，不自动转换参数类型。

## 执行策略

### 纯只读批次

如果当轮所有通过校验的工具都在 `_READ_ONLY_TOOLS` 中，则使用最多 4 个 worker 并行执行。事件可按实际完成顺序达到前端，返回给模型的 tool messages 仍按模型原始调用顺序组装。

### 含写操作的批次

只要存在一个非只读工具，当轮全部调用按模型原始顺序串行执行。这避免读写依赖被错误重排。

### 失败与重试

协调层不自动重试。每个失败结果会以结构化 JSON 作为 tool message 返回模型。模型可以修正参数后再次调用，新调用生成新 `call_id`。当新调用的工具名与上一个失败调用一致时，设置 `retry_of`。现有重复工具组合检测继续防止无限循环。

Python 线程无法安全强制终止已运行的 handler。超时后请求链会继续，但原 handler 可能在后台完成。因此写操作不自动重试，并保留这一限制在技术文档中。

最终实现的单工具等待上限为 30 秒。超时、handler 异常和旧式扁平 `error` 返回都会规范化为 `{"error":{"code":"...","message":"..."}}` 后再回灌模型。

## 前端状态

Task reducer 使用 `run_id + call_id` 作为唯一键：

- 收到新 `call_id` 时追加 TaskItem。
- 收到已有 `call_id` 时只更新状态和结果字段。
- 新的 round 不清空已有 TaskItem。
- `succeeded` 和 `failed` 都是终态。
- 最终 `done` 事件到达后，任务列表显示成功数和失败数。
- 全部成功时可按现有逻辑自动收起。存在失败时保持展开，让用户看到失败原因。

TaskList 和 AgentStepCard 保留现有布局和样式系统，只增加排队、失败和完成的状态表达。

## 兼容性

SSE 和 WebSocket 前后端必须同步发布。临时 Task 协议不对外开放，因此不保留 `batch_start` 的长期兼容分支。为避免开发时前后端短暂不匹配，前端 reducer 在本轮可继续忽略旧 `batch_start` 事件，待后端协议稳定后再单独清理。

## 验证

只执行与本协议直接相关的定向检查：

1. 协调层单元测试：唯一 ID、Schema 校验、套餐权限、错误分类。
2. 执行测试：只读并行、写操作串行、结果顺序稳定。
3. 流式 Agent 测试：多轮调用共用 `run_id`，失败结果返回模型，文本工具协议不泄漏。
4. 前端类型检查和生产构建。

不执行无关的全量后端回归或浏览器端到端测试。

## 完成标准

- 多轮工具调用持续追加到同一个 Tool Run。
- 所有 `call_id` 在单次 Tool Run 内唯一。
- 任何工具失败都不显示为成功。
- 套餐外工具不会进入 handler。
- 参数错误会返回模型，模型重试生成新 TaskItem。
- 独立只读工具在流式路径真正并行执行。
- SSE 和 WebSocket 的 Task 状态表现一致。
- 定向测试、TypeScript 检查和前端构建通过。
