# UniMind DSH M0

首条只读链路：独立 React 验证页 → 本机 Host → 官方 DSH SDK/学习插件 → Django 的本人记忆与学习工具。

这是 M0 开发验证，尚未接入正式模型网关、正式学生服务或桌面安装包。模型端使用本机确定性协议夹具；它验证实际 DSH 的消息、记忆和工具往返，不证明真实模型的路由或教学质量。

## 当前组成

- `plugin.mjs`：实际 Cordis 插件，注册 Django 返回的只读工具和本人记忆上下文。
- `profile.patch.yml`：针对安装版 `0.2.1rc2`，禁用终端、文件、计划模式、子 Agent、搜索及默认遥测。
- `host.py`：只绑定 `127.0.0.1:8791` 的单学生验证 Host。凭据仅在 Host/子进程环境中，不返回浏览器。
- `smoke.py`：启动临时 SQLite/Django 和本机模型协议夹具，验证实际 DSH 工具调用；退出时清理。
- `frontend/src/pages/DshM0.tsx`：仅开发模式 `/dev/dsh`，正式路由不启用。
- `/api/ai/dsh/context/`、`/api/ai/dsh/tools/<name>/`：由 `UNIMIND_DSH_ENABLED` 控制，默认关闭。

当前只选择 `get_learning_stats`、`get_recent_practice_result`、`get_user_weak_points`、`search_courses`、`search_asr`。每次请求使用当前身份重新鉴权；旧记忆版本执行返回 409。M0 使用新运行实例，不恢复旧 Session，也不声称已实现完整记忆生命周期。

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

## 后续门槛

1. 公司模型网关：任务准入、预算、次数结算和模型策略，完成前 Host 拒绝连接外部模型来源。
2. 每轮动态工具选择及实际问法质量验证；当前为启动本轮时按关键词与工作流组选择的有限集合。
3. 完整会话恢复、记忆失效重建、删除与业务记录分离。
4. 公司 Electron 壳、受限 IPC、凭据存储、签名安装与更新。
5. 托管多用户隔离、真实评分样本和正式模型验证。

配置可以启动并不代表上述门槛已经通过。实现计划与证据见 `docs/superpowers/plans/2026-10-25-dsh-m0.md`。
