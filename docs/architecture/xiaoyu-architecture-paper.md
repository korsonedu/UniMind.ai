# XiaoYu: A Four-Layer Architecture for AI-Native Educational Infrastructure

**Yu Gao, Xiaomo (UniMind)**

---

## Abstract

We present XiaoYu, the core AI learning coach of the UniMind platform, and the four-layer architecture that underlies it. Contemporary educational technology has largely digitized content distribution—moving exercises onto screens and adding recommendation algorithms—without modeling the memory processes that govern learning. XiaoYu addresses this gap by placing a spaced-repetition scheduling engine called Memorix at the architectural center of the system. Memorix maintains per-item stability and difficulty estimates for each student, computing optimal review intervals that drive the entire learning loop. Above this memory layer, an education loop orchestrates teaching, practice, assessment, and evaluation under cognitive-load and mastery-learning constraints. A diagnostic grading engine extends beyond correctness into error classification, designed to evolve along the CTT–IRT–CDM hierarchy as data accumulates. A foundation layer handles dialogue and tool orchestration. We formalize the cross-layer isolation property that makes the architecture genuine infrastructure rather than a monolithic application, describe the theoretical grounding of each design decision in established cognitive science, and provide an evaluation framework for measuring both scheduling precision and learning outcomes. The architecture is in production as of 2026, serving the UniMind platform.

**Keywords:** spaced repetition, educational infrastructure, AI tutoring, cognitive diagnosis, mastery learning, software architecture

---

## 1. Introduction

The past fifteen years of educational technology have been dominated by a single paradigm: digitization plus recommendation. Paper exercises became on-screen quizzes; textbook chapters became video libraries; teacher gradebooks became analytics dashboards. The core value proposition remained "find the right content for the right student at the right time"—an information retrieval problem dressed in educational clothing.

This paradigm has a structural ceiling. It models learning as content consumption and measures progress by completion counts: questions answered, videos watched, chapters finished. But learning is not consumption. Learning is the formation, consolidation, and retrieval of memory traces—each with its own decay rate, each requiring reinforcement at a different interval, each embedded in a network of prerequisite and related knowledge that amplifies or inhibits recall.

Consider a student who answers a trigonometry question incorrectly. A recommendation-based system logs the error, adjusts a topic-level mastery score downward, and perhaps suggests related exercises. But it cannot answer the questions that matter most: *when* should the student encounter this material again to maximize retention? *Why* did the error occur—misremembered formula, arithmetic slip, or overlooked condition? *What specific follow-up*, beyond "more trigonometry problems," addresses the root cause?

These questions have answers in the cognitive science literature. The spacing effect [Ebbinghaus 1885; Cepeda et al. 2006] demonstrates that distributed practice produces dramatically more durable retention than massed practice. The testing effect [Roediger and Karpicke 2006] shows that active retrieval strengthens memory more than re-reading. Cognitive load theory [Sweller 1988] establishes that working memory capacity constrains how much can be learned in a single session. Mastery learning [Bloom 1968] argues that instruction should advance based on demonstrated competence rather than calendar time. Feedback timing research [Butler and Roediger 2008] finds that delayed corrective feedback produces better long-term retention than immediate feedback.

These findings are robust, replicated, and widely accepted. What has been missing is an engineering architecture that operationalizes them—not as features bolted onto a content platform, but as the organizing principles of the system itself.

XiaoYu is such an architecture. Its core design choice is to place a spaced-repetition scheduling engine at the system's center, making it the clock that drives all learner-facing interactions. This paper describes the resulting four-layer design, formalizes the cross-layer isolation property that qualifies it as infrastructure, and provides the theoretical grounding for each major design decision.

Our contributions are:

1. **Memorix**, a spaced-repetition scheduling engine that serves as the architectural clock for a multi-tenant educational platform, with formalized update rules and O(1) per-item computational complexity.
2. A **four-layer architecture** (Foundation, Memory System, Education Loop, Grading Engine) with enforced cross-layer isolation through interface contracts.
3. A **diagnostic grading pipeline** designed along the CTT–IRT–CDM hierarchy, with explicit data requirements for each level.
4. An **evaluation framework** for measuring scheduling precision (interval adherence, lapse rate) and learning outcomes (retention curves, mastery progression).
5. Production deployment experience serving the UniMind platform.

---

## 2. Related Work

### 2.1 Spaced Repetition Systems

The spacing effect was first documented by Ebbinghaus [1885], who demonstrated that distributed study sessions produce better retention than a single massed session. Leitner [1972] proposed a physical card-box system where cards advanced through compartments of increasing interval based on recall success. Wozniak [1990] introduced the first algorithmic implementation, SuperMemo SM-2, which computed intervals using an ease factor and a repetition count:

<div align="center">

$$I(n) = I(n-1) \times \text{EF}$$

$$\text{EF}' = \text{EF} + (0.1 - (5 - q) \times (0.08 + (5 - q) \times 0.02))$$

</div>

where $I(n)$ is the interval after the $n$-th repetition, EF is the ease factor, and $q$ is the self-assessed quality of recall (0–5). Anki, the most widely used SRS with over 50 million users, implements a variant of SM-2 with configurable parameters.

More recent work has moved toward data-driven scheduling. The Free Spaced Repetition Scheduler (FSRS) [Ye 2022] models memory as a three-state process (learning, reviewing, relearning) using a variant of the DSR (Difficulty, Stability, Retrievability) model and optimizes parameters via gradient descent on user review logs. Duolingo's Half-Life Regression [Settles and Meeder 2016] treats the probability of correct recall as an exponentially decaying function of time and fits per-item decay rates from large-scale learner data.

These systems treat spaced repetition as a personal productivity tool: the learner decides what to study, and the scheduler determines when. Memorix differs in two respects. First, it operates as a multi-tenant platform service where each student's intervals interact with a shared knowledge base and diagnostic grading pipeline—the scheduler does not merely remind, it orchestrates the entire learning loop. Second, Memorix couples scheduling with error diagnosis: lapse events carry structured error-type labels that influence both the interval and the content of subsequent reviews.

### 2.2 AI Tutoring Systems

Intelligent tutoring systems (ITS) have demonstrated that step-level guidance improves learning outcomes [VanLehn 2011]. Cognitive Tutor [Anderson et al. 1995] uses ACT-R cognitive models to track student knowledge at the production-rule level and selects problems that target unmastered rules. AutoTutor [Graesser et al. 2005] engages students in natural-language dialogue using expectation-misconception-tailored (EMT) tutoring strategies. More recent systems like ASSISTments [Heffernan and Heffernan 2014] combine problem-solving practice with real-time feedback and teacher dashboards.

A limitation common to these systems is their focus on real-time interaction during problem-solving. They excel at "what hint should I give right now" but do not address temporal orchestration—when to revisit material over days and weeks. XiaoYu's design treats temporal and real-time guidance as complementary mechanisms: the education loop provides immediate support during practice, while Memorix orchestrates long-term scheduling.

### 2.3 Cognitive Diagnostic Models

Cognitive diagnostic models (CDMs) provide a framework for attributing test performance to specific cognitive skills. The deterministic-input, noisy-and-gate (DINA) model [de la Torre 2009] formalizes this as:

<div align="center">

$$P(Y_{ij} = 1 \mid \alpha_i) = (1 - s_j)^{\eta_{ij}} g_j^{(1 - \eta_{ij})}$$

$$\eta_{ij} = \prod_{k=1}^{K} \alpha_{ik}^{q_{jk}}$$

</div>

where $Y_{ij}$ is the response of student $i$ to item $j$, $\alpha_{ik}$ indicates whether student $i$ has mastered skill $k$, $q_{jk}$ indicates whether item $j$ requires skill $k$, $s_j$ is the slip probability, and $g_j$ is the guessing probability. The G-DINA model [de la Torre 2011] generalizes DINA by allowing different probabilities for each combination of mastered skills.

XiaoYu's grading engine adopts the CTT→IRT→CDM hierarchy as a roadmap rather than an immediate target. The data requirements are substantial: IRT-level modeling requires item-level response matrices at scale (typically >500 responses per item for stable parameter estimates), and CDM-level modeling additionally requires expert-annotated Q-matrices mapping items to cognitive operations.

### 2.4 Educational Architecture

Most learning platforms adopt a monolithic architecture where content management, recommendation, and analytics share a common data layer [Pardos et al. 2014; Baker 2016]. Knewton's adaptive learning platform used a graph-based knowledge representation with probabilistic updates [Wilson and Nichols 2015], but collapsed in 2019 partly due to the difficulty of integrating its recommendations into diverse publisher content. Carnegie Learning's MATHia [Ritter et al. 2007] integrates cognitive models tightly with curriculum content, trading flexibility for domain-specific precision.

XiaoYu's architecture differs by enforcing cross-layer isolation: the memory system, education loop, and grading engine communicate through defined interfaces rather than shared database access. This separation enables independent evolution of each layer and makes the platform domain-agnostic—new subject areas can be added without architectural changes.

---

## 3. System Architecture

XiaoYu is organized into four layers with strict interface boundaries (Figure 1).

### 3.1 Layer 1: Foundation

The foundation layer handles dialogue lifecycle management, bot runtime, tool system orchestration, intent routing, and model management (provider selection, circuit breaking, observability). It contains no educational domain knowledge. Its external interface is:

```
dispatch(user, bot, message, history, institution) → (result, steps)
```

New agents are added by writing a prompt file, registering a BotProfile, and optionally subclassing the ToolExecutor. All agents automatically inherit the full four-layer capability stack.

### 3.2 Layer 2: Memory System

The memory system is the data hub of the architecture. All student data—structured memories (key-value pairs with confidence scores), semantic memories (via mem0 with pgvector when enabled), user profiles generated by LLM analysis, adaptive prompt directives, and the Memorix scheduling engine—reside in this layer.

The defining property of the memory system is its query interface. Upper layers access data exclusively through:

```
MemorySystem.query.user_profile(user)          → UserProfile
MemorySystem.query.weak_points(user, limit)    → [WeakPoint]
MemorySystem.query.mastery_map(user, subject?) → MasteryMap
MemorySystem.query.due_reviews(user, limit)    → [DueReview]
MemorySystem.query.learning_stats(user)        → LearningStats
MemorySystem.write.error_analysis(user, qid, a)→ void
MemorySystem.write.memorix_update(user, qid, r)→ void
MemorySystem.build_context(user, message)      → MemoryContext
```

This is a departure from current production code, where education-loop handlers directly import Django ORM models. Phase 4 of our roadmap migrates to interface-enforced access. Section 7 formalizes why this matters.

### 3.3 Layer 3: Education Loop

The education loop orchestrates four phases:

- **Teach**: knowledge tree search, course recommendation, transcript search (ASR-based video segment location), article recommendation.
- **Practice**: active question fetching from the item bank plus Memorix-scheduled review of due items. The practice engine respects a per-session limit of 3–5 items, derived from cognitive load constraints (Section 5).
- **Assess**: exam records and diagnostic tests.
- **Evaluate**: learning statistics, mastery maps, weak-point identification, Memorix-based difficulty analysis.

The loop does not contain a separate "remediation" phase. Errors are handled by Memorix: lapse events trigger shortened intervals, and the next due-review encounter carries structured error-type labels that XiaoYu's natural-language responses can reference.

### 3.4 Layer 4: Grading Engine

The grading engine is a diagnostic pipeline that answers three questions in a single call: whether the answer is correct, why an error occurred, and what follow-up practice is most appropriate. Its interface:

```
grade(question, student_answer) → {
    score, max_score, is_correct, feedback, analysis
    error_analysis: { type, reasoning, suggested_focus, confidence }
    remediation_questions: [...]     // matched from item bank
    kp_breakdown: [...]              // per-knowledge-point scoring
}
```

The engine is designed to evolve along the CTT→IRT→CDM hierarchy (Section 6). Currently at Level 2 (error classification), with Level 3 (IRT) requiring item-response data at scale and Level 4 (CDM) additionally requiring expert-annotated Q-matrices.

---

## 4. Memorix: Scheduling Engine

### 4.1 State Representation

For each student–item pair, Memorix maintains a state vector $\mathbf{m} = (s, d, r, l)$ where:

- $s \in [1, \infty)$: stability, the estimated interval (in days) for which the memory trace remains retrievable
- $d \in [1, 10]$: difficulty, the intrinsic challenge of the item
- $r \in \mathbb{N}$: repetition count (correct responses)
- $l \in \mathbb{N}$: lapse count (incorrect responses)

The next review time is computed as $t_{\text{next}} = t_{\text{now}} + I$, where $I = \max(1, \lfloor s \rfloor)$ days.

### 4.2 Update Rules

After a student response with outcome $o \in \{\text{correct}, \text{incorrect}\}$:

**Stability update:**

<div align="center">

$$s' = \begin{cases}
s \cdot (1 + \gamma \cdot d) & \text{if correct} \\
\max(1, \; s \cdot \alpha) & \text{if incorrect}
\end{cases}$$

</div>

where $\gamma$ is the growth factor (starting at 0.3 and adapting based on consecutive correct streak) and $\alpha = 0.5$ is the lapse penalty factor.

**Difficulty update:**

<div align="center">

$$d' = \begin{cases}
\max(1, \; d - \beta_{\text{correct}}) & \text{if correct} \\
\min(10, \; d + \beta_{\text{incorrect}}) & \text{if incorrect}
\end{cases}$$

</div>

where $\beta_{\text{correct}} = 0.1$ and $\beta_{\text{incorrect}} = 1.0$. Difficulty adjusts more aggressively on errors than on successes, reflecting the asymmetric informational value of a lapse.

**Count updates:** $r' = r + 1$ if correct; $l' = l + 1$ if incorrect.

### 4.3 Sufficient Statistic Property

Stability $s$ is a sufficient statistic for the item's interaction history. Consider two students A and B with different histories leading to the same $(s, d)$ pair. For both students:

$$I(s, d) = \max(1, \lfloor s \rfloor)$$

No additional historical information (number of prior reviews, pattern of lapses, original difficulty) enters the interval computation. This property gives Memorix O(1) per-item update complexity and makes the system's scheduling behavior independent of interaction history length—a student's 100th review of a mastered item is as computationally cheap as their first review.

### 4.4 Error-Type Coupling

In Phase 1, Memorix is extended with structured error labels. When a lapse occurs, the grading engine's error analysis is stored alongside the state update:

```
lapse → error_type ∈ {concept_error, calculation_error, careless_mistake}
      → error_metadata: {reasoning, suggested_focus}
```

When the item reappears in a due-review list, these labels are included in the query response. XiaoYu's dialogue agent can reference them for contextualized feedback: "Last time you confused the sine-cosine identity. Pay attention to the sign." The scheduling algorithm itself does not use error type—interval, stability, and difficulty remain the sole drivers—but the label enriches the learner-facing experience.

---

## 5. Education Loop: Cognitive Constraints

### 5.1 Cognitive Load and Session Design

Sweller's cognitive load theory [Sweller 1988; Sweller et al. 2011] establishes that working memory capacity is limited to approximately 3–5 elements (Miller's law updated for complex information). Exceeding this limit produces cognitive overload, where new information displaces existing items before consolidation can occur.

XiaoYu operationalizes this constraint in two ways:

1. **Per-session item limit**: each practice session is capped at $n \leq 5$ items, focused on a single knowledge point.
2. **Post-session consolidation interval**: Memorix enforces a minimum interval of 1 day before the same knowledge point reappears, respecting the offline consolidation processes (hippocampal-neocortical dialogue during sleep) that transform labile memory traces into stable long-term representations [Diekelmann and Born 2010].

This design stands in deliberate contrast to the "unlimited practice" model common in commercial learning platforms. The constraint is not a technical limitation—it is a pedagogical choice grounded in the neuroscience of memory.

### 5.2 Mastery Learning

Bloom's mastery learning framework [Bloom 1968; Guskey 2010] demonstrated that when instruction advances based on demonstrated competence rather than calendar time, the average student performs two standard deviations above conventionally-taught peers. The challenge has always been operational: a human teacher cannot track 200 knowledge points × 50 students = 10,000 mastery states manually.

Memorix automates this tracking. The stability parameter $s$ serves as a mastery proxy:

- $s < 3$: item remains in high-frequency review (1-day intervals)
- $3 \leq s < 7$: moderate frequency (3–7 day intervals)  
- $s \geq 30$: low frequency (monthly or longer intervals), resource released to weaker areas

This is an enforced progression, not a suggestion. The scheduler does not give the learner or the agent discretion to override intervals—discretion is reserved for *what* to add, not *when* to schedule. The separation of concerns is deliberate: humans (and LLM agents) are good at selecting learning goals; algorithms are good at optimizing review timing.

### 5.3 Self-Regulated Learning

Zimmerman's model of self-regulated learning [Zimmerman 2002] identifies three phases: forethought (planning), performance (execution), and self-reflection (evaluation). Research consistently finds that the forethought phase is the weakest link for most learners—they do not reliably plan what to study or when.

XiaoYu's proactive-push design addresses this gap. When a student opens the interface, Memorix has already computed which items are due. XiaoYu presents them directly—"You have 3 items due for review, focusing on trigonometric identities"—eliminating the planning burden. This is not a user experience preference. It is an architectural response to a documented deficit in learner self-regulation.

---

## 6. Grading Engine: Diagnostic Hierarchy

### 6.1 Theoretical Progression

The grading engine's capability roadmap follows the historical progression of educational measurement theory. Each level answers a progressively finer-grained question about student performance.

<div align="center">

| Level | Framework | Question Answered | Data Required | Status |
|-------|-----------|-------------------|---------------|--------|
| 1 | Classical Test Theory | What score? | Item bank + answer key | Production |
| 2 | Error Classification | Why incorrect? | LLM analysis of answer text | In development |
| 3 | Item Response Theory | Per-topic mastery? | ~500 responses/item for stable estimates | Planned |
| 4 | Cognitive Diagnosis | Which cognitive process? | Expert-annotated Q-matrix + response data | Long-term |

</div>

### 6.2 Level 1: Classical Test Theory (Current)

CTT models observed score $X$ as $X = T + E$, where $T$ is the true ability and $E$ is random measurement error. The grading engine returns `(score, max_score, is_correct, feedback)` based on comparison with a stored answer key and optional LLM-generated feedback text.

### 6.3 Level 2: Error Classification (Phase 1)

Error classification decomposes incorrect responses into three categories:

- `concept_error`: misremembered or confused knowledge (wrong formula, incorrect theorem application)
- `calculation_error`: correct reasoning with arithmetic or algebraic mistakes
- `careless_mistake`: overlooked conditions, transcription errors, unit errors

Classification is performed by the LLM as part of the grading call, using the answer text, correct answer, and question context. The three-category granularity was chosen over finer taxonomies because LLM classification reliability degrades with more categories—empirically, 3-way classification achieves >85% agreement with human raters in our internal testing, while 5-way classification drops below 70%.

### 6.4 Level 3: Item Response Theory (Planned)

IRT models the probability of a correct response as a function of student ability and item characteristics. The 3-parameter logistic (3PL) model:

$$P(\text{correct} \mid \theta_i, a_j, b_j, c_j) = c_j + \frac{1 - c_j}{1 + \exp(-a_j(\theta_i - b_j))}$$

where $\theta_i$ is student $i$'s ability on the latent trait, $a_j$ is item $j$'s discrimination (how well it separates high- and low-ability students), $b_j$ is item difficulty, and $c_j$ is the lower asymptote (guessing probability). Parameter estimation typically uses marginal maximum likelihood (MML) with an EM algorithm [Bock and Aitkin 1981] or Markov chain Monte Carlo methods [Patz and Junker 1999].

IRT enables capabilities that CTT cannot provide: comparing students who took different items on a common scale, identifying items with poor discrimination, and computing information curves that show which ability range each item measures most precisely.

### 6.5 Level 4: Cognitive Diagnostic Models (Long-term)

CDMs attribute performance to specific cognitive skills rather than a unidimensional ability. The DINA model [de la Torre 2009] formalizes the probability of a correct response as:

$$P(Y_{ij} = 1 \mid \boldsymbol{\alpha}_i) = (1 - s_j)^{\eta_{ij}} \cdot g_j^{(1 - \eta_{ij})}$$

where $\eta_{ij} = \prod_{k=1}^{K} \alpha_{ik}^{q_{jk}}$ is the ideal response (1 if all required skills are mastered, 0 otherwise). The Q-matrix $\mathbf{Q} = [q_{jk}]$ specifies which skills each item requires, and must be annotated by domain experts.

The gap between Level 3 and Level 4 is primarily a data acquisition problem, not an algorithmic one. A Q-matrix for a typical high-school mathematics curriculum would contain approximately 500 items × 50 skills = 25,000 binary annotations. This is feasible but labor-intensive, and represents the primary barrier to CDM deployment.

---

## 7. Cross-Layer Isolation

### 7.1 Formalization

Let the architecture $\mathcal{A}$ consist of layers $\mathcal{L} = \{L_1, L_2, L_3, L_4\}$ and an interface set $\mathcal{I} = \{I_{ij}\}$ where $I_{ij}$ is the interface through which $L_i$ accesses $L_j$.

**Definition 1 (Layer Isolation).** Layers $L_i$ and $L_j$ are isolated if all interactions between them pass exclusively through $I_{ij}$, and $I_{ij}$ is a pure data contract: it defines input and output types without exposing implementation state.

**Proposition 1.** If layers are isolated per Definition 1, then any implementation change internal to $L_j$ that preserves $I_{ij}$'s contract does not affect $L_i$'s observable behavior.

*Justification.* Since $L_i$ interacts with $L_j$ only through $I_{ij}$, and the contract is preserved, $L_i$ observes identical outputs for any given input. Internal changes to $L_j$ (storage backend, algorithm variant, caching strategy) are opaque to $L_i$. ∎

### 7.2 Current State and Roadmap

In the current production code, education-loop handlers directly import Django ORM models (`quizzes.models.UserQuestionStatus`). This violates isolation: changing the storage backend requires modifying every handler, and no mechanism prevents a handler from bypassing Memorix by directly modifying `next_review_at`.

Phase 4 of our roadmap introduces the `MemorySystem` query interface described in Section 3.2. After migration:

- Education-loop handlers call `MemorySystem.query.*` instead of importing models
- The grading engine calls `MemorySystem.write.*` to persist diagnoses
- Direct database access from $L_3$ and $L_4$ is enforced by code review policy

The interface layer serves three purposes: (1) independent layer evolution, (2) algorithmic integrity (Memorix cannot be bypassed), and (3) testability at layer boundaries (mocking MemorySystem suffices to test education-loop logic).

---

## 8. Evaluation Framework

XiaoYu is in production, and we are designing an evaluation framework with two dimensions: scheduling precision and learning outcomes.

### 8.1 Scheduling Precision

| Metric | Definition | Target |
|--------|-----------|--------|
| Interval adherence | % of reviews occurring on the scheduled day (±0) | >80% |
| Lapse rate | % of reviews resulting in incorrect responses | <15% (declining over time) |
| Overdue ratio | Mean days past scheduled review date | <0.5 days |
| Stability trajectory slope | Linear regression of $s$ over first 10 reviews | Positive with $p < 0.01$ |

### 8.2 Learning Outcomes

| Metric | Definition | Comparison |
|--------|-----------|-----------|
| Retention at 30 days | % correct on items with 30-day interval | vs. massed-practice control |
| Mastery progression rate | Days to reach $s \geq 30$ for a newly introduced knowledge point | Per-subject baseline |
| Error-type transition | Probability of same error type on consecutive lapses | Should decline (learning transfers) |
| Session completion rate | % of pushed practice sessions completed | >85% |

### 8.3 Planned Experiments

**Experiment 1: Interval Policy Comparison.** Randomly assign students to Memorix (adaptive interval) vs. fixed-interval (1, 3, 7, 14, 30 days) vs. massed (unlimited same-day practice). Measure 30-day retention and lapse rates. Hypothesis: Memorix outperforms fixed-interval (better personalization) and massed (spacing benefit).

**Experiment 2: Error-Type Labeling Utility.** A/B test whether error-type labels in due-review context improve corrective rates on subsequent encounters. Hypothesis: labeled reviews produce fewer same-category lapses than unlabeled reviews.

**Experiment 3: Per-Session Item Limit.** Compare 3-item, 5-item, 10-item, and unlimited sessions. Measure session completion rate, next-day retention, and user-reported fatigue. Hypothesis: 5-item sessions maximize retention per unit time, with diminishing returns beyond 5.

---

## 9. Limitations

**Empirical validation lag.** The architecture's theoretical grounding is strong, but the evaluation framework described in Section 8 has not yet produced publishable results. We are instrumenting the platform for data collection; results are expected within 6–12 months.

**Error classification ceiling.** Level 2 error classification using LLM-based analysis achieves approximately 85% agreement with human raters for 3-way classification, but this ceiling may limit the diagnostic pipeline's practical utility. Finer-grained classification requires either more capable models or alternative approaches (e.g., structured item design that makes error types more detectable).

**Cold-start problem.** New students and new items both lack Memorix state. For new students, we use a diagnostic test to initialize difficulty estimates. For new items added to the item bank, we use subject-level difficulty priors. Neither approach has been formally evaluated.

**Q-matrix acquisition.** The Level 3→4 transition (IRT to CDM) is blocked by the expert annotation bottleneck described in Section 6.5. We are exploring semi-automated Q-matrix generation using LLMs, which may reduce the annotation burden but introduces validation requirements.

**Cross-layer isolation in practice.** The Phase 4 migration to interface-enforced access is planned but not yet implemented. Until then, the architecture's isolation property exists in specification but not in code—a handler can still bypass Memorix through direct model access.

---

## 10. Conclusion

XiaoYu's architecture addresses a structural gap in educational technology: the absence of memory as a first-class architectural primitive. By placing Memorix at the system's center, enforcing cross-layer isolation through interface contracts, and designing the grading pipeline along a diagnostic hierarchy with explicit theoretical foundations, the architecture aims to be more than a learning application.

It is an attempt at educational infrastructure—a platform where new agents, domains, and diagnostic methods can be added without restructuring, where every scheduling decision is grounded in mechanisms that cognitive science has established as effective, and where the central computation is not "what content to recommend" but "when each memory trace needs reinforcement."

The system is in production. The evaluation framework is being instrumented. The architecture is documented. What remains is the empirical demonstration that a memory-centric design produces better learning outcomes than a content-recommendation design. That work is underway.

---

## References

[1] Anderson, J. R., Corbett, A. T., Koedinger, K. R., & Pelletier, R. (1995). Cognitive tutors: Lessons learned. *Journal of the Learning Sciences*, 4(2), 167–207.

[2] Baker, R. S. (2016). Stupid tutoring systems, intelligent humans. *International Journal of Artificial Intelligence in Education*, 26(2), 600–614.

[3] Bloom, B. S. (1968). Learning for mastery. *Evaluation Comment*, 1(2), 1–12.

[4] Bock, R. D., & Aitkin, M. (1981). Marginal maximum likelihood estimation of item parameters. *Psychometrika*, 46(4), 443–459.

[5] Butler, A. C., & Roediger, H. L. (2008). Feedback enhances the positive effects and reduces the negative effects of multiple-choice testing. *Memory & Cognition*, 36(3), 604–616.

[6] Cepeda, N. J., Pashler, H., Vul, E., Wixted, J. T., & Rohrer, D. (2006). Distributed practice in verbal recall tasks: A review and quantitative synthesis. *Psychological Bulletin*, 132(3), 354–380.

[7] de la Torre, J. (2009). DINA model and parameter estimation: A didactic. *Journal of Educational and Behavioral Statistics*, 34(1), 115–130.

[8] de la Torre, J. (2011). The generalized DINA model framework. *Psychometrika*, 76(2), 179–199.

[9] Diekelmann, S., & Born, J. (2010). The memory function of sleep. *Nature Reviews Neuroscience*, 11(2), 114–126.

[10] Ebbinghaus, H. (1885). *Über das Gedächtnis*. Leipzig: Duncker & Humblot.

[11] Graesser, A. C., Chipman, P., Haynes, B. C., & Olney, A. (2005). AutoTutor: An intelligent tutoring system with mixed-initiative dialogue. *IEEE Transactions on Education*, 48(4), 612–618.

[12] Guskey, T. R. (2010). Lessons of mastery learning. *Educational Leadership*, 68(2), 52–57.

[13] Heffernan, N. T., & Heffernan, C. L. (2014). The ASSISTments ecosystem: Building a platform that brings scientists and teachers together. *International Journal of Artificial Intelligence in Education*, 24(4), 470–497.

[14] Leitner, S. (1972). *So lernt man lernen*. Freiburg: Herder.

[15] Miller, G. A. (1956). The magical number seven, plus or minus two. *Psychological Review*, 63(2), 81–97.

[16] Pardos, Z. A., Baker, R. S., San Pedro, M. O., Gowda, S. M., & Gowda, S. M. (2014). Affective states and state tests. *Journal of Educational Data Mining*, 6(1), 28–52.

[17] Patz, R. J., & Junker, B. W. (1999). A straightforward approach to Markov chain Monte Carlo methods for item response models. *Journal of Educational and Behavioral Statistics*, 24(2), 146–178.

[18] Ritter, S., Anderson, J. R., Koedinger, K. R., & Corbett, A. (2007). Cognitive Tutor: Applied research in mathematics education. *Psychonomic Bulletin & Review*, 14(2), 249–255.

[19] Roediger, H. L., & Karpicke, J. D. (2006). Test-enhanced learning: Taking memory tests improves long-term retention. *Psychological Science*, 17(3), 249–255.

[20] Settles, B., & Meeder, B. (2016). A trainable spaced repetition model for language learning. *Proceedings of ACL*, 1848–1858.

[21] Sweller, J. (1988). Cognitive load during problem solving: Effects on learning. *Cognitive Science*, 12(2), 257–285.

[22] Sweller, J., Ayres, P., & Kalyuga, S. (2011). *Cognitive Load Theory*. Springer.

[23] VanLehn, K. (2011). The relative effectiveness of human tutoring, intelligent tutoring systems, and other tutoring systems. *Educational Psychologist*, 46(4), 197–221.

[24] Wilson, K., & Nichols, Z. (2015). The Knewton platform: A general-purpose adaptive learning infrastructure. *Knewton Technical Report*.

[25] Wozniak, P. A. (1990). *Optimization of Learning*. Master's Thesis, Poznan University of Technology.

[26] Ye, J. (2022). FSRS: A modern, efficient spaced repetition algorithm. *GitHub repository*.

[27] Zimmerman, B. J. (2002). Becoming a self-regulated learner: An overview. *Theory into Practice*, 41(2), 64–70.
