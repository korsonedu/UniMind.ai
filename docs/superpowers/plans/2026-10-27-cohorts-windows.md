# 可配置学员批次与 Windows 交付

> 使用 superpowers:executing-plans 连续执行，必要冒烟、构建和一次独立复核。

**Goal:** 落实用户新确认的“年度可设置、两批学员同时存在、支持Windows”。

**Architecture:** 新增 StudentCohort，CourseStudentStatus 绑定当前服务批次；多个批次分别判断服务有效期，不设全站默认考试年。React/Directus共用现有Django授权和后台桥；Windows复用 Electron 薄壳，DSH不进客户端。

**Spec:** 用户2026-10-27答复；完整规划的服务年度、有效期和公司客户端交付要求。

## 约束与判断

- 每名学员当前绑定一个批次，多个批次可并存；不开发未要求的同人多套餐叠加。若未来同一人需要双批次权益，需单独扩展。
- 批次字段：name、target_year（目标届别）、exam_date（实际考试日可空）、starts_on、ends_on、is_active、updated_at。服务日期按上海日历，首尾日均有效；目标届别不强制等于实际考试年份。
- 旧明确手工授权不猜年份、不自动失效；未分配批次须在后台明确显示为兼容授权。已绑定批次的账号不可回退旧会员规则绕过过期/停用。
- 学员只读自己的批次，配置/分配仅走已有管理身份；到期保留成绩、会话与已用次数。
- 批次变更进入DSH上下文版本，清除旧运行上下文，保留可见历史；不自动改写学生长期记忆。
- 不自动开放内容、发通知、下单或填正式服务日期；不改真实.env和生产开关。
- Windows x64/NSIS候选独立构建并记录hash，默认无签名；构建不等于Windows真人登录或正式公开分发。

## Review Focus

- 过期/停用批次不能因is_member或旧grant重新获得全权益，普通注册仍有公开课和有限小宇。
- 调整批次不能丢失手工启用标记、原额度使用或正式成绩；未传批次字段的旧调用保持兼容。
- 管理端保存和学生自查都显示正确批次，不跨学生展示；目标年度不硬编码。
- 同样工具权限下改变批次也必须改变DSH上下文版本，旧年对话不继续作为有效运行上下文。
- Windows构建采用HTTPS发布入口、无模型配置，不能把macOS构建当作Windows已验收。

## Task 1：批次配置与权益

**Files:** users/models_learning.py、models.py、learning.py、admin.py与新增0076迁移；backoffice/people.py、views.py；dsh_service.py；Directus People.vue/types/bridge与批次表单；React Billing/types。
**Interfaces:** cohort_info(user) 返回本人批次或None；set_course_student_status(..., cohort_id=...)保留省略字段语义；cohorts.list/save沿用签名后台操作。

- [x] 一份必要冒烟验证两个批次并存、日期/停用/旧授权、权限与批次版本、后台分配及普通账号拒绝。
- [x] 最小实现模型/有效期、后台配置和分配、本人服务页、DSH版本；生成迁移，不设正式默认批次。
- [x] Django check/迁移一致性、定向冒烟、学生端和扩展构建；有备份的合成库迁移，实际管理及本人服务页验证。

## Task 2：Windows 与交付

**Files:** .github/workflows/desktop-windows.yml、dsh/PREVIEW.md、迁移和发布说明。

- [ ] 生成NSIS x64候选，保存安装包hash和构建证据。公开仓库尚未推送，先按官方方式本机交叉构建；不能执行时记录具体阻塞。
- [ ] Windows原生runner的3项URL冒烟与实际安装、登录、会话/课件验证须有真实Windows环境，不能用macOS或交叉编译代替。
- [x] 一次独立复核本阶段增量，Critical/Important为0；保留主仓库用户修改。构建产物与最终记录继续补齐。

## 当前证据

3项批次冒烟先缺少模型/操作失败，补齐后通过；签名后台配置/读取通过，普通Token拒绝。React构建、扩展vue-tsc与build、Django check及迁移一致性通过。0076只应用在备份后的合成库，原20条消息与正式业务计数不变。

独立合成管理库中，真实People/Cohorts组件经现有签名桥创建2027/2028两个有效批次，为合成学员分配A并在保持授权开启时改绑B；同库React“我的服务”由2027届/2027-01-31更新到2028届/2028-01-31。截图m0-two-cohorts-admin-proof、m0-cohort-assigned-proof、m0-cohort-service-a-proof、m0-cohort-service-b-proof。

原生小宇真实模型读取主合成预览的当前批次2027届/2026-11-26，明确考试日未设置，额度190→189，未提取长期记忆；截图m0-cohort-dsh-proof。以上日期都是显式合成配置，不是正式默认值。

唯一独立复核覆盖d6cd2e3..3893d6a，未发现代码阻塞项，Windows实际运行仍是交付条件。主仓库HEAD与原dirty patch SHA256再次核对一致，未修改用户工作区。

后续用户提交4cc80ad已将当前桌面壳改为Electron，保留Tauri作为历史候选。Windows交付以该提交的Electron NSIS workflow为准；旧Rust/SDK交叉构建不再推进。仅停止本任务旧SDK下载，官方LLVM分段文件SHA256已核验，但不再安装为当前产品依赖。当前服务批次实现与复核结果不受壳迁移影响。
