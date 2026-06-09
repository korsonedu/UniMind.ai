# Phase 0 Plan — Memorix-Field 离线验证

> 状态：启动 | 预估：3-5 人日 | 产出：β 估计值 + 模拟对比 → 决策是否进入 Phase 1

## 任务清单

| # | 任务 | 产出 | 预估 |
|---|------|------|------|
| 1 | 从 KnowledgePoint 树构建初始 L 矩阵 | 邻接表 + L (scipy sparse) | 0.5 人日 |
| 2 | 从 ReviewLog 提取转移对，估计 β | β 估计值 ± 置信区间 | 1 人日 |
| 3 | 离线模拟：独立调度 vs 图扩散调度 | retention 曲线对比 | 1 人日 |
| 4 | 汇总报告：β 显著性 + 模拟结果 + 决策建议 | 1 页报告 | 0.5 人日 |

## 关键判定

- β 显著非零（p < 0.05）→ 进入 Phase 1
- β ≈ 0 或置信区间覆盖 0 → 图扩散假说不成立，停止
- β 显著但效应量小（< 5% retention 提升）→ 降级为低优先级，先做方向 2/3

## 数据依赖

- KnowledgePoint（含 parent 外键 + subject 字段）
- ReviewLog（user, knowledge_point, grade, review_time, elapsed_days）
- 生产数据库（47.104.77.217），只读查询
