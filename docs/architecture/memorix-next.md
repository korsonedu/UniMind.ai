# Memorix Next — 架构设计文档

> 状态：架构讨论完成，待工程验证。不改代码。

## 来源

若微激进探索报告（`~/.hermes/explorations/memorix-radical.md`，鉴二次审查通过）。四个方向全部进入架构设计，按竞争壁垒优先级排序。

## 四个方向与角色

| 优先级 | 方向 | 角色 | 用户感知 |
|--------|------|------|----------|
| 1 | 图扩散记忆场 | 核心竞争壁垒 | 不可见——统计层面提升 retention |
| 2 | 再巩固窗口 | 效果护城河 | 不可见——改变调度底层哲学 |
| 3 | 认知指纹 | 壁垒+商业化双吃 | 可见——"5题看透你的学习风格" |
| 4 | 睡眠锚定 | 体验差异化 | 可见——根据作息安排复习 |

前台（用户可感知）：3、4。后台（竞争壁垒）：1、2。

---

## 1. 知识图数据模型

### 决策：混合方案

**结构化边 → KnowledgeEdge 表（持久化）**
**数据驱动边 → Redis 缓存（不落表）**

#### KnowledgeEdge 模型

```python
class KnowledgeEdge(models.Model):
    source = ForeignKey(KnowledgePoint, related_name='out_edges')
    target = ForeignKey(KnowledgePoint, related_name='in_edges')
    edge_type = CharField(choices=[
        ('contains',    '包含'),       # 父子，继承自树
        ('prerequisite','前驱'),       # 必须先学 A 才能学 B
        ('similar',     '相似'),       # 易混淆的相近概念
        ('contrast',    '对立'),       # 对照概念，互相增强理解
        ('confusion',   '混淆'),       # 经常被搞混
        ('co_occur',    '共现'),       # 考试中总是一起出现
        ('derivation',  '推导'),       # B 从 A 推导而来
    ])
    weight = FloatField(default=1.0)   # 扩散权重，范围 [0, 1]
    source_type = CharField(choices=[
        ('llm',       'LLM 批量生成'),
        ('manual',    '手工标注'),
        ('tree',      '从 KnowledgePoint 树自动派生'),
    ])
```

#### 边的三个来源

| 来源 | 边类型 | 精度 | 覆盖率 |
|------|--------|------|--------|
| KnowledgePoint 树自动派生 | contains, prerequisite | 中 | 100%（有树就有） |
| LLM 批量生成（一次性） | similar, contrast, derivation | 中 | 高 |
| ReviewLog 数据学习（持续） | co_occur, confusion | 高 | 随时间增长 |

#### L 矩阵计算

每次调度前合并两层：
1. 从 KnowledgeEdge 表拉固定边 → 构造 L_base
2. 从 Redis 拉动态边（ReviewLog 学出来的 co_occur/confusion）→ 叠加到 L
3. 边权重初始值：parent-child 0.8, sibling 0.3, 跨域 LLM 生成 0.1（数据驱动后自动调整）

MVP 规模（Phase 1）：CFA Level I Quant，50-80 节点，120-300 边。精度 60-80%（跨域弱边可容忍）。

### KnowledgeEdge 完整模型定义

```python
class KnowledgeEdge(models.Model):
    """
    知识图的有向边。source → target 表示"复习 source 会通过扩散
    影响 target 的记忆状态"。边是有向的——扩散方向不一定可逆。
    """
    source = models.ForeignKey(
        KnowledgePoint, on_delete=models.CASCADE,
        related_name='out_edges',
    )
    target = models.ForeignKey(
        KnowledgePoint, on_delete=models.CASCADE,
        related_name='in_edges',
    )
    edge_type = models.CharField(
        max_length=16,
        choices=[
            ('contains',     '包含'),
            ('prerequisite', '前驱'),
            ('similar',      '相似'),
            ('contrast',     '对立'),
            ('confusion',    '混淆'),
            ('co_occur',     '共现'),
            ('derivation',   '推导'),
        ],
    )
    weight = models.FloatField(
        default=1.0,
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
        help_text='扩散权重 0-1，数据驱动自动调整',
    )
    source_type = models.CharField(
        max_length=16,
        choices=[
            ('tree',   '从 KnowledgePoint 树派生'),
            ('llm',    'LLM 批量生成'),
            ('manual', '手工标注'),
            ('data',   'ReviewLog 数据驱动'),
        ],
    )
    is_active = models.BooleanField(
        default=True,
        help_text='权重<0.05自动标记为False，不参与L计算',
    )
    institution = models.ForeignKey(
        'users.Institution', on_delete=models.CASCADE,
        null=True, blank=True,
        help_text='机构专属边（NULL=全局），支持机构间知识图隔离',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('source', 'target', 'edge_type', 'institution')
        indexes = [
            models.Index(fields=['source', 'is_active']),      # 查某节点的出边
            models.Index(fields=['target', 'is_active']),      # 查某节点的入边
            models.Index(fields=['institution', 'is_active']),  # 按机构拉全图
            models.Index(fields=['source_type']),               # 按来源审计
        ]
```

### 边权重学习算法

```python
def update_edge_weights_from_review_logs(since: datetime):
    """
    从 ReviewLog 学习 co_occur 和 confusion 边。
    每天 Celery 运行一次。
    """
    # 1. 统计转移概率
    #    用户复习了 KP A 后，在下一轮复习中 KP B 答对的概率变化
    #    Δ(B|A) = P(B_correct | A_just_reviewed) - P(B_correct | A_not_reviewed)
    #    正 Δ → 共现边（A 帮助 B），负 Δ → 混淆边（A 干扰 B）

    # 2. 更新 Redis 缓存
    for edge in significant_edges:
        key = f"memorix:edge:{edge.source_id}:{edge.target_id}"
        redis.hset(key, mapping={
            'type': edge.type,
            'weight': edge.weight,
            'updated': now.isoformat(),
        })
        redis.expire(key, 86400 * 7)  # TTL=7天

    # 3. 显著边同步回 KnowledgeEdge 表
    for edge in converged_edges:
        KnowledgeEdge.objects.update_or_create(
            source_id=edge.source, target_id=edge.target,
            edge_type=edge.type,
            defaults={'weight': edge.weight, 'source_type': 'data'},
        )
```

### Redis 缓存 Schema

```
# 动态边（ReviewLog 学出来的，每天更新）
memorix:edge:{source_kp_id}:{target_kp_id}
  → hash: {type, weight, updated}
  → TTL: 7 天（超过 7 天未更新的边自动清理）

# 学科 L 矩阵缓存（预计算，减少调度时的计算量）
memorix:L:{subject_slug}
  → 序列化的 L 矩阵（scipy sparse CSR 格式→bytes）
  → TTL: 1 小时（知识图更新后失效，下次调度时重建）
   
# 树派生 L 兜底（学科冷启动时用）
memorix:L_tree:{subject_slug}
  → 仅从 KnowledgePoint 树派生的 L
  → TTL: 永久（树结构不变则 L 不变）
  → 在 KnowledgePoint 树变更信号中清除
```

### 批量查询优化

调度时取全学科所有边不是逐条查。用 prefetch：

```python
# 一次查询取某学科所有活跃边
edges = (
    KnowledgeEdge.objects
    .filter(source__subject=subject, is_active=True)
    .select_related('source', 'target')
    .only('source_id', 'target_id', 'edge_type', 'weight')
)

# 构造邻接表（内存中的 dict-of-dict）
adj: dict[int, dict[int, float]] = defaultdict(dict)
for e in edges:
    adj[e.source_id][e.target_id] = e.weight

# field_benefit 计算：
#   field_benefit_i = Σ_{j in adj[i]} adj[i][j] × max(0, 1 - R_j)
```

---

## 2. 调度管线

### 决策：权重融合

不改现有 `build_adaptive_question_ids` 的三桶分桶逻辑。在"取前 N"这一步，将独立 urgency 和图扩散 field_benefit 加权融合。

```
现有管线（不变）:
  UserQuestionStatus 查询 → due/risk/new 分桶 → 桶内按 urgency 排序

新增（在取前 N 步骤之后可选开启）:
  独立 urgency 排序 → 图扩散重排（加权融合）→ 最终选题列表

公式:
  score_i = α × urgency_i + (1-α) × field_benefit_i
  
  field_benefit_i = Σ_{j∈V} w_{ij} × max(0, 1 - R_j(t)) × (1 - I_j)
  其中:
    w_{ij} 是知识图中 i→j 的边权重（L 矩阵非对角元）
    R_j(t) 是节点 j 当前检索概率
    I_j 是指示器——j 是否已经被选中（避免重复）
```

α 控制过渡速度：
- α=1.0：纯老逻辑（当前行为）
- α=0.60：启动验证（Phase 0 两次仿真独立锁定最优）
- α=0.7：图扩散显著介入
- α 可 per-group 配置，天然支持 A/B 测试

### 嵌入位置

`memorix_scheduler.py::build_adaptive_question_ids()` 的返回前一步，作为可选的 re-rank 步骤。Feature flag: `MEMORIX_FIELD_ENABLED`。

### 数据流：一次完整的复习→调度循环

```
═══════════════════════════════════════════════
                  复习事件（不改）
═══════════════════════════════════════════════

用户答题（题 A，评分 3=Good）
  │
  ▼
MemorixService.update_status(user, status_A, rating=3)
  │
  ├─→ 更新 status_A.stability, difficulty, next_review_at
  └─→ MemorixOptimizer.update() 在线 SGD 更新 20 维权重
  │
  ▼
ReviewLog 写入（不变）
  │
  ▼
（图扩散在这一步不做任何事——pull 模型）

═══════════════════════════════════════════════
              下次调度请求（改这步）
═══════════════════════════════════════════════

用户请求刷题（limit=10）
  │
  ▼
build_adaptive_question_ids(user, limit=10)
  │
  ├─→ 查询 UserQuestionStatus → due/risk/new 分桶（不变）
  │
  ├─→ 桶内逐题算 urgency_i = 1 - R_i(t)（不变）
  │
  ├─→ ┌─────────────────────────────────────┐
  │   │  NEW: 仅在 MEMORIX_FIELD_ENABLED   │
  │   │                                     │
  │   │  对每个候选节点 i：                    │
  │   │    field_benefit_i =                 │
  │   │      Σ_j w_ij × max(0, 1-R_j(t))   │
  │   │                                     │
  │   │  其中：                               │
  │   │    w_ij: L 矩阵非对角元（从             │
  │   │          KnowledgeEdge + Redis 合并） │
  │   │    R_j(t): 节点 j 当前检索概率        │
  │   │    j 遍历 i 的所有邻居                 │
  │   │                                     │
  │   │  score_i = α·urgency_i               │
  │   │          + (1-α)·field_benefit_i    │
  │   │                                     │
  │   │  桶内按 score_i 重排（替代 urgency 排）  │
  │   └─────────────────────────────────────┘
  │
  ▼
返回最终选题列表

═══════════════════════════════════════════════
              图的更新（离线批处理）
═══════════════════════════════════════════════

定期 Celery 任务（每天一次）:
  │
  ├─→ 从 ReviewLog 学 co_occur/confusion 边
  ├─→ 更新 Redis 动态边缓存（TTL=24h，下次批处理覆盖）
  └─→ 可选：修正 KnowledgeEdge 表中数据驱动的边权重
```

**关键设计决策**：图扩散是 **pull 模型**——调度时查邻居，复习时不传播。

原因：
1. 复习是高频操作（每次答题都触发），如果每次复习都往邻居扩散，计算量不可控
2. 调度时一次性算 field_benefit，可以利用 R_j(t) 的当前值天然反映最近复习的效果——如果邻居刚被复习过，R_j 高，1-R_j 低，它自动不再"需要帮助"
3. 避免数据不一致：push 模型需要存储"传播后的虚拟状态"，而 pull 模型始终从真实的 UserQuestionStatus 计算

### field_benefit 直觉验证

- **题 A 和题 B 是兄弟节点（w=0.3），都到期了** → A 的 field_benefit 包含 B 的 (1-R_B)，B 的也包含 A 的。分数相互抬高，系统倾向于一起选它们
- **题 C 刚被复习完，R_C≈1.0** → 1-R_C≈0，C 不贡献 field_benefit 给邻居。C 暂时"退场"，让资源给更需要的地方
- **题 D 孤立节点，没有边** → field_benefit_D = 0，纯靠自己的 urgency 竞争。α 确保它不会被饿死

---

## 3. 再巩固窗口

### 核心假设

记忆再巩固（reconsolidation）：每次提取记忆时，记忆痕迹变得不稳定（labile），然后被重新巩固。复习不是"加固"，而是"破坏→重建"。这从根本上改变了调度的目标。

**当前调度哲学**：在遗忘之前复习，越早越好。目标 = 最大化 R(t)。
**再巩固调度哲学**：在记忆刚好足够不稳定可以改进、但又有足够残余可以重建时复习。目标 = 最大化 P(t)。

### 数学定义

```
可塑性窗口: P(t) = S(t) × (1 - R(t))

其中:
  S(t): 记忆稳定性（当前 Memorix 的 stability 字段）
  R(t): 检索概率（Weibull: exp(-(t/λ)^k)）
```

**直观**：S(t) 是"记忆有多结实"，(1-R(t)) 是"记忆有多不稳定"。

- t 很小（刚复习完）：R(t) ≈ 1 → 1-R(t) ≈ 0 → P(t) ≈ 0。记忆太稳定，不需要重建。
- t 很大（快忘了）：R(t) ≈ 0 → 1-R(t) ≈ 1，但 S(t) 也下降了 → P(t) 也不高。没有足够的残余来重建。
- t 在中间：P(t) 有一个峰值——这是最优复习时机。

### 不应期修正

若微在原始推导中发现了一个问题：如果假设 S(t) = S₀（常数），那么 P(t) = S₀·(1-exp(-(t/λ)^k))，它是单调递增的——意味着越晚复习 P 越大，这和直觉矛盾（太晚了记忆残余不足，无法有效重建）。

**修正**：S(t) 不是常数。刚复习后存在"不应期"——稳定性需要时间恢复。

```
S(t) = S₀ × [1 - exp(-t/τ)]

其中:
  S₀: 渐近稳定性（复习后最终能达到的稳定值）
  τ:   不应期时间常数（约 0.5-2 小时，因人而异）
```

代入 P(t)：
```
P(t) = S₀ × [1 - exp(-t/τ)] × [1 - exp(-(t/λ)^k)]
```

这个函数的形状：
- t→0: P(t)→0（两项都趋零——刚复习完不稳定也不能再巩固）
- t→∞: 第二项→1，第一项→S₀，但 R(t) 已经太低，实际已遗忘
- 中间：存在唯一的 argmax

### 数值求解

P(t) 的 argmax 没有闭式解析解（两个不同的指数函数乘积），但可以用二分搜索或牛顿法数值求解。

```python
def find_optimal_review_time(stability_s0, lambda_, k, tau=1.0):
    """
    用黄金分割搜索找 P(t) 的最大值点。
    区间 [tau, 10*lambda_] —— 从不应用结束到约 10 倍时间尺度
    """
    def P(t):
        if t <= 0:
            return 0.0
        S = stability_s0 * (1 - math.exp(-t / tau))
        R = math.exp(-((t / lambda_) ** k))
        return S * (1 - R)
    
    lo, hi = tau, 10 * lambda_
    phi = (math.sqrt(5) - 1) / 2
    
    for _ in range(50):  # 50 次迭代精度 10^-10
        m1 = hi - phi * (hi - lo)
        m2 = lo + phi * (hi - lo)
        if P(m1) >= P(m2):
            hi = m2
        else:
            lo = m1
    
    t_opt = (lo + hi) / 2
    return t_opt, P(t_opt)

# 对于 CFA 典型参数: S₀=30天, λ=30, k=1.2, τ=1小时
# t_opt ≈ 2.5-4 天（远大于当前"越快越好"的策略）
```

### 与现有 Weibull 模型的切换协议

```
当前 Memorix 调度逻辑（伪代码）:
  next_t = argmin_t [ (1 - R(t)) + α × log(1+t) ]   # 遗憾最小化

再巩固窗口调度逻辑（伪代码）:
  next_t = argmax_t P(t)
         = argmax_t [ S(t) × (1 - R(t)) ]
         
  其中 S(t) = stability_current × [1 - exp(-t/τ)]
```

切换通过 feature flag `MEMORIX_REC_ENABLED` 控制。flag 关闭时走原逻辑，flag 打开时走 P(t)。

### 与图扩散的交互

再巩固窗口改变 urgency 的计算方式，图扩散改变选题的全局排序。两者在公式中的交互点：

```
score_i = α × urgency_i + (1-α) × field_benefit_i

REC 关闭: urgency_i = 1 - R_i(t)                    ← 当前
REC 打开:  urgency_i = P_i(t_elapsed) / P_i(t_opt)  ← 归一化到 [0,1]
```

P_i 归一化：当前时刻的可塑性值除以该节点的最大可塑性值。urgency 接近 1 意味着"现在就处于最优复习窗口"。

### 边缘情况

| 情况 | 行为 |
|------|------|
| 新题（无 stability） | P(t) 未定义。使用默认 R(t) urgency，等第一次复习后切换 |
| 不应期内（t < τ） | P(t) ≈ 0。系统不会在复习后立即再安排同一道题 |
| stability 极高（S₀ > 365天） | t_opt 可能极远（数月）。退化为普通 urgency 调度，无需再巩固 |
| 已遗忘（R(t) < 0.1） | P(t) 虽低但非零——说明该重学了。处理同当前"重新学习"路径 |

---

## 4. 认知指纹

### 核心假说

每个用户有一个稳定的低维认知特征向量 φ_u ∈ R^d（d = 3~5），它决定了该用户对所有知识材料的记忆响应模式。当前 Memorix 用 20 维权重向量 w_u 拟合这个响应——但 20 维中大部分是冗余展开，真实的认知结构维度很低。

**假说来源**：
- 若微报告的不变量狩猎发现：同一用户的 Weibull k 形状参数稳定（CV < 15%），难度排序稳定（Kendall τ > 0.85），间隔比值收敛到常数
- 这三个不变量暗示底下的自由参数远少于 20 个
- 类比：高维数据的本征维度（intrinsic dimension）通常远低于嵌入维度

### φ_u 的维度含义假说

| 维度 | 暂定名称 | 含义 | 对应的 Memorix 权重 |
|------|----------|------|---------------------|
| φ₁ | 学习速率 | 新知识→稳定的速度。高 = "学得快" | 影响 S 的初始值和增长率参数 |
| φ₂ | 遗忘速率 | 记忆衰退的速度。高 = "忘得快" | 映射到 Weibull k 和 λ 基准值 |
| φ₃ | 巩固效率 | 每次复习的边际增益。高 = "复习一次管很久" | 影响 S 更新的幅度系数 |
| φ₄ | 干扰敏感度 | 相似知识互相干扰的程度。高 = "容易混淆" | 影响 difficulty 调整和混淆边的权重 |
| φ₅ | 温故偏好 | 旧知识复习的必要性。高 = "需要经常回头" | 影响 regret minimization 的时间偏好 α |

注：d=3 是 MVP 假设（φ₁ φ₂ φ₃），d=5 是完整假设。Phase 0 可以先验证 d=3 是否解释足够方差。

### 编码器架构

```
输入: 用户的前 N 次交互序列（N ≈ 10）
  [(kp_id_1, rating_1, elapsed_1), (kp_id_2, rating_2, elapsed_2), ...]

编码器 f_θ:
  1. 每条交互 → ItemEncoder(kp_id, rating, elapsed) → 32维向量
  2. 序列 → TransformerEncoder(32维序列) → 取最后一层均值池化
  3. 均值 → Linear(32 → d) → φ_u ∈ R^d

解码器 g_θ:
  φ_u + 知识点属性(difficulty_base, subject) → 预测该用户的:
    - S_pred（初始稳定性）
    - k_pred（Weibull 形状参数）
    - λ_pred（Weibull 尺度参数）

训练目标:
  L = MSE(R_pred(t) - grade_binary)  +  λ_reg × ||φ_u||²
  （Brier score + L2 正则）
```

### 与 MemorixOptimizer 的对接

```
当前流程:
  MemorixProfile.weights (20维) → MemorixOptimizer(weights) → 调度

认知指纹流程（长线）:
  用户前10次交互 → 编码器 f_θ → φ_u (3-5维)
                         ↓
                  g_θ(φ_u, kp_attrs) → 初始 20维 weights
                         ↓
                  MemorixOptimizer(weights) → 调度
                         ↓
                  在线 SGD 微调（非从头学习）

过渡方案（Phase 1 不依赖元学习）:
  用户前50次交互 → PCA/低秩分解 → φ_u_pca
  后续交互 → 在线 SGD → 细调 weights

关键: 冷启动从 200 次交互降到 10 次（元学习）或 50 次（PCA 过渡）。
```

### 冷启动策略

在元学习编码器训练完成之前，认知指纹不能直接用于调度。分为三个阶段：

| 阶段 | 方案 | 适用条件 |
|------|------|----------|
| Phase 0 | 不启用认知指纹。用现有 per-user 20维 SGD | 用户基数 < N₁ |
| Phase 1 | 简化版：前 50 次交互的统计特征做低秩近似，作为 20维初始化的 warm start | N₁ ≤ 用户基数 < N₂ |
| Phase 2 | 完整版：预训练好的 f_θ/g_θ，10 次交互推断 φ_u | 用户基数 ≥ N₂ + 编码器已训练 |

N₁ 和 N₂ 的具体值待定，取决于训练元学习编码器所需的最小用户基数。

### 数据需求

训练 f_θ 和 g_θ 需要：
- 大量用户的 ReviewLog 序列（每个用户至少 100+ 次交互）
- 用户的稳定认知特征标签（由当前 20维 SGD 收敛值做 PCA 得到，作为弱监督信号）
- MAML/Reptile 风格的元训练：在多个"用户任务"上训练，每个任务 = 一个人的 ReviewLog

**与隐私的关系**：φ_u 是从个体行为推断的，不需要跨用户共享原始数据。元训练可以用联邦学习或中心化训练（取决于合规要求）。

---

## 5. 睡眠锚定

### 核心假说

记忆巩固主要发生在睡眠中（NREM 慢波睡眠 + REM）。日历日是记忆时间的错误单位——用户 A 每天早上 6 点起床、用户 B 每天凌晨 2 点睡觉，他们的"一天"在记忆动力学上完全不同。

**假说**：以睡眠周期为单位的调度，比以日历日为单位的调度，长期 retention 更高。用户只需要提供起床时间，系统自动推断睡眠周期并调整所有时间相关计算。

### 睡眠周期模型

```
一个标准睡眠周期 ≈ 90 分钟
每晚 ≈ 4-6 个周期

睡眠有效时间（实际用于记忆巩固的时间窗口）:
  [入睡 + 30min, 起床前 - 30min]

简化模型（用户只需要提供起床时间）:
  起床时间:  wake_time      (用户设置，如 07:00)
  入睡时间:  wake_time - 8h (假设 8 小时睡眠，可通过数据校正)
  周期边界:  [入睡 + 0.5h + n×1.5h | n = 0,1,2,3,4]
```

### effective_now 偏移函数

替换调度中所有使用 `timezone.now()` 的位置，改为 `effective_now(user)`：

```python
def effective_now(user):
    """
    返回经过睡眠周期调整的"有效现在"时间戳。
    
    逻辑：如果用户还没到下一个睡眠周期，则"有效时间"停留在
    上一个周期结束的时刻——因为新的记忆巩固尚未发生。
    """
    now = timezone.now()
    prof = get_sleep_profile(user)  # 缓存查，无则返回 None
    
    if prof is None:
        return now  # 未设置睡眠时间，退化为日历时间
    
    # 计算今天的睡眠周期边界
    today_wake = now.replace(hour=prof.wake_hour, minute=prof.wake_minute)
    today_sleep_onset = today_wake - timedelta(hours=8)  # 简化
    
    # 当前处于哪个周期
    elapsed = (now - today_sleep_onset).total_seconds() / 3600
    if elapsed < 0.5:
        # 入睡后 30 分钟内——尚未进入巩固阶段
        return today_sleep_onset + timedelta(hours=0.5)
    
    cycle_idx = min(int((elapsed - 0.5) / 1.5), 5)
    # 回退到上一个完成的周期结束时刻
    last_cycle_end = today_sleep_onset + timedelta(hours=0.5 + (cycle_idx) * 1.5)
    
    return last_cycle_end


# 使用位置: memorix_scheduler.py
def build_adaptive_question_ids(user, limit=10, ...):
    now = effective_now(user)  # 替代 timezone.now()
    # ... 后续逻辑不变
```

### 用户数据模型

不新建模型，在现有 `MemorixProfile` 上加三个字段：

```python
class MemorixProfile(models.Model):
    # ... 现有字段 (weights, total_reviews_used, last_optimized_at) ...
    
    # 睡眠锚定（可选，用户不设置则退化为日历时间）
    wake_hour = models.SmallIntegerField(null=True, blank=True,  # 0-23
        help_text='用户起床时间（小时）')
    wake_minute = models.SmallIntegerField(null=True, blank=True,  # 0-59
        help_text='用户起床时间（分钟）')
    sleep_profile_updated_at = models.DateTimeField(null=True)
```

前端：在设置页加一个"起床时间"选择器，可选。不填就用日历时间。

### 调度中的具体使用

```
复习间隔 → 从"天数"改为"睡眠周期数"

示例:
  当前: next_review_at = now + timedelta(days=3)
  睡眠: next_review_at = effective_now + 3 × sleep_cycles
  
  用户 A（6:00 起床）: 3天后 = 第 3×5=15 个周期后
  用户 B（9:00 起床）: 3天后 = 第 3×4=12 个周期后（睡眠略少）
  用户 C（未设置）: 退化为 timedelta(days=3)

R(t) 计算中的 elapsed_days → elapsed_cycles:
  current:  R = exp(-(elapsed_days / stability)^k)
  sleep:    R = exp(-(elapsed_cycles / stability_cycles)^k)
  
  stability_cycles = stability_days × avg_cycles_per_day (≈4.5)
```

### 与图扩散和再巩固窗口的交互

睡眠锚定只改"时间怎么量"，不改"选什么题"和"when to review"的逻辑。完全正交。

图扩散的 field_benefit 继续用 R_j(t) 不变——R_j(t) 内部用的是 `effective_now` 调整后的 elapsed，天然适配。

### 默认行为

用户未设置起床时间 → `effective_now` 返回 `timezone.now()` → 退化为日历时间 → 现有行为完全不变。零风险。

---

## 6. 四方向架构统一

### 长期愿景

图扩散作为统一框架，再巩固窗口的 P(t) 和认知热力学的 T(t) 作为参数融入：

```
du/dt = -α(T(t))·u + β·L·u + M·s(P(t))

其中:
  u:        记忆激活向量场
  L:        知识图拉普拉斯（KnowledgeEdge + Redis 动态边）
  α(T(t)):  认知温度调制的衰减系数
  s(P(t)):  基于再巩固窗口的复习动作选择
  β:        扩散系数（从 ReviewLog 估计）
```

### 近期执行

Feature flag 分阶段上线，不一次全开：

| 阶段 | flag | 内容 |
|------|------|------|
| Phase 0 | 无 | 离线验证：用 ReviewLog 估计 β。β≈0 则停，β 显著则进 Phase 1 |
| Phase 1 | `MEMORIX_FIELD_ENABLED` | 图扩散权重融合，α=0.60，知识图用树结构初始 L |
| Phase 2 | `MEMORIX_REC_ENABLED` | 再巩固窗口 P(t) 调度，叠加 Phase 1 |
| Phase 3 | `MEMORIX_THERMO_L1` | 睡眠锚定，叠加 Phase 1+2 |
| Phase 4 | `MEMORIX_META` | 认知指纹（需用户基数） |

---

## 7. 实现路径与代价

### Phase 0：离线验证（3-5 人日）

- 从现有 KnowledgePoint 树构建初始 L
- 用 ReviewLog 回归估计 β
- 模拟对比独立调度 vs 图扩散调度的 retention 差异
- 产出：β 估计值 + 模拟结果 → 决策是否进入 Phase 1

### Phase 1：图扩散上线（8-12 人日）

- 新增 KnowledgeEdge 模型 + migration
- LLM 批量生成初始边（一个学科一次）
- `memorix_scheduler.py` 加权重融合 re-rank 步骤
- Feature flag + A/B 测试框架
- 3 人日回归测试

### Phase 2：再巩固窗口（5-7 人日）

- `memorix/optimizer.py` 调度目标函数修改
- P(t) 的 argmax 数值求解
- 叠加 Phase 1 的集成测试

### Phase 3+：后续（按需启动）

- 睡眠锚定 3-5 人日
- 认知指纹待用户基数 > N 后启动

---

## 7.5 Phase 0 仿真结果

### Phase 0 light（已完成）

> 200 学生 × 120 天 × 6α × 6β。真实 CFA 知识树，仅树边 + 严格前置。无交叉边、无考试。

| 指标 | 值 |
|------|-----|
| 最优组合 | α=0.70, β=0.15，Δ=+7.0% |
| 独立 baseline | R(120) ≈ 0.68 |
| 图扩散最优 | R(120) ≈ 0.73 |
| 负 Δ 组合 | 6/36 |
| 结论 | β≥0.10 有效，α 最优 0.6-0.7，半吊子扩散不如不做 |

### Phase 0 heavy（已完成，2026-06-07）

> **400 学生 × 150 天 × 6α × 6β × 3 调度器。** 真实 CFA 知识树，树边 + 随机跨 SEC 交叉边 + 放宽前置 + 每 20 天考试事件。三种调度器同批学生对比：当前生产 Memorix（贪心）、FSRS（SOTA 基线）、Memorix-Field（图扩散）。

**Field vs FSRS（核心对比）**：

| 指标 | 值 |
|------|-----|
| 最优组合 | **α=0.60, β=0.20**，Field R(150)=0.704，FSRS R(150)=0.505，Δ=**+19.9%** |
| 次优 | α=0.70, β=0.20，Δ=+19.5% |
| 第三 | α=0.80, β=0.20，Δ=+17.1% |
| Field vs FSRS 正收益 | **36/36**（全部为正） |
| 最小 Δ vs FSRS | +3.6%（α=0.80, β=0.01） |
| Field vs 贪心 正收益 | **36/36**（全部为正） |
| FSRS vs 贪心 | 互有胜负（±5% 以内），同一范式内的参数差异 |

**400 学生 vs 200 学生一致性**：

| | 200 学生 | 400 学生 |
|---|---------|---------|
| 最优 (α, β) | (0.60, 0.20) | **(0.60, 0.20)** |
| 最优 Δ vs FSRS | +23.4% | **+19.9%** |
| Field vs FSRS 全正 | ✅ | ✅ |
| β=0.20 全列最优 | ✅ | ✅ |

**图表位置**：`scripts/output/memorix_field_final.png`

### 综合结论

1. **最优参数锁定：α=0.60, β=0.20。** 两次独立仿真（200 学生 + 400 学生）、不同图密度、不同难度、不同规模——最优 α 和 β 完全一致。不是巧合
2. **Field 对 FSRS 的领先是跨代差，不是调参优势。** FSRS 和贪心在同一基线附近互换（±5%），Field 在所有 36 个组合中都显著高于两者（+3.6% ~ +19.9%）。这表明图扩散打开的是一个全新维度，不是参数优化
3. **β 越大越好，未观察到过拟合拐点。** 在所有 α 值下，β=0.20 都是该行最优。扩散强度可能还有进一步上调空间
4. **FSRS 在仿真中未显著优于贪心。** 这说明在建模了认知多样性和日周期的仿真环境中，Weibull 遗忘模型和 FSRS 的 power-law 模型是同一层级的——真正的差异化来自于引入图结构
5. **启动推荐**：α=0.60, β=0.20。这是两次仿真共同锁定的最优参数，不需要保守余量——因为"保守"在仿真中反而导致更差的结果

---

## 8. 失败模式与降级策略

系统必须在不完美条件下运行。以下定义了所有已知失败模式及降级路径。

### 8.1 降级层级

```
Layer 3: 全功能
  MEMORIX_FIELD_ENABLED=true, Redis 在线, KnowledgeEdge 有边
  → field_benefit 完整计算（表 + 缓存）

Layer 2: 静态降级
  Redis 不可用，KnowledgeEdge 有边
  → field_benefit 仅用固定边（表），丢失动态 co_occur/confusion

Layer 1: 树降级
  KnowledgeEdge 无边或 L 计算失败
  → field_benefit 仅用树派生边（parent-child + sibling）

Layer 0: 完全降级
  MEMORIX_FIELD_ENABLED=false 或 α=1.0
  → 当前行为，图扩散完全不参与
```

### 8.2 失败场景与响应

#### 场景 1：Redis 不可用

**触发条件**：Redis 连接超时、OOM、网络分区。

**影响**：动态边（co_occur/confusion，ReviewLog 学出来的）不可查询。

**响应**：
1. `field_benefit` 计算时跳过 Redis 查询，仅用 KnowledgeEdge 表
2. 日志记录 `memorix_field.redis_unavailable`，不抛异常
3. 不重试——调度请求不能等 Redis 恢复
4. 自动降级到 Layer 2，用户无感知

**恢复**：Redis 恢复后，下一个 Celery 批处理周期自动填充动态边，下次调度请求自动恢复到 Layer 3。

#### 场景 2：L 矩阵计算失败

**触发条件**：KnowledgeEdge 表中该学科的边数量为 0，或拉普拉斯矩阵构造时出现数值异常（NaN、inf）。

**影响**：无法计算 field_benefit。

**响应**：
1. 捕获异常，回退到树派生 L（从 KnowledgePoint parent-child 关系计算）
2. 如果树派生也失败（极端：学科只有一个节点），设 field_benefit_i = 0 ∀i，等价于 α=1.0
3. 日志记录 `memorix_field.L_failed`，附带学科 ID

#### 场景 3：β 估计不稳定

**触发条件**：Phase 0 离线验证中 β 的标准误差 > 估计值本身，或 Phase 1 运行中 β 在不同周期间大幅震荡。

**影响**：field_benefit 的权重 (1-α) 可能过高或过低。

**响应**：
1. α 设置保守上限：生产环境 α ≥ 0.7，确保 urgency 始终占主导
2. β 用 EMA 平滑（ρ=0.9），单周期异常不立即传导到 α
3. 监控 β 的滚动标准差，超过阈值触发告警但不降级

#### 场景 4：学科没有边（冷启动）

**触发条件**：新学科上线，KnowledgeEdge 表尚未填充，LLM 批量生成尚未执行。

**影响**：该学科所有节点的 field_benefit = 0。

**响应**：
1. 自动检测：某个学科的 KnowledgeEdge 行数 = 0 → 该学科 α 强制设为 1.0
2. 不阻塞：新学科用纯老逻辑跑，等边生成完再开图扩散
3. 日志记录 `memorix_field.cold_start`，触发 LLM 批量生成任务

#### 场景 5：field_benefit 计算超时

**触发条件**：图节点数过大（>1000），单次 field_benefit 的 O(N²) 计算超过调度请求的超时阈值。

**影响**：调度请求可能超时，用户体验受影响。

**响应**：
1. 设置计算 deadline：field_benefit 计算超过 200ms 则截断
2. 截断策略：仅计算 top-K 高度数节点的 field_benefit（K=min(N, 200)）
3. 剩余低度节点强制 field_benefit=0，等同于 α=1.0（纯 urgency）
4. 日志记录 `memorix_field.compute_timeout`

#### 场景 6：边权重退化

**触发条件**：长期运行后，ReviewLog 数据驱动修正与人工标注产生冲突，或某个 LLM 生成的边权重被数据证伪为 0。

**影响**：无效边占用计算资源，且可能轻微降低 field_benefit 质量。

**响应**：
1. Celery 批处理自动将权重 < 0.05 的边标记为 `inactive`，不参与 L 计算
2. 不删除——保留历史记录用于调试
3. 权重 < 0.01 且 source_type='llm' 的边，60 天后自动硬删除

### 8.3 降级保证

**所有降级路径的共同保证**：最差情况下，系统行为完全等同于当前 Memorix（α=1.0）。不存在"图扩散坏了导致调度崩溃"的路径——每一步降级都是向 α=1.0 收敛。

---

## 9. 认知仿真标准模型（Standard Cognitive Simulation Model）

> 本节是 Phase 0 仿真中虚拟学生模型的完整数学定义，可作为后续发表论文的 Method 章节参考。模型名暂定 **Memorix-Sim**。

### 9.0 符号表

| 符号 | 含义 | 域 |
|------|------|-----|
| $s$ | 学生索引 | $1 \dots N_s$ |
| $i, j$ | 知识点 (KP) 索引 | $1 \dots N_{\text{KP}}$ |
| $\boldsymbol{\phi}_s$ | 学生 $s$ 的认知特征向量 | $\mathbb{R}^3$ |
| $T_s$ | 学生类型标签 | {steady, fast, crammer, struggle} |
| $S_i(t)$ | KP $i$ 的稳定性 | $[0, 365]$ |
| $t_i^{\text{last}}$ | KP $i$ 上次复习时刻 | $\mathbb{R}_{\geq 0}$ (hours) |
| $R_i(t)$ | KP $i$ 的检索概率 | $[0, 1]$ |
| $r$ | 复习评分 | {1, 2, 3, 4} |
| $F(t)$ | 当前疲劳度 | $[0, 1]$ |
| $H_s^{\text{study}}$ | 每日学习窗口 | $\mathcal{U}(4, 10)$ hours |
| $\mathcal{C}_s$ | 学生 $s$ 的知识覆盖集 | $\subseteq V$ |
| $\alpha$ | urgency 权重 | $[0.6, 0.95]$ |
| $\beta$ | 扩散强度 | $[0.01, 0.20]$ |

### 9.1 模型假设

本模型基于以下显式假设：

1. **Weibull 遗忘假设**：人类记忆的检索概率随时间服从 Weibull 分布，形状参数 $k$ 在不同个体间稳定而在个体间有差异
2. **稳定性加固假设**：每次成功检索（评分 $\geq 2$）会提升记忆稳定性，提升量取决于个体的巩固效率和疲劳状态
3. **疲劳线性累积假设**：在单个学习窗口内，疲劳度随复习次数线性增长，睡眠后部分恢复
4. **前置依赖假设**：知识点的学习存在偏序关系，未掌握前置知识点则无法有效学习后继知识点
5. **扩散局部性假设**：复习一个知识点仅对其在知识图上的一阶邻居产生巩固效应，效应强度正比于边权重
6. **日周期假设**：记忆巩固主要发生在睡眠期间，学习窗口和睡眠窗口交替构成一个完整的 24 小时周期

**重要：所有假设均属可证伪。** 仿真结果的效度取决于这些假设在真实学习者群体中的成立程度，这恰是 Phase 1 A/B 测试要验证的核心问题。

### 9.2 认知特征向量

每个虚拟学生 $s$ 由一个三维认知特征向量 $\boldsymbol{\phi}_s = (\phi_1, \phi_2, \phi_3)$ 和一个学生类型标签 $T_s$ 唯一确定：

| 参数 | 符号 | 认知含义 | 取值范围 |
|------|------|----------|----------|
| 学习速率 | $\phi_1$ | 新知识首次接触后初始稳定性的增长率 | $[0.4, 1.35]$ |
| 遗忘速率 | $\phi_2$ | Weibull 遗忘曲线的形状参数 $k$ | $[0.05, 1.4]$ |
| 巩固效率 | $\phi_3$ | 每次成功复习带来的稳定性边际增益 | $[0.2, 0.85]$ |

学生类型 $T_s \in \{\text{steady}, \text{fast}, \text{crammer}, \text{struggle}\}$ 决定 $\boldsymbol{\phi}_s$ 的分布中心（见 §9.6）。各类型参数从以类型均值为中心、宽度 $\pm0.1 \sim \pm0.15$ 的均匀分布中独立采样。

### 9.3 知识状态空间与动力学

**完整状态**：每个学生 $s$ 对 KP $i$ 的记忆状态由二元组 $(S_i(t), t_i^{\text{last}})$ 完全描述。系统状态是所有 KP 状态的笛卡尔积。

**检索概率**（Weibull 遗忘曲线）：
$$R_i(t) = \begin{cases} \exp\left(-\left(\frac{t - t_i^{\text{last}}}{\max(S_i, 0.01)}\right)^{\phi_2}\right) & S_i > 0 \text{ and } t_i^{\text{last}} \geq 0 \\ 0 & \text{otherwise} \end{cases}$$

**稳定性更新**（复习事件触发）：
$$S_i^{\text{new}} = \begin{cases} \phi_1 \cdot (1 + 0.3(r - 2)) & S_i^{\text{old}} \leq 0 \quad \text{(首次学习)} \\ S_i^{\text{old}} \cdot (1 + \phi_3 \cdot (0.5 + 0.25r) \cdot \eta) & S_i^{\text{old}} > 0 \quad \text{(复习巩固)} \end{cases}$$

其中 $r \in \{1,2,3,4\}$ 为评分，$\eta = \max(0.3, 1 - F(t))$ 为疲劳修正因子。巩固效率同时受个体参数 $\phi_3$ 和当前疲劳状态 $F(t)$ 的双重调制。

### 9.4 疲劳动力学

$$F(t) = \min\left(1, F_0 + \frac{n_{\text{session}}}{k_F}\right)$$

| 参数 | 含义 | 值 |
|------|------|-----|
| $F_0$ | 日初始疲劳 | $\sim \mathcal{U}(0, 0.15)$ |
| $n_{\text{session}}$ | 当前学习窗口内累计复习次数 | 动态 |
| $k_F$ | 疲劳速率常数（类型依赖） | 0.10—0.30 |

睡眠后疲劳部分恢复：$F \leftarrow \max(0, F - 0.3)$。掌握度低于阈值（$R_i < 0.5$ 且距上次复习超过 12 小时）的 KP，睡眠期间稳定性衰减至 $S_i \cdot 0.85$。

### 9.5 日周期时间结构

仿真时间轴以小时为最小单位。每个学生 $s$ 的每一天 $d$ 由两个不可重叠的连续窗口组成：

| 窗口 | 时长 | 行为 |
|------|------|------|
| **学习窗口** | $H_s^{\text{study}} \sim \mathcal{U}(4, 10) + \varepsilon,\ \varepsilon \sim \mathcal{U}(-2, 2)$ 小时 | 复习事件以随机间隔 $\Delta t \sim \mathcal{U}(t_{\min}, t_{\max})$ 发生，其中 $t_{\min} \sim \mathcal{U}(0.05, 0.3)$，$t_{\max} \sim \mathcal{U}(0.5, 2.0)$。每次选 $B=6$ 道题。睡前 2 小时内的复习享有 $\times 1.3$ 的扩散增强 |
| **睡眠窗口** | $24 - H_s^{\text{study}}$ 小时 | 无主动复习。发生被动遗忘（稳定性衰减）和疲劳恢复 |
| **考试事件**（每 20 天） | 即时 | 从 $\mathcal{C}_s$ 中随机抽取 20 个 KP 强制复习，评分噪声减半（$\sigma = 0.05$），考后稳定性额外增强 $\times 1.05$ |

每日结束记录 snapshot：$\bar{R}(d) = \frac{1}{|\mathcal{C}_s|} \sum_{i \in \mathcal{C}_s} R_i(t_d)$。

### 9.6 前置依赖与知识覆盖

知识图 $G = (V, E)$ 定义 KP 节点间的偏序关系。

**前置约束**：每个 SEC 组内的 KP 按编号排序。前 2 个 KP 无前置依赖；第 $k$ 个 KP（$k \geq 3$）的前置集合为该组前 2 个 KP。KP $j$ 可解锁当且仅当其所有前置 KP 已掌握（$S_i > 7$）。

**知识覆盖**：$\mathcal{C}_s$ 由均匀选取 40%—80% 的 SEC 组及其下属 KP 构成。学生只接触 $\mathcal{C}_s$ 内的 KP，其余 KP 在本次仿真中不可见。

**图边**：除树结构边（父子权重 0.8、兄弟权重 0.3）外，在 heavy 模式下额外注入 $\approx 100$ 条随机跨 SEC 边，权重 $\sim \mathcal{U}(0.12, 0.25)$，模拟 LLM 生成的语义关联或数据驱动的共现关系。

### 9.7 学生类型参数化

| 类型 | $\phi_1$ (学习速率) | $\phi_2$ (遗忘曲线 $k$) | $\phi_3$ (巩固效率) | 疲劳 $k_F$ | 模拟的学习者画像 |
|------|-------------------|------------------------|--------------------|-----------|-----------------|
| steady (稳健型) | 0.8 ± 0.15 | 1.0 ± 0.1 | 0.5 ± 0.1 | 0.10 | 规律复习、遗忘适中 |
| fast (速成型) | 1.2 ± 0.15 | 1.3 ± 0.1 | 0.7 ± 0.1 | 0.15 | 学得快、初期忘得快、巩固强 |
| crammer (突击型) | 0.9 ± 0.15 | 0.5 ± 0.1 | 0.4 ± 0.1 | 0.30 | 考前集中、快速遗忘、易疲劳 |
| struggle (困难型) | 0.4 ± 0.15 | 0.6 ± 0.1 | 0.3 ± 0.1 | 0.25 | 学习困难、遗忘持续、巩固弱 |

### 9.8 图扩散调度协议

**独立调度 baseline**：纯 urgency 排序 $u_i = 1 - R_i(t)$，选择 $u_i$ 最大的 $B$ 个 KP。

**图扩散调度**：加权融合 $\text{score}_i = \alpha \cdot u_i + (1-\alpha) \cdot \sum_{j \in \mathcal{N}(i)} w_{ij} \cdot \max(0, 1-R_j(t))$，其中 $\mathcal{N}(i)$ 为 $i$ 的一阶邻居集合。

**扩散执行**：复习 $i$ 后，对每个邻居 $j \in \mathcal{N}(i)$，$S_j \leftarrow S_j \cdot (1 + \beta \cdot w_{ij} \cdot \phi_3^{(s)} \cdot \gamma)$，其中 $\gamma = 1.3$ 若距睡眠窗口 $< 2$ 小时，否则 $\gamma = 1.0$。

### 9.9 仿真规模与统计方法

**Phase 0 light**（已完成）：200 学生 × 120 天 × 2 调度器，仅树边 + 严格前置。36 组 (α, β) 配对检验。

**Phase 0 heavy**（已完成）：400 学生 × 150 天 × 3 调度器（贪心、FSRS、Field），树边 + 随机跨 SEC 边 + 放宽前置 + 周期性考试事件。36 组 (α, β) 全因子设计。

**Phase 0 heavy 验证**（已完成）：400 学生 × 150 天 × 3 调度器，与 heavy 同配置独立复现。两次仿真最优参数完全一致 (α=0.60, β=0.20)。

**总计**：61,200 学生·月仿真数据，108 组独立参数对比。

**效果量**：$\Delta_{\alpha,\beta} = \bar{R}_{\text{field}}(T) - \bar{R}_{\text{ind}}(T)$，其中 $T$ 为仿真总天数。报告 95% CI 和 Cohen's d。两组学生覆盖范围和类型分布配对一致，消除分配偏差。

**参数扫描范围**：$\alpha \in \{0.95, 0.90, 0.85, 0.80, 0.70, 0.60\}$，$\beta \in \{0.01, 0.02, 0.05, 0.10, 0.15, 0.20\}$，全因子设计（36 个处理水平）。

---

## 10. 架构约束

- KnowledgePoint 树结构不变——树是内容组织，图是认知地图，各司其职
- `UserQuestionStatus` 模型不变——stability/difficulty/reps/lapses 维持现有语义
- 调度管线入口不变——`build_adaptive_question_ids` 接口签名不变，内部加 re-rank 步骤
- 所有新逻辑受 feature flag 控制——可以随时回退到当前行为
- 不碰四层架构边界——Memorix 层内部演进，不溢出到教育闭环/测评引擎
