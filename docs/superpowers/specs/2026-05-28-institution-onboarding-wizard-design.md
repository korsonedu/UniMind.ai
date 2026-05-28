# 机构主首次注册引导设计

**日期**: 2026-05-28
**状态**: 已批准
**范围**: 替换现有 `OnboardingDialog` 为卡片式引导 wizard

## 背景

现有 `OnboardingDialog` 是一个传统模态表单（邀请码 → 机构信息 → 选科目 → 完成），体验较为局促。需要改为卡片式引导，每张卡片一个问题，渐隐切换，提升首次注册体验。

## 设计决策

- **形式**: 替换现有 OnboardingDialog 组件（保持弹窗形式，内部改为卡片式）
- **触发条件**: 不变 — 用户已登录、无机构、非平台管理员
- **已有机构用户**: 不受影响

## 引导流程（5 张卡片）

| # | 卡片 | 输入类型 | 必填 | 说明 |
|---|------|---------|------|------|
| 1 | 邀请码 | 文本输入 | 是 | 验证 PlanInviteCode，通过后解锁后续卡片 |
| 2 | 机构名称 | 文本输入 | 是 | 对应 Institution.name |
| 3 | 业务规模 | 选项卡片 | 是 | 4 个预设选项：1-50 / 50-200 / 200-500 / 500+ |
| 4 | 主讲科目 | DirectionSelector | 是 | 复用现有组件，预设科目 + 自定义输入 |
| 5 | 机构简介 | 多行文本 | 否 | 可跳过，对应 Institution.description |

### 交互流程

1. 卡片 1 默认展示，输入邀请码 → 点"下一步" → 验证通过 → 卡片 1 渐隐
2. 卡片 2 浮现 → 填名称 → 点"下一步" → 渐隐
3. 卡片 3 浮现 → 点选规模 → 立即渐隐
4. 卡片 4 浮现 → 选科目 → 点"下一步"
5. 卡片 5 浮现 → 填描述或点"跳过"
6. 调用 `POST /users/institutions/create/` 创建机构
7. 成功提示 → `window.location.reload()`

### 每张卡片引导文案

- 卡片 1: "欢迎使用 UniMind！请输入您的邀请码开始创建机构"
- 卡片 2: "给你的机构起个名字吧"
- 卡片 3: "你的机构目前有多少学生？"
- 卡片 4: "你主要教哪些科目？"
- 卡片 5: "简单介绍一下你的机构（可选）"

## 视觉设计

### 弹窗

- 使用 shadcn/ui Dialog 组件
- 内容区: `max-w-lg`，最小高度 400px
- 去掉右上角 X 关闭按钮（引导不应被轻易跳过）
- 底部: 进度指示器（5 个小圆点） + "下一步" / "完成" 按钮

### 卡片动画

- 退出: `opacity: 0, translateY: -20px`，300ms ease-out
- 进入: 从 `opacity: 0, translateY: 20px` 到 `opacity: 1, translateY: 0`，300ms ease-in
- 切换时先退出、等 300ms、再进入（错开动画）
- 使用 CSS transition 实现，不引入额外动画库

### 进度指示

- 底部 5 个小圆点
- 当前步骤: 高亮实心
- 已完成: 实心
- 未完成: 空心

## 后端改动

### Institution model 新增字段

```python
# backend/users/models.py
student_scale = models.CharField(
    max_length=20,
    choices=[
        ('1-50', '1-50 人'),
        ('50-200', '50-200 人'),
        ('200-500', '200-500 人'),
        ('500+', '500+ 人'),
    ],
    blank=True,
    default='',
)
```

### API 改动

复用现有 `POST /users/institutions/create/` 端点，新增接收 `student_scale` 字段。

### Migration

`python manage.py makemigrations` 自动生成。

## 文件改动清单

| 文件 | 改动类型 | 说明 |
|------|---------|------|
| `backend/users/models.py` | 修改 | Institution 新增 `student_scale` 字段 |
| `backend/users/serializers.py` | 修改 | InstitutionSerializer 加 `student_scale` |
| `backend/users/views_institution.py` | 修改 | 创建时接收并保存 `student_scale` |
| `backend/users/migrations/XXXX_*.py` | 新增 | 自动生成的 migration |
| `frontend/src/components/OnboardingDialog.tsx` | 重写 | 卡片式引导 wizard |

## 不做的事

- 不新增 API 端点
- 不改 DirectionSelector 组件
- 不改路由
- 不新增 `onboarding_completed` 字段（已有机构 = 已完成引导）
- 不加联系电话、Logo 等额外步骤
