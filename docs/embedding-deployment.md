# 本地语义记忆模型

聊天仍使用现有云端模型。语义记忆与工具检索共用一个仅监听 `127.0.0.1:8012` 的 llama.cpp 服务，避免 Django、Celery 分别加载模型。

## 固定资源

- 运行时：llama.cpp `b11707`，官方 `llama-b11707-bin-ubuntu-x64.tar.gz`。
- 运行时 SHA256：`88879871f765c3dec22260046e10a76e2ed38de5bdf4a7f68049245a8f4056c8`。
- 模型：`Qwen/Qwen3-Embedding-0.6B-GGUF`，提交 `370f27d7550e0def9b39c1f16d3fbaa13aa67728`。
- 文件：`Qwen3-Embedding-0.6B-Q8_0.gguf`，639150592 字节。
- 模型 SHA256：`06507c7b42688469c4e7298b0a1e16deff06caf291cf0a5b278c308249c3e439`。

资源从官方 [llama.cpp Releases](https://github.com/ggml-org/llama.cpp/releases/tag/b11707) 和 [Qwen 模型仓库](https://huggingface.co/Qwen/Qwen3-Embedding-0.6B-GGUF/tree/370f27d7550e0def9b39c1f16d3fbaa13aa67728) 下载，权重不提交 Git。

## 部署

将运行时解压至 `/opt/unimind-embedding/llama-b11707/`，模型放到 `/opt/unimind-embedding/models/`，保留运行时附带的共享库。安装 `scripts/unimind-embedding.service` 到 systemd，然后启用服务。

在生产 `backend/.env` 中设置：

```dotenv
USE_MEM0=true
MEM0_TELEMETRY=false
AI_EMBEDDING_BASE_URL=http://127.0.0.1:8012/v1
AI_EMBEDDING_MODEL=Qwen/Qwen3-Embedding-0.6B
AI_EMBEDDING_DIMENSIONS=1024
AI_EMBEDDING_API_KEY=local
```

模型使用 last pooling、1024 维向量。当前 2 核、3.5 GB 内存服务器将上下文限制为 8192 token，使用 Q8 KV 缓存和 Flash Attention，单槽运行，CPU 配额为 150%，内存上限为 1400 MB。该限制低于模型原生上下文能力，用于给现有应用保留资源，同时覆盖最近 10 条对话的记忆提取。

先验证模型服务 `/health` 和 `/v1/embeddings`，再重启 `unimind.service`、`unimind-celery.service`。最后检查后端 `/health/` 的数据库及缓存状态，并在隔离的记忆命名空间验证写入、检索和删除。

mem0 使用 PostgreSQL pgvector，按机构分表，查询附带用户过滤；操作历史保存在 `backend/.cache/mem0/history_inst_<id>.db`。旧向量与新模型的维度或向量空间不兼容，更换模型前必须检查现有集合，不能混用。

## 回退

保留发布前 `.env` 副本与应用提交号。异常时恢复应用版本和配置，重启 UniMind、Celery，停止 `unimind-embedding.service`。不要删除用户记忆表、结构化记忆或历史文件。
