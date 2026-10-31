# DSH 体验补齐与 Electron 桌面学习能力

**Goal:** 完成已审查的 DSH 展示／过程缺口，并将 Electron 薄壳接成可使用的桌面学习客户端。
**Spec:** 用户 2026-10-29 要求“开始做 1、2”，对应 docs/DSH_DESKTOP_READINESS.md。
**Architecture:** DSH 通过服务端 Schema 校验的展示工具恢复原生卡片；工具状态沿原 SSE 事件进入现有任务 UI。Electron 主进程只暴露固定业务方法，网页继续使用 Django 账号和课程授权。离线视频仅由服务端签发下载清单，保存在当前账号的 App 私有目录。

## 约束

- 保留工作区所有并发用户修改；不更改生产 .env、不发布、不宣称签名或 Windows 实机验收完成。
- 只做必要冒烟；不使用真实学生或发送真实通知验证，不让 Agent 编辑笔记、提交成绩或发布工单。
- 上下文隔离、sandbox 与 nodeIntegration:false 保持；IPC 校验发送者且不接受任意路径／下载 URL。
- 原生通知和关窗驻留由用户显式开启；离线缓存按账号隔离，退出后不能播放上一账号资源。
- 离线有效期先按服务端授权复核后最多 24 小时，且不得晚于课程批次到期；可联网时重新核验。此为本轮实现默认值，不能宣称已有正式版权／留存政策。
- 更新器仅在配置受信 HTTPS 更新源且发行包签名后形成正式交付；未配置时明确显示状态，不能给出假“最新版”。

## 共享接口

Electron preload 暴露 `window.unimindDesktop`，Promise 方法：
- getState(), syncIdentity(), logout(), updatePreferences({notifications?,keepRunning?})
- notify({title,body,route}), downloadCourse(courseId), removeDownload(courseId), openOfflineLibrary(), openOfflineCourse(courseId)
- checkForUpdates(), installUpdate()
- onNavigate(callback(route)), onStateChanged(callback(state))，均返回取消订阅函数。

State：{version,platform,preferences:{notifications,keepRunning},downloads:[{courseId,title,status:'downloading'|'ready'|'failed',receivedBytes,totalBytes,expiresAt?,error?}],update:{status:'unconfigured'|'idle'|'checking'|'available'|'downloading'|'downloaded'|'error',version?,error?}}。

课程清单：GET `/api/courses/<id>/offline-manifest/`，已认证且沿用 visible_courses(request)。响应 `{user_id,course_id,title,expires_at,version,video:{url,filename,size}}`，expires_at 为 Unix 秒，version 标识课程视频版本。支持 POST `/api/courses/offline-access/` body `{course_ids:[...]}` 返回 `{user_id,courses:[上述清单]}`，对已撤权条目不返回，供主进程复核。文件仅视频，不暗加课程资料下载。

## Tasks

- [x] DSH：受控公式、步骤、函数采样点与回复选项工具；尺寸／链接／数量校验；可靠 call_id 与成功／失败状态；保留最终历史卡片。Owner：DSH worker。
- [x] 服务端离线清单：本人身份、课程范围、媒体、批次到期；必要权限冒烟。Owner：offline backend worker。
- [x] Electron：preload、通知与驻留、菜单快捷键、深链接、账号隔离下载／离线窗口、更新器状态。Owner：Electron worker，仅 frontend/electron。
- [x] React：固定桥接类型、桌面设置与下载入口、课程下载按钮、通知与账号同步、桌面导航事件。Owner：主 agent。
- [x] 集成：前端／Electron 类型与构建、后端定向冒烟、合成 UI／App 验证，记录未完成的外部验收条件。

## Review focus

- 升级前旧会话卡片继续可读；模型数据不执行 HTML、脚本或任意 URL。
- 下载中退出、切账号、撤权、批次到期和过期缓存不得越权；失败保留可重试状态，不能伪称下载完成。
- 资源窗口、第三方页面不能调用主业务 IPC；本地离线协议只读取已登记的当前账号资源并支持视频 Range。
- 未配置更新源、无签名和不支持的平台必须明确说明；不为预览 App 安装正式更新。
- 后台完成通知去重且不发送正文／成绩等隐私数据，点击仅回到受信站内路由。

## 实施与冒烟结果

2026-10-29：完成上述代码链路，未提交、未部署。用户确认暂无正式更新源，先完成机制。

- 前端 `npm run build` 通过；Electron build（打包编译、TypeScript、原3项安全冒烟）通过，生成独立未签名 macOS 预览 App。
- 后端 DSH 定向5项（展示Schema/SSE/发现及原鉴权与路由）、DSH纯函数与卡片来源冒烟通过；离线接口定向3项通过。
- Electron合成进程验证下载完成、授权恢复、Range206、服务不可用时离线HTML、复连撤权403、退出删除缓存。
- 真实Electron界面验证桌面设置、默认关闭开关、未配置更新源状态、独立离线库，以及合成公开课下载、独立本地视频播放与设置页下载管理。身份同步并发误报已修复，重启预览后设置无错误。
- 审查修复多曲线不同采样点断线、输入/评分卡混排失效、更新配置打包路径、启动导航订阅时序及过期磁盘缓存回收。

边界：没有开启用户系统通知／驻留偏好，没有真实模型质量测评、生产开关切换、签名公证、真实更新安装或Windows实机验收。外部账号中心授权码交换仍未接入；受控内容深链接不承担登录回流。
