# UniMind.ai 权限架构

> 最后更新：2026-06-21（四层模型重构）
> 审计范围：全系统（后端 11 个 Django app + 前端 21+ 页面 + 路由/侧边栏 + Agent 工具权限沙箱）

---

## 一、四层权限模型

权限由 **角色** + **方案** 两个维度叠加决定。角色决定你能管理谁，方案决定你能看到什么功能。

### 1.1 四层角色

```
Layer 1  系统管理员    is_superuser=True, institution_id=NULL
Layer 2  机构管理员    institution_role='owner'
Layer 3  老师         institution_role='teacher'
Layer 4  学生         institution_role='student'（或无机构）
```

每层是上一层的**真子集**：学生能用的老师都能用，老师能用的机构管理员都能用，机构管理员能用的超管都能用。

### 1.2 方案层级

方案由机构决定（`Institution.plan`），通过 `get_effective_plan()` 支持父子机构继承。无机构用户使用 `User.personal_plan`。

| 方案 | 说明 |
|------|------|
| `free` | 免费基础功能 |
| `starter` | 入门版 |
| `growth` | 成长版 |
| `enterprise` | 企业版（超管等同此方案） |

统一获取用户生效方案：`get_effective_plan_for_user(user)`

---

## 二、用户模型

### 2.1 User 核心字段（`backend/users/models.py`）

```
is_superuser      : boolean                        （Layer 1：平台超管）
role              : 'student' | 'admin'           （平台角色，默认 student）
is_member         : boolean                        （是否已激活会员）
personal_plan     : 'free' | 'starter' | 'growth' | 'enterprise' （无机构用户的个人方案）
membership_tier   : 同上（已弃用，过渡期保留）
institution       : FK → Institution               （所属机构，超管强制为 null）
institution_role  : 'owner' | 'teacher' | 'student'  （机构内角色，默认 student）
```

### 2.2 四层角色检测

| 属性 | 后端 helper | 前端 |
|------|-----------|------|
| Layer 1 超管 | `is_platform_admin(user)` | `user.is_admin === true` |
| Layer 2 机构所有者 | `is_institution_owner(user)` | `user.is_institution_owner === true` |
| Layer 3 教师 | `is_institution_teacher(user)` | `user.is_institution_teacher === true` |
| Layer 4 学生 | `institution_role == 'student'` | `user.institution_role === 'student'` |

### 2.3 save() 自动规则

```
is_superuser → role='admin', institution=None, institution_role='', is_staff=True, is_member=True
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
| `IsMember` | `is_member_or_admin()`（含会员过期检查） | 知识图谱、热力图、AI 对话 |
| `IsAdminWriteMemberRead` | 读=会员/管理员，写=平台/机构管理员 | 知识点、文章 |
| `HasPlanFeature` | `view.required_feature` 在机构功能列表中 | AI 出题、面试模拟 |
| `HasQuota` | 通用配额检查，`view.quota_resource` 指定资源类型；平台/机构管理员豁免 | 课程/题目/知识点/文章/AI出题/AI调用/PDF模考/面试/对话 |

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

# 功能+配额：方案检查 + 通用配额
permission_classes = [HasPlanFeature, HasQuota]
required_feature = 'ai.generate'
quota_resource = 'ai_question'

# 总量型配额（课程/题目/知识点/文章）：仅需 HasQuota
permission_classes = [IsAdmin, HasQuota]
quota_resource = 'course'

# 功能+会员+配额：会员检查 + 方案检查 + 配额消耗
permission_classes = [IsMember, HasPlanFeature, HasQuota]
required_feature = 'ai.generate'
quota_resource = 'ai_question'
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
| `GET /users/institution/me/` | IsInstitutionAdmin + IsInstitutionActive |
| `GET /users/institutions/overview/` | IsPlatformAdmin |
| `PATCH /users/institution/me/update/` | IsInstitutionOwner + IsInstitutionActive |
| `POST /users/institutions/create/` | IsAuthenticated |
| `POST /users/institution/join-by-slug/` | IsAuthenticated |
| `POST /users/institution/join-by-invite-slug/` | IsAuthenticated |
| `GET /users/join/:slug/` | AllowAny（公开重定向） |
| `GET /api/users/institution/:slug/public/` | AllowAny |

### 5.2 题库（quizzes/）

| 端点 | 权限 |
|------|------|
| `GET /quizzes/questions/` | IsMember（读），IsAdmin（写） |
| `POST/PATCH/DELETE /quizzes/questions/:id/` | IsAdmin |
| `GET/POST /quizzes/knowledge-points/` | IsAdminWriteMemberRead |
| `POST /quizzes/knowledge-points/generate-bulk/` | HasPlanFeature('ai.generate') + HasQuota('ai_question') |
| `POST /quizzes/knowledge-points/import-md/` | IsAdmin OR IsInstitutionAdmin |
| `GET /quizzes/knowledge-points/subjects/` | 公开（无权限） |
| `GET /quizzes/exams/` | IsMember |
| `POST /quizzes/exams/` | IsAdmin |
| `GET /quizzes/graph/heatmap/` | IsMember |
| `GET /quizzes/favorites/` | IsMember |
| `GET /quizzes/wrong-questions/` | IsMember |
| `GET /quizzes/ai/preview/` | HasPlanFeature('ai.generate') + HasQuota('ai_question') |
| `POST /quizzes/ai/pipeline/` | HasPlanFeature('ai.generate') + HasQuota('ai_question') |
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
| ai_assistant | AI 对话 | IsMember + HasQuota('ai_call_total') |
| ai_assistant | 结构化记忆 CRUD | IsMember（仅操作自己的记忆） |
| ai_assistant | 语义记忆 GET/DELETE | IsMember（含所有权验证） |
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

所有涉及多机构数据的视图统一使用 `_apply_institution_filter` 函数（`courses/views.py`、`articles/views.py` 各有一份）：

```python
def _apply_institution_filter(qs, user, request=None):
    """按机构过滤查询集。支持 preview_institution 参数覆盖超管权限。"""
    preview_inst_id = None
    if request:
        preview_inst_id = request.query_params.get('preview_institution')
    if preview_inst_id:
        return qs.filter(Q(institution_id=preview_inst_id) | Q(institution__isnull=True))
    if is_platform_admin(user):
        return qs
    inst = getattr(user, 'institution', None)
    if inst:
        return qs.filter(Q(institution=inst) | Q(institution__isnull=True))
    return qs.filter(institution__isnull=True)
```

**调用方式**：
```python
def get_queryset(self):
    return _apply_institution_filter(Model.objects.all(), self.request.user, self.request)
```

**过滤逻辑**：
- `preview_institution` 参数：超管预览模式下，只看指定机构数据
- 平台管理员（无 preview 参数）：看到全局数据
- 机构用户：看到本机构数据 + 全局数据（`institution__isnull=True`）
- 无机构用户：只看到全局数据

**超管预览模式**：前端进入预览时自动给所有 API 请求附加 `?preview_institution=<id>`，后端识别后覆盖超管的"看全部"逻辑。前端实现在 `api.ts` 的 request interceptor + `useInstitutionStore` 的 `setPreviewInstitutionId`。

**已覆盖的数据模型**：Course、Album、StartupMaterial、CourseTag、Article。新增带 `institution` 字段的模型必须接入此函数。

### 7.1.1 服务层同样需要隔离

视图层的 queryset 过滤只覆盖 API 入口。**服务层代码**（QuestionGenerator、AdversarialPipeline、DiagnosticService、MemorixScheduler 等）如果直接查询 Question / KnowledgePoint，也必须加同样的 `Q(institution=inst) | Q(institution__isnull=True)` 过滤，否则会出现：视图层正确隔离但服务层全局抽题的不一致。

**规则**：任何在服务层查询 Question 或 KnowledgePoint 的地方，如果调用方能拿到 `institution`，查询时必须加机构过滤。

### 7.2 前端 FeatureGuard

```typescript
// FeatureGuard.tsx
if (loading) return <Spinner />
if (hasFeature(feature)) return children
return <Navigate to="/" replace />
```

---

## 7.5 Agent 工具权限沙箱

Agent 的可用工具集按机构方案（plan）过滤，低方案用户无法调用高级工具。

**文件**：`ai_engine/tool_permissions.py`

**调用链**：`chat_service.py` → `filter_tools(bot_type, institution, tools)` → 过滤后的工具列表

| Plan | assistant | planner | exam_generator |
|------|-----------|---------|----------------|
| free | search_knowledge_tree, get_user_weak_points | get_learning_stats, get_knowledge_mastery_map, get_due_reviews, search_knowledge_tree | 不可用 |
| starter | + get_user_wrong_questions, search_courses | get_learning_stats, get_knowledge_mastery_map, get_due_reviews | search_knowledge_points, generate_questions |
| growth | 全部 | 全部 | 全部 |
| enterprise | 全部 | 全部 | 全部 |

**数据隔离补充**：Agent 记忆（mem0 语义记忆）在 pgvector 层面按机构隔离（`inst_{id}` collection），用户层通过 mem0 的 `user_id` 参数过滤。

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
直接注册（/register）→ OnboardingDialog 角色选择
  │
  ├─ 选"学生" → 提示"联系老师获取邀请链接"，账号保留但无法进入系统
  │
  ├─ 选"教师/机构主" → 输入方案邀请码 → InstitutionCreateView → institution_role=owner
  │
  └─ 平台超管：Django createsuperuser → is_superuser → role=admin, is_member=True

邀请链接（/join/:invite_slug）
  │
  ├─ 未登录 → 跳 /register?institution=<invite_slug> → 注册 → 登录 → 自动绑定机构
  │
  └─ 已登录（裸号）→ InstitutionJoinByInviteSlugView → 直接绑定机构，institution_role=student
```

**规则：**
- 学生进入机构的唯一路径是邀请链接（`/join/:invite_slug`）
- 邀请链接支持绑定已有账号——已登录裸号用户点击链接直接加入，无需重新注册
- 教师通过 OnboardingDialog 创建机构成为 owner，需要方案邀请码
- 机构内所有人自动 `is_member = True`，`membership_tier = inst.plan`
- 平台管理员（无机构）看到所有功能（等同于 pro）
- `institution_invite` cookie 机制是死代码（从未写入），实际依赖 URL query 参数

---

## 十、审计发现 & 修复记录（2026-05-21）

### 10.1 已修复

| # | 问题 | 严重性 | 修复 |
|---|------|--------|------|
| 1 | **重复 IsMember 类缺少过期检查** — `users/views.py:28` 的 `IsMember` 只检查 `is_member` 布尔值，不检查 `membership_expires_at`。46+ 视图（quizzes/views_exam, views_memorix, views_question, courses, ai_assistant, faq_system, study_room, interviews, articles）使用此重复类，绕过会员过期控制 | **关键** | `IsMember.has_permission` 改为委托给 `is_member_or_admin()`，一次性修复所有 46+ 视图 |
| 2 | **articles 重复权限类** — `articles/views.py:9` 的 `IsAdminUserOrReadOnly` 写检查用 `is_staff`（仅超级管理员），导致机构管理员无法写文章。与 `permissions.py` 的 `IsAdminWriteMemberRead` 功能重复 | **中** | 删除局部类，统一使用 `IsAdminWriteMemberRead`。同时修复了机构管理员文章写入权限 |
| 3 | **学生看到侧边栏锁和升级弹窗** — 机构学生在低方案机构中看到带锁图标的功能入口，点击弹出 UpgradeModal。学生不应关心方案升级 | **中** | `isInstStudent` 修正为 `Boolean(instInfo) && role==='student'`；sidebar/mobileNav 对学生过滤未解锁项；UpgradeModal 加 `!isInstStudent` 守卫 |
| 4 | ~~**邀请链接默认学生**~~ | **已重构 (2026-05-29)** | OnboardingDialog 增加角色分流（学生/教师），学生被引导走邀请链接；`/join/:invite_slug` 支持已登录裸号直接绑定机构（`InstitutionJoinByInviteSlugView`） |
| 5 | **教师受学生数上限限制** — `InstitutionJoinBySlugView` 的学生数上限检查对教师也生效 | **低** | 学生数上限仅对 `role='student'` 生效 |
| 6 | **激活会员按钮/弹窗冗余** — 用户通过邀请链接注册后自动 `is_member=True`，不再需要激活码激活。MainLayout 中「激活会员」菜单项和弹窗成为死代码 | **低** | 删除 `showActivateDialog`/`activationCode`/`isActivating` 状态、`handleActivate` 函数、桌面+移动端菜单项、激活码 Dialog 组件及不再使用的 import（`Loader2`, `Dialog*`, `Input`, `Label`） |
| 7 | **lib/authz.ts isAdminUser 死代码** — 该函数仅在 PdfMockExam.tsx 一处使用，逻辑与 RequireAdmin 守卫重复 | **低** | 逻辑内联到 PdfMockExam.tsx（`user?.is_admin \|\| user?.is_institution_admin \|\| user?.role === 'admin'`），删除 `authz.ts` |
| 8 | **InstitutionDashboardView 内联 RBAC** — 单视图混合平台管理员/机构管理员/其他三种角色逻辑，`permission_classes=[IsAuthenticated]` 太宽 | **低** | 拆分为两个视图：`PlatformAdminInstitutionOverviewView`（`/institutions/overview/`, `IsPlatformAdmin`）和收紧后的 `InstitutionDashboardView`（`/institution/me/`, `IsInstitutionAdmin + IsInstitutionActive`）。前端 `InstitutionDashboard.tsx` 根据 `isPlatformAdmin && !institution` 选择端点 |

### 10.2 已知但未修复

| # | 问题 | 原因/优先级 |
|---|------|-----------|
| 1 | FeatureGuard 竞态 — `fetchFeatures()` 异步，FeatureGuard 可能在 features 加载前渲染导致错误的 `/` 重定向 | 低概率，RequireAuth 的 loading 状态通常覆盖此窗口 |
| 2 | Prompt 模板（IsPlatformAdmin）vs Pipeline 管理（IsAdmin）权限不一致 | 设计决策：模板全局，pipeline 可机构级 |
| 3 | courses 启动材料/专辑 GET 用 AllowAny | 可能是故意的——公开课程目录 |
| 4 | ~~`permissions.IsMemberOrAdmin` 仅在 `graph_views.py` 使用——与 `users.views.IsMember` 功能重复~~ | **已修复 (2026-05-23)**：统一为 `permissions.IsMember`，`users.views.IsMember` 改为 re-export |

---

## 十一、开发规范

### 11.1 新增后端视图时

1. **权限类从 `users.permissions` 引用**，不要在 app 内定义局部权限类
2. **禁止内联权限检查**：所有 `institution_role in (...)` 判断必须通过 helper 函数或权限类实现
3. 四层权限选择指南：
   - Layer 1（超管）：`IsPlatformAdmin`
   - Layer 2（机构所有者）：`IsInstitutionOwner`
   - Layer 3（教师+所有者）：`IsInstitutionTeacher` 或 `IsInstitutionAdmin`
   - Layer 4（学生/会员）：`IsMember`（含会员过期检查）
4. 机构管理数据必须组合 `IsInstitutionActive`（检查机构启用+方案未到期）
5. 功能门控用 `HasPlanFeature` + `view.required_feature`（基于 `get_effective_plan_for_user`）
6. 消耗性/配额型接口用 `HasQuota` + `view.quota_resource`
7. queryset 必须做机构数据隔离（见第七节模式）

### 11.2 新增前端路由时

1. 在 `App.tsx` 注册路由
2. 如有功能门控，包裹 `FeatureGuard(feature)`
3. 如有管理权限要求，包裹对应的 `Require*` 守卫
4. 侧边栏入口在 `MainLayout.tsx` 的 `navItems` 中添加，标注 `minPlan`（如果有方案要求）

### 11.3 侧边栏规则

- 对学生：`minPlan` 不满足的项**直接隐藏**（不显示锁图标，不触发升级）
- 对教师/owner：`minPlan` 不满足的项显示锁图标，点击唤起 UpgradeModal
- 机构管理菜单项（成员管理、维护）仅 `is_institution_admin` 可见
