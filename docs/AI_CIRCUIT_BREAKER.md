# AI 熔断降级与冗余机制 (AI Circuit Breaker & Fallback)

## 1. 背景与动机
本系统深度依赖大语言模型 (LLM) 进行题目生成、主观题批改和复试模拟。
在生产环境中，第三方 API（如 OpenAI, 智谱, DeepSeek）不可避免地会遇到以下问题：
- API 服务宕机或网络超时。
- 账户余额耗尽或触发 Rate Limit (如 429 Too Many Requests)。
- AI 输出严重格式错误（如 JSON 解析失败、幻觉）。

如果没有任何保护机制，API 的故障将直接导致 C 端学生无法做题、无法看解析，造成严重的客诉。因此，系统必须具备**高可用性 (High Availability)** 和 **优雅降级 (Graceful Degradation)** 能力。

## 2. 核心架构设计

### 2.1 熔断器模式 (Circuit Breaker Pattern)
我们在请求大模型的入口处（如 `backend/ai_engine/service.py`）引入熔断器：
- **闭合状态 (Closed)**：正常请求 API。记录失败次数。
- **断开状态 (Open)**：如果 1 分钟内连续失败 5 次（或延迟超过 10 秒），熔断器跳闸。此时**拦截所有对该 API 的真实网络请求**，直接抛出本地异常。这保护了系统不被长时间挂起的请求拖垮。
- **半开状态 (Half-Open)**：跳闸 5 分钟后，放行少量探测请求。如果成功，恢复为闭合状态；如果依然失败，继续断开。
- *技术落地*：可使用 Python 开源库 `pybreaker` 或基于 Redis 自行实现滑动窗口计数。

### 2.2 优雅降级策略 (Fallback Strategies)
当熔断器断开，或者大模型明确报错时，业务层必须有备用方案 (Plan B)：

1. **AI 出题降级**：
   - *故障场景*：学生点击“生成下一题”，但 AI API 挂了。
   - *降级动作*：立刻从数据库 `Question` 表中，根据用户的当前 Elo 分数，捞取一道**历史已存在的、人工审核过**的固定题目。前端完全不提示错误，用户无感知。
2. **AI 主观题阅卷降级**：
   - *故障场景*：学生提交论述题后，AI 无法打分。
   - *降级动作*：前端弹出温和提示：“AI 老师正在休息，已为您展示标准答案结构，请自评。”直接展示 `rubric`，转为传统估分模式。
3. **复试模拟器降级**：
   - 语音场景容错率极低。如果 TTS/STT 挂了，直接中断并保存当前进度：“考场网络波动，已为您存档，请稍后再试。”

### 2.3 模型级冗余 (Model Redundancy / Routing)
建立一个 **模型路由池 (Model Router)**：
- 首选模型：`gpt-4o`
- 备用模型 1：`claude-3.5-sonnet`
- 备用模型 2 (本地/廉价)：`glm-4-flash`
当首选模型超时或报错时，代码内部自动重试备用模型，只有当所有备用模型都失效时，才触发业务层降级。

## 3. 后续开发指南
- 在 Django 中，将所有的 LLM 调用集中在一个单例 Service 中，不要散落在各个 View 里。
- 在该 Service 中加入 Retry 装饰器 (如 `tenacity` 库) 和 Circuit Breaker 逻辑。
- 在 `backend/ai_engine/observability.py` 中记录每次 API 调用的耗时和状态，对接到 Prometheus/Grafana 或自定义 Admin 看板，实现可视化监控。
