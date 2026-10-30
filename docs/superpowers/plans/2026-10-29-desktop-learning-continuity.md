# 桌面连续学习 Implementation Plan

**Goal:** 完成已获用户“开始”授权的前三项：离线学习闭环、可恢复下载、桌面草稿与任务恢复。
**Spec:** `docs/DSH_DESKTOP_ACCEPTANCE_2026-10-29.md` 的优先级1。
**Architecture:** Electron负责私有离线播放器、账号隔离缓存和持久事件队列；Django复用课程进度、学习活动及学习会话的幂等计数。对话只恢复本地草稿和查询原request_id，不自动重发模型请求。

## 约束与决策

- 保留用户并发修改；最少代码、必要冒烟；不提交、部署、修改生产环境或扩大Agent写笔记权限。
- 原下载互斥、账号清理屏障、IPC发送者校验和私有协议隔离继续成立。
- 下载暂停保存分片；重启将未完成任务展示为暂停，由用户继续。Range或版本不兼容时从零安全重下。
- 离线播放只记录实际播放时间，不补算休眠间隔。事件带稳定event_id，重复同步不重复计学习时长或完成奖励。
- 服务端签发绑定用户／课程／版本／有效期的grant；允许7天内补传有效期内的观看，复网仍检查当前课程权限和版本。撤权或无效授权的终态拒绝要在界面说明；401保留待同步、等待登录。
- 本地缓存不作为DRM。签名grant仅用于服务端验证学习事件来源与期限，不承诺视频防复制。
- 对话恢复只查询原请求及历史；pending、completed、unknown分别处理。无法确认时保留状态，由用户决定重试；不得自动新建request_id、重新扣额或执行动作。
- 新bridge接口能力检测，兼容仍运行的旧预览壳。

## 接口

- Electron：`pauseDownload(courseId)`；现`downloadCourse`用于继续／重试；`onResume({reason:'resume'|'renderer-recovered'})`。
- DesktopState：downloads.status新增paused；storage.usedBytes；learningSync的pending、rejected、error。
- 离线记录：`POST /api/courses/<id>/offline-progress/`，精确字段由服务端与播放器共同确认；事务内写课程及学习会话。
- 对话：只读`GET /api/ai/chat-requests/<request_id>/`，按当前用户、bot和conversation校验；不得把消息正文放查询串。

## 分工与验收

- [x] 原生下载／离线播放：`frontend/electron/**`。暂停／续传、恢复分片、原子持久化、学习队列、休眠与进程异常恢复入口。必要冒烟含取消重试、服务器不支持Range、重启、切账号与重复同步。
- [x] 课程同步：`backend/courses/**`。复用计数逻辑，signed grant、权限与版本、event_id事务幂等；定向验证重复／错账号／撤权／学习时长。
- [x] 对话恢复：`useAgentConversation`、新本地恢复helper及`backend/ai_assistant`状态查询；验证不自动POST、旧请求结果隔离、草稿不被旧响应覆盖。
- [x] React整合：desktop bridge、设置和课程按钮；显示暂停／继续、缓存占用与学习同步状态，恢复时重新确认身份。
- [ ] 整体验收：前端／Electron构建、必要后端冒烟、当前Electron可见链路、一次独立代码复核。更新验收记录，列明正式发行外部条件。

## 当前验收状态

截至2026-10-30，代码、构建、定向冒烟和独立复核已完成。解锁后已实际验收离线同步与续播、会话草稿、原任务重连恢复、Renderer异常恢复，以及一次现有题库练习提交／批改／重连读取。两端未签名内测包已归档。整体验收仍保留待完成：系统睡眠唤醒、Windows实机及正式安装升级不能由上述局部证据替代。详情见 `docs/PRODUCTION_READINESS.md`。
