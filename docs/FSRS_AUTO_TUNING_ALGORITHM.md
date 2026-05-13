# FSRS 参数自动调优算法设计 (FSRS Auto-Tuning Algorithm)

## 1. 背景与动机 (Motivation)

在现有的教育平台中，我们引入了 FSRS (Free Spaced Repetition Scheduler) 算法来计算知识点的记忆留存率 (Retrievability) 和稳定性 (Stability)。然而，不同用户的记忆天赋、学习习惯以及不同学科（如 431 金融学综合中的计算题与概念题）的记忆曲线差异巨大。

默认的 FSRS 权重 (Weights) 是一组基于海量开源数据（如 Anki）预训练的全局参数，它无法实现“千人千面”。
本算法旨在实现 **FSRS 参数的个性化自动调优 (Auto-Tuning)**，使其能够根据用户真实的复习日志 (Review Logs)，动态演化出一套最适合该用户当前状态的权重参数。

此过程类似于一种“自我进化”，不仅能有效降低整体遗忘率，该算法管线本身也是一个极具工程价值和学术价值的亮点。

---

## 2. 核心算法思想 (Core Concept)

FSRS 的本质是一个非线性动态系统，它接收用户的复习历史，输出对下一次召回率的预测。
自动调优的目标是：**最小化预测召回率与实际召回率（通过复习得分体现）之间的误差。**

### 2.1 损失函数 (Loss Function)

我们可以将 FSRS 视为一个机器学习模型。定义损失函数 $L$ 为**对数损失 (Log Loss / Cross Entropy)** 或 **均方误差 (RMSE)**：

$$ RMSE = \sqrt{ \frac{1}{N} \sum_{i=1}^{N} (R_{predict}^{(i)} - R_{actual}^{(i)})^2 } $$

其中：
- $N$ 为该用户积累的历史复习记录条数。
- $R_{predict}^{(i)}$：在第 $i$ 次复习时，当前 FSRS 权重预测的记忆留存率 (0.0 ~ 1.0)。
- $R_{actual}^{(i)}$：第 $i$ 次复习的实际结果。如果用户答对（Recall=Hard/Good/Easy），则视为 1.0；如果答错（Recall=Again），则视为 0.0。

### 2.2 优化方法 (Optimization Method)

由于 FSRS 的状态转移方程是确定且可导的（或可通过自动微分求解），我们可以使用以下算法寻找最优权重：
1. **随机梯度下降 (SGD / Adam)**：如果使用 PyTorch/TensorFlow 重写公式，可以通过反向传播直接优化 17 个（或最新版本的）参数。
2. **SciPy 优化器 (L-BFGS-B / Nelder-Mead)**：在 Python 中，使用 `scipy.optimize.minimize` 直接最小化损失函数，这是目前 FSRS 官方优化器常用的做法。

---

## 3. 系统架构与数据流 (Architecture & Data Flow)

该过程应该是**后台异步且自动化**的，避免阻塞主业务逻辑。

### 3.1 数据准备阶段 (Data Preparation)
1. **数据源**：从数据库（如 `ReviewLog` 表）中提取用户的复习历史。
2. **数据清洗**：
   - 过滤掉跨度过短的重复复习（例如同一天内连续复习 5 次，只保留最后一次有效结果）。
   - 按知识点/题目 (Card) 分组，并按时间戳排序，构建完整的复习时间线 (Time Series)。
3. **数据阈值**：只有当用户的有效复习记录大于 $N_{min}$（例如 300 条）时，才触发首次个人参数调优。

### 3.2 训练与演化阶段 (Training & Evolution Pipeline)
建立一个名为 **Shadow Simulator (影子模拟器)** 的离线管线：

1. **拉取当前权重**：获取用户的当前个性化参数 $W_{current}$（如果没有，则使用全局默认参数 $W_{default}$）。
2. **执行优化**：
   - 将清洗后的数据输入优化器。
   - 设置参数的上下界（Bounds），防止模型过拟合导致参数崩塌（如初始稳定性不可能小于 0.1）。
   - 迭代计算，输出新参数 $W_{new}$。
3. **指标评估 (Validation)**：
   - 使用交叉验证（如留出最近 10% 的记录作为测试集）。
   - 如果 $W_{new}$ 在测试集上的 Loss 比 $W_{current}$ 低超过某个阈值（如改善 2%），则认为进化成功。

### 3.3 部署阶段 (Deployment)
- 将验证通过的 $W_{new}$ 保存回用户配置表（例如 `UserProfile.fsrs_weights`）。
- 记录此次优化的版本、时间、Loss 改进比例等元数据，形成用户的**参数进化日志**。

---

## 4. 代码模块设计草案 (Code Modules Draft)

### 4.1 数据模型扩展 (`models.py`)

```python
# 用户的个性化 FSRS 参数
class FSRSProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    weights = models.JSONField(default=default_weights)
    last_optimized_at = models.DateTimeField(null=True, blank=True)
    total_reviews_used = models.IntegerField(default=0)
    current_loss = models.FloatField(null=True, blank=True)

# 每一次复习必须留痕
class ReviewLog(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    knowledge_point = models.ForeignKey(KnowledgePoint, ...)
    grade = models.IntegerField(choices=[(1, 'Again'), (2, 'Hard'), (3, 'Good'), (4, 'Easy')])
    review_time = models.DateTimeField(auto_now_add=True)
    elapsed_days = models.FloatField(help_text="距离上次复习过去的天数")
    # 记录当时的系统预测状态，用于对比
    predicted_retrievability = models.FloatField() 
```

### 4.2 核心优化器 (`fsrs_optimizer.py` 草案)

```python
import numpy as np
from scipy.optimize import minimize

class FSRSOptimizer:
    def __init__(self, review_data, current_weights):
        """
        review_data: List of List/Dict, e.g., 
        [
            [ {grade: 3, elapsed_days: 0}, {grade: 2, elapsed_days: 1.5}, ... ], # Card 1
            [ {grade: 1, elapsed_days: 0}, {grade: 3, elapsed_days: 0.5}, ... ]  # Card 2
        ]
        """
        self.data = review_data
        self.weights = current_weights

    def _simulate_history(self, weights, card_history):
        # 按照 FSRS 状态转移方程，根据给定的 weights 模拟某张卡片的历史
        # 返回一个列表，包含每一次复习前的预测留存率 [R_pred1, R_pred2, ...]
        pass

    def loss_function(self, weights):
        loss = 0.0
        count = 0
        for card_history in self.data:
            predictions = self._simulate_history(weights, card_history)
            for i, log in enumerate(card_history):
                if i == 0: continue # 第一次没有预测
                actual_r = 1.0 if log['grade'] > 1 else 0.0
                pred_r = predictions[i]
                # 计算 RMSE 或 LogLoss
                loss += (actual_r - pred_r) ** 2
                count += 1
        return np.sqrt(loss / count) if count > 0 else float('inf')

    def optimize(self):
        bounds = [(0.01, 10.0)] * len(self.weights) # 设定参数合法边界
        res = minimize(
            self.loss_function, 
            x0=self.weights, 
            method='L-BFGS-B', 
            bounds=bounds
        )
        if res.success:
            return res.x.tolist(), res.fun
        return None, None
```

### 4.3 Celery 定时任务 (`tasks.py`)

```python
@shared_task
def auto_tune_fsrs_for_all_users():
    users = User.objects.all()
    for user in users:
        # 获取用户最近的 ReviewLogs
        logs = get_review_logs(user)
        if len(logs) > 300: # 达到触发阈值
            optimizer = FSRSOptimizer(logs, current_weights)
            new_weights, new_loss = optimizer.optimize()
            if new_weights and new_loss < current_loss:
                update_user_fsrs_weights(user, new_weights)
```

---

## 5. 后续演进路线 (Future Roadmap)

1. **第一阶段**：实现算法骨架与离线 Markdown/Jupyter 测试，跑通 SciPy 优化流程。
2. **第二阶段**：与 Django/Celery 集成，开启系统夜间定时自进化。
3. **第三阶段**：引入**跨维度多参数组**。不同学科（宏观经济 vs 微观经济）、不同题型（选择题 vs 计算题）可能需要不同的 FSRS 权重。系统将自动对 `ReviewLog` 进行聚类，为用户生成多套特化权重。
4. **第四阶段**：数据看板。在用户前端展示其“记忆进化曲线”，让用户直观地看到 AI 在不断地适应他们的学习节奏。
