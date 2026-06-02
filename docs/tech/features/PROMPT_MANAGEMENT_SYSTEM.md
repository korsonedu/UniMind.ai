# Prompt 管理系统

> 最后更新：2026-05-28

## 概述

Agent 的 system prompt、tool guide、机构人格全部以 **txt 文件** 存储在 `backend/prompts/ai_assistant/bots/` 下，按 bot 名称组织目录。修改 prompt 只需编辑文件，重启服务即生效，不用改 Python 代码。

## 目录结构

```
backend/prompts/ai_assistant/bots/
├── xiaoyu/
│   ├── system_prompt.txt       # 核心人设 + 行为指令
│   ├── tool_guide.txt          # 工具使用指南
│   └── personality.txt          # 机构人格注入模板
├── exam_generator/
│   ├── system_prompt.txt
│   ├── tool_guide.txt
│   └── personality.txt
└── assistant/
    ├── system_prompt.txt
    ├── tool_guide.txt
    └── personality.txt
```

## Prompt 组装流程

运行时由 `AssistantChatService._build_agent_system_prompt()` 按顺序拼接：

1. **system_prompt.txt** — 核心人设（通过 `load_system_prompt()` 加载，fallback 到 DB `Bot.system_prompt`）
2. **tool_guide.txt** — 工具使用指南（通过 `load_tool_guide()` 加载）
3. **机构人格** — `Bot.institution_personality` JSONField 动态注入
4. **记忆上下文** — 结构化记忆 + mem0 语义记忆（运行时）
5. **自适应指令** — `prompt_adapter` 基于用户行为模式生成（运行时）

## 加载机制

`prompt_sync.py` 提供统一的文件加载接口：

| 函数 | 用途 |
|------|------|
| `load_system_prompt(bot)` | 加载 system_prompt.txt，fallback 到 DB |
| `load_tool_guide(bot)` | 加载 tool_guide.txt |
| `load_personality_template(bot)` | 加载 personality.txt |
| `sync_bot_prompt(bot)` | 文件优先覆盖 DB（seed 命令用） |

文件路径由 `bot_registry.get_bot_profile(bot.bot_type).prompt_dir` 决定。

## Bot Registry

`bot_registry.py` 是唯一注册表，定义 `BOT_REGISTRY` 字典：

```python
BOT_REGISTRY = {
    'planner': BotProfile(name='小宇', prompt_dir='xiaoyu', ...),
    'exam_generator': BotProfile(name='命题官', prompt_dir='exam_generator', ...),
}
```

新增 bot 只需：
1. 写 prompt 文件到 `prompts/ai_assistant/bots/{name}/`
2. 在 `BOT_REGISTRY` 加一行
3. （可选）写 ToolExecutor 子类

## 修改 Prompt 的操作步骤

### 修改现有 bot 的 prompt

直接编辑对应的 txt 文件，重启服务即可：

```bash
# 例：修改出题助手的工作流
vim backend/prompts/ai_assistant/bots/exam_generator/system_prompt.txt

# 重启服务
sudo systemctl restart unimind.service
```

### 新增 bot

1. 创建目录和 prompt 文件：
```bash
mkdir backend/prompts/ai_assistant/bots/my_bot
# 创建 system_prompt.txt, tool_guide.txt, personality.txt
```

2. 在 `bot_registry.py` 注册：
```python
'my_bot': BotProfile(
    name='My Bot',
    bot_type='my_bot',
    executor_class=None,  # 延迟加载
    tools_factory=None,
    prompt_dir='my_bot',
    ...
),
```

3. 创建 Bot 数据库记录：
```python
Bot.objects.create(name='My Bot', bot_type='my_bot', system_prompt='')
```

4. 同步 prompt 到 DB：
```bash
python manage.py seed_my_bot  # 或手动调 sync_bot_prompt
```

## 历史说明

此前 system prompt 存储在 `Bot.system_prompt` DB 字段中，tool guide 硬编码在 `chat_service.py` 的 Python 字符串里。2026-05-28 重构后统一迁移到文件模板。
