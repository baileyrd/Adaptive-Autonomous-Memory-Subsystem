# ADR-0005 — Model-neutral, disposable representations

Status: Proposed
Date: 2026-11-23
Tracking: #34 / #35

## Decision

Create a replaceable `RepresentationProvider` boundary with versioned `RepresentationSpec` and immutable `DerivedVector` records. Vectors always reference a canonical source by ID, scope, and SHA-256 digest. The returned vector is an **index artifact**, not independent evidence and not an authoritative belief. Store-provider index layout, lifecycle, and retrieval wiring are deferred to #36 and #37.

Providers must identify provider/model/version and dimension. Generation must be bound to bytes obtained from an authorized canonical retrieval path. This first contract has **no ability to authenticate those bytes or authorize callers**; those checks belong to the storage integration.

## Test fixture

`DeterministicFixtureProvider` performs simple byte-bucket arithmetic for fast, offline contract tests. It is **not a neural model, semantic encoder, embedding quality baseline, or evidence of accuracy**. A real local encoder must be measured independently in #38.

## Compatibility and safety

- Validate finite floats, fixed positive dimensions and stable provider/version identity.
- Do not mix incompatible model-version vectors in a similarity index.
- Do not let model-specific vectors become the sole source of evidence or an authorization decision.
- Indexes are replaceable, rebuildable, and discardable. Stale or unavailable indexes must fall back to deterministic canonical retrieval.
- No new MCP methods, source data mutations, migration, automatic consolidation or promotion are introduced by #35.

## Follow-up exit gates

#36: Scoped index, migrations, rebuild, invalidation, freshness and corruption tests.
#37: Hybrid recall, deterministic fallback and authorization recheck.
#38: Actual neural model evaluation versus lexical baseline using held-out, source-independent labels.
#39: Evidence-based acceptance and limitations.
