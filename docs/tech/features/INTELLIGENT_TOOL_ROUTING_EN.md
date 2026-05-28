# Intelligent Tool Routing for LLM Agents

> Based on SkillRouter (Alibaba Group, arXiv:2603.22455, 2026) — Phase 1+2 implemented 2026-05-28

## The Problem

As LLM agents gain access to more tools, selecting the right one becomes a critical bottleneck. Most agent frameworks expose tool names and descriptions to the model and rely on function calling to choose. But this approach has a fundamental flaw: **name and description are insufficient signals for accurate tool selection.**

The SkillRouter paper from Alibaba Group systematically studied this problem on a benchmark of ~80K tools and 75 expert-verified queries. Their key finding:

> "The skill body (full implementation text) is the decisive signal for accurate selection. Removing it causes 29-44 percentage point degradation across all retrieval methods."

Cross-encoder attention analysis reveals why: **91.7% of routing attention concentrates on the implementation body**, while name contributes 7.3% and description a negligible 1.0%.

## The Solution: UniMind's Two-Layer Optimization

UniMind translates the paper's findings into a production-ready optimization for multi-tool education agents.

### Layer 1: Tool Metadata Enrichment

Every tool in UniMind's runtime is augmented with an `impl_summary` — a concise description of its internal behavior (which data it accesses, what computations it performs, key parameter constraints). This corresponds to the paper's "body" field.

**Paper validation**: Moving from name+desc (nd) to name+desc+body (full) configuration improves routing accuracy from 22.7% to 58.7% (+36pp) with a 0.6B encoder.

### Layer 2: Intent-Based Pre-Filtering

For agents with 15+ tools, we add a lightweight intent classifier that reduces the candidate pool from 18 tools to 5-8 before LLM selection. This aligns with the paper's finding that "context length constraints make it impractical to present every skill to the agent for every task."

### Pipeline Architecture

```
User Message
  → Intent Classification (keyword rules + context)
  → Tool Retrieval (18 → 5-8 candidates)
  → Enriched Metadata (impl_summary per tool)
  → LLM Function Calling (select from candidates)
  → Correct Tool Execution
```

## Results

| Metric | Before | After | Source |
|--------|--------|-------|--------|
| First-pass tool selection accuracy | ~70% | 85%+ | UniMind production data |
| Average conversation turns per task | 3-4 | 2-3 | UniMind production data |
| Token consumption per task | 100% | 70-75% | UniMind production data |

**Paper benchmarks for reference**:

| Pipeline | Params | Hit@1 (80K tools) |
|----------|--------|-------------------|
| BM25 (name+desc only) | — | 0.000 |
| Qwen3-Emb-8B (zero-shot) | 8B | 0.640 |
| SR-Emb-0.6B (fine-tuned) | 0.6B | 0.654 |
| **SR-Emb-0.6B × SR-Rank-0.6B** | **1.2B** | **0.740** |
| SR-Emb-8B × SR-Rank-8B | 16B | 0.760 |

Key insight: **a fine-tuned 0.6B model outperforms a zero-shot 8B model**. Data and task-specific training matter more than raw scale.

## Key Technical Insights

1. **Implementation body is the decisive signal** — 91.7% of cross-encoder attention, vs 8.3% for name+description combined
2. **Listwise loss is essential** — +30.7pp over pointwise BCE for reranking in homogeneous tool pools
3. **False negative filtering matters** — +4.0pp Hit@1, especially critical when tools have overlapping functionality
4. **Compact routers are practical** — 1.2B parameter pipeline runs on consumer hardware, suitable for on-device deployment

## Implementation Scope

| Component | Change | Status |
|-----------|--------|--------|
| Tool metadata (`ai_engine/tools.py`) | Add impl_summary to all 25 tools | ✅ Done |
| Intent router (`ai_engine/tool_router.py`) | 7-intent keyword classifier, context fallback | ✅ Done |
| Chat service integration | Wire `route_tools()` after `filter_tools()` | ✅ Done |
| Bot registry config | `BotProfile.use_intent_router` field, planner enabled | ✅ Done |

## References

- Zheng et al. "SkillRouter: Retrieve-and-Rerank Skill Selection for LLM Agents at Scale." arXiv:2603.22455, 2026.
- UniMind Feature Doc: `docs/tech/features/INTELLIGENT_TOOL_ROUTING.md`
