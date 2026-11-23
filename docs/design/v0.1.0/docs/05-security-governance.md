# 05 — Security, Safety and Governance

**Version:** 0.1.0 | **Status:** Proposed

## Trust boundaries

1. Raw external content is untrusted even when stored, summarized or embedded.
2. Agent generated interpretations are proposals and never inherit human/system authority.
3. An MCP client host may authorize data sharing, but the server must independently enforce permitted actions and data scopes.
4. Indexers and neural workers process data with least privilege; they cannot bypass canonical access policies.
5. Shared memory crosses security boundaries only through deliberate promotion with provenance and scope checks.

## Threat model and mitigations

| Threat | Required control | Validation |
|---|---|---|
| Prompt-injection in recalled evidence | Treat memory content as data, label source trust, never execute instructions from content | Poisoned-memory corpus |
| Forged evidence/provenance | Source authentication, digests, origin attestation where possible | Tamper tests |
| Evidence laundering | Track independent origin/derivation lineage | Duplicate-source simulation |
| Unauthorized retrieval | Deny-by-default ACL/ABAC before candidates and after expansion | Cross-scope fuzzing |
| Leakage via similarity index | Tenant-aware index partition/filter and postfilter; prevent ranking side channels | Isolation tests |
| Unauthorized belief promotion | Separation of proposal from acceptance; reviewer authorization | Privilege escalation tests |
| Race on belief revision | Optimistic version preconditions and immutable history | Concurrent update tests |
| Deletion undone by rebuild | Erasure fences/tombstones integrated into indexing and backup restoration | Restore/reindex deletion test |
| Resource exhaustion | Input size, graph depth, rate, tokens and compute budgets | Load/abuse tests |
| Stale actionable memory | Validity intervals, freshness flags, point-in-time policy checks | Old permission replay tests |

## Authorization

Define `tenant`, `principal`, `scope`, `operation`, `purpose`, `sensitivity`, `retention` as explicit policy dimensions. Operations should include `ingest`, `read`, `revise`, `propose`, `promote`, `share`, `export`, `erase`, `administer`. Scope is not equivalent to ownership. No broad superuser path inside general model-facing tools. Authorization applies to edges and derived summaries, not only root records.

## Audit model

An audit record captures actor, operation, target scope, decision, policy/version, time, correlation ID and safe outcome metadata. Do not write confidential evidence payloads into audit logs. Audit and deletion logs themselves have independently defined retention and redaction policies.

## Data lifecycle

- **Retention:** explicit classification and policy evaluation at ingest.
- **Archival:** index demotion without claiming deletion.
- **Revocation:** immediate recall denial across all interfaces.
- **Erasure:** authoritative payload and derivatives removed under defined guarantees; track inaccessible backups and deletion propagation.
- **Exceptions:** legal holds or operational limits must be reported explicitly rather than described as complete deletion.
- **Export:** signed manifest and scoped references with evidence lineage.

## Model and learning safety

Neural-generated associations are leads, not proof. Consolidation candidates must preserve source lineage, confidence basis and conditions of applicability. High-impact claims require independent verification. A model's internal state is not presumed accessible or reconstructable. The service should not execute recalled procedures unless a separate authorized runtime evaluates them.

## Minimum go-live checklist

- Threat model reviewed and signed off.
- Untrusted-content injection tests pass.
- Retrieval isolation and permissions verified.
- Backup restoration does not resurrect erased data.
- Privileged operations require separate authorizations.
- Incident response runbook and redaction processes tested.
- Dependencies and protocol versions pinned and monitored.
