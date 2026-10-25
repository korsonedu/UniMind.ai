# UniMind DSH M0

首条只读链路：独立 React 验证页 → 本机 Host → 官方 DSH SDK/学习插件 → Django 的本人记忆与学习工具。

产品基线现为服务端 harness：DSH 是 UniMind 内部组件，网页、移动网页和薄桌面客户端共用服务端 AI 接入；桌面不内置 DSH，也不以安装包作为本轮前置门槛。本机 Host 是这一组件的开发原型，尚未接入站点身份和多用户托管，不能直接公开端口用于学生服务。

这是 M0 开发验证，尚未接入正式学生服务或桌面安装包。支持本机确定性协议模拟和经授权的 DeepSeek 官方模型；二者都经过本地单任务网关。真实模型链路可运行也不证明教学质量或正式网关已经完成。

## 当前组成

- `plugin.mjs`：实际 Cordis 插件，注册 Django 返回的只读工具和本人记忆上下文。
- `profile.patch.yml`：针对安装版 `0.2.1rc2`，禁用终端、文件、计划模式、子 Agent、搜索及默认遥测。
- `host.py`：只绑定 `127.0.0.1:8791` 的单学生验证 Host。凭据仅在 Host/子进程环境中，不返回浏览器。
- `gateway.py`：每轮临时任务网关，凭据随实例失效；上游密钥只留在网关，DSH 收到一次性任务凭据。限制模型、工具、请求次数和输入输出，不对上游错误自动重试或切换模型。
- `smoke.py`：启动临时 SQLite/Django 和本机模型协议夹具，验证实际 DSH 工具调用；退出时清理。
- `frontend/src/pages/DshM0.tsx`：仅开发模式 `/dev/dsh`，正式路由不启用。
- `/api/ai/dsh/context/`、`/api/ai/dsh/tools/<name>/`：由 `UNIMIND_DSH_ENABLED` 控制，默认关闭。

当前只选择 `get_learning_stats`、`get_recent_practice_result`、`get_user_weak_points`、`search_courses`、`search_asr`。每次请求使用当前身份重新鉴权；旧记忆版本执行返回 409。同一会话的每一轮启动独立运行时进程，通过真实 SDK `resume_session` 恢复历史。

## 工具候选与迁移范围

完整学生目录含 25 个定义；新目录排除 Agent 自动笔记写入 save_session_note，再按当前权限过滤。共用 route_tools 做候选选择，显式使用确定性关键词/历史回退，复用工作流依赖和大目录语义检索入口；不在新路径触发旧 AIEngine 分类。候选还要与 M0 的 5 个可执行工具求交集，未迁移工具只在开发诊断中标注，不注册执行。

Host 只将当前有效会话的最近 6 条、每条最多 1000 字符传给路由；记忆、权限或运行配置失效时丢弃这份路由上下文。用户可见的保留原聊天不因此重新参与模型上下文。工具鉴权和参数检查仍由 UniMind 执行。

11 条代表问法的确定性回退对照通常保留 21 个候选，约 16 KiB Schema；当前开放 5 个工具为 3298 bytes。这是迁移范围限制，不代表 DSH 已优化路由或证明成本下降。旧 LLM/新 DSH 分类对照、真实 Embedding 质量、每步动态候选和实际业务任务完成仍待验收。详见 `docs/superpowers/plans/2026-10-25-dsh-routing-comparison.md` 与 `2026-10-25-xiaoyu-migration.md`。

## 本地会话

`sessions.py` 将用户可见对话与原生 DSH 运行上下文分开，按业务源地址和当前学生 ID 隔离目录。独立 Host 使用 `.m0-state/sessions`；隔离验证启动器改用临时目录，退出时清理，避免合成账号的历史混入后续验证。浏览器只保存随机会话 ID，刷新后经 Host 重新鉴权读取本人记录。

每轮及读取会话时检查记忆版本、允许的工具定义、模型策略、模型来源、插件/profile 与 SDK 版本。变化时清理旧 DSH home，创建新运行会话，保留原用户可见对话供查看；不会把原聊天重新拼成模型上下文。模型调用结束后再校验一次，避免中途更正后返回旧上下文生成的结果。失败或崩溃遗留的轮次在下次使用前重建，不自动当作成功历史恢复。

开发页提供新会话、连续追问、刷新恢复、导出可见对话和删除本地会话。导出只含消息和可见元数据，不包含 DSH 事件、原始工具返回、内部提示词、配置或凭据；删除会清理该会话正文与运行上下文，长期记忆及既有模型用量记录分别保留。该原型尚未实现正式留存期限、跨端同步、服务端删除指令、资料导出限制及账号退出流程，不以本地流程替代这些验收。

## 安装

在本 worktree 根目录执行，使用独立环境，不修改业务 Python 环境：

```sh
uv venv .m0-venv --python python3.14
uv pip install --python .m0-venv/bin/python -r dsh/requirements.txt
```

SDK 自带运行时，不依赖系统 Node 22。前端使用项目既有依赖；开发工具链可使用已提供的 Node 24。

## 运行协议冒烟与验证页

当前工作机已有 Django 依赖环境，命令如下：

```sh
.m0-venv/bin/python dsh/smoke.py \
  --backend-python /Users/eular/Desktop/科晟开发/UniMind/UniMindCode/backend/.venv/bin/python
```

加 `--serve` 可在冒烟后保留临时服务，供验证页操作。另开终端在 `frontend/` 运行：

```sh
npm run dev -- --host 127.0.0.1 --port 5175 --strictPort
```

访问 [M0 验证页](http://127.0.0.1:5175/dev/dsh)。读取记忆与候选工具，然后运行协议链路。Host 未启动时界面应清楚显示状态，普通 React 业务入口仍保留。该入口与临时学生数据不是正式课程服务。

用户已授权使用当前工作机的 DeepSeek 官方配置。要验证真实模型，将现有 `.env` 路径交给启动器，不把文件复制到 worktree，也不把密钥写进命令或页面：

```sh
.m0-venv/bin/python dsh/smoke.py \
  --backend-python /Users/eular/Desktop/科晟开发/UniMind/UniMindCode/backend/.venv/bin/python \
  --official-env /Users/eular/Desktop/科晟开发/UniMind/UniMindCode/backend/.env \
  --serve
```

启动器只从现有配置读取密钥，并校验原来源是 DeepSeek 官方；按官方 [Anthropic 兼容接口](https://api-docs.deepseek.com/guides/anthropic_api/) 使用固定地址。业务与模型两种令牌互不替代；业务令牌仅用于本机隔离 Django。正式来源与模拟来源在页面分别标注。

任务策略由 Django 固定为 `assistant.chat.planner` 的 fast 路由，沿用现有模型选择；每轮最多 4 次模型请求，每次请求体最多 64 KiB、输出最多 1024 tokens，任务 90 秒失效。网关禁止模型升级、额外工具和上游跳转；包括失败在内的上游尝试都占用次数。没有备用供应商，不声称具备自动 fallback。

上游不可重试的 4xx（含 401、402、422）保留状态并终止本任务后续上游访问，避免被统一转成 502 后触发 SDK 重试。2026 年 10 月 25 日后续官方验证返回 402，按 [DeepSeek 错误码](https://api-docs.deepseek.com/zh-cn/quick_start/error_codes/) 表示余额不足；已停止该来源的后续调用，当前开发页改为明确标注的本地协议模拟，真实模型验证等待账户恢复。

真实调用的逐请求 usage 写入忽略目录 `.m0-state/gateway-usage.jsonl`，含任务 ID、模型、状态、时间、输入输出与缓存 tokens，不存提示词、回答或学生记忆。任务到期或 Host 退出时主动中断已连接的上下游 socket，等待处理线程终结后再写审计；不完整 usage 保留未知状态，不按零成本结算。页面总输入按未缓存、缓存读取、缓存创建相加，并保留明细，口径见 [Messages 用量定义](https://platform.claude.com/docs/en/build-with-claude/prompt-caching)。当前是单任务技术预算，未接正式学生周期额度、人民币费用上限或业务扣费；本机用户也可修改原型，不能作为正式客户端的可信收费边界。

成功证据应包含实际 SDK、隔离 Django、两次模型协议请求、真实学习统计工具返回及本人记忆隔离。已观察到安装版使用 `/v1/messages`；不能用 OpenAI SSE 夹具替代这一格式。

## 后端冒烟

在 `backend/` 执行：

```sh
ACCOUNT_ENABLED=false ACCOUNT_RSA_KEY_PATH='' ACCOUNT_DEV_LOCAL_CACHE=true \
  /Users/eular/Desktop/科晟开发/UniMind/UniMindCode/backend/.venv/bin/python \
  -m pytest ai_assistant/tests/test_dsh_smoke.py -q
```

只检查新桥接的默认关闭、匿名拒绝、本人记忆、工具范围、参数及版本失效。未执行全量回归或生产操作。

离线 Host 边界检查：在 worktree 根目录运行 `.m0-venv/bin/python dsh/tests_smoke.py`。覆盖错误响应不泄露 Token、禁止业务请求跳转，以及 fixture 拒绝未隔离的数据库。fixture 子进程在 Django 初始化前检查父进程创建的临时 SQLite 路径，不能直接指向默认或环境中的业务数据库。

网关 HTTP 冒烟：`.m0-venv/bin/python dsh/tests_gateway_smoke.py`。仅连接本机模型模拟，检查错误凭据、模型升级、输出/输入越限、额外工具、次数耗尽、实际 SSE 用量，以及部分行持续传输时的期限中断和退出后的完整审计。

会话离线冒烟：`.m0-venv/bin/python dsh/tests_session_smoke.py`，检查账号与路径隔离、工具权限变化、失败轮次、公开导出范围、删除范围和官方模式的会话状态。默认协议冒烟还会实际启动两个 Host 解释器进程与两个 DSH 进程恢复同一会话，再通过隔离 Django 的既有接口更正/删除合成记忆，验证旧上下文不进入下一轮模型请求。

## 后续门槛

1. 公司服务端网关：将本机原型移至可信服务端，接通正式任务准入、周期额度、费用预算与结算；不能把本机一次性凭据视为正式跨端授权。
2. 每轮动态工具选择及实际问法质量验证；当前为启动本轮时按关键词与工作流组选择的有限集合。
3. 完整会话生命周期：正式留存期限、跨端同步、退出登录、资料导出限制与删除状态协调；当前只完成本地原型。
4. M2 公司薄 Electron 客户端，共用服务端 AI；另验收登录、受限系统能力、签名安装与更新，不内置 DSH。
5. 托管多用户隔离、真实评分样本和正式模型验证。

配置可以启动并不代表上述门槛已经通过。实现计划与证据见 `docs/superpowers/plans/2026-10-25-dsh-m0.md`。
