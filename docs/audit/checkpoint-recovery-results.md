# #124 scoped checkpoint recovery: proposed contract and disposable test

**Completed design/disposable experiment; product checkpoint persistence remains unimplemented.** Authority: [#124](https://github.com/baileyrd/Adaptive-Autonomous-Memory-Subsystem/issues/124), O5 / FR-009 / H6; coordinated under #105. Evidence: [proposed ADR-0010](../adr/0010-disposable-task-checkpoints.md), [preregistered protocol](checkpoint-recovery-protocol.md), [aggregate results](checkpoint-recovery-results.json), [216 resumed-action traces](checkpoint-recovery-decisions.jsonl), [data pins](../../scripts/checkpoint_recovery_preregistration.json), [execution pins](../../scripts/checkpoint_recovery_execution.json).

## Outcome: guarded claims work, checkpoint-only recovery loses coverage

On 48 source-held-out interruption cases, checkpoint-only recovery chose the oracle-correct action on **12/48**, bounded journal reconstruction using trusted current-head IDs **40/48**, and the direct canonical-head deterministic control **44/48**. Checkpoint-minus-transcript is **−58.33 pp**, descriptive twelve-family bootstrap 95% interval **[−91.67, −25.00] pp** (2,000 resamples, seed 0). The design cases had the same pattern, 6/24 vs 20/24 vs 22/24. This is a negative overall recovery result, not evidence of cognitive learning or a model's inability to use checkpoints. The fixture deliberately overrepresents invalid/lifecycle cases; its mix is not an estimate of production cache failure rates.

Valid checkpoints resumed correctly in **8/8 eligible held-out cases**, including four where the bounded transcript had lost the state event. But the contract intentionally provides no automatic refresh, canonical fallback or newer-cache lookup: expired, stale, superseded, revoked or invalid proposals are denied even while their underlying canonical evidence remains available to transcript/control reconstruction. An otherwise available next task action is still scored as a failure when checkpoint recovery abstains. The four access-revoked cases correctly abstain and count as correct authorization outcomes; checkpoint's 12 correct outcomes therefore consist of **8 actual resumed actions plus 4 required denials**, not 12 completed task steps.

## Contract and authority boundaries

ADR-0010 proposes immutable checkpoint identity/generation/parent, task/scope/producer, completed versus pending work, constraints, exact evidence references, recorded/effective times, expiry and supersession. A checkpoint is a progress **claim**, not completion evidence. A trusted host recognizes the candidate digest/proposer, current reader grant/task revision and canonical head IDs. Registration does not endorse the claim's contents. Every accepted reference is resolved through the current scoped canonical store and matched on digest, source/proposer identity and both times; the claimed state must match current task-state reports.

In the original fixtures, isolated revoked, foreign and invalid-reference cases returned unavailable. The original reader classified supersession before time checks and expiry before reference checks. It did not establish uniform rejection for combined faults or enforce owner-only lifecycle disclosure. ADR-0010 now specifies those boundaries. The post-review tests use separate design fixtures and add no observations to this scorecard.

The registry and executor roles are **trusted synthetic fixtures**, not an authentication, signature, registration or real-world completion-attestation service. The contract is proposed for review. Only temporary sidecar JSON and existing disposable AAMS fixture databases are written. There is no checkpoint table, migration, native/MCP API or new product operation. No neural/learned activation, authority change or automatic memory edit occurs.

## Held-out decision and safety scorecards

All arms use the same grants, task manifests, requested time bounds and final 8,192-byte state/citation limit. The journal baseline selects up to eight recent authorized records, checks whether their IDs include the host-supplied current heads, then rereads those heads from the store. The 40/48 score measures this host-assisted reconstruction. Independent discovery of authoritative state from journal text was unmeasured. In the other arms, the checkpoint uses explicit evidence references; the canonical control reads the host's current canonical heads directly. This compares reconstruction interfaces/internal lookup policies, not equal numbers of database reads or model capabilities. The deterministic control does **not** see scoring-oracle state and still abstains on conflicting canonical certificates.

| Held-out measure | Journal + host heads | Checkpoint | Canonical control |
| --- | ---: | ---: | ---: |
| Correct actions, including required access denial | 40/48 | 12/48 | 44/48 |
| Actual ready/resumed actions | 36 | 8 | 40 |
| Abstentions | 12 | 40 | 8 |
| Valid-cache families (ready + truncated journal) | 4/8 | 8/8 | 8/8 |
| Changed constraints correctly acted on | 4/4 | 0/4 (stale denial) | 4/4 |
| Invented completed steps | 0 | 0 | 0 |
| Lost constraints in returned states | 0 | 0 | 0 |
| Active-constraint cases with no returned state | 0 | 4 | 0 |
| Repeated already-completed work | 0 | 0 | 0 |
| Unauthorized / expired-cache disclosures | 0 | 0 | 0 |
| Valid returned citations | 36/36 | 8/8 | 40/40 |
| Evidence / logical database / sidecar hashes equal across measured loop | Yes | Yes | Yes |

Zero lost constraints does **not** mean constraints were reconstructed in rejected cases: checkpoint recovery withholds all state on four changed-constraint requests. Likewise no invented progress can coexist with poor completion coverage. Abstaining on contradictory reports is safe but fails the physical next-action objective when the simulator knows an answer.

Checkpoint held-out statuses: **8 ready, 4 stale, 4 expired, 4 superseded, 8 contradictory and 20 unavailable**. Fabricated progress claims are recognized registered proposals but rejected because the source report does not substantiate them. Cross-scope/future/wrong-digest references return no partial state. Conflict fixtures contain two authorized current heads that disagree; all three reconstruction methods preserve the ambiguity. The original negative #129 model result and older experiment artifacts remain unchanged.

## Freshness, interruption and validation

Source-disjoint cases and the proposed contract were committed before evaluation implementation or aggregate scoring at **`37cfe47839e608821a350d93ff42ca75f6ace347`**. Executable/test sources were frozen before the first aggregate invocation at **`2531d98175138cdae6b398d8a5ff32b9b88ca7a2`**. There was no held-out retuning or post-result source amendment. Twelve shared synthetic families have two design/four held-out variants each, with opaque IDs. Replay checks design/held-out separation for record IDs, scopes and source actors. Separation from #117/#119/#123 was author-reported at preregistration. The runner has no prior-fixture inputs or hashes to verify that assertion. These are author-visible source-held-out variations, not twelve new independent real-world tasks.

A preparer writes the fixture ledger and sidecars, exits, and a different interpreter reopens them for each arm. Process IDs confirm the handoff. The worker opens a write-capable SQLiteMemoryStore before taking its first digest. Opening this store can run migrations. The database, evidence and sidecar hash comparisons cover the subsequent reconstruction loop only. The audit reads every sidecar to hash it. The recorded observations establish fresh-process recovery on prepared fixtures. Integrity across reopen, enforced read-only storage and independent model replacement were unmeasured.

Eight new tests exercise all lifecycle outcomes, authorization before file/reference probes, byte-identical foreign/missing/revoked/bad-reference responses, registered fabrication, self-asserted type/identity attacks, changed constraints, conflicting certificates, transcript truncation, pins and actual subprocess replay. No test requires an outcome benefit. All **191 repository tests**, formatting, lint, compilation and the MCP demo pass locally. PR-head CI links, exact head and any merge restrictions are recorded on the linked PR/#124/#105 rather than inferred from older main CI.

## Separate operating-cost record

Local Linux/Python 3.12.14, sequential fresh workers; each arm's database is 720,896 bytes and its 72 disposable sidecars total 76,098 bytes. Each request has three timing passes; repeats are not independent task samples.

| Arm | Request p50 | Request p95 | Median CPU | Peak RSS |
| --- | ---: | ---: | ---: | ---: |
| Journal + host heads | 0.907 ms | 2.998 ms | 0.909 ms | 25,144 KiB |
| Checkpoint | 0.399 ms | 1.228 ms | 0.403 ms | 24,916 KiB |
| Canonical control | 0.317 ms | 1.429 ms | 0.318 ms | 25,004 KiB |

Mixed valid/early-rejection timings include a first request, exclude scoring/final citation audits and are not inference, cold-start tails, concurrency or deployment qualification. Cache rejection may be fast precisely because no task resumes. Cost never suppresses the action scorecard.

```sh
python -m pip install -e '.[mcp]' ruff==0.14.6
python scripts/evaluate_checkpoint_recovery.py > recovery.json
python -m unittest discover -s tests -p test_checkpoint_recovery.py -v
ruff format --check src tests scripts
ruff check src tests scripts
python -m compileall -q src tests scripts
python -m unittest discover -s tests -v
python -m aams.demo
```

Input/source mismatch or a disclosure/mutation invalidates execution and exits 3. PIDs/timings may vary; exact action/status/state/citation outcomes and hashes are the replay targets. Optional llama-cpp runtime/model bytes are absent here; no substitute model decisions are fabricated. Real model-agent recovery/replacement, authenticated completion, task graphs, transactional lifecycle, retention/erasure and product persistence remain unmeasured/unimplemented.

## Recommendation

Review the proposed authority/lifecycle contract before any persistent checkpoint API. Retain conservative rejection and require an explicitly designed, reauthorized canonical reconstruction or refresh path instead of silently trusting expired/stale claims. Test that follow-up in another frozen experiment; do not patch a fallback into this already-scored comparison. Evaluate actual model reconstruction with a canonical-context capability control before claiming O5/H6 benefit. Keep native/MCP BM25/guarded behavior, canonical evidence and authority unchanged.
