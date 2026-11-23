# AAMS MVP acceptance contract

**Status:** Proposed execution baseline for [goal #1](https://github.com/baileyrd/Adaptive-Autonomous-Memory-Subsystem/issues/1). **Scope:** runnable, local-first memory service for AI hosts, not autonomous neural learning.

## Design sources and open decisions

The [AAMS v0.1.0 design dossier](design/v0.1.0/README.md) provides the architectural baseline. [Goal #1](https://github.com/baileyrd/Adaptive-Autonomous-Memory-Subsystem/issues/1) and its linked issues define the release acceptance criteria and dependency order. The original dossier is preserved as supplied. Record changes to its design proposals in ADRs.

- The Python bootstrap follows the dossier's modular-monolith proposal. #3 will validate the transactional storage choice against atomic writes, durable evidence and schema evolution.
- Issue #1 and issues #4–#5 bring temporal reconstruction and contradiction visibility into the MVP. The dossier's product requirements list those under Alpha. #4 defines temporal validity and scoped authority, and #5 defines ranking and the evaluation fixture.
- #6 starts with the dossier's local stdio deployment proposal and verifies protocol and client compatibility, including support for the dossier's proposed 2026-07-28 version.
- Checkpoints, autonomous consolidation, neural association and broader lifecycle features follow the dossier's later milestones.

## Core demonstration
1. Start AAMS in a documented local environment.
2. An authorized caller stores an observation and original source provenance.
3. Shut down and restart the process; the committed observation remains.
4. A second authorized session recalls it through an MCP tool.
5. Append a belief revision referencing evidence; do not mutate original evidence.
6. Query current and prior belief states by time or revision.
7. Explain why a claim is believed and identify conflicting evidence.
8. Reject unauthorized cross-scope access without disclosing protected existence.
9. Run tests, recovery checks and an executable demo from a fresh checkout.

## P0 domain invariants
- **Evidence:** immutable identity; source, scope, digest, acquisition time, producer, payload/reference and validation status.
- **Formation:** stable ID, kind, evidence links, scope, recorded/valid time, producer, provenance and epistemic state.
- **Belief:** append-only revisions with optimistic concurrency, evidence links, epistemic state and temporal reconstruction.
- **Recall:** deterministic exact lookup and modest relevance ranking, scope/time filters, bounded responses, source citations, contradiction and truncation fields.
- **Authorization:** scoped access before every write, read, relation traversal and MCP response.
- **Persistence:** atomic commits, restart verification and corruption/recovery tests.
- **Interfaces:** model-neutral domain API with MCP `memory_form`, `memory_recall`, `memory_explain`, `memory_revise` over a verified supported transport.

## Delivery trace
| Issue | Scope | Exit evidence |
|---|---|---|
| #2 | Bootstrap and documentation | clean checkout runs tests, CI, ADR, reviewed design baseline |
| #3 | Evidence and formations | durable atomic writes + restart/integrity tests |
| #4 | Beliefs and security | revision replay + authorization tests |
| #5 | Recall | deterministic ranked recall + explanation tests |
| #6 | MCP | protocol/client tests + cross-session demo |
| #7 | Hardening | fault/security/benchmark evidence + reproducible release |

## Out of MVP
Neural training, autonomous generalization, proactive model context injection, distributed replication, multi-node consensus, and model-weight mutation. Deferred does **not** mean untracked: retain roadmap references.

## Validation and release rule
A feature is not done when only its schema or interface exists. Cite test commands, outputs, CI URLs and reviewed commit SHA. Never label the MVP released without the full end-to-end demonstration. Protocol versions and SDK compatibility must be verified at implementation time rather than copied from design notes without testing.
