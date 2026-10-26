# DSH 长期记忆提取迁移

日期：2026 年 10 月 26 日。目标：把每轮对话后的长期记忆提取从旧 text 模型调用迁到服务端 DSH 结构化任务，并保证来源、去重、删除和停用边界。

## 边界

- UNIMIND_DSH_MEMORY_ENABLED 默认关闭；关闭时保留原 memory_service 提取路径。
- 固定 fast 模型、800 tokens、一次请求，无重试或供应商 fallback。
- 只接受用户亲口明确陈述的事实；evidence 必须出现在本轮用户消息中，confidence 不低于 0.6。
- 手动设置或已停用的记忆不被自动覆盖。
- 同一 conversation_id + 用户消息哈希只处理一次；删除记忆后同轮不重建。
- 开关开启时停用 mem0 自动提取，保留检索。
- 不迁移记忆分析、个性化指引等其他模型分支。

## 实现

- AgentMemory 增加 evidence、source_conversation_id 和 dsh 来源；新增 MemoryExtractionLog 幂等记录。
- dsh_tasks 增加 assistant.memory_extract 任务与 submit_memories schema。
- gateway 增加 fast/1 次/800 tokens 预算，temperature 0.2。
- memory_service 增加 DSH 提取、候选校验、合并与回退边界；views 两个入口传入 conversation_id。
- 迁移：ai_assistant/0031_agentmemory_evidence_and_more.py。

## 验证

- 定向测试 24 passed：evidence 校验、低置信度拒绝、手动/停用不被覆盖、同轮幂等、删除后不重建、失败不写日志、mem0 自动提取停用、固定预算。
- Django check 无问题，makemigrations 无遗漏，网关冒烟 7 tests OK。
- 未验收：真实模型提取质量、生产开关、正式留存与跨端同步。
