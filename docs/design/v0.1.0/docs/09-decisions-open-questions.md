# 09 — Architecture Decisions, Risks and Open Questions

**Version:** 0.1.0 | **Status:** Initial proposals

## Proposed architecture decisions

| ADR | Decision | Rationale | State |
|---|---|---|---|
| ADR-001 | Model-neutral canonical memory representation | Survive model replacement and avoid embedding lock-in | Proposed |
| ADR-002 | Immutable original evidence, append-only belief revisions | Maintain epistemic integrity and temporal replay | Proposed |
| ADR-003 | Hybrid symbolic / optional neural association | Precision and provenance plus flexible retrieval | Proposed |
| ADR-004 | MCP is adapter, not storage or domain model | Interoperability independent of one protocol | Proposed |
| ADR-005 | Modular monolith for first slice | Minimize distributed consistency and ops complexity | Proposed |
| ADR-006 | Separate unverified candidates from authoritative beliefs | Stop self-reinforcing hallucination | Proposed |
| ADR-007 | Scope/authorization at every derivation and read | Prevent indirect cross-agent leakage | Proposed |
| ADR-008 | Strong canonical commits; eventual derived indexes with watermarks | Correctness plus scalable retrieval | Proposed |
| ADR-009 | No autonomous high-impact knowledge promotion in MVP | Require evidence of reliability before granting authority | Proposed |

## High-priority open questions

1. Which data representations are essential to MVP: symbolic claims, source blobs, relationships and checkpoints—or also native spatial/time-series primitives?
2. What constitutes independent corroboration for model-produced observations and tool outputs?
3. Which sources and actors can assign authoritative status, and under what policy?
4. What first hosting profile should be optimized: embedded single-agent, local multi-agent, or remote multi-tenant?
5. What are the strict commitments for erased information in offline backups and downstream external exports?
6. How should multi-modal evidence be preserved when original data is sensitive or restricted?
7. How are task outcomes observed objectively enough to train recall utility?
8. Which MCP client versions are mandatory at launch, and what compatibility burden is acceptable?
9. What exactly triggers a checkpoint, and which task fields are authoritative vs inferred?
10. What metrics justify promoting consolidated lessons into broad shared memory?

## Project risk register

| Risk | Likelihood/impact | Mitigation |
|---|---|---|
| Schema complexity delays first usable slice | Medium/High | Strict MVP types and schema-version migration tests |
| Hallucination laundering during consolidation | High/High | Origin lineage, proposal-only default, independent verification |
| Retrieval makes models overconfident | Medium/High | Explicit uncertainty, contradiction and task evaluation |
| Data deletion incomplete across derivatives | Medium/High | Lineage graph, access-deny fence, propagation verification |
| Neural index tied to one model | Medium/Medium | Disposable provider-versioned projection |
| MCP client/version mismatch | Medium/Medium | Target spec pin, tested adapters, compatibility matrix |
| Operational complexity balloons | Medium/High | Modular monolith, measurable promotion criteria |
| Multi-tenant security leakage | Medium/High | Policy-first design and adversarial scope tests |

## Decision log convention

Each accepted ADR must record: date, decision-maker, alternatives considered, evidence, rationale, implications, migration strategy, and superseded decisions. Changing an ADR creates a new version instead of silently editing the historical rationale.

## Recommended next execution action

**Execute AAMS-001 through AAMS-004 (M00)**: ratify the canonical entities/invariants, construct a small synthetic evaluation dataset, and select physical technology based on an evidence-backed spike. Do not start with an embedding integration or distributed architecture.
