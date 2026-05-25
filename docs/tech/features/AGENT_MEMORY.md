# Agent 记忆系统

## 概述

Agent 记忆系统让 AI 助教能够跨会话记住用户的关键信息（偏好、学业状态、交互习惯），并在后续对话中自动注入上下文，实现"越用越懂你"的体验。

## 架构

```
用户对话 → process_ai_chat()
  ├── 对话前：get_memories_for_injection() → 注入 system prompt
  └── 对话后：extract_memories_async() → 后台线程提取 → 写入 AgentMemory
```

## 数据模型

`ai_assistant/models.py` — `AgentMemory`

| 字段 | 类型 | 说明 |
|------|------|------|
| user | FK → User | 记忆归属 |
| memory_type | CharField(20) | `preference` / `academic` / `interaction` / `teacher_context` |
| key | CharField(200) | 记忆键，如"偏好数学推导风格" |
| value | TextField | 记忆值，如"喜欢用具体例子先引入" |
| source | CharField(20) | `auto`（AI 提取）/ `manual`（用户设置） |
| confidence | Float | 置信度 0-1 |
| use_count | Integer | 被引用次数 |
| is_active | Boolean | 是否启用 |

索引：`(user, memory_type, is_active)`

## 记忆服务

`ai_assistant/services/memory_service.py`

### 检索（对话注入）

```python
get_memories_for_injection(user, limit=10) -> str
```

- 按 `updated_at` + `use_count` 排序，取 top N
- 拼接为 markdown 格式，上限 800 字符
- 更新 `use_count` 和 `last_used_at`

### 提取（对话后）

```python
extract_memories_async(user, conversation_history)
```

- 后台线程调用 `AIEngine.call_ai()` + `memory_extraction_prompt.txt`
- 解析 JSON 输出 `{memories: [{type, key, value, confidence}]}`
- 按 key 去重：已存在则更新 confidence，不存在则创建
- 低 confidence（<0.3）的记忆自动标记 `is_active=False`

### CRUD

标准增删改查，用户只能操作自己的记忆。手动创建的记忆自动设 `source='manual'`。

## API

| Method | Path | 说明 |
|--------|------|------|
| GET | `/api/ai/memories/` | 列表（支持 `?type=preference` 过滤） |
| POST | `/api/ai/memories/` | 创建手动记忆 |
| PATCH | `/api/ai/memories/<id>/` | 更新 |
| DELETE | `/api/ai/memories/<id>/` | 删除 |

## 记忆注入位置

`ai_assistant/services/chat_service.py` — `_build_agent_system_prompt()`

在 base prompt 和 tool guide 之间插入：

```
## 用户记忆
- 偏好用具体例子引入概念（来源：历史对话）
- 目标院校：清华五道口（来源：用户设置）
```

## Prompt 模板

`prompts/ai_assistant/memory_extraction_prompt.txt`

指导 AI 从对话中提取结构化记忆，输出 JSON schema：
```json
{"memories": [{"type": "preference", "key": "...", "value": "...", "confidence": 0.8}]}
```

## 迁移

- `ai_assistant/0006_agentmemory.py` — schema migration
