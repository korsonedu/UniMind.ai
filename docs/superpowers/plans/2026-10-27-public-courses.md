# 注册学生公开课接通

> 使用 superpowers:executing-plans 在当前 worktree 连续执行；按用户要求仅必要冒烟，最后一次独立复核。

**Goal:** 落实用户已确认的“注册学生：公开课＋小宇有限量使用”，课程学员保留全课。

**Architecture:** 复用现有课程工作台和 CourseModule.is_public；注册用户获得课程入口，服务端统一过滤课程对象与直接媒体。未归类或未明确开放的课程不对体验用户开放，不新增价格、期限或套餐。

**Tech Stack:** Django/DRF、现有 React/Zustand。

**Spec:** 用户原始权益要求；完整规划 M1 的公开/付费资源边界。

## 约束与审查重点

- 课程学员和管理员访问保持原状；匿名和停用账号不能因公开标记得到新的访问。
- 课程列表、详情、模块、专辑及嵌套列表不得泄露未开放课程；媒体不能绕过相同过滤。
- 公开模块仅由已有管理员操作标记，不自动开放任何现有课程。
- 体验用户不能触发转录/大纲生成，启动材料没有公开标记，保持课程学员范围。
- 小宇周额度和工具权限不扩张；公开课入口不显示无权使用的测评、答疑、自习或学情错误。

## Tasks

### Task 1：服务端公开范围

**Files:** users/permissions.py、courses/access.py、courses/views.py、courses/modules.py、courses/serializers.py、courses/views_tags.py、school_system/media_serve.py。
**Interfaces:** visible_courses(request) 返回本人内容范围与公开模块的交集；has_full_course_access(user) 仅为课程学员或平台管理员。

- [x] 写并运行 courses/tests/test_public_courses_smoke.py：注册学生仅列表/读取公开课，私有/未归类404，媒体200/403、匿名401，专辑嵌套不越界；未授权生成和启动材料拒绝，课程学员仍可读取。
- [x] 最小实现统一范围和生成限制，运行这份必要冒烟至通过。

### Task 2：复用界面并交付

**Files:** CoursePortal.tsx、OutlinePanel.tsx、DSH_MIGRATION.md、上述冒烟。
**Interfaces:** 继续使用原 course.video 入口；full.report/video.outline 等独立能力决定附加 UI，不新增页面或路由。

- [x] 公开课工作台不请求无权读取的学情，快捷入口按既有能力展示；体验用户只读现成大纲，不自动生成。
- [x] 前端构建；实际网页以合成注册账号验证公开课列表/详情及不可访问私有课。5秒合成视频完整播放；注册学生真实DSH回答额度13→12。
- [ ] 一次独立复核和必要修复；更新交付边界，精确本地提交，不发布生产。
