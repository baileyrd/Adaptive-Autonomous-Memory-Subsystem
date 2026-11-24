# AAMS cognitive-memory alignment audit (initial evidence review)

**Date:** 2026-11-23  
**Status:** Initial design-to-roadmap audit; implementation-level traceability and task-outcome validation remain open.  
**Coordination:** [alignment issue #115](https://github.com/baileyrd/Adaptive-Autonomous-Memory-Subsystem/issues/115); [current research goal #105](https://github.com/baileyrd/Adaptive-Autonomous-Memory-Subsystem/issues/105).

**Implementation follow-up:** The [31-item traceability matrix](cognitive-memory-traceability.md) now inspects code and named tests, with [reproduced baseline evidence](cognitive-memory-baseline.json), a [bounded offline evaluation plan](cognitive-memory-evaluation-plan.md), and a [revised research acceptance contract](../acceptance/v1.0-research.md). The preliminary assessments below are retained as the initial review; consult the matrix for implementation status. Neural public quality and comparative cognitive task outcomes remain open.

## Original design intent

The [v0.1.0 dossier](../design/v0.1.0/README.md) defines AAMS as an independent, model-neutral, evidence-preserving **cognitive memory** service. Its thesis is to measurably improve AI reasoning, reliability, continuity and future decisions. Embeddings and latent representations are replaceable indexing aids, not canonical truth.

The [requirements](../design/v0.1.0/docs/01-product-requirements.md) specify objectives O1–O7, including reusable memories and relationships (O2), revisable evidence-grounded beliefs (O4), checkpoints/continuity (O5), and behavioral improvement evaluated empirically (O7). Its FR-009 through FR-016 include checkpointing, contradictions, governed consolidation, deletion, sharing, proactive recall, feedback-learned ranking and knowledge-gap proposals, with different priorities and release horizons.

The [original roadmap](../design/v0.1.0/docs/06-roadmap.md) planned evidence and beliefs first, then recall, temporal continuity, consolidation, governance, neural adaptation, and finally proactive learning research. The [MVP contract](../MVP_SPEC.md) deliberately excluded neural training and autonomous generalization **from MVP**, not from the overall project. Therefore, emphasizing BM25 at the MVP stage was valid; treating retrieval speed as the long-term measure of memory intelligence would not be.

## Demonstrated alignment / evidence still needed

| Original capability | Evidence available during initial audit | Assessment / next proof |
|---|---|---|
| Immutable scoped evidence and source provenance (O1, FR-001/002) | Established MVP contract and completed security/migration PRs (#75 and related milestones) | **Reported implemented**; map source, assertions and exact-head tests |
| Recall with provenance, scoped policy and temporal evidence (O3/O4, FR-003–008) | v0.7/v0.8 acceptance history; BM25 default via #90 | **Reported implemented**; trace exact API/security tests |
| Retrieval ranking benefit (H5 component) | v0.8 BM25 held-out evaluations; BM25 baseline retained | **Measured for retrieval**, not proof of cognitive/task-level learning |
| Contradiction detection and historical belief correctness (FR-010, H2/H3) | MVP/roadmap describe functionality | **Verification incomplete**; test actual contradiction and retrospective decision tasks |
| Relationship formation, consolidation, lineage and review (O2, FR-011, H4) | Designed in v0.1.0 roadmap | **Unknown implementation/outcome**; audit code/workflows, especially unauthorized promotion |
| Checkpoint restore and cross-model task continuity (O5, FR-009, H6) | Planned milestone M04 | **Unknown**; demonstrate independent-agent reconstruction and task outcome |
| Multi-agent sharing, deletion and scope governance (O6, FR-012/013, H7) | Scope protections reported in recent security evaluations | **Partial evidence only**; verify erasure/rebuild and controlled sharing |
| Outcome feedback and learned improvement (O7, FR-015, H1/H4/H5) | v0.7 learned router was not superior; shadow kept offline | **Not demonstrated**; design outcome-based paired tasks |
| Proactive recall and knowledge-gap proposals (FR-014/016, H8) | Explicit future research milestones | **Deferred/unknown**, not a production capability claim |
| Neural retrieval/association (M07, H5) | v0.9 resource benchmarks; #112–#114 experiments | **Quality remains unmeasured for ONNX candidates** after cost screening; assess offline effectiveness separately |

**Caution:** A roadmap, merged PR, passing CI or benchmark on ranking does not by itself establish that the memory subsystem improves reasoning, transfer or long-horizon decisions. Entries above are preliminary until evidence-linked code/test inspection.

## Process failure and correction

Current v1.0 goal #105 and quality issue #109 defined a sequence in which neural candidates could undergo quality evaluation **only after** passing a ≤5 ms incremental p95 and ≤2× RSS gate. This gate answers deployment affordability, but prevents experimental discovery of whether rejected approaches offer material recall benefit. The original [research hypothesis H5 and neural gates](../design/v0.1.0/docs/08-research-evaluation.md) call for measuring retrieval utility **and** operating cost, not replacing utility measurement with a cost veto.

Apply four separate scorecards:

1. **Memory correctness and safety:** provenance, exact history, temporal validity, contradiction visibility, scoped authorization, injection protection and no unauthorized promotion; failure blocks any candidate from serving and must be visible in experimental reports.
2. **Cognitive-memory utility:** improved task success, decision correctness, less repeated error, better cross-session continuity, calibration and transfer to unseen problems versus no memory, raw search and structured memory.
3. **Retrieval effectiveness:** recall@k, nDCG@k, unique evidence discovered beyond BM25, citation precision and pairwise failure analysis on held-out grouped queries.
4. **Operational efficiency:** warm/cold p50/p95/p99 latency, peak/steady RSS, CPU, storage, startup and index rebuild costs.

A model that fails an operational deployment constraint may still be evaluated **offline** for research utility, within a bounded and safe evaluation environment. Do not activate it in production or waive scope/time/provenance guarantees. Keep BM25 as the production default.

## Priority work and acceptance

**P0 — Close traceability unknowns.** Produce an O1–O7, FR-001–016 and H1–H8 matrix linking code paths, named tests, CI SHA, actual outcomes, status (verified/partial/missing/unknown), and next experiment. Reuse existing issues/PRs and avoid duplicate implementation.

**P1 — Neural quality before efficiency decisions.** Independently test the existing pinned ONNX, static and BM25 paths against held-out paraphrase/vocabulary-mismatch/SciFact/SQuAD plus episodic/contradiction/temporal cases. Compare retrieved **candidate sets**, not only reranking of BM25 candidates. Separate quality estimates and confidence intervals from measured resources; report incomplete arms as unmeasured. Do not silently lower security or change live routing.

**P2 — Demonstrate adaptive memory, not merely adaptive ranking.** Test associations, reviewed consolidations, contradictory belief revisions, checkpoints and decision/outcome feedback using paired, preregistered tasks. Compare no memory, raw search, current structured memory and experimental neural-assisted variants. Track false confidence, lineage collapse, temporal errors, scope leakage, negative transfer and error recurrence.

**P3 — Architecture and deployment decision.** Select a candidate only on demonstrated cognitive or retrieval benefit, preservation of safety invariants and justified cost, using a quality–cost Pareto table. Live canary/activation remains a separate explicitly authorized decision.

## Verification boundaries

This initial review directly checked the original dossier, product requirements, original roadmap, original research hypotheses, active v1.0 issue definitions and open PR summaries as of 2026-11-23. It did **not** exhaustively inspect implementation modules, execute benchmarks, or independently replicate all historic measurements. Do not mark the traceability matrix or neural-quality experiment complete until those steps are performed.

**Next action:** complete P0 implementation-level traceability and launch P1's reproducible **offline quality-only** evaluation as a bounded PR; keep active PR #112–#114 unblocked and avoid overlapping changes.
