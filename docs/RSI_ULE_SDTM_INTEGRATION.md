# RSI × ULE × SDTM 集成运维参考

本集成沿用 6A＋6B 的版本与观察记录、SDTM 来源校验与公司级四层总体架构（`facts / state / decision / views / runtime`）。以下为 T1 至 T6 的实现口径。参见 [四层总体架构](architecture/FOUR_LAYER_ARCHITECTURE.md)、[RSI sidecar 6A＋6B](product/2026-11-12-rsi-sidecar-6ab.md) 和 [SDTM 学习记忆](SDTM_LEARNING_MEMORY.md)。

| 模块与四层坐标 | 职责 |
| --- | --- |
| SDTM & RSI 证据/数据集（L2 `state/rsi/`） | `rsi_evidence` 将私有策略试用和公共方法采用的后续表现汇入同一只读证据视图；结构化诊断标记同题答案披露；`rsi_dataset` 按带时区截止点导出留出包与 S 回放数据集。 |
| ULE／ULR & 在线策略 S（L3 `decision/rsi_policy.py` + `runtime/`） | 每轮冻结 RSI 机制与上下文来源。版本化 S 策略负责 `recheck_timing` 和 `method_ranking`，记录候选、选择、实际分配概率、全链路 `trace_id` 及关联 SDTM 帧。答复成功保存后登记完成，客户端展示时登记呈现。 |
| RSI Shadow／Replay（L2 `state/rsi/teaching_shadow.py`） | G 和 E 从项目证据按带时区的截止点导出留出包。留出案例要求分配、提交和批改均在截止后，排除已披露、重复或无法核实来源案例。ULR 启用时 G／E 使用 `ulr_native`。S 全程离线报告 IPS、SNIPS 和 Kish ESS。 |
| M 治理（L3 `decision/rsi_governance.py`） | 检查候选、来源及硬门禁（默认至少两例、S 要求 `Kish ESS ≥ 2`）。通过后由映射平台管理员显式批准。G／S 支持项目灰度与全局范围；E 仅作为项目灰度参考。 |

## 迁移与配置

以下为 `ai_assistant` 新增迁移（承接 `0053_mcp_dcr_and_external_servers`）。生产发布先在新版本代码上执行 `python manage.py migrate`，按依赖顺序应用至 `0056`，再启动新版服务和工作进程，最后按试点范围启用开关。S 开关为 `off` 时，符合条件的复测回合仍会写入内置决策记录。

| 迁移 | 模型变更 |
| --- | --- |
| `0054_teachingdecisionlog` | 新增 `TeachingDecisionLog`（含全链路 `trace_id` 索引字段），每条提问、每个决策点一条记录。 |
| `0055_alter_teachingresearchrun_kind` | 为既有 `TeachingResearchRun.kind` 加入 S。 |
| `0056_teachingmechanismactivation` | 新增 `TeachingMechanismActivation`，记录生效范围、研究版本、G 发布版以及审批和回滚记录。 |

默认安全配置如下。

```dotenv
UNIMIND_RSI_ONLINE_POLICY_MODE=off
UNIMIND_RSI_POLICY_PROJECTS=
UNIMIND_RSI_EXPLORATION_RATE=0.0
```

- `UNIMIND_RSI_ONLINE_POLICY_MODE` 接受 `off`、`shadow`、`active`。项目名单填逗号分隔的 ID，名单外沿用内置行为。已批准的全局 S 仍受开关和名单约束。探索率接受 `0.0` 至 `0.5` 的有限值。
- 全链路试点使用 `UNIMIND_LEARNING_RUNTIME=ulr`、`UNIMIND_SDTM_TASK_MEMORY_MODE=active`、`UNIMIND_SDTM_STRUCTURED_DIAGNOSTICS=true`，并把认证诊断项目 ID 加入 `UNIMIND_SDTM_DIAGNOSTIC_PROJECTS`。SDTM 任务记忆模式按环境配置，诊断名单按项目配置。

## 操作者命令

在 `backend` 执行。变量填当前项目、研究记录、激活记录与平台管理员的实际 ID。截止点采用带时区的 ISO 8601 时间。G／E 的 `--from-sdtm` 会执行真实模型调用，S 全程离线。三条命令需各用新的输出路径，报告以 `0600` 写入，包含项目私有材料的衍生内容。

```sh
python manage.py research_teaching_mechanisms --from-sdtm --project "$PROJECT_ID" \
  --kind G --cutoff "$CUTOFF" --baseline-instruction '按标准核对独立作答。' --output g-report.json
python manage.py research_teaching_mechanisms --from-sdtm --project "$PROJECT_ID" \
  --kind E --cutoff "$CUTOFF" --baseline-instruction '按答案键核对作答。' --output e-report.json
python manage.py research_teaching_mechanisms --from-sdtm --project "$PROJECT_ID" \
  --kind S --cutoff "$CUTOFF" --decision-point recheck_timing \
  --target-policy '{"immediate-v1":0.5,"delayed-v1":0.5}' --output s-report.json

python manage.py govern_teaching_mechanism --action evaluate --run-id "$RUN_ID"
python manage.py govern_teaching_mechanism --action approve --run-id "$G_RUN_ID" \
  --reviewer-id "$ADMIN_ID" --scope project_canary --method-spec reviewed-method.json
python manage.py govern_teaching_mechanism --action approve --run-id "$S_RUN_ID" \
  --reviewer-id "$ADMIN_ID" --scope project_canary
python manage.py govern_teaching_mechanism --action rollback --activation-id "$ACTIVATION_ID" \
  --reviewer-id "$ADMIN_ID" --reason '撤回试点版本'
```

`--method-spec` 为 G 的审核输入，须含 `key`、非空的 `requires` 和 `source`，发布指令取自研究候选。G／S 全局批准使用 `--scope global`。批准和回滚均校验 `is_platform_admin` 及 `UNIMIND_DIRECTUS_ADMIN_MAP`。回滚默认退役 G 方法或撤销 S 激活。如有上一版，可显式加 `--restore-previous`。新回合按当前状态路由。历史方法版本和帧继续保留，来源完整且仍有权限时，`TaskMemoryFrame` 可通过 `task_memory_store.restore()` 按原 `packet_digest` 恢复。

## 呈现回执与证据边界

- `POST /api/ai/learning/exposure/present/` 需登录，提交本人已完成助手答复的 `message_id`，可传 `surface`（默认 `chat_card`，也支持 `hint_reply`、`recheck_card`、`practice_card`）和 `card_type`。重复提交同一答复保留首次 `presented_at`，返回 `created=false`。记录从 `assigned` 经 `reply_completed` 到 `presented`，呈现后仍保留 `adherence='unverified'`。
- 只有策略实际给出的分配概率才入账。关闭策略、影子推荐或模型自行选择时，未知的 `propensity` 保持为空，历史记录不补造概率。
- 影子研究和回放均须经管理员显式批准才能生效。独立作答仍有提交自报的帮助来源边界，方法证据和 S 回放固定 `causal_claim=False`。客观答案锚点与离线估计用于机制核对，真实教学收益需另行验证。
