# Agent 代码结构简化设计

日期：2026-05-28
状态：Approved

## 问题

Agent 行为定义散落在 4+ 个位置，改一个 bot 需要同时改 5-6 个文件：

1. **Prompt 碎片化**：DB `Bot.system_prompt`、文件 `bot_{id}_prompt.txt`、`chat_service.py` inline tool guide、seed 命令硬编码 — 四处定义，互相不同步
2. **bot_type 分发重复**：`consumers.py`、`views.py`（3 个入口）、`chat_service.py` 各有 if/elif 判断该用哪个 ToolExecutor
3. **无统一注册表**：bot_type → (ToolExecutor, tools, prompt) 的映射隐含在散落的 if/elif 中

## 方案

Bot Registry + File Templates + Shared Dispatch。

### 1. Bot Registry

新增 `backend/ai_assistant/bot_registry.py`，唯一注册表：

```python
@dataclass
class BotProfile:
    name: str                          # "xiaoyu", "exam_generator", "assistant"
    bot_type: str                      # Bot model 的 bot_type 值
    executor_class: type[AssistantToolExecutor]
    tools_factory: callable            # get_planner_tools, etc.
    prompt_dir: str                    # prompts 文件目录名
    is_exclusive: bool = False
    model_tier: str = "fast"

BOT_REGISTRY: dict[str, BotProfile] = {
    "planner": BotProfile(...),
    "exam_generator": BotProfile(...),
    "assistant": BotProfile(...),
}

def get_bot_profile(bot_type: str) -> BotProfile:
    return BOT_REGISTRY.get(bot_type, BOT_REGISTRY["assistant"])
```

新增 bot 流程：写 prompt 文件 → 在 `BOT_REGISTRY` 加一行 → （可选）写 ToolExecutor 子类。

### 2. Prompt 文件结构

从按 ID 命名 + inline Python 改为按 bot 名称组织、职责分离：

```
backend/prompts/ai_assistant/bots/
├── xiaoyu/
│   ├── system_prompt.txt       # 核心人设 + 行为指令
│   ├── tool_guide.txt          # 工具使用指南
│   └── personality.txt          # 机构人格注入模板（含 {teaching_style} {tone} 占位符）
├── exam_generator/
│   ├── system_prompt.txt
│   ├── tool_guide.txt
│   └── personality.txt
└── assistant/
    ├── system_prompt.txt
    ├── tool_guide.txt
    └── personality.txt
```

Prompt 组装顺序（chat_service.py 中）：
1. `system_prompt.txt` → 核心人设
2. `tool_guide.txt` → 工具使用指南
3. `personality.txt` → 机构人格（如有 institution，模板填充）
4. `memory_context` → 运行时注入（记忆 + 学术数据）
5. `prompt_adapter` directives → 自适应指令

### 3. Shared Dispatch

新增 `backend/ai_assistant/services/chat_dispatch.py`，封装 3 个入口的共用逻辑：

```python
def dispatch_bot_chat(
    bot: Bot,
    user: User,
    message: str,
    history: list[dict],
    institution=None,
    *,
    stream: bool = False,
    on_tool_call=None,
    on_tool_result=None,
) -> dict | Generator:
    profile = get_bot_profile(bot.bot_type)
    system_prompt = build_system_prompt(bot, profile, user, institution)
    executor = profile.executor_class(user=user, institution=institution)
    tools = profile.tools_factory(user, institution)
    ...
```

3 个入口简化：
- `consumers.py` (WebSocket) → 调 `dispatch_bot_chat(stream=True, on_tool_call=..., on_tool_result=...)`
- `views.py AIChatView` (Polling) → 调 `dispatch_bot_chat()`
- `views.py AIChatStreamView` (SSE) → 调 `dispatch_bot_chat(stream=True)`

## 文件变更清单

| 操作 | 文件 | 说明 |
|------|------|------|
| 新增 | `ai_assistant/bot_registry.py` | Bot 注册表 |
| 新增 | `ai_assistant/services/chat_dispatch.py` | 统一 dispatch |
| 新增 | `prompts/ai_assistant/bots/xiaoyu/system_prompt.txt` | 从 bot_4 + seed 合并 |
| 新增 | `prompts/ai_assistant/bots/xiaoyu/tool_guide.txt` | 从 chat_service.py 提取 |
| 新增 | `prompts/ai_assistant/bots/xiaoyu/personality.txt` | 从 chat_service.py 提取 |
| 新增 | `prompts/ai_assistant/bots/exam_generator/` (3 文件) | 同上 |
| 新增 | `prompts/ai_assistant/bots/assistant/` (3 文件) | 同上 |
| 改 | `ai_assistant/services/chat_service.py` | 删除 inline tool guide，改用文件加载 |
| 改 | `ai_assistant/consumers.py` | 删除 if/elif，调 dispatch_bot_chat |
| 改 | `ai_assistant/views.py` | 同上 |
| 改 | `management/commands/seed_xiaoyu.py` | 删除硬编码 prompt，从文件读取 |
| 改 | `management/commands/seed_exam_agent.py` | 同上 |
| 改 | `ai_assistant/prompt_sync.py` | 简化或废弃 |
| 删除 | `prompts/ai_assistant/base_assistant_prompt.txt` | 未使用 |
| 删除 | `prompts/ai_assistant/bots/bot_1~5_prompt.txt` | 迁移后删除 |
| 不动 | `ai_engine/tools.py` | Tool schema 不变 |
| 不动 | `services/tool_executor.py` | ToolExecutor 子类不变 |
| 不动 | `ai_engine/config.py` | 模型路由不变 |
| 不动 | `models.py` | Bot 模型不变 |

## 迁移策略

渐进式迁移，每步可独立测试和回滚：

1. **Phase 1**：创建 `bot_registry.py` + prompt 文件目录结构
2. **Phase 2**：创建 `chat_dispatch.py`，内部调用现有 chat_service 逻辑
3. **Phase 3**：3 个入口切换到 dispatch_bot_chat（先 polling，再 SSE，最后 WebSocket）
4. **Phase 4**：清理 chat_service.py inline tool guide，改为文件加载
5. **Phase 5**：清理 seed 命令、prompt_sync、废弃文件

## 验证

- `make backend-check` 通过
- 3 个入口（polling/SSE/WebSocket）功能不变
- 修改 prompt 文件后重启服务，bot 行为即时生效
- 新增 bot 只需：prompt 文件 + registry 一行
