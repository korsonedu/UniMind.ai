# UniMind.ai 权限架构

> 最后更新：2026-05-21  
> 审计范围：全系统（后端 11 个 Django app + 前端 21 个页面 + 路由/侧边栏）

---

## 一、三层权限模型

UniMind 的权限由三个独立维度叠加决定：

| 维度 | 后端存储 | 控制范围 |
|------|---------|---------|
| **平台角色** | `User.role` — `student` / `admin` | 是否为平台超级管理员 |
| **机构角色** | `User.institution_role` — `owner` / `teacher` / `student` | 机构内的管理权限 |
| **方案层级** | `Institution.plan` + `User.membership_tier` — `free` / `solo` / `plus` / `pro` | 功能可见性 |

实际权限取三者**交集**：方案决定你能看到什么功能，机构角色决定你能管理谁，平台角色决定你能跨机构操作。

---

## 二、用户模型

### 2.1 User 核心字段（`backend/users/models.py`）

```
role              : 'student' | 'admin'           （平台角色，默认 student）
is_member         : boolean                        （是否已激活会员）
membership_tier   : 'free' | 'solo' | 'plus' | 'pro' （个人会员等级）
institution       : FK → Institution               （所属机构，可为 null）
institution_role  : 'owner' | 'teacher' | 'student'  （机构内角色，默认 student）
```

### 2.2 计算属性

| 属性 | 定义 | 含义 |
|------|------|------|
| `is_platform_admin` | `is_superuser AND institution_id IS NULL` | 无机构归属的超级管理员 |
| `is_institution_admin`（前端） | `institution IS NOT NULL AND institution_role IN ('owner','teacher')` | 机构管理者 |
| `is_institution_owner`（前端） | `institution IS NOT NULL AND institution_role = 'owner'` | 机构所有者 |

### 2.3 save() 自动规则

```
is_superuser → role='admin', is_staff=True, is_member=True
```

---

## 三、机构模型

### 3.1 Institution（`backend/users/models.py:150-211`）

```
plan              : 'free' | 'solo' | 'plus' | 'pro'  （机构方案，默认 free）
plan_expires_at   : datetime                            （过期时间）
is_active         : boolean
max_students      : 属性，free=30, solo=50, plus=200, pro=999999
student_count     : 属性，institution_role='student' 的人数
is_plan_active    : 属性，is_active AND 未过期
invite_slug       : 邀请链接标识
```

### 3.2 PLAN_FEATURES 功能矩阵（`backend/users/models.py:237-264`）

```
free (6):
  quiz.manual  quiz.exam  wrong.review  basic.stats  ai.generate  course.video

solo (11 = free + 5):
  + memorix.review  full.report  knowledge.graph  ai.assistant  video.outline

plus (18 = solo + 7):
  + faq.system  pdf.mock  study.room  multi.teacher  class.compare  data.export  interview.mock

pro (27 = plus + 9):
  + brand.custom  api.access  student.payment  private.deploy  i18n.custom
    sso.saml  audit.log  dedicated.support  sla.99.9
```

---

## 四、后端权限类（`backend/users/permissions.py`）

### 4.1 权限类一览

| 类 | 放行条件 | 典型用途 |
|----|---------|---------|
| `IsPlatformAdmin` | `is_superuser` | Prompt 模板、邀请码管理 |
| `IsAdmin` | 平台管理员 OR 机构 owner/teacher | 题目 CRUD、课程管理 |
| `IsInstitutionAdmin` | 机构 owner/teacher | 成员管理、积分奖励 |
| `IsInstitutionOwner` | 仅机构 owner | 机构设置编辑、角色修改 |
| `IsInstitutionActive` | 机构启用且未过期 | 叠加在其他机构权限上 |
| `IsInstitutionMember` | 属于任意机构 | 机构内排行榜 |
| `IsMemberOrAdmin` | `is_member_or_admin()`（含会员过期检查） | 知识图谱、热力图 |
| `IsAdminWriteMemberRead` | 读=会员/管理员，写=平台/机构管理员 | 知识点、文章 |
| `HasPlanFeature` | `view.required_feature` 在机构功能列表中 | AI 出题、面试模拟 |
| `HasAIQuota` | Free 版每月 20 次，Solo+ 无限 | AI 出题 |
| `HasPointsBalance` | `user.elo_points >= view.points_cost` | AI 对话、面试 |

### 4.2 辅助函数

| 函数 | 逻辑 |
|------|------|
| `is_platform_admin(user)` | `is_authenticated AND is_superuser` |
| `is_institution_admin(user)` | `institution IS NOT NULL AND role IN ('owner','teacher')` |
| `is_member_or_admin(user)` | 平台/机构管理员 OR（`is_member AND 会员未过期 AND 试用未过期`） |
| `get_user_capabilities(user)` | 聚合角色+权限组+extra_permissions，应用 blocked_permissions |
| `has_capability(user, cap)` | `cap in get_user_capabilities(user)` |

### 4.3 DEFAULT_PERMISSION_CLASSES

`settings.py` 全局默认：`IsAuthenticated`。所有未显式设置 `permission_classes` 的视图默认要求登录。

### 4.4 权限类组合模式

```python
# 机构管理：叠加管理员 + 机构活跃检查
permission_classes = [IsAuthenticated, IsInstitutionAdmin, IsInstitutionActive]

# 功能+配额：方案检查 + 用量配额
permission_classes = [HasPlanFeature, HasAIQuota]
required_feature = 'ai.generate'

# 功能+积分：方案检查 + 积分消耗
permission_classes = [IsMember, HasPlanFeature, HasPointsBalance]
required_feature = 'interview.mock'
points_cost = 50
```

---

## 五、后端视图权限总表

### 5.1 用户系统（users/）

| 端点 | 权限 |
|------|------|
| `POST /users/register/` | AllowAny |
| `POST /users/login/` | AllowAny |
| `GET /users/me/` | IsAuthenticated |
| `PATCH /users/me/` | IsAuthenticated |
| `POST /users/me/activate/` | IsAuthenticated |
| `GET /users/me/weekly-report/` | IsMember |
| `GET/POST /users/institutions/` | IsPlatformAdmin |
| `GET/POST /users/institution/students/` | IsInstitutionAdmin + IsInstitutionActive |
| `GET /users/institution/me/features/` | IsAuthenticated |
| `GET /users/institution/me/dashboard/` | IsAuthenticated（内联 RBAC） |
| `PATCH /users/institution/me/` | IsInstitutionOwner + IsInstitutionActive |
| `POST /users/institutions/create/` | IsAuthenticated |
| `POST /users/institution/join-by-slug/` | IsAuthenticated |
| `GET /users/join/:slug/` | AllowAny（公开重定向） |
| `GET /api/users/institution/:slug/public/` | AllowAny |

### 5.2 题库（quizzes/）

| 端点 | 权限 |
|------|------|
| `GET /quizzes/questions/` | IsMember（读），IsAdmin（写） |
| `POST/PATCH/DELETE /quizzes/questions/:id/` | IsAdmin |
| `GET/POST /quizzes/knowledge-points/` | IsAdminWriteMemberRead |
| `POST /quizzes/knowledge-points/generate-bulk/` | HasPlanFeature('ai.generate') + HasAIQuota |
| `POST /quizzes/knowledge-points/import-md/` | IsAdmin OR IsInstitutionAdmin |
| `GET /quizzes/knowledge-points/subjects/` | 公开（无权限） |
| `GET /quizzes/exams/` | IsMember |
| `POST /quizzes/exams/` | IsAdmin |
| `GET /quizzes/graph/heatmap/` | IsMemberOrAdmin |
| `GET /quizzes/favorites/` | IsMember |
| `GET /quizzes/wrong-questions/` | IsMember |
| `GET /quizzes/ai/preview/` | HasPlanFeature('ai.generate') + HasAIQuota |
| `POST /quizzes/ai/pipeline/` | HasPlanFeature('ai.generate') + HasAIQuota |
| `GET/POST /quizzes/admin/prompt-templates/` | IsPlatformAdmin |

### 5.3 课程/文章/AI/面试/自习室/通知

| App | 端点 | 权限 |
|-----|------|------|
| courses | 视频进度 | IsMember |
| courses | 课程/专辑 CRUD 写 | IsAdmin |
| courses | 课程/专辑 读 | IsMember |
| courses | 素材/专辑 读 | AllowAny |
| articles | 文章 CRUD 写 | IsAdminWriteMemberRead |
| articles | 文章 读 | IsAdminWriteMemberRead（读=会员/管理员） |
| articles | 浏览量+1 | IsMember |
| ai_assistant | Bot 管理 | IsAdmin（写），IsMember（读） |
| ai_assistant | AI 对话 | IsMember + HasPointsBalance(30) |
| interviews | 全部 | IsMember + HasPlanFeature('interview.mock') |
| faq_system | 全部 | IsMember（内联教师/管理员检查用于写操作） |
| study_room | 全部 | IsMember |
| notifications | 全部 | IsAuthenticated（广播=IsAdmin） |

---

## 六、前端权限

### 6.1 路由守卫（`App.tsx`）

| 守卫 | 条件 | 不满足→重定向 |
|------|------|-------------|
| `RequireAuth` | `token` 存在 | → `/login` |
| `RequirePlatformAdmin` | `user.is_admin`（= is_superuser AND 无机构） | → `/settings` |
| `RequireAdmin` | `user.is_admin` OR `user.is_institution_admin` | → `/settings` |
| `RequireInstitution` | 平台管理员 OR（有机构 AND 非学员角色） | → `/` |
| `FeatureGuard(feature)` | `hasFeature(feature)` | → `/` |

### 6.2 路由守卫矩阵

```
/                          RequireAuth → HomeRedirect
/courses, /tests, /articles, /settings    RequireAuth（无 FeatureGuard）
/qa, /tests/*, /study, /ai, /knowledge-map/*
/knowledge-map, /course/:id, /tests/review,
/mock-exam, /interviews                    RequireAuth + FeatureGuard
/system-settings, /management,
/institution/admin                         RequireAuth + RequireAdmin
/institution, /institution/students        RequireAuth + RequireInstitution
/invite-codes, /prompt-templates           RequireAuth + RequirePlatformAdmin
/intro/:slug                               public（无守卫）
```

### 6.3 侧边栏过滤（`MainLayout.tsx`）

**身份变量：**
```typescript
isSuperAdmin  = user.role === 'admin' && !instInfo
isInstStudent = Boolean(instInfo) && user.institution_role === 'student'
myPlanLevel   = Math.max(planLevel(user.membership_tier), planLevel(instPlan))
atLeast(lvl)  = myPlanLevel >= lvl
```

**学生特殊处理：**
- 侧边栏/移动端导航：过滤掉 `minPlan` 不满足的项（直接隐藏，不显示锁图标）
- UpgradeModal：学生完全不渲染
- 「升级套餐」按钮：学生隐藏
- 「激活会员」菜单：学生隐藏
- 机构管理菜单项：仅 `is_institution_admin` 可见

**非学生（教师/owner/独立用户）：**
- 锁定的功能项显示锁图标，点击唤起 UpgradeModal
- 「升级套餐」按钮当 `myPlanLevel < 3` 时显示
- 「激活会员」当非会员时显示

### 6.4 功能到方案映射（`UpgradeModal.tsx`）

```
solo:  memorix.review, ai.assistant, full.report, knowledge.graph, video.outline
plus:  faq.system, multi.teacher, class.compare, data.export, study.room, pdf.mock, interview.mock
pro:   brand.custom, api.access, student.payment, private.deploy, i18n.custom, sso.saml, audit.log, dedicated.support, sla.99.9
```

---

## 七、数据隔离

### 7.1 后端 queryset 过滤模式

几乎所有涉及多机构数据的视图都遵循此模式：

```python
def get_queryset(self):
    qs = Model.objects.all()
    if not is_platform_admin(self.request.user):
        inst = getattr(self.request.user, 'institution', None)
        if inst:
            qs = qs.filter(Q(institution=inst) | Q(institution__isnull=True))
        else:
            qs = qs.filter(institution__isnull=True)
    return qs
```

- 平台管理员：看到全局数据
- 机构用户：看到本机构数据 + 全局数据
- 无机构用户：只看到全局数据

### 7.2 前端 FeatureGuard

```typescript
// FeatureGuard.tsx
if (loading) return <Spinner />
if (hasFeature(feature)) return children
return <Navigate to="/" replace />
```

---

## 八、权限能力系统（细粒度）

### 8.1 能力常量（`permissions.py:7-12`）

```
learning.access    member.access    admin.panel
content.manage     users.manage     system.manage
```

### 8.2 角色→能力映射

```
student : [learning.access]
member  : [learning.access, member.access]
admin   : [learning.access, member.access, admin.panel, content.manage, users.manage, system.manage]
```

### 8.3 UserAccessProfile

一对一关联 User，提供 `extra_permissions` 和 `blocked_permissions`（JSON list），以及 `PermissionGroup`（多对多）。通过 `get_user_capabilities(user)` 聚合。

> 注意：此系统当前仅在管理后台的 SuperuserPanel 中暴露，未被业务视图使用。

---

## 九、用户流向与角色来源

```
注册（无机构、无角色）
  │
  ├─ 平台超管：Django createsuperuser → is_superuser → role=admin, is_member=True
  │
  ├─ 教师创建机构：OnboardingDialog → InstitutionCreateView → institution_role=owner
  │
  ├─ 教师加入机构：邀请链接(?role=teacher) → InstitutionJoinBySlugView → institution_role=teacher
  │
  ├─ 学生加入：邀请链接（默认） → InstitutionJoinBySlugView → institution_role=student
  │
  └─ 游离用户：未加入机构，institution_role 默认='student' 但无 institution
```

**规则：**
- 学生进入机构的唯一路径是邀请链接
- 教师可以通过邀请链接（?role=teacher）加入，或创建新机构成为 owner
- 机构内所有人自动 `is_member = True`，`membership_tier = inst.plan`
- 平台管理员（无机构）看到所有功能（等同于 pro）

---

## 十、审计发现 & 修复记录（2026-05-21）

### 10.1 已修复

| # | 问题 | 严重性 | 修复 |
|---|------|--------|------|
| 1 | **重复 IsMember 类缺少过期检查** — `users/views.py:28` 的 `IsMember` 只检查 `is_member` 布尔值，不检查 `membership_expires_at`。46+ 视图（quizzes/views_exam, views_memorix, views_question, courses, ai_assistant, faq_system, study_room, interviews, articles）使用此重复类，绕过会员过期控制 | **关键** | `IsMember.has_permission` 改为委托给 `is_member_or_admin()`，一次性修复所有 46+ 视图 |
| 2 | **articles 重复权限类** — `articles/views.py:9` 的 `IsAdminUserOrReadOnly` 写检查用 `is_staff`（仅超级管理员），导致机构管理员无法写文章。与 `permissions.py` 的 `IsAdminWriteMemberRead` 功能重复 | **中** | 删除局部类，统一使用 `IsAdminWriteMemberRead`。同时修复了机构管理员文章写入权限 |
| 3 | **学生看到侧边栏锁和升级弹窗** — 机构学生在低方案机构中看到带锁图标的功能入口，点击弹出 UpgradeModal。学生不应关心方案升级 | **中** | `isInstStudent` 修正为 `Boolean(instInfo) && role==='student'`；sidebar/mobileNav 对学生过滤未解锁项；UpgradeModal 加 `!isInstStudent` 守卫 |
| 4 | **邀请链接默认学生** — 加教师需要 owner 事后手动改角色 | **中** | `JoinInstitutionView` 支持 `?role=teacher` 参数，链路透传 cookie → register → login → join API |
| 5 | **教师受学生数上限限制** — `InstitutionJoinBySlugView` 的学生数上限检查对教师也生效 | **低** | 学生数上限仅对 `role='student'` 生效 |

### 10.2 已知但未修复

| # | 问题 | 原因/优先级 |
|---|------|-----------|
| 1 | `InstitutionDashboardView` 内联 RBAC — 单个视图混合三种角色逻辑，`permission_classes=[IsAuthenticated]` 太宽 | 低优先，功能正常，拆分需前端配合 |
| 2 | FeatureGuard 竞态 — `fetchFeatures()` 异步，FeatureGuard 可能在 features 加载前渲染导致错误的 `/` 重定向 | 低概率，RequireAuth 的 loading 状态通常覆盖此窗口 |
| 3 | Prompt 模板（IsPlatformAdmin）vs Pipeline 管理（IsAdmin）权限不一致 | 设计决策：模板全局，pipeline 可机构级 |
| 4 | courses 启动材料/专辑 GET 用 AllowAny | 可能是故意的——公开课程目录 |
| 5 | `permissions.IsMemberOrAdmin` 仅在 `graph_views.py` 使用——与 `users.views.IsMember` 功能重复但位置不同 | 修复 #1 后，`IsMember` 已委托给 `is_member_or_admin()`，两者等价 |

---

## 十一、开发规范

### 11.1 新增后端视图时

1. **权限类从 `users.permissions` 引用**，不要在 app 内定义局部权限类
2. 机构管理数据必须用 `IsInstitutionAdmin` + `IsInstitutionActive` 组合
3. 功能门控用 `HasPlanFeature` + `view.required_feature`
4. 消耗性功能叠加 `HasPointsBalance` + `view.points_cost`
5. queryset 必须做机构数据隔离（见第七节模式）
6. **不要用 `users.views.IsMember`**——虽然它现在已委托给正确的实现，但建议直接 import `IsMemberOrAdmin` 让意图更清晰

### 11.2 新增前端路由时

1. 在 `App.tsx` 注册路由
2. 如有功能门控，包裹 `FeatureGuard(feature)`
3. 如有管理权限要求，包裹对应的 `Require*` 守卫
4. 侧边栏入口在 `MainLayout.tsx` 的 `navItems` 中添加，标注 `minPlan`（如果有方案要求）

### 11.3 侧边栏规则

- 对学生：`minPlan` 不满足的项**直接隐藏**（不显示锁图标，不触发升级）
- 对教师/owner：`minPlan` 不满足的项显示锁图标，点击唤起 UpgradeModal
- 机构管理菜单项（成员管理、维护）仅 `is_institution_admin` 可见
