# `@unimind/mcp-proxy`

零依赖本地 `stdio ↔ Streamable HTTP` 桥接器，让只支持本地 `stdio` 的桌面端 MCP 客户端（如 **Claude Desktop**、**Raycast**、**Obsidian MCP 插件**）一行命令接入 UniMind.ai 学习记忆 MCP 服务。

## 快速使用

先在 UniMind「设置 → 高级 → 外部 Agent」创建一次性 Bearer 凭证，然后按对应客户端填入配置：

### Claude Desktop (`claude_desktop_config.json`)

```json
{
  "mcpServers": {
    "unimind-learning-memory": {
      "command": "npx",
      "args": [
        "-y",
        "@unimind/mcp-proxy",
        "--url",
        "https://unimind-ai.com/api/ai/learning-memory/mcp/"
      ],
      "env": {
        "UNIMIND_LEARNING_MEMORY_TOKEN": "umlm_your_token_here"
      }
    }
  }
}
```

### Raycast / Obsidian MCP 插件

- **Command**: `npx`
- **Args**: `-y @unimind/mcp-proxy --url https://unimind-ai.com/api/ai/learning-memory/mcp/`
- **Env**: `UNIMIND_LEARNING_MEMORY_TOKEN=umlm_your_token_here`

## 本地开发测试

```bash
npm test
```
