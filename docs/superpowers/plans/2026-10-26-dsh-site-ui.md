# DSH 站点 React 接入实施计划

> 使用 superpowers:executing-plans 在既有隔离 worktree 连续执行。用户已要求继续，不重复设计访谈。仅做必要冒烟，一次独立代码复核。

**Goal:** 既有开发 React 页可经站点 Cookie 调用已完成的 DSH chat/session API，验证真实登录边界与恢复。

**Architecture:** /dev/dsh 保留原本机 Host 模式；?source=site 明确选择站点模式。站点 status 仅返回当前账号和模型来源标识，不返回凭据或配置；请求使用既有 Cookie。站点会话 ID 只在 sessionStorage 按账号保存，正文不写浏览器存储。沿用只读卡片，不改变正式小宇。

**Tech Stack:** 既有 React/TypeScript、fetch、Django/DRF、实际 DSH SDK 0.2.1rc2。

**Spec:** /Users/eular/Desktop/科晟开发/UniMind/规划/2026-10-25-新UniMind完整规划-v1.2.md 第六、十二、十四、十五节；已完成的 dsh-site-bridge 计划。

## Constraints and rulings

- 入口仅 DEV，站点开关默认关闭，不修改实际 .env、不部署。
- 不新增模型调用、用户凭据存储、价格、数据库迁移或生产登录旁路。
- 站点调用不使用 axios 的自动重试和 30 秒默认超时；fetch 手动重试保留同一 request_id/提问/会话，避免网络断开后重复消费。
- 退出/身份失效立即清除内存中的聊天、卡片、记忆和当前标签页索引，中止本页请求；旧异步结果不得回填。服务端任务可能已结算，取消页面请求不承诺撤销任务。
- 只有隔离数据库 fixture 提供合成学生 Cookie 启动链接；不加入业务 URL。浏览器只验证开发页，不切流正式小宇。
- 现阶段整轮 JSON 返回；实时流式 UI 单独迁移，不能把加载提示称为流式。

## Review Focus

- 账号退出/切换或旧响应晚到时不展示上一个学生的正文、卡片和记忆。
- 网络异常后以同一请求 ID 恢复结果，不自动追加第二次问答。
- 404 默认关闭、401 未登录、403 权益不足和 503 忙碌有明确提示且不误报模型来源。
- 页面刷新只恢复当前账号的会话 ID，浏览器不保存正文或凭据。
- 原 Host 模式继续可用，站点模式不会落回固定学生 Host。

## Task 1: 最小站点状态接口

Files: backend/ai_assistant/views_dsh.py、urls.py、tests/test_dsh_site_smoke.py。

- [x] 写定向冒烟，验证默认关闭、匿名拒绝、当前账号、模拟仅 DEBUG、无配置秘密；先复现缺少入口。
- [x] 增加 GET /api/ai/dsh/status/，继承既有站点鉴权/开关。
- [x] 运行该定向冒烟，确认通过。

## Task 2: React 请求及会话接入

Files: frontend/src/pages/DshM0.tsx。

- [x] 明确站点来源、Cookie fetch、status/context/chat/session 请求、按账号标签页索引、手动同 ID 重试。
- [x] 请求中止与旧结果保护；身份失效/退出清空敏感状态；原 Host 行为保留。
- [x] 前端构建；在隔离 fixture 中浏览器验证 Cookie 登录、工具卡、刷新恢复、退出及切换身份。

## Task 3: 证据与收尾

Files: dsh/smoke.py、site_smoke.py、README.md、迁移记录。

- [x] fixture 增加可选 --serve 模式及仅合成身份的 Cookie 启动链接，不暴露 Token。
- [x] 实际站点 SDK 冒烟、浏览器可见证据和针对性失败提示核验；不访问付费模型。
- [x] 一次独立复核，修复重要问题，更新文档并本地提交。


## 验收与边界

- 5 项站点后端聚合冒烟通过；状态接口及无效来源检查均先失败后通过。状态只声明来源配置有效，不声明上游余额或模型实际可用。
- 实际 SDK/临时 Django 双学生站点冒烟通过，沿用身份隔离、恢复、幂等、额度、失败释放和删除证据。前端类型与生产构建通过，临时跨窗口控件已移出 public，最终构建不含该控件。
- 浏览器实际通过 Cookie 返回学情卡片、刷新恢复相同会话；模拟服务端完成后响应丢失，手动同 ID 恢复返回原两条消息。失效 Cookie 清空旧聊天；另一学生只显示本人身份。浏览器跨窗口 storage 事件先复现旧记忆残留，修复后立即清空；在途请求退出后没有回填。
- 一次独立复核发现两项 Important，已分别 RED→GREEN 修复，无追加复审。Minor 保留：默认关闭时 DRF 通用 404 detail 可能覆盖更明确的中文入口提示。
- Ruling: 保留既有开发分支和 worktree，继续本地提交，不合并、推送或部署。代价是需后续发布流程才能交付学生使用。Paid 模型质量、正式切流/流式 UI、桌面以及整页重载后的 pending 请求恢复均未纳入本批；既有后端配额/会话实现不重复审查，实际契约由本批端到端冒烟验证。

浏览器证据：.m0-state/m0-site-ui-proof.png（站点结果卡），.m0-state/m0-site-identity-clear-proof.png（退出清空）。这些截图与临时数据库不进入 Git。
