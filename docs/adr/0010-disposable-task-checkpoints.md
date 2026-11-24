# ADR-0010: Scoped task checkpoint claims and disposable recovery

Date: 2026-11-24. Status: **Proposed for contract review; evaluation-only**. Tracking: [#124](https://github.com/baileyrd/Adaptive-Autonomous-Memory-Subsystem/issues/124), O5 / FR-009 / H6, coordinated by #105. This does not authorize product persistence, migrations, native/MCP operations, automatic edits or model promotion. Existing ledger semantics and BM25/guarded defaults are unchanged.

## Authority and identity

A checkpoint is an immutable **claim about resumable task state**, not evidence that work completed. Its proposed versioned envelope identifies checkpoint, task, scope, producer, generation, superseded parent, task revision, recorded/effective times, expiry, completed/pending steps, open constraints and exact evidence references. References carry scoped ID, digest, source/producer and temporal metadata. A checkpoint cannot grant access or validate its own producer.

A trusted host supplies the current task grant, authorized readers/proposer identity, active generation and registered candidate digest, current task revision and canonical state-head references. Host registry membership means only that this particular proposal is recognized; it does not make its progress claims authoritative. The experiment's host inputs are trusted fixtures, not an implemented authentication/registration service. Actual application authentication, signatures, concurrent registration and durable lifecycle enforcement need separate design review.

## Amended restore and lifecycle contract

The [original run](../audit/checkpoint-recovery-results.md) predates this amendment. Its reader and artifacts are frozen. The [amended reader](../../scripts/checkpoint_recovery_amended.py) and [regression suite](../../tests/test_checkpoint_recovery_amended.py) exercise these rules separately, using disposable design fixtures.

1. Check the current task grant, principal and scope before opening the sidecar. The host supplies a task owner separately from its list of readers. Ownership confers no read grant. A currently authorized reader may receive a verified ready state and its citations. Only a currently authorized owner may receive a detailed rejection reason.
2. Bind task, scope, registered identity, digest, producer, generation and parent. Current revocation, unknown identities and changed envelopes always yield public `unavailable`. All rejections carry null state and empty citations.
3. The trusted host assigns an immutable `registered_at` when it first records each proposal. The candidate supplies its own claimed recorded and effective times. Require claimed recorded time ≤ host registration time ≤ both requested recorded cutoff and current time. Require claimed effective time ≤ requested effective cutoff and expiry after claimed recording. Missing or invalid registration time fails closed. Equality at the registration cutoff permits further checks.
4. Check schema and reauthorize each exact reference through the current scoped store. Validate status, digest, provenance, both requested time bounds and both claim time bounds. A foreign, missing, malformed or time-invisible reference yields public `unavailable`, including on expired or superseded proposals.
5. After these gates, a recognized older generation takes precedence over expiry. An unknown future generation or mismatched active ID is unavailable. The active candidate expires when current time reaches its expiry. Historical queries retain current grants, revocations, lifecycle and task heads. The requested cutoffs constrain which claims and evidence may be used. Lifecycle reasons describe current usability.
6. For a live candidate, a revision or head-set mismatch yields stale. Resolve the current heads against the designated executor, producer and source. Conflicting certificates or disagreement with the claimed completed steps, pending complement or constraints yields contradictory. Ready requires a complete match. These checks never write or trigger fallback.
7. Return superseded, expired, stale or contradictory only to the authorized owner. Other readers receive the same public unavailable response for every rejection. Timing equivalence is outside this contract.

## Lifecycle and storage boundary

The candidate lifecycle is proposed -> registered inert claim -> ready or rejected at read-time -> expired/revoked/superseded. Registration never promotes a claim into canonical completion. Supersession preserves identity and previous candidate history; revocation/expiry denies cache reuse without deleting immutable source evidence. Separate canonical evidence may remain readable through transcript reconstruction after cache expiry/revocation. Product retention/erasure and checkpoint tombstones remain open under #127.

Only disposable sidecar JSON in an evaluator-owned temporary directory is written here, alongside a disposable existing AAMS database of immutable fixture evidence. A preparer publishes both, exits, and a different interpreter reopens them with a fresh read grant. No checkpoint table or API is added to `src/aams`. Product persistence cannot be called implemented by this prototype. Contract acceptance, schema/migration, quotas, transactional registration/supersession and host revocation must be reviewed in a later bounded PR before product writes.

## Alternatives and open decisions

Blindly replaying a summary is simpler but permits invented progress and stale constraints. Treating checkpoints as authoritative formations conflates agent claims with completed work. Automatic canonical rebase would expand authority and hide the stale-state decision. The proposed fail-closed contract favors observable rejection; it can reduce successful resumption compared with reconstructing current evidence, and the experiment must report that cost.

Open before product implementation: authenticated completion attestations and task ownership; task-head concurrency; atomic checkpoint/registry snapshots; backward-compatible schemas; non-prefix task graphs; expiry/retention/erasure interaction; safe explicit refresh; resource quotas; model-driven reconstruction and independent model replacement. The experiment does not settle these by assuming an LLM follows the contract.
