# AI 出题多智能体对抗管线 (ARC Pipeline)

## 1. 架构概览

4 个 AI Agent 迭代博弈，生成高质量题目：

```
Author → Reviewer → AuthorRevise → Classifier
  ↑                       ↓              │
  └─── 最多 3 轮迭代 ──────┘              │
                                          ▼
                                    审核队列 →
                                     批次多样性报告
```

**实现位置**: `backend/quizzes/services/adversarial_pipeline.py`

## 2. 角色定义

### A — Author（出题专家）
- **模型**: v4-flash, structured_output
- **职责**: 根据知识点 + 人工指定的目标难度和题型生成候选题目
- **约束**: `difficulty_level` 锁定为人工外生输入，AI 不得自行偏离
- **输出**: `AUTHOR_OUTPUT_SCHEMA` → questions[]

### R — Reviewer（教学质量审查）
- **模型**: v4-pro + thinking(high), simple_chat_text（唯一开 thinking 的任务）
- **职责**: 从 3 个维度审查题目教学质量（不审计难度——那是 Classifier 的职责）
  1. **discrimination（区分度）**: 是否能有效区分掌握者和未掌握者
  2. **clarity（表述清晰度）**: 题干是否无歧义，选项是否互斥
  3. **coverage（知识覆盖度）**: 是否准确命中目标知识点的核心内容
- **评分**: `score = (discrimination + clarity + coverage) / 3`
- **门禁**: score < 0.7 → 退回 AuthorRevise；任一维度 < 0.4 → 硬性不通过
- **最多 3 轮迭代**

### AuthorRevise（修改专家）
- **模型**: v4-flash, structured_output
- **职责**: 根据 Reviewer 反馈逐条修改题目（表述不清、偏离知识点等）
- **注意**: 不修改难度（难度由人工外生锁定）

### C — Classifier（审计专家）
- **模型**: v4-flash, structured_output
- **职责**: 三层审计——管线中唯一做难度合规检测的 Agent
  1. **答案正确性**: 客观题正确选项是否确实正确？主观题参考答案是否有事实错误？
  2. **认知层级与难度合规**: Bloom 认知层级（6 级）+ 实际难度 vs 目标难度
  3. **知识标签与题型分类**: 从全学科 KP 树中选出题目实际涉及的知识点（可跨知识点）
- **输出**: `CLASSIFIER_OUTPUT_SCHEMA` → detected_difficulty, difficulty_match, bloom_level, answer_correct, knowledge_tags, question_type
- **批次报告**: 全部单题审计后，生成批次多样性报告（相似题目检测 + 知识覆盖缺口 + 整体评价）

## 3. 难度外生控制

难度由人工在前端选择（entry/easy/normal/hard/extreme），贯穿全管线：

| 难度 | 定义 |
|------|------|
| entry | 概念识记，纯记忆型，单步结论 |
| easy | 基础理解 + 1-2 步直接推理，干扰项较弱 |
| normal | 概念+情境结合，2-3 步推理，干扰项有迷惑性 |
| hard | 跨章节或多模型联动，≥3 步严谨推理，干扰项高相似 |
| extreme | 高压综合题，模型选择/条件变化/现实约束，需严密论证 |

AI 不得自行决定或修改难度。Classifier 检测到难度偏离时标记 `difficulty_match=false`，但不自动拒绝——进入人工审核队列。

## 4. 关键配置

- `MAX_ITERATIONS = 3`: Reviewer→AuthorRevise 最多迭代 3 轮
- `QUALITY_THRESHOLD = 0.7`: Reviewer 通过分数线

## 5. 代码结构

```
backend/
├── quizzes/services/adversarial_pipeline.py  # 管线核心逻辑
├── ai_engine/tools.py                        # JSON Schema 定义（4 个 Agent + 批次报告）
├── ai_engine/config.py                       # 模型路由（pipeline.* 前缀）
├── ai_engine/service.py                      # structured_output / simple_chat_text
└── prompts/pipeline/                         # Prompt 模板
    ├── author_generate.txt
    ├── reviewer_adversarial.txt
    ├── classifier.txt
    └── reviewer_single.txt

frontend/
└── src/pages/maintenance/PipelinePanel.tsx   # 出题中心 UI（难度选择器+预览+审核）
```
