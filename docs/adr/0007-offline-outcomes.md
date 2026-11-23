# ADR-0007 — Offline retrieval policy outcomes are not authoritative evidence

Status: Proposed
Date: 2026-11-23
Tracking: v0.6 goal #56; first implementation #57

## Motivation

v0.5 stores bounded telemetry but has no training or online policy-update path. User/model satisfaction is not a substitute for independently measured task correctness. An observational log records only the action selected; it does not prove what an unselected retrieval mode would have achieved.

## Decision

Provide immutable `OfflineOutcome` and `OfflineRiskBudget` contracts and a pure `compare_controlled` calculation. Every outcome includes opaque task and grouping IDs, selected retrieval mode, measured outcome label, measured latency, policy version and an explicit observational-versus-controlled-replay basis. No raw query or memory payload is permitted.

A controlled comparison must contain the same uniquely identified tasks measured under **different** modes and matched group IDs. Observational logs are rejected from controlled comparison rather than reinterpreted as counterfactual observations. Duplicate samples, absent matches, malformed labels and bad budgets fail closed.

The output summarizes satisfaction/unsatisfaction counts and a simple candidate average-latency risk check. This is descriptive accounting, not a causal estimate or policy selector. A true controlled claim also depends on experimental design, randomization/matching and independent sources beyond the validation implemented here.

## Non-goals and limits

- No live retrieval, automated policy updates, model training, MCP tools, new persisted tables, or candidate-belief promotion.
- No claim that an opaque group ID proves independent evidence, privacy, or correct labeling; offline experiment harness #58 must validate provenance/split constraints.
- No changed lexical default or v0.5 routing semantics.
- Do not infer alternative-mode quality from feedback rows for one mode.
- No optimization claims absent a larger held-out comparison across domains, true outcomes and matched resource budgets.

## Next acceptance gates

#58: fixed leakage-aware offline corpus and split/experiment runner.
#59: versioned, non-authoritative candidate policies trained exclusively offline.
#60: matched held-out task/relevance/cost and calibration evaluation.
#61: verified release matrix, safe fallback and limitations.
