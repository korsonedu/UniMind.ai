# UniMind DSH M0

首条只读链路：独立 React 验证页 → 本机 Host → 官方 DSH SDK/学习插件 → Django 的本人记忆与学习工具。

产品基线现为服务端 harness：DSH 是 UniMind 内部组件，网页、移动网页和薄桌面客户端共用服务端 AI 接入；桌面不内置 DSH，也不以安装包作为本轮前置门槛。本机 Host 仍是单学生开发原型，不能直接公开端口用于学生服务。另有默认关闭的站点 API，已完成站点身份、隔离 worker 和既有周额度的本地接入；正式小宇入口尚未切换，未部署。

这是 M0 开发验证，尚未接入正式学生服务或桌面安装包。支持本机确定性协议模拟和经授权的 DeepSeek 官方模型；二者都经过本地单任务网关。真实模型链路可运行也不证明教学质量或正式网关已经完成。

## 当前组成

- `plugin.ts`：TypeScript Cordis 插件，导出 name、inject 和 apply(ctx: Context)，注册 Django 返回的只读工具和本人记忆上下文；锁定版运行时直接加载该源文件。
- `profile.patch.yml`：针对安装版 `0.2.1rc2`，禁用终端、文件、计划模式、子 Agent、搜索及默认遥测。
- `host.py`：只绑定 `127.0.0.1:8791` 的单学生验证 Host。凭据仅在 Host/子进程环境中，不返回浏览器。
- `gateway.py`：每轮临时任务网关，凭据随实例失效；上游密钥只留在网关，DSH 收到一次性任务凭据。限制模型、工具、请求次数和输入输出，不对上游错误自动重试或切换模型。
- `smoke.py`：启动临时 SQLite/Django 和本机模型协议夹具，验证实际 DSH 工具调用；退出时清理。
- `frontend/src/pages/DshM0.tsx`：仅开发模式 `/dev/dsh`，正式路由不启用。
- `/api/ai/dsh/context/`、`/api/ai/dsh/tools/<name>/`：由 `UNIMIND_DSH_ENABLED` 控制，默认关闭。

当前开放 17 个学生只读工具：学习统计、最近练习、薄弱点、课程/讲稿、知识查询、错题/题目查询、学习记录、掌握图谱、到期复习、Memorix 分析、题库预览、考试历史、学习报告、成就和同类题。每次请求使用当前身份重新鉴权；旧记忆版本执行返回 409。同一会话的每一轮启动独立运行时进程，通过真实 SDK `resume_session` 恢复历史。

## 工具候选与迁移范围

完整学生目录含 25 个定义；新目录排除 Agent 自动笔记写入 save_session_note，再按当前权限过滤。共享 route_tools 只保留为候选对照诊断。实际提供给模型的是 resources、practice、progress、mastery 四个业务组之一，每组最多 7 个业务工具，加一个 find_learning_tools；每次模型请求最多 8 个工具。无法识别的问题只提供发现工具，零业务权限账号也不会获得发现工具。

初始组复用确定性关键词/历史分类，不调用旧 AIEngine。缺少能力时，模型通过原生工具调用选择另一个已授权组。发现工具只暂存选择；在下一次 system-prompt/assemble 中同步替换注册表和模型 Schema，避免同批已接受调用被注销，也避免锁定版本 pre-step 的一轮 Schema 延迟。完整业务许可版本仍用于会话失效与执行鉴权，分组不是权限边界。

Host 只将当前有效会话的最近 6 条、每条最多 1000 字符传给初始路由；记忆、权限或运行配置失效时丢弃这份路由上下文。旧可见聊天不重新参与模型上下文。网关重新检查完整授权范围、8 工具上限与原有 4 次模型请求预算；发现同样占用模型轮数，不能无限切组。

首轮 5 工具报告保留为历史基线。当前 11 个代表场景初始可见 1～8 个工具；实际发现样例为 1 → 4 → 4 个，Schema 为 687 → 2792 → 2792 bytes。页面区分旧共享候选、初始组、完整业务许可及本轮调用轨迹。此处验证工具发现机制、上限与业务数据链路，不报告真实模型准确率、整体成本或延迟改善。记录见 2026-10-26-dsh-group-routing.md。

## 只读结果卡片

`cards.py` 适配 SDK 0.2.1rc2 实际的 tool/call 与 tool/result 事件，只接纳当前许可工具的成功返回。插件通过原生 output.presentationMeta 将受控卡片写入 tool/result.data.meta；output.render 去掉 visual，只把业务数据传给模型。Django 从业务查询构造结果卡片；Host 仅允许 data_card、knowledge_map、practice_result、question_preview 和 practice_quiz，链接限制在已知站内路由。模型正文及任意 render_visual 不参与卡片执行。

DSH 原生有工具调用/结果展示接口 presentCall、presentResult、presentationMeta，以及可选 Web Client 的工具展示 slot 与 Conversation 扩展；这些机制没有提供现成的 UniMind 教学卡片。当前复用原生持久展示元数据，由独立 UniMind React 消费，保留产品界面边界。参考：[插件基础](https://deepseek-harness.github.io/deepseek-harness/develop/basic/)、[工具编写参考](https://deepseek-harness.github.io/deepseek-harness/reference/cookbook/adding-a-tool)。Python 代码是 Django 业务与开发 Host/网关，Cordis 插件本体为 TypeScript。

React 复用学习概览、掌握图谱和练习结果组件，题目只展示预览。既有 PracticeQuizCard 的提交/批改路径不接入本页，预览题不含答案；错题及显式查题的参考答案可展开查看。讲稿时间段显示为来源文本，打开课程不承诺直接跳转时间点。卡片随会话保存，刷新后可查看当时快照；最新状态以正式详情页为准。开发页导出只取对话文字，不导出卡片数据。

协议夹具中输入 `M0只读演示：学习统计。` 会在四次请求预算中跨组调用八个业务工具，展示合成数据；`M0工具发现` 验证只有发现工具时恢复课程查询的三步流程。该流程验证事件与业务结果链路，不用于评估模型意图理解或任务完成率。

输入 `M0批改快照` 查询合成的批改中记录。DSH 结果卡明确提示这是查询时的进度，通过详情页查看最新状态，不承诺自动刷新；普通练习结果卡保留原有行为。

## 本地会话

`sessions.py` 将用户可见对话与原生 DSH 运行上下文分开，按业务源地址和当前学生 ID 隔离目录。独立 Host 使用 `.m0-state/sessions`；隔离验证启动器改用临时目录，退出时清理，避免合成账号的历史混入后续验证。浏览器只保存随机会话 ID，刷新后经 Host 重新鉴权读取本人记录。

每轮及读取会话时检查记忆版本、允许的工具定义、模型策略、模型来源、插件/profile 与 SDK 版本。变化时清理旧 DSH home，创建新运行会话，保留原用户可见对话供查看；不会把原聊天重新拼成模型上下文。模型调用结束后再校验一次，避免中途更正后返回旧上下文生成的结果。失败或崩溃遗留的轮次在下次使用前重建，不自动当作成功历史恢复。

开发页提供新会话、连续追问、刷新恢复、导出可见对话和删除本地会话。导出只含消息和可见元数据，不包含 DSH 事件、原始工具返回、内部提示词、配置或凭据；删除会清理该会话正文与运行上下文，长期记忆及既有模型用量记录分别保留。站点 API 已提供本人会话读取与删除，并清理相应缓存正文；正式留存期限、跨端同步、资料导出限制及账号退出流程仍待验收，不以本地流程替代这些验收。

## 安装

在本 worktree 根目录执行，使用独立环境，不修改业务 Python 环境：

```sh
uv venv .m0-venv --python python3.14
uv pip install --python .m0-venv/bin/python -r dsh/requirements.txt
```

SDK 自带运行时，不依赖系统 Node 22。前端使用项目既有依赖；开发工具链可使用已提供的 Node 24。

插件类型检查在独立的 `dsh/` 目录运行：

```sh
npm ci --ignore-scripts --no-audit --no-fund
npm run typecheck
```

依赖及 lockfile 锁定官方 DSH `0.2.1-rc.2`、Cordis `4.0.5`、TypeScript `5.9.3` 和 Node 24 声明，对应 Python SDK `0.2.1rc2`。NodeNext 严格检查开启，未跳过第三方声明检查。显式补入同版本 `dsh-attachment`，因为官方 LLM 声明引用它。npm 的 `latest` 标签曾指向早期预览版本，不能据此混装。依赖只用于开发检查，插件的运行时导入仍全部为 type import；不改变已锁定的 SDK 可执行文件。

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

真实调用的逐请求 usage 写入忽略目录 `.m0-state/gateway-usage.jsonl`，含任务 ID、模型、状态、时间、输入输出与缓存 tokens，不存提示词、回答或学生记忆。任务到期或 Host 退出时主动中断已连接的上下游 socket，等待处理线程终结后再写审计；不完整 usage 保留未知状态，不按零成本结算。页面总输入按未缓存、缓存读取、缓存创建相加，并保留明细，口径见 [Messages 用量定义](https://platform.claude.com/docs/en/build-with-claude/prompt-caching)。独立 Host 仍只有单任务技术预算；下方站点入口已复用既有学生周问答次数，但未实现人民币费用上限或新收费方案。开发机上的可修改原型不能作为正式收费边界。

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

1. 公司服务端部署：将默认关闭的站点入口部署到可信运行环境，验收正式任务准入、人民币费用预算和生产结算；站点身份与既有周问答次数已本地接通。
2. 每轮动态工具选择及实际问法质量验证；当前已实现初始分组及原生按需发现，真实模型的选择质量、复合任务及延迟/成本仍待验收。
3. 完整会话生命周期：正式留存期限、跨端同步、退出登录、资料导出限制与删除状态协调；当前已完成本地及站点 API 的本人读取/删除，完整生命周期尚未验收。
4. M2 公司薄 Electron 客户端，共用服务端 AI；另验收登录、受限系统能力、签名安装与更新，不内置 DSH。
5. 生产多用户容量、恢复演练、真实评分样本和正式模型验证；当前两个合成学生的隔离协议链路已通过。

配置可以启动并不代表上述门槛已经通过。历史首条链路见 `docs/superpowers/plans/2026-10-25-dsh-m0.md`；当前分组与站点接入证据见同目录的 `2026-10-26-dsh-group-routing.md` 和 `2026-10-26-dsh-site-bridge.md`。


## 站点身份与额度入口（默认关闭）

站点可通过 POST /api/ai/dsh/chat/ 提交 message、UUID request_id 和可选 session_id。使用现有站点 Cookie/Token 认证；请求不能选择模型、学生、Python、路径或回调来源。POST /api/ai/dsh/session/new/、read/、delete/ 管理当前学生的会话。当前正式小宇入口没有切换。开发页 /dev/dsh 保留单学生本机 Host；/dev/dsh?source=site 明确使用站点 Cookie 调用上述 API，不会失败后回落 Host。GET /api/ai/dsh/status/ 返回当前学生和已配置模型来源，无法通过来源校验时禁用模型调用；它不保证供应商账户余额或实际 SDK 可用。

需由服务端配置 UNIMIND_DSH_ENABLED、UNIMIND_DSH_SITE_ENABLED、UNIMIND_DSH_PYTHON（独立 SDK Python 绝对路径）、UNIMIND_DSH_API_URL（固定 loopback 业务地址）和 UNIMIND_DSH_STATE_DIR（私有绝对路径）。本轮未修改实际 .env 或开通正式服务。正常模式仅使用现有 DeepSeek 官方配置；UNIMIND_DSH_FIXTURE_URL 只允许 DEBUG 下的显式本机协议服务。

Django 为聊天任务签发 120 秒回调凭据，仅供 context/tools 使用，绑定当前用户及 pending 额度预留的 attempt_id；结束后凭据失效。会话控制凭据仅能读取本人 context。每轮独立 worker，通过私有 stdin 接收任务；其环境不继承 Django SECRET_KEY、数据库密码或其他业务秘密。模型上游密钥仍只留在任务网关，DSH 接收一次性网关凭据。独立 worker 不对外开端口，前端不需要安装 SDK。

复用现有 AIUsageReservation 与 WeeklyAIUsage：相同 request_id 幂等，只有 completed 且有完整回答才确认一次既有问答额度，失败释放。未新增账本、价格或数据库模型。每学生的父进程锁覆盖模型运行、额度提交和删除，worker 也保护原生状态；全局最多 4 个 SDK 运行时，繁忙时在调用模型前拒绝。SQLite 只串行化本入口短额度写入，模型仍可并发，不修改旧业务数据库配置；其他引擎继续使用既有事务。该机制限定单台服务器，不代表生产容量或跨节点协调已验收。

父进程预先分配并保留新会话目录；超时终止整个子进程组并清理未交付的新会话，既有会话不会因此被删除。删除先清除缓存正文并保留无正文的删除标记，再清理文件；重试可识别已删除的本人会话，原 request_id 不会重放正文。既有用量事实保留。正式留存、跨端退出及生产恢复演练仍按完整规划验收。

实际站点链路冒烟：

```sh
.m0-venv/bin/python dsh/site_smoke.py \
  --backend-python /Users/eular/Desktop/科晟开发/UniMind/UniMindCode/backend/.venv/bin/python
```

启动临时数据库和两个合成学生，通过真实站点认证、独立 worker、实际 DSH 与 Django 回调验证隔离、恢复、幂等、额度、失败及删除。不访问付费模型，不使用真实学生数据。新增的默认关闭入口未部署。


## 站点 React 验证

实际站点冒烟加 --serve --port 8000 可保留临时服务；Vite 仍使用既有 /api 代理。通过 /api/ai/dsh-fixture/student-a/ 或 student-b/ 设置仅属于临时数据库的 HttpOnly Cookie，然后进入 /dev/dsh?source=site。这些启动路径只存在于隔离 fixture 的 WSGI 包装层，不在业务 URL 中，也不会打印 Token。/api/ai/dsh-fixture/logout/ 清除合成 Cookie；drop-next-chat/ 用于模拟真实服务端完成、但浏览器响应丢失的情况。

站点页使用 Cookie fetch，避免既有 axios 的自动重试和 30 秒默认超时。未确认返回时保留内存中的同一问题、会话和 request_id，手动恢复不会重新创建另一轮；整页重载不承诺恢复未确认请求。已知会话 ID 在 sessionStorage 按当前学生分开保存，正文、卡片、记忆和请求正文不写浏览器存储。刷新只恢复当前学生的会话。

当前页面的退出事件、身份 Store 变化、跨窗口 auth-storage 变化会立即清空内存中的身份、聊天、记忆、卡片和标签页索引，并中止本页请求；焦点恢复时另向服务端复核。旧异步结果不回填。取消页面请求不会撤销可能已完成的服务端任务，也不承诺取消已发生的模型用量。站点页现使用下述 ASGI 实时返回；原整轮 JSON 接口仍保留用于兼容及同 ID 恢复。

来源依据服务端配置校验，未配置、未授权地址或非 DEBUG 的 fixture 不标成官方模型，也不会开放调用。默认关闭、权益和会话失败保留后端状态；404 有时沿用 DRF 的通用 detail，进一步细分提示为后置文案小项。实施和验收见 2026-10-26-dsh-site-ui.md。


## ASGI 实时返回

POST /api/ai/dsh/chat/stream/ 沿用相同 Cookie、参数、request_id、额度及开关，返回 text/event-stream。step、text_delta、tool_status 是未提交的暂态事件；done 含通过原生 DSH 会话、记忆/权限复核与既有额度确认的完整结果，error 表示本轮未完成。页面以最终结果覆盖暂态，失败、退出、停止接收时清空暂态；不会将暂态正文导出或保存为正式聊天。

锁定版 SDK 的 Python 通知以结算记录为主；网关只提取供应商 text_delta，并排除 reasoning、工具参数与原始事件。本人已授权工具名称/返回状态来自 SDK 的 root session 通知。事件经 worker 专用私有 pipe 返回，FD 在启动 SDK 前关闭继承属性；上游凭据与内部配置不进入该通道。

Django 使用 async iterator，模型、文件锁与 ORM 位于独立同步任务线程。队列固定 64 项；慢客户端可丢暂态片段，终止事件会腾出暂态空间，生产线程无需等待客户端即可清理连接。完全未消费响应不会启动任务；断开已启动传输只关闭页面接收，任务仍按既有规则结算，SDK 子进程保留 120 秒父进程上限。手动恢复沿用同一 request_id，不自动补发新任务。

实际验证使用 Daphne ASGI；普通 WSGI 会缓冲 async iterator，不作为实时证据。site_smoke 的本地协议夹具每 150ms 输出一段，验证至少三段正文、首段先于 done、正文拼接与 DSH 最终回答一致、原生工具状态/卡片、跨 JSON/SSE 幂等及失败释放。浏览器截图 .m0-state/m0-live-stream-proof.png 捕获到生成中片段；停止接收后恢复同一任务，仅追加原任务对应两条消息。以上不代表真实模型质量或生产代理/容量验收。

## 可作答练习卡

get_practice_questions 现在返回 practice_quiz 卡片，复用现有 PracticeQuizCard。题目由服务端按内容范围抽取，卡片不含答案；学生在卡片内作答，提交走 /quizzes/submit-exam/，以 submission_id 和答案哈希幂等，后台评分沿用既有 QuizExam 事务与 DSH 评分开关。聊天内旧的 grade_student_answer 写工具仍不开放。未验收真实评分质量、生产提交量和正式权益。


## DSH 评分任务（独立开关，默认关闭）

UNIMIND_DSH_GRADING_ENABLED 开启时，AIService 仅对 quizzes.grade_question 和 quizzes.objective_analysis 改走服务端 DSH。既有题干/评分点提示词与后处理继续使用；主观 pro/2500 tokens/temperature .2，客观解析 fast/2000/.4，均一次模型请求上限。collector 成功即 concludeTurn；评分 profile 关闭 llm-retry，失败不回旧模型，客观解析失败可沿用确定性反馈。

structured_plugin.ts 为实际 Cordis 模块，只注册指定 collector；无学生回调凭据、长期记忆、学习工具、文件/终端工具。任务由私有 stdin 传入，SDK home 位于私有临时目录并在结束删除，与聊天共用四个 SDK 槽位。父进程超时或中断先终止整个进程组。源码使用现有 jsonschema 并在 backend/requirements.txt 明确锁定；SDK 接收支持的 Schema 子集，后端仍完整校验。

既有练习 UI 经 GET /api/ai/practice/session/<id>/ 读取自己已创建的会话，避免再次抽题而提交旧 ID；已完成结果刷新可恢复。此接口复核身份、归属与当前题目范围，并区分整卷考试提交事实。提交按题数给每题130秒等待，不自动重试该写请求；DSH 开启时 Celery 预批改150/180秒，关闭时保持60/90秒。原业务事务决定成绩/ Memorix/PracticeSubmission，一次失败不写半份结果。独立 chat 周额度不因一次评分再扣。

本地实际 SDK/ASGI 与合成主观题已验证一次 pro 请求、8/10、重复提交一次落库、他人拒绝、暂态错误不重试/不落分，以及客观确定性0分。浏览器显示逐题反馈并刷新恢复。真实模型质量、Celery生产运行、并发容量和正式开关启用未验收；详见 2026-10-26-dsh-grading.md。


## DSH 教研解析（独立开关，默认关闭）

UNIMIND_DSH_TEACHING_ENABLED 开启时，Directus 教研后台的“文本解析”把粘贴资料解析为候选题，人工编辑并确认后才入库。只接受一个考点，材料上限 10000 字符；固定 fast/3200 tokens/一次请求，无重试或 fallback。缺失的答案和评分点保持为空，由人工补齐；候选题不会自动写入正式题库。开关关闭时入口明确拒绝，旧解析路径不受影响。真实模型解析质量、生产后台与正式内容范围未验收；详见 2026-10-26-dsh-teaching-parse.md。


## DSH 会话标题（独立开关，默认关闭）

UNIMIND_DSH_TITLE_ENABLED 开启时，首轮对话标题由服务端 DSH 结构化任务生成：fast/64 tokens/一次请求，返回超过 15 字时截断。DSH 失败或返回为空时回退用户首句前 15 字，不阻塞回答；已有手动标题不会被覆盖。关闭时保留原 simple_chat_text 路径。标题与分类属于系统内部成本，不重复扣学生问答次数。真实模型标题质量与生产开关启用未验收。


## DSH 长期记忆提取（独立开关，默认关闭）

UNIMIND_DSH_MEMORY_ENABLED 开启时，每轮完整对话后的长期记忆提取改走服务端 DSH 结构化任务：fast/800 tokens/一次请求。候选必须带有本轮用户原话 evidence，且置信度不低于 0.6；助手建议、假设、未确认计划和临时情绪不写入。手动设置或用户停用的记忆不会被覆盖。同一会话同一轮只处理一次，用户删除记忆后该轮不会重建；提取失败不写处理记录，下一轮可重试，不阻塞对话。开关开启时停用 mem0 自动提取，保留其语义检索。真实模型提取质量、生产开关与留存策略未验收。


## 服务端会话发现

GET /api/ai/dsh/sessions/ 沿用站点身份和默认关闭开关，返回当前用户标识与最近最多50项会话元数据：id、首条用户消息最多60字摘要、updated_at、message_count。按业务源/账号目录隔离，拒绝目录和 transcript 文件符号链接，坏文件不阻断其余有效条目。不返回消息数组、原生状态或凭据；不调用模型、不扣问答次数。

站点开发页可在没有标签页 session_id 的情况下选择并恢复服务器历史。身份变化/刷新/取消清空旧列表与在途请求，status/list 和 read/status 校验用户一致；待确认提问期间禁用切换，删除后移除入口。新标签页恢复原两条消息与学情卡已在实际浏览器验收，截图 .m0-state/m0-server-session-list-proof.png。这里只完成同一服务器身份下的发现/恢复，正式留存、分页、目录容量与跨节点同步仍需验收。
