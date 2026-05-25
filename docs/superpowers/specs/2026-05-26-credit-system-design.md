# 教师端积分系统设计

**状态**：Spec 已完成，暂不实施  
**日期**：2026-05-26  
**背景**：参考 Lovart 等产品的积分模式，用积分取代现有 AI 配额体系

---

## 1. 决策摘要

| 维度 | 决策 |
|------|------|
| 定位 | 积分**取代**现有 AI 月度配额 |
| 范围 | 只针对 AI 生成类操作（出题、解析、判分等 LLM 调用） |
| 获取方式 | 会员每月赠送 + 可单独购买积分包 |
| 有效期 | 购买的积分包永久有效 |
| 计费方式 | 固定消耗（每个操作固定积分） |
| 方案选择 | 方案 A：机构积分池（积分挂在 Institution 上） |

## 2. 现状分析

### 当前配额体系

- 机构级月度配额，按 plan 分级（Free/Starter/Growth/Enterprise）
- AI 相关配额：`ai_question`（月）、`ai_call_total`（月）
- 内容创建配额：`course`、`question`、`knowledge_point`、`article`（总量）
- 导出配额：`pdf_export`、`interview`（月）
- **关键**：`HasQuota` 权限类对 institution admin（owner/teacher）豁免配额检查

### 需要替换的部分

只替换 AI 生成类的月度配额，其余保留：

| 资源 | 当前 | 改为 |
|------|------|------|
| `ai_question` | 月度硬限（30/100/3000/unlimited） | 积分消耗 |
| `ai_call_total` | 月度硬限（100/500/3000/unlimited） | 积分消耗 |
| `pdf_export` | 保留月度配额 | 不变 |
| `interview` | 保留月度配额 | 不变 |
| 内容创建 | 保留总量配额 | 不变 |

## 3. 方案 A：机构积分池

### 数据模型

```python
# Institution 新增字段
class Institution(models.Model):
    # ... 现有字段 ...
    credit_balance = models.IntegerField(default=0)  # 当前可用积分
    credit_monthly_grant = models.IntegerField(default=0)  # 本月会员赠送积分（仅记录，实际充值到 balance）
```

```python
# 新模型：积分交易记录
class CreditTransaction(models.Model):
    institution = models.ForeignKey(Institution, on_delete=models.CASCADE)
    amount = models.IntegerField()  # 正数=收入，负数=消耗
    reason = models.CharField(max_length=50)  # monthly_grant / purchase / ai_question / ai_grading / ...
    reference_id = models.CharField(max_length=100, blank=True)  # 关联对象 ID（Order ID / Question ID 等）
    operator = models.ForeignKey(User, null=True, on_delete=models.SET_NULL)  # 操作人
    created_at = models.DateTimeField(auto_now_add=True)
```

```python
# 新模型：积分包商品
class CreditPack(models.Model):
    name = models.CharField(max_length=100)  # "100 积分包"
    credits = models.IntegerField()  # 积分数量
    price_cents = models.IntegerField()  # 价格（分）
    is_active = models.BooleanField(default=True)
    sort_order = models.IntegerField(default=0)
```

### 积分消耗表

| AI 操作 | 消耗积分 | 说明 |
|---------|---------|------|
| AI 出题（对抗管线，含 Author+Reviewer+Revise+Classifier） | 10 | 一次完整出题流程 |
| AI 解析（文本/文件 → 结构化题目） | 5 | 包含 chunked 解析 |
| AI 判分（主观题） | 2 | 单次判分 |
| AI 答案生成（创建题目时自动生成） | 1 | 轻量调用 |
| AI 面试评分 | 3 | 面试模拟评分 |

> 具体数值需要根据实际 token 消耗和成本核算调整。

### 会员赠送方案

| Plan | 每月赠送积分 | 折算约 |
|------|------------|--------|
| Free | 0 | — |
| Starter | 200 | ~20 次 AI 出题 |
| Growth | 1000 | ~100 次 AI 出题 |
| Enterprise | 5000 | ~500 次 AI 出题 |

赠送积分**按月清零**（每月 1 号充值，未用完的作废）。购买的积分包永久有效，消耗时**先用赠送积分，再用购买积分**。

### 支付流程

积分包购买复用现有支付流程：
1. 前端展示积分包列表（`/billing` 页面新增 tab）
2. 用户选择积分包 → 创建 Order（新增 order type: `credit_pack`）
3. 支付完成后 webhook → `confirm_order` → 增加 `credit_balance` + 记录 `CreditTransaction`
4. 与会员购买共用同一套 gateway（Stripe/微信/支付宝/Airwallex）

### 权限/配额改动

1. `HasQuota` 权限类中，AI 相关资源改为检查 `credit_balance >= 消耗积分`
2. 取消 admin 豁免——教师使用 AI 也要消耗积分（这是核心变化）
3. `increment_quota` 改为 `consume_credits(institution, amount, reason, operator)`
4. 内容创建和导出配额保持不变

### 前端改动

- **InstitutionDashboard**：显示积分余额、本月消耗趋势
- **Billing 页面**：新增"积分商店" tab，展示积分包 + 购买
- **AI 出题页面**：操作前显示"本次消耗 X 积分，当前余额 Y"
- **积分不足时**：引导购买积分包或升级 plan

### 需要处理的边界情况

- 积分不足时，AI 操作直接拒绝，返回明确提示
- 购买积分包的 Order 与会员 Order 复用同一模型，通过 `order_type` 字段区分
- 退款时需扣回对应积分
- 机构 plan 降级时，已购买的积分包保留，但停止月度赠送

## 4. 不变的部分

- 内容创建配额（course/question/knowledge_point/article）保持总量限制
- 导出配额（pdf_export/interview）保持月度限制
- Plan 功能矩阵（PLAN_FEATURES）不变
- 学生端不受影响

## 5. 后续扩展（v2）

- **个人积分限额**：Owner 可给每个教师分配月度上限
- **积分转赠**：机构间积分转让
- **按 token 计费**：根据实际 LLM token 消耗动态计算积分
- **积分排行榜**：教师用量可视化

## 6. 风险与权衡

| 风险 | 应对 |
|------|------|
| 教师习惯了免费无限用，改为积分消耗可能抵触 | Growth/Enterprise 赠送量足够大，实际影响有限 |
| 积分定价不合理导致亏损 | 先按 token 成本的 2-3 倍定价，观察数据后调整 |
| 改动 HasQuota 影响面大 | 只改 AI 相关分支，其他资源路径不动 |
