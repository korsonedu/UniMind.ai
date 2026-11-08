# 会话工具与交互实验发布

本次从生产提交 `4d87775` 分离构建，只包含会话计算工具、交互实验和运行器边界；保留课程图片通道与当前小宇界面。

## 开关

生产保持 `DEBUG=false`，启用：

```dotenv
UNIMIND_LEARNING_EXPERIMENTS_ENABLED=true
UNIMIND_LEARNING_WORKER_ROOT=/opt/unimind-learning-worker
```

本地原型仍可使用 `DEBUG=true` 与 `UNIMIND_LEARNING_EXPERIMENTS_PROTOTYPE=true`。关闭生产开关即可停止暴露和执行新能力。学生权限、账号与对话归属检查保留，无新增数据库表或迁移。

## 独立运行器

专用用户为 `unimind-learning`，家目录 `/var/lib/unimind-learning`。`/opt/unimind-learning-worker` 中保存两个独立脚本、固定 `playwright==1.59.0` 的 `venv` 和 Chromium Headless Shell 1217；代码、解释器和浏览器由 root 管理，运行用户不能改写。

生产通过临时 systemd 单元执行，最多同时 2 个，每个内存 512 MiB、禁用交换、最多 96 个进程、1 核 CPU 配额、10 秒服务时限与 12 秒父进程时限。单元使用非 root 身份、独立网络和临时目录、只读系统、隐藏用户目录、禁止获得新权限，并隔离 `/opt/unimind`、`/opt/unimind-venvs`、`/var/lib/unimind`。浏览器沙箱保持开启；生成代码只接收明确 JSON 输入，不获得 Django 或模型凭据。

Ubuntu 的用户命名空间限制需要固定 Chromium 的专用规则 `deploy/unimind-learning-chromium.apparmor`。该规则使用 `unconfined` 加 `userns`，安装须有明确授权；它不改变全局 AppArmor 限制，文件、网络和资源边界由上述 systemd 单元施加。浏览器升级后需重新核对规则中的可执行文件路径。

## 验证和回滚

发布前运行定向浏览器/DSH 冒烟、课程图片兼容冒烟、DSH TypeScript 检查和前端生产构建。服务器上先验证非 root Worker、禁网及站点文件不可访问，再开启开关；公开健康接口、服务状态和新 API 鉴权均需通过。

本次回滚资料保存在 `/opt/unimind-backups/session-learning-tools-20261108`：旧提交、旧前端绝对路径、私有环境文件和 PostgreSQL 自定义格式一致性备份。应用回滚应关闭新开关，恢复旧代码与前端链接并重启应用；本次无数据库迁移，通常无需回灌数据库。独立运行器和专用规则在关闭功能后不会被应用调用。

服务器隔离冒烟已确认运行 UID 为 995，站点环境文件及 root 主目录不可见，网络连接返回 `ENETUNREACH`，`NoNewPrivs=1`。专用规则已获用户明确授权并安装，Chromium 自带沙箱保持开启，系统全局 `kernel.apparmor_restrict_unprivileged_userns=1` 保持不变。

## 2026-11-08 上线记录

功能提交 `7588a72`，生产首次切换至 `e6c4d99`（包含预检文档）；活动前端为 `/opt/unimind-releases/session-learning-tools-e6c4d99/frontend/dist`。生产保持 `DEBUG=false`，新开关已开启，Django 系统检查通过；应用、Celery 和 Nginx 均 active，公网 `/health/` 的数据库和缓存检查正常，公网 HTML 与本次构建字节一致。

合成临时账号沿真实 DSH 回调和公网 API 验证了工具注册、动态名称调用返回 42、HTML 预览、实验读取、状态 PATCH 与重新读取，以及未认证请求被拒绝。此轮线上冒烟没有模型 API 请求，完成后已删除合成账号及关联消息、Token 和预留记录。生产私有结果在回滚目录的 `production-smoke.json`。
