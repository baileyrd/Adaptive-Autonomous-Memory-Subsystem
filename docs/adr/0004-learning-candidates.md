# ADR-0004 — Inert learning candidates and governance boundary

Status: Proposed for v0.3-01
Date: 2026-11-23

## Decision

Introduce an independent learning-candidate type distinct from both immutable `Evidence` and append-only authoritative `BeliefRevision`. A candidate is explicitly **untrusted** and begins only in `proposed`. It references source evidence by stable IDs, has one scope, identifies the proposer and captures the proposed claim. It does not assert that sources are independent or that a claim is true.

A separate `CandidateTransitionRequest` represents an intended lifecycle transition; it is neither an authorization token nor an executed transition. Its immutable fields identify candidate, scope, expected state, desired state, actor, rationale and time.

Transition graph:

```text
proposed --validate--> validated --approve--> approved --promote--> promoted
     |                     |
     +----reject-----------+----reject--> rejected
```

`promoted` and `rejected` are terminal statuses for one candidate. New evidence or reassessment creates a new candidate with lineage; no retroactive mutation of historical evidence.

## Invariants and limits

- Only explicit persisted decisions by a trusted, scope-checked policy engine can change candidate state. These pure contracts **do not** implement such a policy engine.
- Distinct evidence IDs are required within and across supporting/refuting lists; uniqueness alone does not prove source independence. v0.3-02 must check evidence scope and lineage in canonical storage.
- The candidate contract cannot be interpreted as memory authority or promoted by a model-generated request.
- Pure transition requests do not update persistent state or override AccessContext. v0.3-02 must bind caller identity to the trusted host and commit audited transitions atomically with expected-version checks.
- No MCP tool is exposed in this slice; existing tool semantics remain unchanged.
- Candidates must be excluded from authoritative recall until an explicitly authorized promotion policy and projection are implemented and tested.

## Alternatives

Placing proposed abstractions directly in BeliefRevision was rejected because it would mix staged learning with authoritative belief history. Automatically promoting when a confidence threshold passes was rejected because probability of usefulness is not permission or independent evidence.

## Exit evidence

Typed contract tests cover immutability, invalid timestamps/identifiers, repeated evidence links, illegal transitions, terminal states, stale state and cross-scope transition requests. Persistence, authorization, provenance independence and generation are subsequent bounded issues #25 and #26.
