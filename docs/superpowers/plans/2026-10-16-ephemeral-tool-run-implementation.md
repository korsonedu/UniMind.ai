# UniMind Ephemeral Tool Run Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** 将一次聊天请求中的多轮真实工具调用收敛为一个临时 Tool Run，统一参数校验、权限检查、并发执行、失败反馈和前端 Task 状态。

**Architecture:** 新增请求级 `ToolRunCoordinator`，由它规范化和执行工具调用并发出统一 `step` 事件；`AIEngine` 只保留模型流和 messages 循环；前端用纯 reducer 按 `run_id + call_id` 累积 Task。协调层只使用套餐过滤后的完整工具定义，不扩大现有权限边界。

**Tech Stack:** Python 3、Django、pytest、`concurrent.futures`、React 18、TypeScript、Vite。

**Spec:** [2026-10-16-ephemeral-tool-run-design.md](../specs/2026-10-16-ephemeral-tool-run-design.md)

## Global Constraints

- 只修改本计划列出的文件，不改 Celery、Pipeline、数据库和 Redis。
- 不引入第三方编排或 JSON Schema 依赖，只实现项目当前工具定义使用的 Schema 子集。
- 保留 `ToolExecutor` 现有 handler、日志和路由自愈逻辑，协调层只在执行前收紧校验。
- 同轮只要含一个写工具，全部按模型原顺序串行；纯只读批次最多 4 个 worker。
- Python 超时只能停止等待，无法杀死已经运行的线程。协调层不得自动重试写工具。
- 前端只增加协议和状态表达，不重新设计现有 TaskList。
- 工作区若出现用户手工改动，只暂存本计划产生的文件或独立 hunk。无法安全拆分时保留未提交，禁止把用户改动带入提交。
- 只做本文列出的聚焦测试，不跑全量回归或浏览器端到端测试。

## Review Focus

- 套餐外工具、未知工具和非法参数在进入 handler 前失败。
- 路由漏选但套餐许可的工具仍可执行，Schema 取自路由前完整定义。
- 并发完成顺序可以变化，返回给模型的 tool messages 必须保持模型调用顺序。
- `queued → running → succeeded|failed` 对同一 `call_id` 单调变化，失败不得显示为完成。
- 多轮调用沿用同一 `run_id`，新调用不得覆盖旧 TaskItem。
- SSE 和 WebSocket 的 `done` 都携带相同来源的 `run_id`。

---

## Task 1: 建立协调层的数据模型、调用规范化和参数校验

**Files:**

- Create: `backend/ai_engine/tool_run.py`
- Create: `backend/ai_engine/tests/test_tool_run.py`

**Interfaces:**

```python
@dataclass(frozen=True)
class PreparedToolCall:
    index: int
    tool_call: dict
    call_id: str
    name: str
    arguments: dict
    label: str
    retry_of: str | None = None
    error: dict | None = None


@dataclass(frozen=True)
class ToolCallOutcome:
    call: PreparedToolCall
    result: str
    failed: bool
    error: dict | None = None


```

`ToolRunCoordinator` 构造参数固定为 `tool_executor`、`tool_definitions`、`on_step=None`、`read_only_tools=frozenset()`、`run_id=None`、`max_workers=4`。公开执行接口固定为 `execute_batch(tool_calls: list[dict], round_number: int) -> list[ToolCallOutcome]`。

- [x] 在 `test_tool_run.py` 写最小失败测试，覆盖上游空 ID、重复 ID、文本协议 `dsml_` ID 都被替换为本 Run 唯一且带 `call_` 前缀的 ID。
- [x] 写参数校验失败测试，覆盖 JSON 非对象、缺少 required、基本类型错误和 `additionalProperties: false`。
- [x] 写权限边界测试，区分 `unknown_tool` 和 `permission_denied`，并确认两者都不调用 executor。
- [x] 运行红灯测试：

  ```bash
  cd backend
  .venv/bin/python -m pytest ai_engine/tests/test_tool_run.py -q
  ```

- [x] 在 `tool_run.py` 实现 `_tool_registry()`。优先读取 executor 上的 `_permitted_tool_definitions`，未设置时使用构造参数中的 `tool_definitions`。
- [x] 实现 `_normalize_call()`。保留本 Run 内首次出现的标准上游 ID；空 ID、重复 ID 和 `dsml_` 前缀 ID 使用 `call_{uuid4().hex}`。
- [x] 实现递归 `validate_arguments(schema, value, path='$')`，只支持 `object`、`array`、`string`、`integer`、`number`、`boolean`、`required`、`additionalProperties`，并明确排除 Python `bool` 被当作 `integer`。
- [x] 非法调用构造成结构化结果，格式固定为：

  ```python
  json.dumps({"error": {"code": code, "message": message}}, ensure_ascii=False)
  ```

- [x] 重新运行本 Task 测试并确认通过。
- [x] 检查 `git diff -- backend/ai_engine/tool_run.py backend/ai_engine/tests/test_tool_run.py`，确认没有超出协调层范围的实现。
- [x] 如工作区可安全暂存，提交：`git add backend/ai_engine/tool_run.py backend/ai_engine/tests/test_tool_run.py && git commit -m "feat: add tool run coordinator validation"`。

## Task 2: 实现统一生命周期、并发策略和失败关联

**Files:**

- Modify: `backend/ai_engine/tool_run.py`
- Modify: `backend/ai_engine/tests/test_tool_run.py`

**Interfaces:**

协调层只发送如下事件，不发送 `batch_start` 或 `task_list.update`：

```python
{
    "type": "step",
    "run_id": coordinator.run_id,
    "call_id": call.call_id,
    "round": round_number,
    "name": call.name,
    "label": call.label,
    "status": "queued" | "running" | "succeeded" | "failed",
    "duration_ms": 12,
    "result_summary": "获取 8 条学习记录",
    "retry_of": call.retry_of,
    "error": {"code": "execution_error", "message": "工具执行失败"},
}
```

- [x] 增加失败测试：所有调用先收到 `queued`，合法调用随后收到 `running` 和唯一终态，非法调用直接收到 `failed`。
- [x] 增加只读并发测试。两个阻塞 executor 调用的总耗时应明显小于串行耗时，返回的 outcomes 仍按输入 index 排序。
- [x] 增加混合批次串行测试。一个只读工具加一个写工具时，第二个调用只能在第一个完成后开始。
- [x] 增加错误分类测试，覆盖 handler 抛异常、JSON 结果含 `error`、超时，并断言错误码分别为 `execution_error` 或 `timeout`。
- [x] 增加重试关联测试。同名工具上一次失败后再次出现时，新 `call_id` 的 `retry_of` 指向上次失败 ID；协调层自身不重复执行。
- [x] 运行红灯测试：

  ```bash
  cd backend
  .venv/bin/python -m pytest ai_engine/tests/test_tool_run.py -q
  ```

- [x] 实现 `_emit()`、`_execute_one()` 和 `_classify_result_error()`。用 `time.monotonic()` 计算 `duration_ms`，并调用现有 `generate_step_label`、`summarize_tool_result`、`extract_step_actions`。
- [x] 对 `render_visual` 和 `quick_generate` 保留现有事件附加字段：成功时分别附加 `visual` 或 `questions`，解析失败归类为 `execution_error`。
- [x] 纯只读合法批次用 `ThreadPoolExecutor(max_workers=min(4, len(calls)))` 和 `as_completed()` 执行；混合批次用普通循环执行。
- [x] 并发分支只按完成顺序发送终态事件，方法返回前按 `PreparedToolCall.index` 排序 outcomes。
- [x] 每次失败更新 `_last_failed_by_tool[name]`，成功后移除该工具的失败引用。
- [x] 重新运行本 Task 测试并确认通过。
- [x] 检查协调层没有自动重试、没有状态持久化、没有动态扩大许可集。
- [x] 如可安全暂存，提交：`git add backend/ai_engine/tool_run.py backend/ai_engine/tests/test_tool_run.py && git commit -m "feat: execute tool runs with lifecycle events"`。

## Task 3: 接入 AIEngine，并统一套餐 Schema 和传输层 run_id

**Files:**

- Modify: `backend/ai_engine/service.py`
- Modify: `backend/ai_engine/tests/test_text_tool_calls.py`
- Modify: `backend/ai_assistant/services/tool_executor.py`
- Modify: `backend/ai_assistant/services/chat_service.py`
- Modify: `backend/ai_assistant/services/chat_dispatch.py`
- Modify: `backend/ai_assistant/views.py`
- Modify: `backend/ai_assistant/consumers.py`
- Modify: `backend/ai_assistant/tests/test_tool_executor_permissions.py`
- Modify: `backend/ai_assistant/tests/test_chat_history.py`

**Interfaces:**

路由前同时记录名称和完整定义：

```python
permitted_tools = filter_tools(bot_type, institution, tools)
tool_executor._permitted_tool_names = {
    item['function']['name'] for item in permitted_tools
}
tool_executor._permitted_tool_definitions = {
    item['function']['name']: item for item in permitted_tools
}
tools = route_tools(
    user_message,
    permitted_tools,
    recent_messages=history_messages,
    bot_type=bot_type,
)
```

流式返回值始终包含 Run：

```python
{"content": clean_content, "run_id": coordinator.run_id}
```

- [x] 扩展 `test_tool_executor_permissions.py`，断言路由后的 `_allowed_tool_names` 可以缺少某工具，但 `_permitted_tool_definitions` 仍保存套餐过滤后的完整 Schema。
- [x] 扩展 `test_text_tool_calls.py`，模拟至少两轮工具调用，断言所有 `step` 事件共享 `run_id`、ID 唯一、无 `batch_start`、最终结果含相同 `run_id`。
- [x] 增加失败回灌测试。第一次工具参数非法时，下一轮发给模型的 `role=tool` 内容包含结构化 `invalid_arguments`，模型可用新 `call_id` 再次调用。
- [x] 扩展 SSE 和 WebSocket 定向测试，断言 `done.run_id == result.run_id`。
- [x] 运行红灯测试：

  ```bash
  cd backend
  .venv/bin/python -m pytest ai_engine/tests/test_text_tool_calls.py ai_assistant/tests/test_tool_executor_permissions.py ai_assistant/tests/test_chat_history.py -q
  ```

- [x] 在 `BaseToolExecutor.__init__` 增加空的 `_permitted_tool_definitions`，保持现有 `_permitted_tool_names` 和 `_allowed_tool_names` 语义。
- [x] 在 `chat_service.py` 与 `chat_dispatch.py` 的 `filter_tools()` 后、`route_tools()` 前保存套餐许可名称和完整定义。
- [x] 在 `AIEngine.call_ai_with_streaming_tools()` 进入模型循环前创建一个 `ToolRunCoordinator`，整个请求只创建一次。
- [x] 用 `execute_batch(tool_calls, round_i + 1)` 替换 `_generate_task_list()`、`batch_start`、伪并发和重复的串行执行代码。
- [x] assistant message 使用 coordinator 规范化后的 `tool_call`；tool message 使用对应 outcome 的 `call_id` 和 `result`，并保持原始顺序。
- [x] 重复调用检测改为从 outcomes 读取工具名。保留现有最大轮次和中间文本逻辑。
- [x] 所有流式提前返回和正常返回都附加 `run_id`。错误事件仍按现有路径发送，避免改变 HTTP 错误语义。
- [x] 删除已失去调用方的 `_generate_task_list()` 和流式路径局部标签、摘要、Task 更新代码，只清理由本次替换产生的孤儿 import/变量。
- [x] `views.py` 和 `consumers.py` 发出的最终 `done` 增加 `run_id: result.get('run_id')`，两条传输路径不自行生成 ID。
- [x] 重新运行本 Task 测试并确认通过。
- [x] 如可安全暂存，提交：

  ```bash
  git add backend/ai_engine/service.py backend/ai_engine/tests/test_text_tool_calls.py backend/ai_assistant/services/tool_executor.py backend/ai_assistant/services/chat_service.py backend/ai_assistant/services/chat_dispatch.py backend/ai_assistant/views.py backend/ai_assistant/consumers.py backend/ai_assistant/tests/test_tool_executor_permissions.py backend/ai_assistant/tests/test_chat_history.py
  git commit -m "feat: integrate request scoped tool runs"
  ```

## Task 4: 建立前端 Tool Run reducer，并迁移两个聊天入口

**Files:**

- Create: `frontend/src/types/toolRun.ts`
- Modify: `frontend/src/hooks/useAgentChat.ts`
- Modify: `frontend/src/hooks/useAgentConversation.ts`
- Modify: `frontend/src/components/TaskList.tsx`
- Modify: `frontend/src/components/AgentStepCard.tsx`
- Modify: `frontend/src/components/AgentChatLayout.tsx`
- Modify: `frontend/src/components/AgentTimeline.tsx`
- Modify: `frontend/src/hooks/useXiaoYuEngine.ts`
- Modify: `frontend/src/dev/previewApi.ts`

**Interfaces:**

```typescript
export type ToolTaskStatus = 'queued' | 'running' | 'succeeded' | 'failed';

export interface AgentStep {
  type?: 'step';
  run_id: string;
  call_id: string;
  round: number;
  name: string;
  label: string;
  status: ToolTaskStatus | 'batch_start';
  duration_ms?: number;
  result_summary?: string;
  retry_of?: string | null;
  error?: { code: string; message: string } | null;
  actions?: Array<{ label: string; route: string }>;
  visual?: { type: string; payload: unknown };
  questions?: (GeneratedQuestion & { index: number; answer_preview: string })[];
}

export interface TaskListData {
  run_id: string;
  items: TaskItem[];
  completed: boolean;
}

export function reduceToolRun(
  previous: TaskListData | null,
  event: AgentStep,
): TaskListData | null;

export function completeToolRun(
  previous: TaskListData | null,
  runId?: string,
): TaskListData | null;
```

- [x] 在 `toolRun.ts` 先写纯 reducer，并用 TypeScript 的穷尽分支保证四种状态都被处理。收到 `batch_start` 时原样返回 previous，作为短期兼容。
- [x] reducer 在 `run_id` 变化时建立新 Run；同一 Run 的新 `call_id` 追加，已有 ID 原位合并，保持首次出现顺序。
- [x] `completeToolRun()` 只在 `run_id` 相同或 done 未提供 ID 时设置 `completed: true`，不伪造未收到的终态。
- [x] 将 `AgentStep`、`TaskItem`、`TaskListData` 从组件和 hook 中移到 `types/toolRun.ts`，更新 import，避免 hook 与组件循环依赖。
- [x] `useAgentChat.ts` 每个 step 都调用 `reduceToolRun`；`done` 使用后端 `run_id` 调用 `completeToolRun`。步骤时间线仍按 `call_id` upsert。
- [x] `useAgentConversation.ts` 使用同一 reducer，删除对嵌套 `task_list.update` 的依赖，保留旧 `batch_start` 的忽略逻辑。
- [x] `TaskList.tsx` 将 queued/running 视为活动项，将 succeeded/failed 视为终态。失败项展示错误信息；存在失败时不自动折叠。
- [x] `AgentStepCard.tsx` 将计时条件改为 `running`，增加 queued、succeeded、failed 图标和样式。actions、visual、questions 只在 succeeded 时使用。
- [x] 对 `AgentChatLayout.tsx`、`AgentTimeline.tsx`、`useXiaoYuEngine.ts` 做机械状态迁移：`done` 改为 `succeeded`，`calling` 改为 `running`，失败分支不得触发成功卡片。
- [x] 更新 `previewApi.ts` fixture 为新事件格式，补齐一个固定 `run_id` 和递增 round。
- [x] 运行 TypeScript 和生产构建：

  ```bash
  cd frontend
  npm run build
  ```

- [x] 用 `rg -n "batch_start|task_list\.update|status === 'done'|status: 'done'|status === 'calling'" frontend/src` 检查遗漏，只允许 reducer 的临时 `batch_start` 兼容分支和非工具领域的同名状态。
- [x] 检查 `TaskList.tsx` diff，确保没有覆盖用户现有的折叠动效、间距和样式调整。
- [x] 如可安全暂存，逐文件暂存；若 `TaskList.tsx` 含用户改动，使用 `git add -p frontend/src/components/TaskList.tsx` 并检查 `git diff --cached`。提交：`git commit -m "feat: show cumulative tool run tasks"`。

## Task 5: 聚焦验收和技术说明

**Files:**

- Modify: `docs/superpowers/specs/2026-10-16-ephemeral-tool-run-design.md`
- Modify: `docs/superpowers/plans/2026-10-16-ephemeral-tool-run-implementation.md`

- [x] 在设计文档的执行限制处补充最终实现采用的超时行为和实际事件字段，若实现与设计一致则不改正文。
- [x] 运行协调层和已有相关测试：

  ```bash
  cd backend
  .venv/bin/python -m pytest ai_engine/tests/test_tool_run.py ai_engine/tests/test_text_tool_calls.py ai_assistant/tests/test_tool_permissions.py ai_assistant/tests/test_tool_executor_permissions.py ai_assistant/tests/test_chat_history.py ai_assistant/tests/test_conversation_projects.py -q
  ```

- [x] 运行 Python 语法检查：

  ```bash
  cd backend
  .venv/bin/python -m compileall -q ai_engine ai_assistant
  ```

- [x] 再次运行前端构建：

  ```bash
  cd frontend
  npm run build
  ```

- [x] 检查最终差异：`git diff --check`、`git status --short`、`git diff --stat`。
- [x] 对照 Review Focus 人工检查：权限边界、Schema 来源、结果顺序、run_id 贯通、失败终态和前端累计逻辑。
- [x] 将本计划实际完成项改为 `[x]`，未完成项保留并写明原因。
- [x] 如文档产生变更且可安全暂存，提交：`git add docs/superpowers/specs/2026-10-16-ephemeral-tool-run-design.md docs/superpowers/plans/2026-10-16-ephemeral-tool-run-implementation.md && git commit -m "docs: record tool run implementation"`。

## Completion Evidence

实施完成时必须给出以下证据，不以“应该可用”代替：

- 后端聚焦 pytest 的通过数量和命令。
- `compileall` 成功。
- 前端 `npm run build` 成功。
- 一组多轮事件样例，能看到同一 `run_id` 下多个不同 `call_id`。
- 一组失败样例，能看到 `failed`、结构化 error 和后续 `retry_of`。
- 最终修改文件清单，以及用户原有改动未被带入提交的说明。
