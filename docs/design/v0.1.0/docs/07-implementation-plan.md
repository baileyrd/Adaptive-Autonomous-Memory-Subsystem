# 07 — Implementation Plan

**Version:** 0.1.0 | **Status:** Proposed

## Implementation principles

Build a **modular monolith** first with strict domain boundaries, reproducible tests, and a single canonical identity/transaction substrate. Introduce microservices or a distributed graph only if measurements demonstrate need. The initial project does not assume any existing repository, language, infrastructure or external dependency.

## Suggested repository layout (technology-independent)

```text
aams/
  README.md
  docs/
    adr/                       # Architecture decisions
    specifications/            # Canonical schema, API versions
    operations/                # Backup, restore, erasure, security
  schemas/                     # Versioned JSON schema / IDL
  src/
    domain/                    # Evidence, formation, belief, scope types
    storage/                   # Transaction and content interfaces
    cognitive/                 # Formation, recall, revision, consolidation
    policy/                    # AuthZ, retention, erasure
    adapters/
      mcp/                     # Versioned MCP transport/tool mapping
      native/                  # Native API / SDK facade
    workers/                   # Index, consolidate, delete
  tests/
    contract/
    integration/
    adversarial/
    evaluation/
    fixtures/
  benchmarks/
  examples/
  deployment/
```

## Build order and first vertical slice

### Sprint-like slice A — Foundations

1. Formal domain IDs and evidence schema.
2. Transactional store, content digest and idempotency.
3. Policy decision interface; deny-by-default.
4. Crash/restart and schema migration tests.

**Proof:** repeated ingest and forced restart return the same committed observation, never partial state.

### Slice B — Claims and revisions

1. MemoryFormation validator and evidence linkage.
2. Belief model, append revision transaction, optimistic concurrency.
3. Temporal `as_of` query and provenance traversal.
4. Fixtures for contradictions, copy lineage and supersession.

**Proof:** historic and current belief can be reconstructed with no evidence mutation.

### Slice C — Recall end-to-end

1. Candidate generator using canonical indexes (exact, entity, relation, time).
2. Ranking baseline using deterministic non-neural features.
3. Budgeted context packet with evidence citations and epistemic caveats.
4. MCP `memory_form`, `memory_recall`, `memory_explain`, `memory_revise`.
5. Contract and conformance tests across at least two supported clients.

**Proof:** externally connected agent passes MVP scenario without privileged data leakage.

### Slice D — Reliability and learning proposals

1. Checkpoints and resume validation.
2. Contradiction and duplicate-lineage detection.
3. Candidate consolidation/decision episode workflow.
4. Deletion propagation, restore drills and controlled sharing.

**Proof:** automated suite detects evidence laundering, stale belief use and deletion resurrection.

### Slice E — Neural experiments

1. Representation adapter and model-versioned index.
2. Neural candidate expansion/reranking on same evaluation corpus.
3. Measure benefit relative to deterministic baseline.
4. Retain neural components only if objective criteria improve and factual fidelity is preserved.

## Testing pyramid

- **Unit:** schema validators, state transitions, temporal comparisons, policy logic, deterministic rankings.
- **Property:** revision chain invariants, idempotency, no-orphan evidence, erasure monotonicity.
- **Integration:** storage rollback, replay, index lag, MCP->domain equivalence, background job retries.
- **Compatibility:** pinned 2026-07-28 wire conformance, optional older versions separately, host SDK versions.
- **Security:** injected instructions in evidence, scoped relationship traversal, mixed-tenancy indexes, stale permissions, privilege escalation.
- **Fault:** process kill at every transaction boundary, unavailable encoder, full disk, worker restart, restore from backup.
- **Evaluation:** retrieval nDCG/recall with source evidence, contradiction recall, task pass rate, decision quality, latency and token cost.

## Continuous integration gates

On every change: format/lint, unit, schema compatibility, policy test, integration test. On release candidate: protocol conformance, full replay, fault injection, privacy/erasure, reproducible benchmark, dependency audit and disaster recovery exercise. No merge based on a green summary alone; inspect actual revision and test artifacts.

## Engineering deliverables per card

Each bounded development card must specify: desired behavior, scope/non-goals, touched interfaces, acceptance tests, security/consistency considerations, migration needs, benchmark evidence, and an independent reviewer. A finished card must include reproducible evidence and updates to relevant ADR/docs.

## Initial service contracts

- `EvidenceRepository`: `append`, `get_authorized`, `verify_digest`.
- `FormationRepository`: `create`, `get_authorized`, `list_by_evidence`.
- `BeliefRepository`: `append_revision(expected_version)`, `get_as_of`, `trace_evidence`.
- `RecallEngine`: `recall(CognitiveNeed, AccessContext) -> EvidencePacket`.
- `PolicyEngine`: `authorize(actor, action, scope, content_labels) -> Decision`.
- `RepresentationProvider`: `encode`, `version`, `health`; fully optional.
- `ErasureCoordinator`: `request`, `deny_access`, `propagate`, `verify`.

## Release checklist

1. All P0 requirements are traced to passing tests.
2. Schema migrations are forward/backward-tested for declared support window.
3. MCP compatibility is verified against pinned spec and actual clients.
4. Restore and erasure drills are documented.
5. Observability reports stale indexes and degraded paths correctly.
6. No hidden automatic promotion or cross-scope sharing exists.
7. User/developer-facing documentation accurately distinguishes prototype from proven behavior.
