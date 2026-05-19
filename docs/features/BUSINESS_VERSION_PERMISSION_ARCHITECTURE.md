# UniMind.ai B 端多租户 + 版本权限控制架构

## 一、核心架构概览

```
┌─────────────────────────────────────────────────────────┐
│                   Super Admin（我们）                      │
│          is_superuser=True, institution=NULL              │
│                                                          │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐              │
│  │ 机构 A    │  │ 机构 B    │  │ 机构 C    │   ...        │
│  │ Pro 版   │  │ Plus 版  │  │ Basic 版 │              │
│  │ 到期:12月 │  │ 到期:9月  │  │ 到期:6月  │              │
│  │ 5个管理员 │  │ 2个管理员 │  │ 1个管理员 │              │
│  │          │  │          │  │          │              │
│  │ 200学生  │  │ 80学生   │  │ 30学生   │              │
│  └──────────┘  └──────────┘  └──────────┘              │
│       ↑ 不能跨机构访问         ↑ 不能跨机构访问             │
└─────────────────────────────────────────────────────────┘
```

**三条铁律：**

1. **Super Admin 控制机构** — 创建、禁用、改版本、改到期时间
2. **机构管理员控制学生** — 学生在机构内封闭管理，不可跨机构
3. **版本控制功能入口** — 学生看到的所有功能由机构当前版本决定

---

## 二、数据模型设计

### 2.1 新增模型：Institution（机构 / 租户）

```python
# backend/users/models.py — 新增

class Institution(models.Model):
    """B 端购买方机构"""
    name = models.CharField(max_length=200, verbose_name="机构名称")
    slug = models.SlugField(max_length=100, unique=True, verbose_name="机构标识")
    contact_name = models.CharField(max_length=100, verbose_name="联系人")
    contact_email = models.EmailField(verbose_name="联系邮箱")
    contact_phone = models.CharField(max_length=20, blank=True, verbose_name="联系电话")

    # 版本与计费
    plan = models.CharField(
        max_length=20,
        choices=[('free', 'Basic'), ('plus', 'Plus'), ('pro', 'Pro')],
        default='free',
        verbose_name="当前版本"
    )
    plan_expires_at = models.DateTimeField(null=True, blank=True, verbose_name="版本到期时间")
    max_students_override = models.IntegerField(null=True, blank=True, verbose_name="学员上限（覆写）")

    # 状态
    is_active = models.BooleanField(default=True, verbose_name="是否启用")

    # 品牌
    custom_domain = models.CharField(max_length=200, blank=True, verbose_name="自定义域名")
    logo = models.ImageField(upload_to='institution_logos/', blank=True, verbose_name="机构Logo")

    # 元信息
    notes = models.TextField(blank=True, verbose_name="管理员备注")
    created_by = models.ForeignKey(
        'User', on_delete=models.SET_NULL, null=True,
        related_name='created_institutions', verbose_name="创建人"
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    class Meta:
        verbose_name = "机构"
        verbose_name_plural = "机构"
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.name} ({self.get_plan_display()})"

    @property
    def max_students(self):
        """有效学员上限"""
        if self.max_students_override is not None:
            return self.max_students_override
        return PLAN_STUDENT_LIMITS.get(self.plan, 50)

    @property
    def student_count(self):
        return self.students.filter(institution_role='student').count()

    @property
    def is_plan_active(self):
        if self.plan_expires_at is None:
            return True
        return self.plan_expires_at > timezone.now()
```

### 2.2 修改 User 模型 — 关联机构

```python
# backend/users/models.py — 在现有 User 模型中增加以下字段

class User(AbstractUser):
    # ... 现有字段保持不变 ...

    # === 新增：B 端多租户字段 ===
    institution = models.ForeignKey(
        'Institution',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='students',
        verbose_name="所属机构"
    )
    institution_role = models.CharField(
        max_length=20,
        choices=[('owner', '机构所有者'), ('teacher', '教师'), ('student', '学员')],
        default='student',
        verbose_name="机构内角色"
    )

    @property
    def is_institution_admin(self):
        """机构管理员（owner 或 teacher）"""
        return self.institution is not None and self.institution_role in ('owner', 'teacher')

    @property
    def is_institution_owner(self):
        """机构所有者（仅 owner）"""
        return self.institution is not None and self.institution_role == 'owner'

    @property
    def is_platform_admin(self):
        """平台级管理员（我们）"""
        return self.is_superuser and self.institution_id is None
```

### 2.3 版本功能标志映射（硬编码配置）

```python
# backend/users/plan_features.py

PLAN_STUDENT_LIMITS = {
    'free': 50,
    'plus': 200,
    'pro': 9999,  # 不限
}

PLAN_FEATURES = {
    'free': [
        'quiz.manual',         # 手动题库管理
        'quiz.exam',           # 基础组卷考试
        'student.management',  # 学员管理
        'basic.stats',         # 基础数据统计
    ],
    'plus': [
        'quiz.manual',
        'quiz.exam',
        'student.management',
        'basic.stats',
        'course.management',   # 课程视频管理
        'knowledge.graph',     # 知识图谱
        'video.outline',       # AI 视频大纲打点
        'faq.system',          # 在线答疑
    ],
    'pro': [
        'quiz.manual',
        'quiz.exam',
        'student.management',
        'basic.stats',
        'course.management',
        'knowledge.graph',
        'video.outline',
        'faq.system',
        'study.room',          # 实时学习房间
        'ai.question_gen',     # AI 智能出题
        'memorix.adaptive',    # Memorix 自适应复习
        'analytics.dashboard', # 高级学情看板
        'api.access',          # API/白标对接
    ],
}

def get_plan_features(plan: str) -> list[str]:
    return PLAN_FEATURES.get(plan, PLAN_FEATURES['free'])

def has_feature(institution, feature: str) -> bool:
    """检查机构是否有某个功能"""
    if institution is None:
        return False
    if not institution.is_active or not institution.is_plan_active:
        return False
    return feature in get_plan_features(institution.plan)
```

### 2.4 权限层级总结

```
                     ┌──────────────────┐
                     │  Platform Admin   │  is_superuser=True, institution=NULL
                     │  （我们）          │  能看所有机构、所有学生、所有数据
                     └────────┬─────────┘
                              │ 管理
              ┌───────────────┼───────────────┐
              ▼               ▼               ▼
     ┌────────────┐  ┌────────────┐  ┌────────────┐
     │ Institution│  │ Institution│  │ Institution│
     │   Owner    │  │   Owner    │  │   Owner    │
     │ role=owner │  │ role=owner │  │ role=owner │
     └─────┬──────┘  └─────┬──────┘  └─────┬──────┘
           │               │               │
     ┌─────┴──────┐        │               │
     ▼            ▼        ▼               ▼
  教师(teacher) 教师    教师(teacher)    ...
     │
     ├─ 管理学员（增删改查）
     ├─ 管理内容（题库、课程）
     └─ 不可：管教师、改机构设置
           │
     ┌─────┼──────┐
     ▼     ▼      ▼
   学生A  学生B  学生C
  role=   role=   role=
  student student student
```

---

## 三、后端权限控制实现

### 3.1 DRF 权限类

```python
# backend/users/permissions.py — 新增以下类

from rest_framework import permissions
from users.plan_features import has_feature

class IsPlatformAdmin(permissions.BasePermission):
    """平台管理员（is_superuser），已有，保持不变"""
    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated and request.user.is_platform_admin


class IsInstitutionAdmin(permissions.BasePermission):
    """机构管理员（owner 或 teacher）—— 可管理学生和内容"""
    def has_permission(self, request, view):
        user = request.user
        return (user and user.is_authenticated
                and user.institution is not None
                and user.institution_role in ('owner', 'teacher'))


class IsInstitutionOwner(permissions.BasePermission):
    """机构所有者（仅 owner）—— 可改机构设置、管理教师"""
    def has_permission(self, request, view):
        user = request.user
        return (user and user.is_authenticated
                and user.institution is not None
                and user.institution_role == 'owner')


class IsInstitutionActive(permissions.BasePermission):
    """所在机构有效（已启用 + 版本未到期）"""
    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if user.is_platform_admin:
            return True
        inst = user.institution
        if inst is None:
            return False
        return inst.is_active and inst.is_plan_active


class HasPlanFeature(permissions.BasePermission):
    """
    检查用户所在机构是否具备指定功能标志。
    用法：
        class AIQuestionGenerateView(APIView):
            permission_classes = [IsAuthenticated, IsInstitutionActive, HasPlanFeature]
            required_feature = 'ai.question_gen'
    """
    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if user.is_platform_admin:
            return True
        required = getattr(view, 'required_feature', None)
        if required is None:
            return True
        return has_feature(user.institution, required)


class IsInstitutionMember(permissions.BasePermission):
    """属于某个机构的成员（学生或管理员）"""
    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated and request.user.institution is not None
```

### 3.2 View 使用示例

```python
# backend/quizzes/views_ai.py — 修改示例

class AIQuestionGenerateView(APIView):
    permission_classes = [IsAuthenticated, IsInstitutionActive, HasPlanFeature]
    required_feature = 'ai.question_gen'  # 被 HasPlanFeature 读取

    def post(self, request):
        # 只有 Pro 版机构能走到这里
        ...
```

### 3.3 API 端点设计

#### Super Admin 端点（管理所有机构）

```python
# backend/users/urls.py — 实际路由（摘录关键端点）

urlpatterns = [
    # ... 现有路由 ...

    # === Super Admin：机构 CRUD ===
    path('institutions/', InstitutionListView.as_view()),              # GET 列表 / POST 创建
    path('institutions/<int:pk>/', InstitutionDetailView.as_view()),   # GET/PUT/DELETE
    path('institutions/<int:pk>/activate/', ...),
    path('institutions/<int:pk>/deactivate/', ...),
    path('institutions/<int:pk>/change-plan/', ...),
    path('institutions/<int:pk>/preview/', ...),                       # 超管预览机构

    # === Super Admin：全局用户 & 权限管理 ===
    path('admin/superusers/users/', ...),         # GET 列表 / PATCH 编辑
    path('admin/user-tags/', ...),                # GET 列表 / POST 创建
    path('admin/permission-groups/', ...),        # GET 列表 / POST 创建

    # === 机构管理员（owner / teacher）：学员管理 ===
    path('institution/me/students/', ...),           # GET 列表 / POST 创建/批量导入
    path('institution/me/students/<int:pk>/', ...),  # GET 详情 / DELETE 移除
    path('institution/me/students/<int:pk>/stats/', ...),   # GET 学习统计
    path('institution/me/students/<int:pk>/reset-password/', ...),

    # === 机构成员管理（owner / teacher） ===
    path('institution/me/members/', ...),                # GET 所有成员（教师+学员）
    path('institution/me/members/<int:pk>/role/', ...),  # PATCH 切换角色（仅 owner）

    # === 机构自服务 ===
    path('institution/me/', ...),                    # GET 仪表盘
    path('institution/me/update/', ...),             # GET/PUT 机构设置（仅 owner）
    path('institution/me/features/', ...),           # GET 功能列表
    path('institution/me/regenerate-invite-slug/', ...),  # POST（仅 owner）
]
```

#### 关键 View 实现骨架

```python
# backend/users/views_institution.py

class InstitutionListView(APIView):
    """Super Admin: 机构列表 + 创建"""
    permission_classes = [IsAuthenticated, IsPlatformAdmin]

    def get(self, request):
        qs = Institution.objects.all().prefetch_related('students')
        # 支持 ?search= & ?plan= & ?is_active=
        serializer = InstitutionSerializer(qs, many=True)
        return Response(serializer.data)

    def post(self, request):
        serializer = CreateInstitutionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        institution = serializer.save(created_by=request.user)
        return Response(InstitutionSerializer(institution).data, status=201)


class InstitutionFeatureView(APIView):
    """返回当前用户所属机构的功能列表 + 元信息"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        inst = request.user.institution
        if inst is None:
            # 平台管理员：返回全部功能
            return Response({
                'is_platform_admin': True,
                'institution': None,
                'features': list(PLAN_FEATURES['pro']),
            })
        return Response({
            'is_platform_admin': False,
            'institution': {
                'id': inst.id,
                'name': inst.name,
                'plan': inst.plan,
                'plan_label': inst.get_plan_display(),
                'plan_expires_at': inst.plan_expires_at,
                'is_active': inst.is_active,
                'is_plan_active': inst.is_plan_active,
                'max_students': inst.max_students,
                'student_count': inst.student_count,
            },
            'features': get_plan_features(inst.plan),
        })
```

---

## 四、前端权限控制实现

### 4.1 版本功能 Zustand Store

```typescript
// frontend/src/store/useInstitutionStore.ts — 新文件

import { create } from 'zustand';
import api from '@/lib/api';

interface InstitutionInfo {
  id: number;
  name: string;
  plan: 'free' | 'plus' | 'pro';
  plan_label: string;
  plan_expires_at: string | null;
  is_active: boolean;
  is_plan_active: boolean;
  max_students: number;
  student_count: number;
}

interface InstitutionState {
  isPlatformAdmin: boolean;
  institution: InstitutionInfo | null;
  features: string[];
  loading: boolean;

  fetchFeatures: () => Promise<void>;
  hasFeature: (feature: string) => boolean;
  hasAnyFeature: (...features: string[]) => boolean;
  clear: () => void;
}

export const useInstitutionStore = create<InstitutionState>((set, get) => ({
  isPlatformAdmin: false,
  institution: null,
  features: [],
  loading: false,

  fetchFeatures: async () => {
    set({ loading: true });
    try {
      const { data } = await api.get('/institution/me/features/');
      set({
        isPlatformAdmin: data.is_platform_admin,
        institution: data.institution,
        features: data.features,
        loading: false,
      });
    } catch {
      set({ loading: false });
    }
  },

  hasFeature: (feature: string) => {
    const { isPlatformAdmin, features } = get();
    if (isPlatformAdmin) return true;
    return features.includes(feature);
  },

  hasAnyFeature: (...features: string[]) => {
    return features.some(f => get().hasFeature(f));
  },

  clear: () => set({
    isPlatformAdmin: false,
    institution: null,
    features: [],
    loading: false,
  }),
}));
```

### 4.2 登录后自动拉取

```typescript
// frontend/src/store/useAuthStore.ts — 在 setAuth 之后调用

import { useInstitutionStore } from './useInstitutionStore';

// 在 Login 页面 or useAuthStore.setAuth 中：
setAuth(user, token);
// 立即拉取机构功能列表
useInstitutionStore.getState().fetchFeatures();
```

### 4.3 侧边栏 — 全部入口可见 + 置灰锁定

```tsx
// frontend/src/layouts/MainLayout.tsx — 侧边栏改造思路

import { useInstitutionStore } from '@/store/useInstitutionStore';
import { Lock } from 'lucide-react';

// 导航项定义增加 requiredFeature 字段
const navItems = [
  { label: '题库管理',   icon: BookOpen,  href: '/quizzes',    requiredFeature: 'quiz.manual' },
  { label: '智能出题',   icon: Sparkles,  href: '/ai-generate', requiredFeature: 'ai.question_gen' },
  { label: '知识图谱',   icon: GitGraph,  href: '/knowledge',   requiredFeature: 'knowledge.graph' },
  { label: '课程管理',   icon: Video,     href: '/courses',     requiredFeature: 'course.management' },
  { label: '视频大纲',   icon: ListVideo, href: '/video-outline',requiredFeature: 'video.outline' },
  { label: '在线答疑',   icon: MessageCircle, href: '/faq',     requiredFeature: 'faq.system' },
  { label: '学习房间',   icon: Users,     href: '/study-room',  requiredFeature: 'study.room' },
  { label: '学情看板',   icon: BarChart3, href: '/analytics',   requiredFeature: 'analytics.dashboard' },
  { label: '学员管理',   icon: GraduationCap, href: '/students',requiredFeature: 'student.management' },
  { label: '系统设置',   icon: Settings,  href: '/settings',    requiredFeature: null }, // 所有人都能看到
];

// 渲染逻辑
function SidebarNav() {
  const { hasFeature, institution } = useInstitutionStore();

  return navItems.map(item => {
    const isAvailable = !item.requiredFeature || hasFeature(item.requiredFeature);

    return (
      <div key={item.href} className="relative group">
        <a
          href={isAvailable ? item.href : '#'}
          className={cn(
            'flex items-center gap-3 px-4 py-2 rounded-lg transition-colors',
            isAvailable
              ? 'hover:bg-blue-50 text-gray-700'
              : 'text-gray-400 cursor-not-allowed opacity-50'
          )}
          onClick={e => {
            if (!isAvailable) {
              e.preventDefault();
              // 弹出升级引导弹窗
              openUpgradeModal(item.requiredFeature);
            }
          }}
        >
          <item.icon size={20} />
          <span>{item.label}</span>
          {!isAvailable && <Lock size={14} className="ml-auto" />}
        </a>

        {/* Hover 提示 */}
        {!isAvailable && (
          <div className="hidden group-hover:block absolute left-full ml-2 top-1/2 -translate-y-1/2
                          bg-gray-800 text-white text-xs px-2 py-1 rounded whitespace-nowrap z-50">
            升级至 {getRequiredPlan(item.requiredFeature)} 版
          </div>
        )}
      </div>
    );
  });
}
```

### 4.4 升级引导弹窗

```tsx
// 点击锁定功能时弹出
function UpgradeModal({ feature, onClose }) {
  const { institution } = useInstitutionStore();
  const requiredPlan = getRequiredPlan(feature);

  return (
    <Dialog open onOpenChange={onClose}>
      <DialogContent>
        <DialogTitle>升级解锁更多功能</DialogTitle>
        <DialogDescription>
          当前版本：<strong>{institution?.plan_label}</strong>。
          此功能需要 <strong>{requiredPlan}</strong> 版本。
        </DialogDescription>
        <div className="flex gap-4 mt-4">
          <Button variant="outline" onClick={onClose}>暂不升级</Button>
          <Button onClick={() => window.location.href = '/pricing'}>
            查看升级方案
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
```

### 4.5 路由守卫

```tsx
// frontend/src/components/FeatureGuard.tsx — 新文件

import { Navigate } from 'react-router-dom';
import { useInstitutionStore } from '@/store/useInstitutionStore';

export function FeatureGuard({ feature, children }: { feature: string; children: React.ReactNode }) {
  const { hasFeature, loading } = useInstitutionStore();

  if (loading) return <div>加载中...</div>;
  if (!hasFeature(feature)) return <Navigate to="/pricing" replace />;
  return <>{children}</>;
}

// 用法：
// <Route path="/ai-generate" element={
//   <FeatureGuard feature="ai.question_gen">
//     <AIGeneratePage />
//   </FeatureGuard>
// } />
```

---

## 五、业务流程

### 5.1 机构上线流程

```
我们（Super Admin）
  │
  ├─ 1. 在管理后台创建 Institution 记录
  │     - 填入机构名称、联系人、选择版本、设置到期日
  │     - 系统自动创建机构管理员账号（或使用已有账号关联）
  │
  ├─ 2. 机构管理员收到账号信息邮件
  │     - 包含登录链接 + 管理员账号密码
  │
  ├─ 3. 机构管理员登录 → 进入机构管理后台
  │     - 可自定义机构名称/Logo
  │     - 创建学员账号（批量导入 or 逐个创建）
  │     - 或生成「机构邀请码」，学员自行注册时填入
  │
  └─ 4. 学员登录 → 看到机构版界面
        - 可使用的功能 = 机构当前版本 ∩ 学员角色权限
        - 学员看不到其他机构的数据
```

### 5.2 机构到期/禁用处理

```
机构到期 or 被禁用
  │
  ├─ 后端：所有该机构 API 请求 → IsInstitutionActive 拒绝 → 403
  │
  ├─ 前端：useInstitutionStore → is_plan_active=false
  │     → 侧边栏所有功能显示锁定
  │     → 页面顶部显示红色横幅："服务已到期，请联系机构管理员续费"
  │
  └─ 学员端：无法使用任何功能，但历史数据保留
        → 续费后自动恢复
```

### 5.3 学生账号创建方式

支持三种方式，机构可自行选择：

| 方式 | 适用场景 | 实现 |
|------|----------|------|
| **管理员批量创建** | 机构统一导入 | POST `/institution/students/` 批量接口 + Excel 导入 |
| **邀请码自助注册** | 开放注册 | 机构后台生成邀请码 → 学生注册页输入 → 自动关联机构 |
| **邀请链接注册** | 微信/朋友圈分发 | `unimind.ai/join/{institution.slug}?code=xxx` → 注册页预填机构 |

---

## 六、Super Admin 管理面板

### 6.1 前端页面：机构管理

```
/ admin / institutions
┌──────────────────────────────────────────────────────┐
│  机构管理                              [+ 新建机构]   │
│                                                      │
│  🔍 搜索...   [全部版本 ▾]  [全部状态 ▾]              │
│                                                      │
│  ┌─────────────────────────────────────────────┐     │
│  │ 机构名称      版本   学员数   到期日    状态   │     │
│  ├─────────────────────────────────────────────┤     │
│  │ 研途考研      Pro   162/∞   2026-12-31  ✅   │     │
│  │ 金程教育      Plus   78/200  2026-09-15  ✅   │     │
│  │ 文都431      Basic  23/50   2026-06-01  ⚠️   │     │
│  │ XX考研机构    Pro     0/∞   -           ⏸️   │     │
│  └─────────────────────────────────────────────┘     │
│                                                      │
│  点击机构 → 进入详情：                                 │
│    - 基本信息（可编辑）                                │
│    - 版本管理（改版本 / 续费 / 改到期日）              │
│    - 管理员列表                                        │
│    - 学员统计（总数 / 活跃 / 新增趋势）                │
│    - 操作日志                                          │
│    - [禁用机构] [删除机构] 按钮                        │
└──────────────────────────────────────────────────────┘
```

### 6.2 关键操作 API

```python
# 改版本
class InstitutionChangePlanView(APIView):
    permission_classes = [IsAuthenticated, IsPlatformAdmin]

    def post(self, request, pk):
        institution = get_object_or_404(Institution, pk=pk)
        new_plan = request.data.get('plan')
        new_expires_at = request.data.get('plan_expires_at')

        if new_plan not in dict(PLAN_CHOICES):
            return Response({'error': '无效的版本'}, status=400)

        old_plan = institution.plan
        institution.plan = new_plan
        if new_expires_at:
            institution.plan_expires_at = new_expires_at
        institution.save()

        # 记录操作日志（可选）
        # InstitutionAuditLog.objects.create(
        #     institution=institution,
        #     operator=request.user,
        #     action='change_plan',
        #     detail=f'{old_plan} → {new_plan}'
        # )
        return Response(InstitutionSerializer(institution).data)


# 禁用/启用
class InstitutionDeactivateView(APIView):
    permission_classes = [IsAuthenticated, IsPlatformAdmin]

    def post(self, request, pk):
        institution = get_object_or_404(Institution, pk=pk)
        institution.is_active = False
        institution.save()
        return Response({'status': 'deactivated'})
```

---

## 七、迁移步骤

### Phase 1：模型 + 后端（预计 2-3 天）

1. 创建 `Institution` 模型 → `python manage.py makemigrations && migrate`
2. User 模型增加 `institution` + `institution_role` 字段 → migration
3. 创建 `users/plan_features.py` 功能标志配置
4. 创建 `users/permissions.py` 新增权限类（IsInstitutionActive, HasPlanFeature, IsInstitutionMember）
5. 创建 `users/views_institution.py` + `users/serializers_institution.py`
6. 创建 `users/urls.py` 新路由
7. 为现有 AI/Pro 功能 View 添加 `HasPlanFeature` + `required_feature`

### Phase 2：前端（预计 2-3 天）

1. 创建 `useInstitutionStore.ts`
2. 改造 `useAuthStore` 登录后自动拉取 feature
3. 改造 `MainLayout.tsx` 侧边栏（全部入口可见 + 锁定态）
4. 创建 `FeatureGuard.tsx` 路由守卫
5. 创建 `UpgradeModal.tsx` 升级引导弹窗
6. 创建 Super Admin 机构管理页面 `/admin/institutions`

### Phase 3：存量数据迁移 + 测试（预计 1 天）

1. 现有用户：`institution=NULL` → 自动成为平台级独立用户（向后兼容）
2. 如需将旧用户归入某机构，用 Django shell 批量迁移
3. 端到端测试：超管创建机构 → 机构管理员登录 → 创建学生 → 学生刷题 → 功能锁定验证

---

## 八、关键设计决策记录

| 决策 | 选择 | 理由 |
|------|------|------|
| 租户隔离方式 | 共享 DB + institution FK | 早期机构少，无需独立数据库；FK 隔离足够 |
| 版本定义方式 | 硬编码配置 `plan_features.py` | 版本少（3个），改配置比改数据库快 |
| 功能入口策略 | 全部可见 + 置灰锁定 | 产品即销售，每次点击都是升级机会 |
| 机构内角色 | owner(全权限) / teacher(学生+内容管理) / student(纯学习) | 三层分级，owner 可把管理权委派给 teacher |
| 学员注册方式 | 管理员创建 + 邀请码 + 邀请链接三模式 | 大机构批量导入，小机构分享链接，微信分发 |
| 到期后数据 | 保留不删，续费恢复 | 降低续费摩擦，不给用户离开理由 |
| 平台管理员 | `is_superuser=True` + `institution=NULL` | 复用 Django 原生机制，降低复杂度 |

---

## 九、数据库迁移 SQL（参考）

```sql
-- 新增 institution 表
CREATE TABLE users_institution (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name VARCHAR(200) NOT NULL,
    slug VARCHAR(100) NOT NULL UNIQUE,
    contact_name VARCHAR(100) NOT NULL,
    contact_email VARCHAR(254) NOT NULL,
    contact_phone VARCHAR(20) NOT NULL DEFAULT '',
    plan VARCHAR(20) NOT NULL DEFAULT 'free',
    plan_expires_at DATETIME NULL,
    max_students_override INTEGER NULL,
    is_active BOOL NOT NULL DEFAULT 1,
    custom_domain VARCHAR(200) NOT NULL DEFAULT '',
    logo VARCHAR(100) NOT NULL DEFAULT '',
    notes TEXT NOT NULL DEFAULT '',
    created_by_id INTEGER NULL REFERENCES users_user(id),
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- User 表增加字段
ALTER TABLE users_user ADD COLUMN institution_id INTEGER NULL REFERENCES users_institution(id);
ALTER TABLE users_user ADD COLUMN institution_role VARCHAR(20) NOT NULL DEFAULT 'student';
```
