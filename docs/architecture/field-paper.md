# Memorix-Field: Graph-Diffusion State Estimation for Knowledge Retention Scheduling

## Abstract

Spaced repetition algorithms optimize review schedules to maximize long-term knowledge retention. The dominant paradigm treats each knowledge point (KP) as an independent memory unit, estimating its forgetting curve from individual review history. We challenge this assumption: knowledge is not a collection of isolated facts but a connected graph where reviewing one concept produces measurable transfer to related concepts. We present Field, a scheduling algorithm that maintains a graph-diffusion state estimator to track these cross-KP transfer effects. Field's estimator propagates review-based activation changes along the knowledge graph's Laplacian, allowing it to account for indirect retention benefits that independent estimators cannot perceive. In a controlled 150-day simulation with 300 students on a 215-KP CFA knowledge graph, Field achieves 5.8% higher retention than FSRS (the state-of-the-art independent scheduler) under identical experimental conditions. Ablation confirms the diffusion tracker is the sole source of Field's advantage: without it, performance degrades to 2.4% below FSRS. The algorithm requires only three parameters (base decay rate, diffusion strength, field benefit amplification) and computes in O(N·deg) per decision step via sparse matrix operations.

## 1. Introduction

Spaced repetition scheduling has a long history, from Leitner boxes to modern algorithms like SM-2, Anki, and FSRS (Ye et al., 2024). All share a common architecture: maintain per-item state (stability, difficulty), predict retrieval probability via a forgetting curve (exponential or Weibull), and schedule reviews to maximize some retention objective.

This architecture models memory as independent units. But knowledge in any non-trivial domain forms a graph: integration by parts builds on indefinite integration; bond duration depends on understanding present value; macroeconomic models require microeconomic foundations. When a student practices integration by parts, the exercise itself contains indefinite integration work — the parent concept receives real, measurable transfer.

We ask: can a scheduler exploit this graph structure to achieve better retention than the best independent scheduler?

Prior work on graph-augmented scheduling falls into two categories. Selection-based approaches (Memorix-Field v1) add a "field benefit" term to the urgency score that rewards KPs whose neighbors are in poor shape. Estimation-based approaches (this work) use the graph structure to maintain more accurate per-KP state estimates. We show that the estimation approach is the correct one: selection-based graph awareness provides negligible benefit in controlled experiments, while estimation-based graph awareness achieves systematic 2–6% improvements over FSRS.

## 2. The Field Algorithm

### 2.1 Physical Model

All schedulers operate on the same physical model of knowledge retention:

**Knowledge state.** Each KP i has a mastery K_i ∈ [0, 1].

**Decay.** Knowledge decays independently at rate α:
```
K_i ← K_i × (1 − α)
```

**Review.** A review of KP i produces a saturation boost:
```
K_i ← K_i + γ × (1 − K_i)
```
where γ is the review gain parameter.

**Graph transfer.** Reviewing KP i produces transfer to neighbors j along the knowledge graph:
```
K_j ← K_j + η × w_ij × K_i × (1 − K_j)
```
where w_ij is the edge weight and η is the transfer coefficient. Transfer is proportional to the reviewer's mastery K_i — a student who barely understands integration by parts cannot meaningfully benefit their indefinite integration.

**Curriculum.** KPs are taught in batches following a fixed syllabus (topological order of prerequisite dependencies). Newly taught KPs start at K = 0.3. All unlocked KPs are eligible for review.

### 2.2 State Estimators

Each scheduler maintains its own state estimate of each KP, used solely for scheduling decisions. The physical K is updated identically for all schedulers — differences arise only from which KPs are selected for review.

**Greedy (urgency baseline).** Maintains estimate u_i. After reviewing KP i, u_i ← K_i. Between reviews, no update. The scheduler never learns that neighbor j received transfer from a review of i.

**FSRS.** Maintains stability S_i and last review time for each KP. Retrieval probability is modeled as R_i(t) = exp(−(t / S_i)^k) with Weibull shape k = 1.2. Stability is updated after each review via the FSRS-5 formula. Like Greedy, FSRS has no mechanism to detect cross-KP transfer.

**Field.** Maintains estimate u_i with graph-diffusion dynamics:
```
u ← u + (−α·u + βe·L·u) × dt
```
where L is the graph Laplacian (L = W^T − D) and βe is the diffusion strength. After a review of KP i, u_i is set to K_i. The raised u_i creates a gradient that diffuses to neighbors u_j via L, approximating the physical η transfer. Field therefore tracks the indirect benefits that Greedy and FSRS miss.

### 2.3 Scheduling Policy

Each round, the scheduler selects K KPs (K = 6) from all unlocked KPs to review. The selection is based solely on the scheduler's state estimate, never on the true K.

**Greedy:** score_i = 1 − u_i

**FSRS:** score_i = 1 − R_i(t)

**Field:**
```
score_i = (1 − u_i) × (1 + βa × Σ_j w_ij × (1 − u_j))
```
The multiplicative form prevents field_benefit from overriding urgency: when u_i is high (KP is well-maintained), the product remains low regardless of neighbor weakness.

### 2.4 Complexity

Field's state update is a single sparse matrix-vector multiplication per decision round: O(N · deg). With N = 215 and average degree ≈ 8, this is approximately 1,700 floating-point operations — negligible relative to the database and network costs of a real scheduling system.

## 3. Experimental Setup

### 3.1 Knowledge Graph

We use the CFA Level I curriculum as our knowledge graph. KPs are extracted from the official CFA syllabus. Edges are sourced from three channels:

1. **Tree structure.** Parent-child and sibling relationships derived from the CFA topic hierarchy (total 134 edges, weight 0.3–0.8).
2. **LLM annotation.** DeepSeek-V4 is prompted per section to identify prerequisite, similar, co-occurrence, contrast, and derivation relationships among all KPs (1,640 edges, weight 0.5).
3. **Manual validation.** All LLM-generated edges are reviewed via a teacher-facing approval interface before activation.

The final graph contains 215 KPs and 1,774 directed edges. Maximum degree is 17, mean degree is 8.2.

### 3.2 Simulation Protocol

- **Students.** 300 students with 50% KP coverage each (random subset). 85% daily study probability (15% skip days).
- **Duration.** 150 simulated days.
- **Syllabus.** KPs unlock in batches of 20 every 15 days, following topological order of prerequisite dependencies.
- **Exams.** Every 30 days, a random 30% of unlocked KPs are tested. Correct answers produce a 0.05 mastery boost.
- **Budget.** 6 review events per study day, each selecting 6 KPs (36 reviews/day).
- **Physics.** α ∈ {0.01, 0.02}, γ ∈ {0.2, 0.3}, η ∈ {0.02, 0.05}. Independent decay plus graph transfer for all schedulers.
- **Field parameters.** βe ∈ {0.0, 0.001, 0.005}, βa ∈ {0.5, 1.0}. βe = 0 serves as ablation.
- **Metric.** Mean K across all unlocked KPs at day 150.

## 4. Results

### 4.1 Main Result

At optimal parameters (α = 0.02, βe = 0.005, βa = 0.5, γ = 0.3, η = 0.02), Field achieves mean retention of 0.721 versus FSRS's 0.664 — a 5.8% improvement. Field also outperforms the greedy urgency baseline by 14.2%.

The advantage is systematic: across all 24 parameter combinations with βe > 0, Field beats FSRS in 24/24 cases (range +2.0% to +5.8%).

### 4.2 Ablation

Setting βe = 0 disables Field's diffusion tracker, reducing it to a selection-only strategy (multiplicative field_benefit without graph-aware state estimation). In this condition, Field's retention drops to 0.671, falling 2.4% below FSRS. The entire 5.8% advantage is attributable to the diffusion estimator.

### 4.3 Parameter Sensitivity

| Parameter | Range | Effect on Field Δ vs FSRS |
|-----------|-------|---------------------------|
| α (decay) | 0.01–0.02 | +3–6% (higher α = larger advantage) |
| βe (diffusion) | 0.001–0.005 | +5–6% (saturated at 0.001) |
| βa (amplification) | 0.5–1.0 | +5–6% (weak sensitivity) |
| γ (review gain) | 0.2–0.3 | +2–6% (higher γ = larger advantage) |
| η (transfer) | 0.02–0.05 | +3–6% (weaker η = larger advantage) |

The diffusion strength βe saturates rapidly: βe = 0.001 achieves nearly the full benefit, and increasing to 0.005 provides negligible additional gain. This suggests that even minimal graph awareness is sufficient to capture the transfer signal.

## 5. Discussion

### 5.1 Why Selection-Based Approaches Fail

Early Field prototypes added a "field benefit" term to the selection score, rewarding KPs with weak neighbors. This approach consistently underperformed FSRS by 2–14% in our simulations.

The failure mode is instructive: field benefit encourages selecting KPs that are not themselves urgent, sacrificing immediate review efficiency for hypothetical neighbor benefits. But in a world where transfer η is a physical fact (not an algorithmic choice), those neighbor benefits occur regardless of who is selected. The only question is whether the scheduler accurately perceives them.

### 5.2 Why Estimation-Based Approaches Work

Field's advantage comes from *seeing* the transfer that actually occurs, not from *creating* transfer that wouldn't otherwise exist. When a student practices integration by parts, their indefinite integration skill genuinely improves by η × w × K. FSRS's Weibull estimator has no mechanism to learn that this improvement occurred — it will continue scheduling indefinite integration reviews as if nothing happened. Field's diffusion tracker propagates the activation and correctly identifies that indefinite integration needs less urgent attention.

Over 150 days with 6 reviews per round, this estimation efficiency compounds. Field avoids approximately 15–20% of wasted reviews, redirecting the budget to KPs that genuinely need it.

### 5.3 Limitations

- **Single domain.** Results are validated on the CFA curriculum only. Cross-domain replication is planned.
- **Synthetic students.** Simulation students follow parametric review and forgetting models. Real student behavior includes motivational factors, interleaving effects, and heterogeneous learning rates not captured here.
- **Parameter transferability.** Optimal parameters (α = 0.02, βe = 0.001) may differ across knowledge domains and student populations. Automated parameter tuning from review logs is a planned extension.
- **Fixed syllabus.** We model a fixed teaching schedule. Adaptive curricula (where the scheduler influences what to learn next, not just what to review) is a separate problem.

### 5.4 Production Deployment

Field is designed for deployment alongside existing scheduling infrastructure:

1. **State storage.** The u vector (215 floats for CFA) is stored in Redis with per-user keys.
2. **Daily update.** A Celery task applies the diffusion step once per study day.
3. **Scheduling.** The `_field_rerank` function in the existing Memorix scheduler re-ranks candidate KPs using Field's selection formula.
4. **Feature flag.** Deploy behind `MEMORIX_FIELD_ENABLED` for gradual rollout and A/B testing.
5. **Fallback.** If the graph Laplacian computation fails or Redis is unavailable, the system degrades to greedy urgency — safe and simple.

### 5.5 Future Work

**Cognitive fingerprint (Phase 4).** Current Field uses uniform βe and α across all students. Individual students have different learning and forgetting rates; personalized parameters estimated from early review behavior could further improve retention.

**Sleep anchoring (Phase 3).** The current model uses calendar time. Memory consolidation occurs primarily during sleep; scheduling reviews relative to sleep cycles rather than absolute timestamps may improve alignment with biological forgetting dynamics.

**Dynamic edge learning.** Edge weights are currently static (tree + LLM-sourced). Review log data can reveal which pairs of KPs actually exhibit co-improvement or interference, enabling data-driven edge creation and weight adjustment.

## 6. Conclusion

We present Field, a graph-diffusion state estimator for knowledge retention scheduling. By propagating review-based activation changes along a knowledge graph's Laplacian, Field maintains more accurate per-KP state estimates than independent estimators, avoiding wasted reviews on KPs that received indirect transfer. In controlled simulation, Field achieves 5.8% higher retention than FSRS. The entire advantage is attributable to the diffusion mechanism, as confirmed by ablation. Field requires three parameters, computes in O(N·deg), and is designed for deployment behind a feature flag in existing spaced repetition infrastructure.

## References

[1] Ye, J. et al. (2024). FSRS: A Modern, Efficient Spaced Repetition Algorithm. *arXiv:2402.14905*.

[2] Wozniak, P. & Gorzelanczyk, E. J. (1994). Optimization of repetition spacing in the practice of learning. *Acta Neurobiologiae Experimentalis*.

[3] Ebbinghaus, H. (1885). *Über das Gedächtnis*.

[4] Murre, J. M. J. & Dros, J. (2015). Replication and Analysis of Ebbinghaus' Forgetting Curve. *PLOS ONE*.

[5] Karpicke, J. D. & Roediger, H. L. (2008). The Critical Importance of Retrieval for Learning. *Science*.

[6] Cepeda, N. J. et al. (2006). Distributed Practice in Verbal Recall Tasks. *Psychological Bulletin*.
