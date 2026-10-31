# DSH 站点实时返回实施计划

> 使用 superpowers:executing-plans 在既有隔离 worktree 连续执行，仅定向冒烟，一次独立复核。

**Goal:** React 站点模式实时显示正文和已授权工具状态，完成后以现有 DSH 会话/卡片及账本为准。

**Architecture:** 固定官方网关仅提取 text_delta（忽略 reasoning/tool arguments）；SDK 原生通知仅提取本人允许工具的名称与完成状态。独立 worker 经专用私有 pipe 返回临时事件，stdout 最终结果保持不变。Django async SSE 消费有界队列，现有同步任务在隔离线程完成鉴权、锁与结算；不阻塞 ASGI loop。

**Tech Stack:** 既有 Django/DRF ASGI、Python pipe/thread/queue、SDK 0.2.1rc2、React fetch。

**Spec:** 完整规划 v1.2 第六、十二、十四、十五节及已完成站点入口计划。

## Constraints / rulings

- 新入口沿用两个默认关闭开关与站点身份，不改变正式小宇，不部署。
- 本批实现暂态输出；仅完整 DSH 结果通过现有记忆/权限复核与额度确认后发送 done，失败发送 error 并清空 UI 暂态，不保存半段答案。
- 断开浏览器只停止传输，不承诺撤销已派发任务；SDK 子进程保留 120 秒上限，父任务按既有规则结算收尾。同 request_id 可恢复，不自动创建新任务。暂态事件不落盘、不进入学生导出。
- 事件只允许 step/text_delta/tool_status；不发原生事件、推理、参数、内部配置。队列最多 64 项，慢客户端允许丢弃暂态片段，完整最终结果始终覆盖暂态。心跳不表示进度。
- 独立 SDK 继续由原父进程超时终止并清理；事件 FD 不向 SDK 子孙进程继承。
- 实际验证须经 ASGI；WSGI 对 async iterator 的缓冲不能作为实时通过证据。

## Review Focus

- SSE 断开、未开始消费及客户端变慢不泄漏 reservation、进程或无限增长的队列。
- 输出只含正文/允许工具名，不含推理、参数或其他账号；退出时旧暂态不回填。
- done 之前必须已确认成功额度，错误/不完整流不伪装成功；同 ID 只结算一次。
- JSON 旧入口及会话/删除继续遵守原身份与锁，临时增量不写正式历史。
- ASGI 中同步 ORM 与锁不在 event loop 上执行，Cookie/默认关闭/权益仍有效。

## Task 1: 受控实时事件

Files: dsh/gateway.py、host.py、worker.py；backend/ai_assistant/services/dsh_runtime.py；dsh/tests_gateway_smoke.py。

- [x] 定向先复现缺少实时正文过滤/回调。
- [x] 网关正文增量与 SDK 工具状态白名单，worker 私有 FD 与父读取线程，保留最终 JSON 契约。
- [x] 过滤冒烟与原 Host/网关必要冒烟。

## Task 2: ASGI 站点流与 React

Files: backend/ai_assistant/views_dsh.py、urls.py、services/dsh_stream.py、tests/test_dsh_site_smoke.py；frontend/src/pages/DshM0.tsx。

- [x] 先验证实时事件先于任务结束、同 ID 不重复结算。
- [x] 复用任务结算函数、async SSE 有界队列与断开生命周期，React 增量/暂态提示/结束替换及失败清空。
- [x] 定向后端冒烟、前端构建。

## Task 3: 实际验收

Files: dsh/smoke.py、site_smoke.py、README、迁移记录。

- [x] 站点 fixture 使用实际 ASGI 并保留合成 Cookie 入口；本地夹具分段输出。
- [x] 验证首个正文事件先于完整结果、原生卡片/账本、失败释放及重试；浏览器实际可见。
- [x] 一次复核与必要修复，本地提交；继续处理迁移清单，不能把本批等同整体产品完成。


## 实施与验收

10 项网关/会话冒烟通过；正文过滤与实时回调先失败后通过。7 项站点聚合冒烟通过，含实时事件先于结算的门闩、JSON/SSE 同 ID 幂等、失败释放，以及有界队列的慢客户端、未消费及断连生命周期。前端构建通过。实际 Daphne/SDK 双学生验证 [3,1] 次数与至少三段真实传输，浏览器捕获到正在生成的片段及停止接收/同 ID 恢复，截图 .m0-state/m0-live-stream-proof.png。

一次实际独立复核发现终止事件阻塞清理，定向冒烟 RED→GREEN 修复；不追加复审。审查最初指定模型遇用量限制，未实际开始，改由可用模型完成。没有其他延期小项。

Ruling: 暂态正文来自固定网关，最终结果由 DSH 决定，不伪造 SDK token 通知；代价是暂态不代表已通过最终记忆/权限检查。断开只关闭传输，SDK 继续受原上限约束并结算；代价是停止接收后仍可能产生已派发的用量。官方质量、生产代理/负载、正式切流与旧基线全量审查不在本批，本地协议和浏览器结果不替代这些验收。保留开发分支/worktree，仅本地提交。
