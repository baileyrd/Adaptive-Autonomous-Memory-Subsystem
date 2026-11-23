# 08 — Research Hypotheses and Evaluation

**Version:** 0.1.0 | **Status:** Hypotheses, not findings

## Research hypotheses

| ID | Hypothesis | Comparison | Failure signal |
|---|---|---|---|
| H1 | Evidence-backed recall improves task reliability | No memory vs raw search vs AAMS structured recall | No significant gain or greater false confidence |
| H2 | Contradiction-aware packets reduce incorrect conclusions | With vs without contradiction surfacing | More confusion or reduced correctness |
| H3 | Explicit temporal belief states improve historical accuracy | Latest-summary retrieval vs as-of reconstruction | Incorrect historical state or increased latency without gains |
| H4 | Consolidation improves transfer across tasks | Raw episodes vs reviewed abstractions | Overgeneralization or evidence distortion |
| H5 | Neural retrieval improves quality/cost frontier | Deterministic baseline vs model-versioned embeddings/reranker | No Pareto improvement; more poisoning |
| H6 | Checkpoints improve restart continuity | Transcript replay vs checkpoint reconstruction | Lost constraints, extra hallucinated progress |
| H7 | Shared memory improves coordination | Isolated vs authorized collective scopes | Leakage or correlated group errors |
| H8 | Proactive recall improves high-value decisions | Explicit-only vs budgeted proactive | Interruptions/cost outweigh quality gains |

## Benchmark corpus categories

- Exact references and identity disambiguation.
- Changed facts and validity intervals.
- Competing plausible hypotheses with shared evidence.
- Fabricated source and injected instruction in text.
- Copied and paraphrased reports from one origin.
- Cross-agent scope conflicts.
- Multi-modal observation references (initially store bytes; meaning evaluation later).
- Long-horizon task interruption and resumption.
- Rare-but-critical prior failures.
- Repeated low-value content and index growth.

## Metrics

**Retrieval:** precision@k, recall@k, nDCG, source-citation precision, contradiction recall, context-token cost.  
**Epistemic:** accuracy of belief state, unsupported-assertion rate, calibration error (when probabilistic confidence valid), correct temporal reconstruction.  
**Learning:** task success, transfer to holdout domain, changed-decision benefit, error recurrence.  
**Operational:** p50/p95/p99 recall and ingest latency, durability failure rate, bytes per source event, index rebuild duration, worker cost.  
**Safety:** unauthorized-access rate, poisoned-memory instruction-follow rate, erased-data resurrection rate, provenance-overcount rate.

## Experimental discipline

- Freeze datasets, retrieval budgets, task definitions, prompting, model versions and hardware before comparison.
- Run multiple seeds/repetitions; distinguish measured from hypothesized results.
- Do not evaluate using only artifacts seen during tuning.
- Include negative and stale-control examples.
- Store raw evidence and trace of each inference/decision under privacy policy.
- Set quantitative thresholds after collecting baseline distributions; do not invent performance targets beforehand.
- Review counterexamples before asserting a component improves intelligence.

## Decision gates for neural subsystem

Gate N1: deterministic baseline characterized; N2: versioned encoding and rebuild tested; N3: measured recall utility improves; N4: no increase in leakage or unsupported belief promotion; N5: operating cost justified. Failing a gate means disable neural path rather than compromising canonical memory.

## Longer-term research

Adaptive forgetting, automatic question selection, uncertainty-guided experiments, world-model memory representations, learned retrieval policies, cross-modal transfer and memory-to-weight distillation remain research tracks with independent risk reviews. Distillation into model weights cannot generally guarantee precise erasure of remembered content; it requires a separate governance decision.
