# duration_days 改动清单

## 1. 运行迁移
```bash
cd backend
python3 manage.py migrate
```

## 2. models.py — PlanInviteCode 类
找到 `class PlanInviteCode(models.Model):`，在 `plan` 字段下面加一行：
```python
    duration_days = models.IntegerField(default=30, verbose_name='有效天数（0=永久）')
```

然后找到 `validate_and_use` 方法，把返回那行：
```python
return True, obj.plan
```
改成：
```python
return True, obj.plan, obj.duration_days
```

再找到 `generate` 方法签名：
```python
def generate(cls, plan, created_by, count=1, max_uses=1, note=''):
```
改成：
```python
def generate(cls, plan, created_by, count=1, max_uses=1, duration_days=30, note=''):
```

并在创建对象的 `cls.objects.create(...)` 参数里加上 `duration_days=duration_days`。

## 3. views_institution.py — PlanInviteCodeGenerateView
找到 `class PlanInviteCodeGenerateView`，在 post 方法里加：
```python
duration_days = max(0, int(request.data.get('duration_days', 30)))
```
然后 generate 调用里加上 `duration_days=duration_days`。

## 4. views_institution.py — InstitutionCreateView
找到 `class InstitutionCreateView`，在验证码之后取 duration_days：
```python
from datetime import timedelta
from django.utils import timezone
```
把 `valid, result = PlanInviteCode.validate_and_use(invite_code)` 改成：
```python
valid, result = PlanInviteCode.validate_and_use(invite_code)
```
如果是三返回值：
```python
valid, *rest = PlanInviteCode.validate_and_use(invite_code)
if not valid:
    return Response({'error': rest[0]}, status=400)
plan, duration_days = rest[0], rest[1] if len(rest) > 1 else 30
```

创建 Institution 时，加 `plan_expires_at`：
```python
plan_expires = None
if duration_days > 0:
    plan_expires = timezone.now() + timedelta(days=duration_days)

inst = Institution.objects.create(
    ...
    plan_expires_at=plan_expires,
    ...
)
```

## 5. 前端 InviteCodeAdmin.tsx
生成邀请码的表单里加一个「有效天数」输入框：
```tsx
<div className="space-y-1">
  <p className="text-[10px] font-bold text-[#AEAEB2] uppercase">有效天数</p>
  <Input type="number" min={0} max={3650} value={durationDays}
    onChange={e => setDurationDays(parseInt(e.target.value) || 0)}
    className="h-10 w-22 rounded-xl text-sm" placeholder="0=永久" />
</div>
```

并在 state 和 handleGenerate 里加 `durationDays` 状态，API 调用传 `duration_days: durationDays`。
