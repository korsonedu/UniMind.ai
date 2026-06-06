# XiaoYu: A Four-Layer Architecture for AI-Native Educational Infrastructure

## Abstract

We present XiaoYu, the core AI learning coach of the UniMind platform, and the four-layer architecture that underlies it. The architecture centers on a novel design choice: treating memory state—not content recommendation—as the system's primary organizing principle. A spaced-repetition scheduling engine called Memorix drives the entire learning loop, determining when each student should encounter each item based on continuously updated stability and difficulty estimates. Above this memory layer sit an education loop (teach, practice, assess, evaluate), a grading engine that extends beyond correctness into cognitive diagnosis, and a foundation layer handling dialogue and tool orchestration. We describe the theoretical grounding of each layer—spacing effect, retrieval practice, cognitive load theory, mastery learning, and the CTT–IRT–CDM diagnostic hierarchy—and argue that the architecture's key property, cross-layer isolation enforced through interface contracts, makes it a genuine piece of educational infrastructure rather than a monolithic application.

---

## 1. Introduction

The past decade of educational technology has largely been a story of digitization. Paper exercises became on-screen quizzes; textbook chapters became video libraries; teacher gradebooks became analytics dashboards. These products solved information distribution—making it easier to find and assign content—but they left untouched a deeper question: what happens between the moment a student answers a question and the moment they encounter it again?

A student's learning state is not a list of completed exercises. It is a dynamic set of memory traces, each with its own decay rate, each requiring reinforcement at a different interval. A system that cannot model this state is, at best, a smart content library. It can recommend what to study next but cannot compute when.

UniMind's architecture begins from this observation. We place a spaced-repetition scheduling engine—Memorix—at the center of the system, not as a feature but as the clock that drives everything else. This paper describes the resulting four-layer design, its theoretical foundations, and the cross-layer isolation properties that qualify it as educational infrastructure.

---

## 2. Architecture Overview

The system is organized into four layers with strict interface boundaries:

**Layer 1 — Foundation.** Dialogue lifecycle management, bot runtime, tool system, intent routing, and model orchestration. This layer contains no educational domain knowledge.

**Layer 2 — Memory System.** All student data—structured memories, semantic embeddings, user profiles, and the Memorix scheduling engine—reside here. A query interface (MemorySystem.query.* / MemorySystem.write.*) is the sole access point. Upper layers do not import database models directly.

**Layer 3 — Education Loop.** Four phases form a closed loop: teach (knowledge tree search, course recommendation, transcript search), practice (active question fetching plus Memorix-due reviews), assess (exams and diagnostic tests), and evaluate (learning statistics, mastery maps, weak-point analysis).

**Layer 4 — Grading Engine.** A diagnostic pipeline that answers three questions in a single call: correct or not, why the error occurred, and what follow-up practice is most appropriate. The engine is designed to evolve along the CTT–IRT–CDM diagnostic hierarchy as answer data accumulates.

---

## 3. Memorix: Spaced Repetition as System Clock

Memorix maintains two core parameters for each student–item pair: stability, which estimates the probability the memory trace remains intact, and difficulty, which captures the item's intrinsic challenge. These parameters interact with a lapse counter to compute the next review interval.

The design draws on three established findings. The spacing effect (Ebbinghaus, 1885) holds that distributed practice produces more durable retention than massed practice; Memorix enforces this by spacing intervals from one day to several months based on stability. The testing effect (Roediger & Karpicke, 2006) demonstrates that active retrieval strengthens memory more than re-reading; Memorix ensures that every encounter is a recall attempt rather than passive review. Feedback-timing research (Butler & Roediger, 2008) shows that delayed corrective feedback produces better long-term retention than immediate feedback; Memorix's one-day minimum interval places correction at the threshold where forgetting has begun but retrieval is still possible.

A notable computational property follows from the design: stability serves as a sufficient statistic for the full interaction history with a given item. The interval computation depends only on the current stability and difficulty values, not on the sequence of responses that produced them. Each update is O(1), and the system scales linearly with the number of student–item pairs.

---

## 4. The Education Loop

The loop (teach → practice → assess → evaluate) is shaped by two additional theoretical constraints.

**Cognitive load.** Sweller (1988) established that working memory can hold approximately three to five elements at once. XiaoYu therefore limits each practice session to three to five items focused on a single knowledge point. After completion, Memorix imposes a one-day consolidation interval before the same material reappears, respecting the brain's need for offline consolidation.

**Mastery learning.** Bloom (1968) argued that instruction should proceed based on demonstrated competence rather than calendar time. Memorix operationalizes this principle: stability below a threshold keeps an item in high-frequency review; stability above the threshold lengthens the interval, freeing resources for weaker areas. The system does not suggest this—it enforces it algorithmically.

---

## 5. Grading Engine: Beyond Correctness

The grading engine follows a diagnostic hierarchy aligned with the historical progression of educational measurement theory.

**Level 1 — Classical Test Theory (current).** Output: observed score, maximum score, feedback text. The model is score = true ability + random error, with no decomposition of error sources.

**Level 2 — Error classification (in development).** The engine classifies incorrect answers into three categories: concept error (misremembered or confused knowledge), calculation error (correct reasoning with arithmetic mistakes), and careless mistake (overlooked conditions or transcription errors). Each category implies a different instructional response—re-teaching, practice volume, or strategy training—making classification practically meaningful.

**Level 3 — Item Response Theory (future).** With sufficient data, the system estimates independent mastery probabilities per knowledge point, along with item parameters (discrimination, difficulty, guessing probability). Two students with identical 60% accuracy may require entirely different interventions depending on which items they answered correctly.

**Level 4 — Cognitive Diagnostic Models (long-term).** The ultimate target is attribution at the cognitive sub-process level: not "trigonometry mastery 0.6" but "understands formula transformation but cannot apply it to novel problems." This requires expert-annotated Q-matrices mapping knowledge points to cognitive operations.

---

## 6. Cross-Layer Isolation

A defining property of the architecture is that cross-layer calls must pass through defined interfaces. The education loop queries student data through MemorySystem.query; the grading engine writes diagnosis results through MemorySystem.write. Direct database access from upper layers is prohibited.

This constraint serves three purposes. First, it enables independent evolution: the grading engine can upgrade its scoring model without affecting the education loop, and the memory system can change its storage backend without modifying callers. Second, it guarantees algorithmic integrity: no handler can bypass Memorix by directly modifying next_review_at. Third, it makes the system testable at layer boundaries—mocking MemorySystem suffices to test education-loop logic in isolation.

---

## 7. Related Work

Spaced-repetition systems such as Anki and SuperMemo have demonstrated the efficacy of algorithmic scheduling for individual learners. These systems treat scheduling as a personal productivity tool. Memorix differs in making scheduling the architectural center of a multi-tenant educational platform, where each student's intervals interact with a shared knowledge base and a diagnostic grading pipeline.

AI tutoring systems (VanLehn, 2011) have shown that step-level guidance improves learning outcomes, but most implementations focus on real-time hint generation during problem-solving. XiaoYu's design emphasizes temporal orchestration—when to surface what, over days and weeks—as a complementary mechanism.

Cognitive diagnostic models (de la Torre, 2011) provide a rigorous framework for attributing performance to specific skills. XiaoYu's grading engine adopts the CDM hierarchy as a roadmap but acknowledges the data requirements: IRT-level modeling needs item-level response data at scale, and CDM-level modeling requires expert-annotated Q-matrices.

---

## 8. Conclusion

XiaoYu's architecture addresses a gap in educational technology: the absence of memory as a first-class architectural primitive. By placing a spaced-repetition scheduler at the system's center, enforcing cross-layer isolation, and designing the grading pipeline along a diagnostic hierarchy with clear theoretical foundations, the system aims to be more than a learning application. It is an attempt at educational infrastructure—a platform where new agents, domains, and diagnostic methods can be added without restructuring, and where every scheduling decision is grounded in mechanisms that cognitive science has established as effective.
