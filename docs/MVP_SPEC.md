# AAMS MVP acceptance contract

**Status:** Proposed execution baseline for [goal #1](https://github.com/baileyrd/Adaptive-Autonomous-Memory-Subsystem/issues/1). **Scope:** runnable, local-first memory service for AI hosts, not autonomous neural learning.

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
