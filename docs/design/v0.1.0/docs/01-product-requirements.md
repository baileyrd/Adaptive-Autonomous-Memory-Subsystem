# 01 — Product Requirements

**Version:** 0.1.0 | **Status:** Proposal

## Problem statement

AI systems can retrieve text yet still fail to retain a reliable distinction between an event, its interpretation, an uncertain hypothesis, a decision and its measured outcome. Existing conversation context is ephemeral; model weight updates are difficult to audit; naive summary accumulation magnifies errors. AAMS provides persistent, accountable learning inputs without assuming that a memory system is itself a general reasoner.

## Objectives

- O1: Preserve exact and attributable source evidence before deriving meaning.
- O2: Capture reusable memories and relationships with identity and relevant context.
- O3: Answer explicit cognitive retrieval requests with relevance, citations and contradiction visibility.
- O4: Track beliefs as evidence-linked, revisable claims with temporal scope.
- O5: Restore task continuity across sessions and model replacements using checkpoints.
- O6: Support multiple authorized agents and scoped knowledge sharing.
- O7: Evaluate learning and behavioral improvement empirically, not by recall volume.

## Personas / actors

- **AI host:** application that mediates model interaction, consent and tool execution.
- **Agent:** authenticated model-associated worker and source of proposed observations.
- **Verifier:** independent actor or system authorized to attest evidence and review promotions.
- **Memory administrator:** sets retention, quotas, trust policies, domains and sharing rules.
- **Learning worker:** background consolidator that proposes, never silently promotes, derived knowledge.

## Functional requirements

| ID | Priority | Requirement | Verification |
|---|---|---|---|
| FR-001 | P0 | Append source evidence with checksums, origin, time and access scope | Round-trip and integrity tests |
| FR-002 | P0 | Create immutable-identity memory formation referencing evidence | Schema/constraint tests |
| FR-003 | P0 | Retrieve by exact identifiers and contextual query | Deterministic and relevance tests |
| FR-004 | P0 | Return provenance, epistemic status, applicability and belief revision | Contract tests |
| FR-005 | P0 | Enforce tenant, principal, domain and memory-scope authorization | Deny-by-default security tests |
| FR-006 | P0 | Revise beliefs by appending revisions without rewriting source observations | History reconstruction tests |
| FR-007 | P0 | Expose MCP tools and resources via adapter with protocol pinning | MCP interoperability tests |
| FR-008 | P0 | Recover committed state after crash/interruption | Fault-injection tests |
| FR-009 | P1 | Store task checkpoints with resumability and expiration | Restore task tests |
| FR-010 | P1 | Identify contradiction and provenance overlap | Adversarial corpus tests |
| FR-011 | P1 | Consolidate evidence into reviewable candidate abstractions | Review and rejection tests |
| FR-012 | P1 | Enforce retention, erasure, derivative lineage and auditable deletion status | End-to-end erasure tests |
| FR-013 | P1 | Allow policy-gated promotion from private to shared memory | Boundary tests |
| FR-014 | P2 | Proactive recall via host opt-in with relevance/interruption budgets | Controlled user-agent evaluation |
| FR-015 | P2 | Learn retrieval/ranking strategies from task outcome feedback | A/B evaluation |
| FR-016 | P2 | Propose knowledge gaps and informative experiments | Human/agent expert validation |

## Nonfunctional requirements

**Correctness:** no silent overwrites, referential integrity, reconstructable belief changes, and consistent policy enforcement across APIs.  
**Security:** no executable instructions inherited from retrieved content; scoped credentials; protected transport; audit logs; encryption at rest/in transit where deployed.  
**Reliability:** crash-safe commits; migrations; backup/restore; idempotent ingestion; operational health checks.  
**Efficiency:** explicit latency/token/cost budgets and a measured retrieval quality–latency Pareto curve.  
**Portability:** canonical representation independent of any embedding provider or particular foundation model.  
**Interoperability:** versioned MCP adapter with fallback negotiation for older clients as explicitly supported.  
**Observability:** trace capture, ranking explanations, audit trail, redacted metrics, provenance lineage.

## Out of scope for initial release

- Training the foundation model or writing directly into model weights.
- Inferring secret internal reasoning or hidden activations from MCP.
- Autonomous execution of external actions on the basis of recalled text.
- Guaranteed causal inference from observational data alone.
- Fully automatic, unsupervised truth adjudication.
- Global consensus across agents or unrestricted cross-tenant sharing.

## Release definitions

**Prototype (MVP):** evidence capture, formations, belief revisions, exact+basic semantic recall, MCP, permissions and crash recovery.  
**Alpha:** checkpoints, temporal queries, contradiction surfacing, consolidation candidates, real eval corpus.  
**Beta:** scoped multi-agent sharing, deletion lineage, optional neural ranking, performance and security hardening.  
**Research:** proactive retrieval, autonomous learning utility, memory-to-weights experiments (optional and separately governed).
