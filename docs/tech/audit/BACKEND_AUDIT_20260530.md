# UniMind 后端全量审计报告

**审计日期**: 2026-05-30  
**审计范围**: 后端 11 个 Django app + 辅助模块（school_system, ai_engine, core）  
**总代码量**: ~31,662 行 Python  
**审计维度**: 业务逻辑、安全漏洞、数据隔离、支付逻辑、AI 集成、文件上传、性能、代码质量

---

## 审计方法

- 静态代码审查（逐文件扫描 views/serializers/services/models）
- 安全模式匹配（SQL 注入、XSS、CSRF、IDOR、认证绕过）
- 数据隔离一致性检查（机构级过滤逻辑）
- 并发安全分析（支付、AI 线程）
- N+1 查询检测（serializer 嵌套查询）

---

## 风险等级定义

| 等级 | 含义 | 响应时间 |
|------|------|---------|
| **P0** | 可被利用的安全漏洞，直接影响数据安全或资金安全 | 立即修复 |
| **P1** | 业务逻辑缺陷，可能导致数据泄露或功能异常 | 本周修复 |
| **P2** | 性能问题、代码质量、维护风险 | 排期修复 |

---

## P0 — 安全漏洞（5 项）

### P0-1: `preview_institution` IDOR — 任意机构数据可被查看

**严重程度**: 高  
**文件**: `backend/courses/views.py:26-31`, `backend/articles/views.py:17-23`  
**影响**: 任意已认证用户可通过 `?preview_institution=<id>` 查看其他机构的课程/文章数据

**问题描述**:  
`_apply_institution_filter()` 函数接受 `preview_institution` query 参数，用于平台管理员预览其他机构数据。但函数**未校验请求用户是否为平台管理员**，任何已认证用户传入此参数即可绕过机构隔离。

```python
# courses/views.py:26-31 — 当前代码
def _apply_institution_filter(qs, user, request):
    preview = request.query_params.get('preview_institution')
    if preview:  # ← 未检查 is_platform_admin
        return qs.filter(institution_id=preview)
    ...
```

**修复建议**:  
在函数开头增加平台管理员身份校验：
```python
if preview:
    if not (user.is_authenticated and user.is_platform_admin):
        raise PermissionDenied("仅平台管理员可预览其他机构数据")
    return qs.filter(institution_id=preview)
```
同时将此函数提取到 `core/utils.py` 作为共享工具，消除 courses/articles 间的重复代码（见 P1-9）。

---

### P0-2: 媒体文件未认证可直接访问

**严重程度**: 高  
**文件**: `backend/school_system/media_serve.py:62-93`  
**影响**: 未认证用户可访问任意媒体文件（视频、文档、图片），绕过机构隔离

**问题描述**:  
媒体文件服务的机构级权限检查仅在用户已认证时执行。未认证请求直接跳过检查，进入文件服务逻辑：

```python
# media_serve.py:62-77
if request.user.is_authenticated:
    # 机构隔离检查
    ...
# ← 未认证用户直接跳到文件服务，无任何限制
```

**修复建议**:  
将认证检查前置，未认证用户直接返回 401：
```python
if not request.user.is_authenticated:
    return HttpResponse("Unauthorized", status=401)
```

---

### P0-3: 支付确认竞态条件 — 并发 webhook 可导致双重会员激活

**严重程度**: 高  
**文件**: `backend/payments/services/base.py:54-82`  
**影响**: 支付网关重复发送 webhook 时，用户可能被重复激活会员

**问题描述**:  
`confirm_order()` 函数在检查 `order.status == 'paid'` 和后续 `order.save()` 之间没有使用数据库行锁或原子事务。两个并发线程可能同时读取 `status='pending'`，各自执行激活逻辑：

```python
# base.py:54-82
def confirm_order(order):
    if order.status == 'paid':  # ← 无 select_for_update()
        return
    order.status = 'paid'
    order.save()  # ← 两个线程都可能到达此处
    activate_membership(order)  # ← 可能执行两次
```

虽然 `PaymentTransaction.gateway_txn_id` 有唯一约束可防止重复交易记录，但 `activate_membership` 可能已被调用两次，导致会员时长翻倍。

**修复建议**:  
使用 `select_for_update()` + `transaction.atomic()`：
```python
from django.db import transaction

def confirm_order(order_id):
    with transaction.atomic():
        order = Order.objects.select_for_update().get(id=order_id)
        if order.status == 'paid':
            return
        order.status = 'paid'
        order.save()
        activate_membership(order)
```

---

### P0-4: Webhook 端点在 secret 未配置时接受任意请求

**严重程度**: 中-高  
**文件**: `backend/payments/views.py:130-152`  
**影响**: 如果 `PAYMENT_WEBHOOK_SECRET` 环境变量未配置，攻击者可伪造支付确认

**问题描述**:  
`WebhookView` 设置 `permission_classes = []`（符合 webhook 设计），但签名验证是**条件性的** — 仅在 `PAYMENT_WEBHOOK_SECRET` 存在时才校验。如果该环境变量未配置，任何 POST 请求都可触发 `confirm_order()`：

```python
# payments/views.py:130-152
class WebhookView(APIView):
    permission_classes = []  # 无认证

    def post(self, request):
        secret = getattr(settings, 'PAYMENT_WEBHOOK_SECRET', None)
        if secret:  # ← 仅在 secret 存在时验证
            signature = request.headers.get('X-Signature')
            if not verify_signature(...):
                return Response(status=403)
        # ← secret 未配置时，直接处理
        confirm_order(order)
```

**修复建议**:  
在生产环境中强制要求 `PAYMENT_WEBHOOK_SECRET` 配置：
```python
if not secret:
    if not settings.DEBUG:
        return Response({"error": "Webhook secret not configured"}, status=500)
    # 仅开发环境允许无 secret
```

---

### P0-5: `UpdateProfileView` 缺少权限声明

**严重程度**: 中  
**文件**: `backend/users/views.py:119`  
**影响**: 如果 DRF 全局默认权限未设置为 `IsAuthenticated`，此端点可能允许未认证访问

**问题描述**:  
`UpdateProfileView` 继承 `generics.UpdateAPIView` 但未声明 `permission_classes`。对比同文件中的 `UpdateEmailView`（line 558）和 `UpdatePasswordView`（line 576）均正确设置了 `permission_classes = [permissions.IsAuthenticated]`。

**修复建议**:  
显式声明权限：
```python
class UpdateProfileView(generics.UpdateAPIView):
    permission_classes = [permissions.IsAuthenticated]
    ...
```

---

## P1 — 数据隔离与业务逻辑缺陷（7 项）

### P1-6: `AnswerActionView` 无机构用户可操作任意回答

**严重程度**: 中  
**文件**: `backend/faq_system/views.py:233-243`  
**影响**: 未绑定机构的用户可对任意机构的回答进行点赞/采纳操作

**问题描述**:  
`AnswerActionView` 使用 `get_object_or_404(Answer, pk=pk)` 直接加载回答，机构隔离检查在之后执行，但对无机构用户完全跳过：

```python
# faq_system/views.py:233-243
answer = get_object_or_404(Answer, pk=pk)
inst = request.user.institution
if inst and answer.question.institution != inst:  # ← inst 为 None 时跳过
    return Response(status=403)
```

**修复建议**:  
无机构用户应被拒绝访问：
```python
if not inst:
    return Response(status=403)
if answer.question.institution != inst:
    return Response(status=403)
```

---

### P1-7: `BIAnalyticsView` 无机构用户获得全平台数据

**严重程度**: 中  
**文件**: `backend/users/views.py:169-217`  
**影响**: 未绑定机构的管理员角色用户可查看全平台分析数据

**问题描述**:  
当 `is_platform=False` 且 `inst=None` 时，`user_filter` 和 `qs_filter` 均为空字典，查询变为无过滤的全平台视图：

```python
# users/views.py:178-179
if is_platform:
    user_filter = {}
    qs_filter = {}
else:
    user_filter = {'institution': inst} if inst else {}  # ← inst=None 时无过滤
    qs_filter = {'user__institution': inst} if inst else {}
```

**修复建议**:  
无机构用户不应获得任何数据：
```python
else:
    if not inst:
        return Response({"results": []})
    user_filter = {'institution': inst}
    qs_filter = {'user__institution': inst}
```

---

### P1-8: OSS `object_key` 未校验归属机构

**严重程度**: 中  
**文件**: `backend/courses/views.py:216-251`  
**影响**: 用户可构造其他机构的 object_key 枚举或覆盖文件

**问题描述**:  
`OSSUploadCompleteView` 接受用户提交的 `object_key`，仅检查 `bucket.object_exists(object_key)`，不验证 key 是否属于当前用户的机构。攻击者可构造 `institutions/{other_id}/video/{filename}` 形式的 key。

**修复建议**:  
在处理前验证 object_key 前缀：
```python
expected_prefix = f"institutions/{request.user.institution_id}/"
if not object_key.startswith(expected_prefix):
    return Response(status=403)
```

---

### P1-9: `_apply_institution_filter` 重复代码

**严重程度**: 低（维护风险）  
**文件**: `backend/courses/views.py:25-37`, `backend/articles/views.py:16-29`  
**影响**: 机构隔离逻辑在两处重复，修改一处可能遗漏另一处

**修复建议**:  
提取到 `core/utils.py`，两个 app 共用同一实现。

---

### P1-10: AI 后台线程无超时 kill 机制

**严重程度**: 中  
**文件**: `backend/ai_assistant/views.py:308-316`  
**影响**: LLM 调用挂起时，线程可能运行数分钟无法回收

**问题描述**:  
`AIChatView` 使用 `threading.Thread` 处理 AI 请求，但没有线程级超时机制。虽然 LLM 调用有 `LLM_REQUEST_TIMEOUT_SECONDS`（默认 120s）和重试，但线程本身无法被强制终止。

**修复建议**:  
考虑使用 `concurrent.futures.ThreadPoolExecutor` 配合 `future.result(timeout=...)`，或在 finally 中设置超时标志让线程自行退出。

---

### P1-11: SSE 流式响应可能保存空结果

**严重程度**: 中  
**文件**: `backend/ai_assistant/views.py:459`  
**影响**: Agent 线程未完成时，空响应可能被写入数据库

**问题描述**:  
`agent_thread.join(timeout=5)` 仅等待 5 秒。如果 Agent 仍在运行，`_result_container[0]` 为 `None`，空响应会被保存：

```python
# ai_assistant/views.py:459
agent_thread.join(timeout=5)
result = _result_container[0]  # ← 可能为 None
if result:
    save_message(result)  # ← None 时跳过，但 SSE 已发送结束信号
```

**修复建议**:  
增加重试等待或标记响应为"处理中"状态，避免空响应入库。

---

### P1-12: `AIChatResetView` 无速率限制

**严重程度**: 低-中  
**文件**: `backend/ai_assistant/views.py:333`  
**影响**: 恶意用户可批量删除全部对话历史

**问题描述**:  
`AIChatResetView` 删除用户所有聊天消息（可选按 bot 过滤），无确认机制、无软删除、无速率限制。

**修复建议**:  
至少添加速率限制（如 10 次/小时），并考虑软删除机制。

---

## P2 — 性能与代码质量（9 项）

### P2-13: N+1 查询 — `QuestionSerializer.get_is_favorite/get_is_mastered`

**文件**: `backend/quizzes/serializers.py:33-44`  
**问题**: 每个 question 序列化时各执行一次 `UserQuestionStatus.objects.filter()` 查询  
**影响**: 题目列表 N 个题目 → 2N 次额外查询  
**修复**: 在 view 层用 `prefetch_related` 预取状态，或用 `annotate` 批量计算

### P2-14: N+1 查询 — `faq_system` 的 `get_is_liked/get_is_followed`

**文件**: `backend/faq_system/serializers.py:35-58`  
**问题**: M2M 字段 `likes` 和 `followers` 未预取，每个问题序列化时各查一次  
**修复**: view 层添加 `.prefetch_related('likes', 'followers')`

### P2-15: N+1 查询 — `KnowledgePointSerializer.get_children()`

**文件**: `backend/quizzes/serializers.py:18`  
**问题**: 对每个知识点执行 `children.exists()` + `children.all()` 两次查询  
**修复**: 使用 `prefetch_related('children')` 或 `annotate(has_children=Count('children'))`

### P2-16: 简历上传未使用中心化文件校验 ~~（误报）~~

**文件**: `backend/interviews/views.py:329`  
**结论**: **误报** — 代码已使用 `validate_upload_file()` 中心化校验（含 magic bytes 检查）

### P2-17: 分片上传清理无定时任务 ~~（误报）~~

**文件**: `backend/courses/tasks.py:34`, `backend/school_system/settings.py:398`  
**结论**: **误报** — `cleanup_expired_chunks_task` 已定义，Celery beat 已配置每天凌晨 3 点执行

### P2-18: 密码修改允许弱密码

**文件**: `backend/users/views.py:586`  
**问题**: `UpdatePasswordView` 仅要求 6 字符，注册要求 8 字符  
**修复**: 统一为 8 字符最小长度

### P2-19: 裸 `int()` 转换 query params

**文件**: `backend/courses/views.py:505`, `backend/users/views.py:763,882`, `backend/users/views_admin.py:30`  
**问题**: `int(request.query_params.get('page', 1))` 非数字输入导致 ValueError 500 错误  
**修复**: 使用 `try/except ValueError` 或 DRF 的 `IntQueryParam` 验证

### P2-20: Rate limiting Redis 宕机时静默失效

**文件**: `backend/core/rate_limit.py:59`  
**问题**: `except Exception: return None` 在 Redis 不可用时静默关闭速率限制  
**修复**: 至少记录 warning 日志，或降级为内存计数器

### P2-21: CSP 允许 `unsafe-eval`

**文件**: `backend/school_system/middleware.py:77-78`  
**问题**: `'unsafe-inline'` 和 `'unsafe-eval'` 显著削弱 XSS 防护  
**修复**: 评估是否可移除 `unsafe-eval`（Vite 构建通常不需要）

---

## 正面发现

| 领域 | 评价 |
|------|------|
| **SQL 注入防护** | 全程使用 Django ORM，无 raw SQL，风险极低 |
| **XSS 防护** | 无 `mark_safe`，HTML 模板正确使用 `escape()` |
| **Serializer 合规** | 全部使用显式字段列表，无 `fields = '__all__'` 违规 |
| **文件上传校验** | `core/file_validation.py` 提供全面的扩展名/MIME/magic bytes 校验 |
| **认证体系** | Cookie+Token 双认证、登录暴力破解保护、账户锁定机制完善 |
| **AI 熔断器** | 三态熔断（closed/open/half-open）+ 指数退避重试设计良好 |
| **RBAC 权限模型** | 能力矩阵 + 层级角色 + 可复用 Permission 类，架构清晰 |
| **密码安全** | 验证码使用 `make_password` 哈希存储，非明文 |

---

## 总体风险评估

| 维度 | 评级 | 说明 |
|------|------|------|
| **认证/授权** | B+ | 整体完善，个别 view 缺少显式声明 |
| **数据隔离** | B | 核心逻辑正确，但 `preview_institution` 和无机构用户是盲区 |
| **支付安全** | B- | 竞态条件是主要风险，webhook 校验需加固 |
| **AI 集成** | B | 熔断/重试/可观测性良好，线程管理需改进 |
| **文件安全** | A- | 中心化校验完善，个别端点未接入 |
| **性能** | B- | N+1 查询集中在 serializer 层，需系统性优化 |

---

## 修复状态（2026-05-30）

```
✅ P0 全部修复（commit 09c24c2）:
├── P0-1  preview_institution IDOR
├── P0-2  媒体文件未认证访问
├── P0-3  支付竞态条件
├── P0-4  Webhook secret 强制校验
└── P0-5  UpdateProfileView 权限

✅ P1 全部修复（commit 09c24c2）:
├── P1-6  FAQ 无机构用户隔离
├── P1-7  BIAnalytics 无机构数据泄露
├── P1-8  OSS object_key 校验
├── P1-11 SSE 空响应保护
└── P1-12 AIChatReset 速率限制

✅ P2 全部修复（commit 47b8e38）:
├── P2-13~15  N+1 查询优化
├── P2-16     误报（已使用中心化校验）
├── P2-17     误报（已有 Celery beat 定时任务）
├── P2-18     密码策略统一
├── P2-19     int() 安全转换
├── P2-20     Redis 降级日志
└── P2-21     CSP unsafe-eval 移除

⬜ P1-10 AI 线程超时 kill（需架构调整，暂未修）
```
