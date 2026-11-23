# 03 — Memory and Belief Model

**Version:** 0.1.0 | **Status:** Proposed

## First principle

Separate **what was experienced** from **what was inferred**. A model-generated paraphrase is neither raw evidence nor independent corroboration.

## Core entities

| Entity | Essential fields |
|---|---|
| Evidence | `evidence_id`, `content_digest`, `modality`, `source_actor`, `source_locator`, `observed_at`, `recorded_at`, `scope_id`, `trust_class`, `payload_ref`, `retention_policy` |
| MemoryFormation | `formation_id`, `kind`, `semantic_payload`, `evidence_ids`, `context`, `epistemic_status`, `created_at`, `scope_id`, `schema_version` |
| Belief | `belief_id`, `proposition`, `scope_context`, `current_revision_id`, `validity_interval` |
| BeliefRevision | `revision_id`, `belief_id`, `parent_revision_id`, `support_ids`, `refute_ids`, `state`, `uncertainty`, `rationale_ref`, `recorded_at`, `effective_at`, `actor_id` |
| Relationship | `from_id`, `to_id`, `relation_type`, `evidence_ids`, `qualifiers`, `confidence_basis`, `revision_id` |
| DecisionEpisode | `decision_id`, `goal`, `context`, `alternatives`, `chosen_action`, `expected_outcome`, `actual_outcome`, `evidence_ids`, `evaluation_state` |
| Procedure | `procedure_id`, `preconditions`, `steps`, `postconditions`, `failures`, `verification`, `version` |
| Checkpoint | `checkpoint_id`, `task_id`, `active_goals`, `completed_steps`, `unresolved_items`, `referenced_formations`, `next_actions`, `expires_at` |
| DerivedRepresentation | `representation_id`, `source_ids`, `algorithm_version`, `model_id`, `encoding_type`, `materialized_at` |
| AccessPolicy | `scope_id`, `principal`, `capability`, `constraints`, `retention`, `sharing` |

## Formation kinds

1. Experiential — directly observed or reported event with context.
2. Semantic — propositions and concepts.
3. Procedural — strategies and skills with applicability constraints.
4. Causal — intervention hypotheses, causal claims, and support levels.
5. Decision — alternatives, rationale, outcome, lessons.
6. Hypothetical — predictions/counterfactuals and unknowns.
7. Self-model — attributable capability limits, calibration and constraints of a specific agent/model.

These are logical kinds, not physical silos. Each formation may have multimodal payload and multiple derived representation types.

## Epistemic state machine

`hypothetical`, `observed`, `inferred`, `contested`, `superseded`, `rejected` are *qualifiers*, not a naive linear state transition. A disputed claim may be observed as a quotation but contested as a statement about the world. The semantic claim's state and evidence record's observation status are separate. Claims move through evidence-backed revisions with explicit actors and revision reasons.

## Temporal model

Track separately: occurrence/event time, ingestion time, applicable validity interval, revision recorded time and knowledge-as-of time. Historical queries answer both what was believed then and what is now believed about the earlier event. Never silently rewrite the past when the belief changes.

## Confidence and calibration

Do not manufacture precise probability numbers. Store an uncertainty representation plus calibration provenance (`calibration_dataset`, `method`, `date`, `domain`) if numeric probabilities are used; otherwise use explicit qualitative support/unknown. Distinguish epistemic uncertainty, source reliability and situational applicability.

## Evidence independence

Each assertion carries lineage. If one source is copied into ten summaries, those ten derivatives contribute at most one independent evidentiary origin. A learned claim must not use its own previous generation as independent support. Independent replication requires independent observation or appropriately independent methodology.

## Relationship vocabulary (initial)

`supports`, `refutes`, `derived_from`, `causes_hypothesis`, `precedes`, `part_of`, `applicable_when`, `contradicts`, `supersedes`, `depends_on`, `analogous_to`, `tested_by`, `produced_outcome`, `mentions`. Typed relations have validation rules, directionality and metadata; relation expansion is always permission-checked.

## Lifecycle

`created -> indexed -> active -> archived/under_review/superseded -> erased` is a management lifecycle, independent of epistemic state. Erasure can occur from any eligible state under authorized policy. Unverified generated content cannot be promoted to factual authority through lifecycle transitions alone.

## Example (conceptual, not executable interface contract)

```json
{
  "formation_id": "fm_example",
  "kind": "experiential",
  "semantic_payload": {"observation": "p95 latency decreased in trial A"},
  "evidence_ids": ["ev_trial_A_metrics"],
  "context": {"environment": "trial-A", "workload": "fixed-input-v1"},
  "epistemic_status": "observed",
  "uncertainty": {"kind": "measurement_interval", "value": "see ev_trial_A_metrics"},
  "scope_id": "domain:perf-trials",
  "schema_version": "0.1.0"
}
```

## Cognitive checkpoints

Store **inspectable task state** rather than claiming an exact reproduction of hidden model activations or private reasoning. Resume via reconstruction, verification and agent permission checks; checkpoints never grant authority or bypass current constraints.
