# Cognitive-memory implementation traceability

Tracking: [#115](https://github.com/baileyrd/Adaptive-Autonomous-Memory-Subsystem/issues/115), coordinated through [#105](https://github.com/baileyrd/Adaptive-Autonomous-Memory-Subsystem/issues/105). Audit date: 2026-11-23. This is workstream A; it does not close the task-level outcome or neural research workstreams.

Follow-up: [#117's synthetic decision pilot](cognitive-task-pilot.md) now reports actual rule-agent decisions separately from evidence coverage, including unsafe choices and an inconclusive four-family comparison. The baseline statuses below remain bounded to the audited main SHA; the pilot does not establish model-agent reasoning, long-term learning, task checkpoints or unseen-domain transfer.

## Evidence boundary

Audited implementation: main `79a4d1f0ae4026a185b03abaecc9507022444115`. The initial audit branch at `7eb791884e13743029d9ef54ae1c85908cb04cb9` adds documentation only and has identical product, script and test bytes. [Integrated main CI](https://github.com/baileyrd/Adaptive-Autonomous-Memory-Subsystem/actions/runs/45311798184) passed. This audit also reran all **137 tests**, formatting, lint, compilation, the MCP demo, governed-learning evaluation and synthetic retrieval replay on Python 3.12.14/Linux. [Machine-readable evidence](cognitive-memory-baseline.json) records commands, input hashes, environment and aggregate results. PR-head CI is recorded on the associated PR and #115; main CI is not substituted for changed-head CI.

Source requirements: [O1–O7 and FR-001–016](../design/v0.1.0/docs/01-product-requirements.md), [H1–H8](../design/v0.1.0/docs/08-research-evaluation.md), [original roadmap](../design/v0.1.0/docs/06-roadmap.md), and reconciled [MVP contract](../MVP_SPEC.md). Existing release numbers do not imply completion of the original roadmap's M00–M09.

**Verified** means the stated, bounded behavior is implemented and directly exercised, with remaining assumptions named. **Partial** means only part of the original requirement has evidence. **Unimplemented** means no corresponding product workflow was found in the inspected modules/schema/API. **Unknown** means an outcome has not been independently measured. None means production traffic or general intelligence was validated. A passing test of a mechanism is not a positive research finding.

Evidence references used below (all paths are relative to this document):

- **E:** [contracts](../../src/aams/contracts.py), [storage](../../src/aams/storage.py), [storage tests](../../tests/test_storage.py), [integrity tests](../../tests/test_audit_integrity.py), [scoped identity tests](../../tests/test_scoped_ids.py).
- **B:** `SQLiteMemoryStore.revise/get_belief/belief_history`, [belief tests](../../tests/test_beliefs.py), especially `test_reconstruct_known_and_effective_history`, `test_unauthorized_links_and_rollback`, and `test_rejects_observation_promotion_and_invalid_validity`.
- **R:** [CognitiveMemory](../../src/aams/recall.py), [recall tests](../../tests/test_recall.py), especially `test_historical_and_current_contradiction_explanation`; [vector index](../../src/aams/vector_index.py) and [tests](../../tests/test_vector_index.py), including `test_hybrid_scope_and_temporal_reauthorization`.
- **M:** [MCP adapter](../../src/aams/mcp_server.py), [MCP tests](../../tests/test_mcp.py), including `test_executable_restart_workflow`, `test_schemas_and_nonleaking_errors`, and `test_instruction_like_evidence_is_inert_and_revoked_grants_deny_write`; [demo](../../src/aams/demo.py).
- **L:** [candidate contracts](../../src/aams/learning.py), [consolidation proposals](../../src/aams/consolidation.py), storage's `create_candidate/validate_candidate/decide_candidate/append_outcome`; [candidate tests](../../tests/test_candidate_storage.py), [consolidation test](../../tests/test_consolidation.py), [outcome tests](../../tests/test_outcomes.py), [learning evaluation](../../scripts/evaluate_learning.py).
- **F:** [recovery tests](../../tests/test_recovery.py): `test_ingestion_crash_before_and_after_commit`, `test_revision_crash_preserves_history`, `test_backup_restores_and_broken_links_are_detected`.
- **P:** [offline policy](../../src/aams/offline_policy.py), [candidate trainer](../../src/aams/offline_candidate.py), [offline tests](../../tests/test_offline_policy.py), [shadow observer](../../src/aams/shadow_observer.py) and its [tests](../../tests/test_shadow_observer.py). [v0.6](../acceptance/MVP-v0.6.md) and [v0.7](../acceptance/MVP-v0.7.md) report bounded offline/shadow results, not live learning.
- **Q:** [v0.8 retrieval results](../acceptance/MVP-v0.8.md), [public benchmark](../../scripts/evaluate_retrieval.py), [SciFact benchmark](../../scripts/evaluate_scifact.py), [synthetic replay](../../scripts/offline_experiment.py), [v0.9 resource disposition](../audit/onnx-quality-gate.md). Published results are historical evidence, not newly reproduced public-data experiments here.

## Objectives

| ID | Status | Implementation, tests and measured outcome | Remaining proof / gap |
| --- | --- | --- | --- |
| O1 | Verified | E: immutable payload/digest and origin metadata, transactional ingest; `test_round_trip_and_process_restart`, `test_corruption_is_reported`. | Exact bytes and supplied provenance are verified; trusted source labels do not attest real-world authenticity. |
| O2 | Partial | E/L: typed formations, evidence links, belief support/refutation and candidate lineage persist. | No general typed relationship graph or measured reuse/transfer benefit. |
| O3 | Verified | R/M: bounded query/exact packets, citations, explicit contradictions and deterministic ranking; scoped/time tests pass. Q measures retrieval effectiveness. | General reasoning benefit and recall beyond tested corpora remain unknown. |
| O4 | Verified | B: evidence-linked append-only revisions, optimistic concurrency, recorded-as-of and effective-time reconstruction. | Correctly storing a supplied claim does not validate its truth or improve decision accuracy by itself. |
| O5 | Unimplemented | F/M demonstrate storage/service restart, not task checkpoints. No checkpoint schema, save/restore API, expiration or model-replacement task test found. | Implement task continuity and evaluate reconstruction separately from database durability. |
| O6 | Partial | E/M: trusted host grants one scope and operation rights; same IDs in other scopes are hidden. | No private-to-shared promotion workflow, tenant policy engine or measured collective coordination. |
| O7 | Partial | P/Q/L: reproducible retrieval, proposal-coverage and routing experiments; outcome revisions preserve predicted/measured fields. | No independent no-memory/raw-search/structured-memory task-success, recurrence or transfer comparison. |

## Functional requirements

| ID | Status | Implementation / named test / outcome | Limitation and next proof |
| --- | --- | --- | --- |
| FR-001 | Verified | E: `Evidence`, `ingest`, digest/origin/scope/time validation; `test_evidence_requires_source_and_digest`, `test_partial_write_rolls_back`. | Supplied source identity remains a host trust assumption. |
| FR-002 | Verified | E: `MemoryFormation`, immutable identity and scoped evidence foreign keys; `test_formation_is_immutable`, `test_formation_needs_evidence`. | Typed values are not automatic abstraction or a relationship graph. |
| FR-003 | Verified | R: `recall/explain`, deterministic exact and contextual ranking; `test_exact_and_bounds`, `test_stable_ranked_fixture_precision_and_scope`. | Quality is bounded to measured inputs; semantic fixture provider is not a neural model. |
| FR-004 | Partial | R/B: citation source/digest, epistemic state, validity and revision metadata are returned and time-filtered. | No full task-specific applicability reasoning or calibrated confidence guarantee. |
| FR-005 | Partial | E/M/R: `AccessContext` scope and explicit grants, nonleaking missing/foreign responses; `test_identifier_in_one_scope_is_not_observable_from_another`. | Trusted host constructs grants; no independent authentication, hierarchical tenant/domain ACL or dynamic in-process revocation. |
| FR-006 | Verified | B: `test_reconstruct_known_and_effective_history`, `test_concurrent_revision_conflict`; original evidence unchanged. | History correctness tested; downstream reasoning benefit unmeasured. |
| FR-007 | Partial | M: four tools through pinned MCP SDK 2.3.0/local stdio; executable multi-process demo and wire tests. | No MCP resource interface or independent multi-host-client interoperability matrix. |
| FR-008 | Verified | F: before/after commit process-kill and backup restore tests pass. | Process termination is the fault model; disk-full, power loss and distributed replicas untested. |
| FR-009 | Unimplemented | No checkpoint record/API, resumability/expiration mechanism or task-restore test found. | Store restart does not satisfy task checkpoint acceptance. |
| FR-010 | Partial | R/B/L: explicit contested/support/refute state and literal `not:` counterexamples; provenance grouping by actor/locator/digest; contradiction tests. | No general semantic contradiction discovery; disguised copies and external independence unproven. |
| FR-011 | Verified | L: deterministic proposals, reviewer grants, versioned approval/rejection and provenance checks; `test_policy_history_and_restart`, `test_concurrent_decisions_and_contradiction`. | Verified only for literal repeated-text proposals; approved candidates stay staged and canonical promotion is denied. Transfer benefit unknown. |
| FR-012 | Unimplemented | No retention/erasure API, tombstone traversal, derivative deletion or post-restore resurrection test found. | Disposable index rebuild is not auditable erasure. |
| FR-013 | Unimplemented | Scope isolation exists, but no policy-gated private-to-shared promotion path/test found. | Candidate approval is not sharing or canonical promotion. |
| FR-014 | Unimplemented | Recall is caller-requested. Shadow observation evaluates a request already made. | No proactive host opt-in scheduler, interruption budget or benefit evaluation. |
| FR-015 | Partial | P/L: offline routing training, controlled paired outcomes, telemetry/shadow evaluation; `test_observational_data_is_not_counterfactual_evidence`. | Labels concern retrieval satisfaction, not independently grounded long-horizon tasks; no learned serving activation or demonstrated behavioral improvement. |
| FR-016 | Unimplemented | No knowledge-gap proposal, informative-experiment selection or expert-validation workflow found. | Requires its own bounded research design and governance. |

## Research hypotheses

| ID | Status | Evidence available | Outcome still needed |
| --- | --- | --- | --- |
| H1 | Unknown | E/R/L provide evidence-backed recall; local reviewer evidence coverage is 2/3 baseline versus 3/3 augmented. | Coverage is not task reliability. Compare no memory, raw search and structured memory with independent decision scoring. |
| H2 | Unknown | B/R expose explicit contradictions, tested on deterministic examples. | Randomized paired packet ablation and independently scored incorrect-conclusion/abstention rates. |
| H3 | Unknown | B verifies recorded/effective historical state reconstruction. | Compare latest summary versus as-of reconstruction on blinded historical decision tasks. |
| H4 | Unknown | L gives staged reviewed abstractions and provenance safeguards; fixture proposal precision 0.5, recall 2/3. | Transfer to unseen task families with distortions and overgeneralization counted. |
| H5 | Partial | Q: BM25's retrieval gain measured; main's full ONNX public quality unknown. #112 reports static quality/cost results on its open branch. | Independently evaluate actual neural candidates, including cost failures; compare candidate discovery, regressions and safety alongside cost. |
| H6 | Unknown | F verifies storage restart; FR-009 task checkpoint implementation absent. | Transcript replay versus checkpoint reconstruction after interruption/model replacement. |
| H7 | Unknown | E/M verify scoped isolation, not authorized collective reasoning quality. | Isolated versus deliberately authorized shared evidence, measuring leakage and correlated errors. |
| H8 | Unknown | Proactive recall is absent. | Explicit-only versus opt-in budgeted proactive recall, with interruptions and costs. |

## Measured evidence and negative findings

The rerun of `evaluate_learning.py --repetitions 30` produced 4 proposals, 1 approval, zero false approvals, zero canonical promotions and zero foreign candidates after restart. Coverage was **2/3 to 3/3 reviewer evidence tasks**; proposal precision **0.5**, recall **2/3**. These are the fixed synthetic fixture's outcomes, not decision or learning gains. The replay rerun uses the deterministic fixture provider; it cannot establish neural quality. See the JSON evidence for per-split aggregates and timing caveats.

Historical v0.8 public measurements improved BM25 retrieval relative to overlap. v0.9 and #114 show ONNX RSS failures, which are deployment evidence only. #112 reports a small static encoder passing costs but unsuccessful preregistered reranking, and slow score fusion with positive retrieval deltas. #113 reports an oracle reranking ceiling rather than a model experiment. These open PR results remain branch-local claims until their exact heads, raw results and reviews are checked for the next experiment; this audit does not certify or merge them. Their work is retained, not recreated.

Storage correctness, retrieved evidence coverage, policy-label satisfaction and task-level cognitive improvement must never be reported as interchangeable measurements. In particular, feedback records are append-only claims about measurements; their existence does not prove the measurement was independently grounded.

## Prioritized gap backlog

| Order | Bounded next slice | Dependency / existing owner | Acceptance evidence |
| --- | --- | --- | --- |
| 1 | Offline ONNX quality runner and scorecards | #109 under #115/#105; reuse #112 encoders and #114 cost tools after inspecting branches. No cost prerequisite. | Pinned bounded held-out SQuAD/SciFact and semantic/contradiction results or explicit failed/unexecuted arms; safety invalidation; cost reported separately. |
| 2 | Independent decision/outcome benchmark | #115 workstream C; reuse #27 outcome store and #58 replay rather than rebuilding them. | Freeze no-memory/raw-search/structured-memory task contracts and blinded labels; paired history/contradiction/rare-failure cases, false confidence and recurrence. |
| 3 | Checkpoint contract and restore slice | FR-009/O5, original AAMS-017; no active duplicate found. Size a dedicated implementation issue before code. | Explicit constraints/progress/provenance/expiration; another process reconstructs task state without inventing completed work. Model replacement remains unknown until tested. |
| 4 | Relationship/lineage projection and reviewed transfer evaluation | O2/H4; extend existing formations/candidates, retain #25/#26 policy. | Scope-filtered typed links and unseen-family transfer; no generated evidence counted as independent, no promotion bypass. |
| 5 | Erasure and controlled sharing design | FR-012/013; original AAMS-021/022. | Resolve immutable-ledger versus erasure semantics explicitly; tombstone/restore/index tests and a distinct authorized sharing workflow. |
| 6 | Proactive recall / knowledge-gap research | FR-014/016 and H8 after task baselines and governance. | Host opt-in, bounded interruptions, expert validation, negative transfer and safety evidence before any live proposal. |

No missing capability is silently authorized for implementation by its appearance here. The next retrieval experiment and later task-level work follow the [evaluation plan](cognitive-memory-evaluation-plan.md) and [research acceptance contract](../acceptance/v1.0-research.md). #115 remains open until its broader exit evidence exists.
