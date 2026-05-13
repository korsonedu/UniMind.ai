# Superuser 人员管理与 RBAC 权限系统 (RBAC User Management)

## 1. 背景与动机
随着系统逐渐成熟，单一的 `is_superuser` 无法满足后续业务的发展。
系统需要区分：只做题的学生、可以上传题目的兼职教研员、能够审核 AI 题目的专家，以及掌握系统最高权限的管理员。
我们需要引入 **基于角色的访问控制 (Role-Based Access Control, RBAC)**，并为用户画像打标签，以便于后续的个性化推荐。

## 2. 角色体系划分 (Role Hierarchy)

我们将系统内的用户身份划分为以下几个梯队：

1. **System Admin (系统管理员)**：
   - 拥有最高权限，可访问 Django Admin，配置 Prompt 模板，调整 FSRS 全局参数。
2. **Content Reviewer (教研审核员)**：
   - 核心职责：拦截 AI。在 AI 多智能体管线生成的题目入库（进入公开池）之前，如果遇到高难度或争议题目，需经 Reviewer 人工点一次“发布”。
3. **Content Creator (内容贡献者)**：
   - 拥有上传文档、批量导入真题、发起“AI OCR 一键录题”任务的权限。
4. **Student / Standard User (普通学生)**：
   - 只能消费内容（做题、看课、查看自己的图谱与 FSRS 状态）。

## 3. 用户标签与画像体系 (User Tagging & Profiling)

权限是硬限制，而标签是软推荐。为了实现第 1、2 点的个性化，我们需要一套标签系统。

### 3.1 动态标签设计 (Dynamic Tags)
在 `User` 模型之外，建立 `UserTag` 关联表：
- **静态标签 (手动/注册录入)**：如 `跨考生`、`二战`、`目标院校: 清华`。
- **动态标签 (系统自动打标)**：如 `微观薄弱`、`计算题杀手`、`夜猫子学习者`。

### 3.2 标签与业务的联动逻辑
- **FSRS 联动**：不同的静态标签（如跨考生 vs 本专业）在首次注册时，分配不同的 FSRS 初始化默认权重（跨考生初始遗忘率更高）。
- **组队与排行榜**：为相同标签的用户建立竞争小组（如“跨考生 431 冲刺营”）。

## 4. 架构落地设计 (Implementation Architecture)

### 4.1 扩展 Django Auth
使用 Django 内置的 `Group` 和 `Permission` 框架，尽量不造轮子。
```python
# 扩展默认 User 模型 (如果尚未扩展)
class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    student_type = models.CharField(choices=[('cross_major', '跨考'), ('same_major', '本专业')])
    target_university = models.CharField(max_length=100, blank=True)
    tags = models.ManyToManyField(UserTag, blank=True)
    # 结合点 1：记录 FSRS 独立配置
    # 结合点 2：记录图谱历史掌握度
```

### 4.2 API 中间件拦截
在 DRF (Django REST Framework) 层面，编写自定义的 Permission 类：
```python
class IsContentReviewer(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user.groups.filter(name='Content Reviewer').exists()
```

## 5. 后续 AI 编码指南 (For AI Assistant)
- **解耦操作**：不要直接修改 Django 的原生 `User` 模型（如果项目已经在运行），使用 `UserProfile` (OneToOne) 是更安全、兼容性更好的基建方式。
- **Admin 界面改造**：编写 `admin.py` 时，提供一个直观的界面，允许管理员在一个页面内为用户分配 Group，并手动添加 Tags。
