# ADR-0011: Scoped erasure and restore fencing

Status **proposed for authority review**. Tracking [#127](https://github.com/baileyrd/Adaptive-Autonomous-Memory-Subsystem/issues/127), FR-012, coordinated through #105. Baseline `5d592c16eb766d1db92b0de273c78f7a992f740b`. The issue calls this AAMS-021. The historical roadmap numbers erasure AAMS-022 and uses AAMS-021 for scoped sharing. This proposal covers the issue's erasure scope. [Historical roadmap](../design/v0.1.0/docs/06-roadmap.md#L76-L79)

**A source erasure retires every old lesson revision that depended on the source.** Independent surviving observations remain readable under their own grants. They may support a separately derived and reviewed lesson with a new identity. A restored database stays quarantined until a trusted erasure record outside the backup timeline proves the served scope is current. Rebuild from the reconciled source set. If freshness cannot be proved, deny that scope, including lexical and exact reads.

## What can return from a backup today

| Surface | Current path and implication |
| --- | --- |
| Source payload, provenance, formation and ingest replay | `evidence` stores bytes, digest, actor/locator/producer and both times. Scoped `formation_evidence` joins shared source rows to formations. `ingestion` stores request keys and fingerprints. Evidence update/delete triggers abort. Identity is scoped, and MCP grants guard the native API. Existing reads return evidence from the open file. [Ledger schema and ingest](../../src/aams/storage.py#L40-L67) · [Scoped identity](0008-scoped-canonical-identity.md) · [MCP source ingestion](../../src/aams/mcp_server.py#L94-L160) |
| Belief and outcome history | `belief_revision` has parent and sequence plus proposition, rationale and temporal fields. `belief_evidence` records support/refute roles. `outcome_revision` binds an episode to a candidate with outcomes and conditions. `outcome_evidence` holds source IDs. History rows and evidence links have immutable triggers and are reachable by historical queries. [Schema](../../src/aams/storage.py#L71-L157) · [Historical reads](../../src/aams/storage.py#L517-L593) · [Outcome history](../../src/aams/storage.py#L900-L1003) |
| Candidate, lessons and other relationships | `learning_candidate` owns the claim, `candidate_evidence` links support and refutation, and append-only `candidate_decision` holds reviewer transitions and rationale. Approval requires another principal, at least two eligible support groups and no refutation. Approved candidates are staged and cannot be promoted through this API. Consolidation previews derive from bounded scoped source scans. #146 read a reviewed lesson in a disposable evaluator. General persisted derived-from edges and cross-scope promotion are design work. #135 relationship sidecars are offline fixtures. [Candidate enforcement](../../src/aams/storage.py#L648-L880) · [Preview](../../src/aams/consolidation.py) · [Reviewed lesson experiment](../audit/lesson-transfer-results.md) · [Relationship protocol](../audit/lineage-protocol.md) |
| Lexical, vectors and response caches | BM25 ranks current authorized rows and keeps a bounded in-process term cache keyed by scope, ID and digest. Optional vector batches and vectors persist beside the ledger, key by scope/provider space and validate count, source digest and checksum. Rebuild scans the open scoped evidence table. A consistent older database can satisfy current integrity checks. [Recall and terms](../../src/aams/recall.py#L227-L299) · [Vector snapshot and rebuild](../../src/aams/vector_index.py#L19-L160) |
| Checkpoints, telemetry and artifacts | Checkpoint claims and restore registries in ADR-0010 are disposable sidecars. The product has no checkpoint storage table. Retrieval telemetry stores opaque attempt IDs per principal/scope, excludes expired records, and can delete a principal's live observations. That is separate from source erasure. Shadow observations/pairs are process-local, and offline evaluations can emit files. There is no inventory of host caches, replicas, prompts, exports or externally held copies in the current service. [Checkpoint ADR](0010-disposable-task-checkpoints.md) · [Telemetry retention](../retrieval-telemetry.md) · [Shadow pairs](../../src/aams/shadow_pairs.py#L75-L118) |
| Backup and restore | The documented SQLite backup copies canonical and derived tables into a private file. Restore opens the verified file or a private copy. `verify_integrity()` validates SQLite and canonical invariants. It has no knowledge of erasure events after the snapshot. Vector recovery can rebuild from whatever canonical rows the restored file holds. [Restore procedure](../../README.md#L60-L87) · [Recovery test](../../tests/test_recovery.py#L111-L139) · [Vector recovery](../vector-index.md#recovery-and-backup-replay) |

Erasure coordinators, durable tombstones, lineage traversal across products, derivative invalidation and restore freshness gates remain design-only. The historical design calls for revoking recall before propagating erasure and for deletion across live projections and replicas. [Lifecycle architecture](../design/v0.1.0/docs/02-architecture.md#L74-L76) · [FR-012 traceability](../audit/cognitive-memory-traceability.md#L53)

## Authorization, copies and derivatives

1. A trusted host authenticates the operator and an explicit, current **erase-source** grant for one scope, bound to a policy and request key. Only the scope's designated data controller may issue that grant. General write access, candidate review, telemetry deletion and a caller-supplied scope do not confer it. Validate the grant before target resolution. Uniform denial prevents learning whether a foreign target exists. Use a stable opaque host origin key within the scope. Caller-supplied source actor/locator or a content digest alone cannot establish origin identity. Bind duplicate records and stale ingestion jobs to the same scoped origin. Quarantine unresolved provenance.
2. On an eligible request, atomically commit a monotonic fence to an independent authority before any success response or further serving from the old generation. Use `(scope, authorization owner, request key)` for retries, bind it to the same origin and policy, and return the original receipt on a repeat. Reject a changed target under the same key. Legal holds or immutable offsite media must receive an explicit policy disposition, with authorization and lifecycle status distinct from ordinary reads. Distinguish **fenced** from **purged**. Publication races, concurrent requests, crash/retry and atomic authority writes are production requirements.
3. Resolve direct and transitive dependencies using both supporting and refuting edges. Deny the source, its same-origin copies, linked formations, affected historical belief revisions and any descendants that may incorporate their content, outcome conditions and revision links, candidate claims, decisions with payload-bearing rationale, and dependent lesson/checkpoint state. Retire the entire affected lesson revision. Removing one citation alone can leave erased text or turn a contradicted claim into an apparent positive. A single-source lesson has no surviving basis. A multi-source lesson is likewise retired, even when two eligible independent supports remain. A new candidate may use only surviving evidence, under a new identity and existing validation and independent review. Where lineage is incomplete, quarantine material whose nondependence cannot be established.
4. Invalidate scoped term caches, response/session caches, sidecars, queued jobs and vector/lexical projections from the old generation. Purge managed live copies, retired dependent content, links and source-bearing ingest fingerprints. A supported implementation can replace the active ledger with a reconciled store, then securely dispose of superseded SQLite files, WAL/journals, replicas and managed exports under an approved media policy. Index workers must build from the reconciled ledger and check the fence again before publication. Retire logs or telemetry that can link to the payload. Independent telemetry can use its existing retention policy. Scope B keeps its separately authorized records, even if it uses coincident IDs and origin tokens. Existing grants and scope boundaries still apply.

Ordinary callers see the same “unavailable” as for absent evidence, with no old text, digest, parent links, scores, match counts or reference IDs. Historical queries honor the current fence. A separate privileged audit can report opaque operation ID and scoped fence token, authorization reference, policy/version, time, propagation status, coarse counts and outstanding media classes. Avoid payloads, reversible locators, source digests and free-form rationale in this retained record. Retain the minimum fence material until every admissible restore or replay source predating it has been eliminated or permanently excluded. Set audit and backup retention windows through the authority decision. Managed backups that cannot be rewritten immediately remain isolated, subject to expiry/destruction or approved cryptographic disposal. External copies beyond operator control need explicit limitations and escalation rather than a verified purge claim.

## Restore and rebuild

- Fence authority must live outside the SQLite backup chain and use an independently trusted current, monotonic head per scope. It authenticates journal epochs, membership and completeness. A signed old journal alone cannot prove freshness. Bind the backup to scope/schema and prior journal coverage. Restore into quarantine, verify structural integrity, obtain the current authority head and a complete journal or authenticated compacted state covering all possible effects since that backup. Never allow an operator to replace the authority by restoring an application file.
- Reconcile before opening any serving endpoint. Exclude fenced origins and retired closure from the replacement ledger and any builder input. Rebuild vectors and lexical/cached state from allowed records only. Recheck the head at publication, bind the served generation to it and revoke or recheck prior reader leases. A worker racing erasure must discard or retry stale work. Apply the same fence to replay/import queues and later ingestion of a denied origin.
- Missing, stale, unauthenticated or incomplete authority state leaves the affected scope unavailable for restore, exact lookup, lexical fallback and derived rebuild. Never interpret an unavailable journal as empty. A separately verified scope may be served independently if isolation is maintained. Only a privileged operator can see the restore-blocked reason.

## Authority decision and disposable evidence

Before implementation, the project owner and designated data authority must approve an explicit **exception to immutable evidence and append-only history** in [AGENTS.md](../../AGENTS.md), [ADR-0002](0002-sqlite-evidence.md), and the affected history contracts. The proposed exception permits only an authenticated scope-bound erasure workflow to remove protected payloads and dependent revisions/links from the active ledger and its managed copies, while preserving minimal audit/fence records. Approve the grant issuer and hold policy, derivative retirement and rereview rules, authority trust/retention and unavailability behavior, and backup/media obligations. Merely approving an ADR or review test does not authorize product deletions, migrations, deployment or work on real backups. Those require a separate implementation decision and rollout approval.

The [test-only contract model](../../tests/test_erasure_restore_contract.py) uses a real temporary SQLite ledger with an approved three-source lesson, a copied source, and a synthetic legacy one-source summary. The native review rejects a single-origin candidate because approval requires two independent groups. The reviewed single-origin summary is represented by a legacy fixture sidecar. It takes and restores a pre-erasure SQLite snapshot, verifies that raw restoration would contain the old data and “fresh” vectors, then constructs a separate serving projection using a current external fixture head. Native exact and lexical paths over that projection withhold the erased copies, and the rebuilt vector index contains only survivors. The fixture binds its filtered entries to the digest of the verified bytes and rechecks that digest before returning a rebuilt view. Deterministic tests advance the fence just after the first journal read and during vector rebuild. Both stale builds fail and retries serve only the surviving rows. An old open view, missing fence, stale fence and altered fence cannot serve A. Same-key retry is stable, wrong-scope and unprivileged requests fail, B remains readable, and a new lesson can be separately reviewed with the two survivors.

Tests exercise that in-process gate, scoped materialization and native rebuild over filtered fixture input. The admissible head is trusted test state, and the known direct dependencies are fixture data. They do not prove authenticated external persistence, atomic leases, complete production traversal of beliefs/outcomes, stale ingestion rejection, physical media purge, real backup operations, or end-to-end enforcement across native and MCP callers. No product source, schema or real backup changes are included.

```sh
PYTHONPATH=src python -m unittest discover -s tests -p test_erasure_restore_contract.py -v
```

## Approved restore protection

Use `open_restored_scope(backup, authority, scope)` from `aams.restore` for native reads
and index rebuilds. For MCP, start one read-only server per authorized scope with
`--restore-backup BACKUP --restore-authority AUTHORITY --principal PRINCIPAL --scope SCOPE`.
The host binds the principal and scope using its existing access policy and supplies the
trusted authority path. The backup must be a standalone SQLite snapshot of the currently
supported schema. Live-mode opening via `SQLiteMemoryStore(path)` or MCP `--db` accepts a
trusted live database. Never publish an old snapshot or a restore projection using those
live-mode entry points.

The authority lives outside the backup and rollback domain. Its SQLite interface is:

```sql
CREATE TABLE restore_scope_head (
    scope TEXT PRIMARY KEY,
    generation INTEGER NOT NULL CHECK (generation >= 0)
);
CREATE TABLE restore_coverage (
    scope TEXT NOT NULL,
    generation INTEGER NOT NULL CHECK (generation >= 0),
    backup_sha256 TEXT NOT NULL,
    complete INTEGER NOT NULL CHECK (complete IN (0, 1)),
    closure TEXT NOT NULL,
    PRIMARY KEY (scope, generation, backup_sha256)
);
```

Administrators must configure the authority from the current, independently verified
erasure record. Only its trusted writer may advance a scope head. Generations increase
monotonically, and the authority must remain outside the restore and rollback process.
The writer uses SQLite transactions against the same authority file. As part of advancing
a head, it can publish coverage in the same transaction or leave the scope unavailable
until verification completes. Do not replace or roll back the authority database out of
band. This interface consumes authenticated, current coverage supplied by the host.
It does not issue erasure decisions, authenticate a remote journal, or detect rollback
of the trusted authority itself.

Coverage binds a head to the SHA-256 of the exact backup bytes. The closure JSON object
contains five arrays of scoped IDs, named `evidence`, `formations`, `beliefs`,
`candidates`, and `episodes`. Include aliases, copies, and dependent records that
cannot be discovered through persisted relationships. Set `complete=1` only when
the current authority can account for all relevant erasures and dependency paths in
that snapshot. An empty closure is an affirmative verification. Unknown coverage or
lineage leaves the scope unavailable.

Opening captures the untouched backup into private quarantine, verifies coverage, and
creates a separate scope-only projection. Persisted evidence links expand the excluded
set to formations, complete belief chains, learning candidates and reviews, and complete
outcome chains. Outcomes associated with an excluded candidate are excluded too. Even
with surviving sources, an old reviewed lesson stays excluded if it depended on erased
evidence. A future lesson would require a new review of independent surviving sources.
The projection imports neither cached vectors nor telemetry or ingestion replay rows.
The context manages the lifetime of the temporary files.

Native and MCP reads revalidate the pinned coverage before exposing results. An open
view becomes unavailable if that coverage disappears or the scope head advances. A
separately verified scope can continue serving. Reopen a stale view only after coverage
for the current head is available. Persisted vector publication shares an authority
transaction with the head check through the projection commit, so a head advance during
encoding prevents publication. The old view also cannot serve a previously built index
after a head advance. This protects serving and publication, including a previously opened
guarded view. Backup retention and physical purge still require their separate authority
decision.
