# Canonical fallback after an unusable checkpoint

A freshly authorized canonical read recovered 36 additional correct decisions on 56 held-out synthetic requests. Direct canonical reads achieved the same score. The measured gain comes from restoring access to usable canonical evidence after cache rejection. These data show no action-quality advantage to placing a checkpoint before the direct canonical read.

| Held-out outcome | Checkpoint only | Checkpoint + fallback | Direct canonical |
| --- | ---: | ---: | ---: |
| Correct decisions | 12/56 | 48/56 | 48/56 |
| Correct resumptions | 4 | 40 | 40 |
| Correct abstentions when final access was denied | 8 | 8 | 8 |
| Unavailable state with an active constraint | 4 | 0 | 0 |
| Valid returned citations | 4/4 | 40/40 | 40/40 |
| Invented progress / returned active constraints lost / repeated steps | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 |

The preregistered paired difference was **+64.29 percentage points**, with 36 gains and zero newly wrong decisions. The descriptive 95% interval from resampling the 14 families was **+42.86 to +85.71 points**. Design-split totals were 6/28, 24/28 and 24/28 respectively. The two splits share synthetic mechanisms. Family balance was chosen to exercise rejection and cannot estimate production cache failure rates. The simulator, trusted host and decision rule are deterministic; model replacement and general cognitive benefit remain unmeasured.

## What happened on rejection

Each of nine held-out families contributed four gains: expiry, supersession, checkpoint revocation, stale constraints, fabricated progress, foreign reference, foreign envelope, missing sidecar and a reader without owner privileges. In the changed-constraints family the newly resolved action was to handle the active constraint. Fallback classified success using independently authorized current evidence and never promoted the rejected claim.

All arms abstained on four contradictory-head and four historically invisible-head cases. Those eight safe abstentions scored as misses against the simulator’s physical next action. The eight **correct** abstentions were four initially denied requests and four grants revoked between attempts. In the latter family, checkpoint-only had already abstained on an expired claim; its correct action under the final grant does not demonstrate a second authorization check. The fallback arm checked the fresh grant and performed zero canonical lookups on those four requests. No denied or expired-cache state disclosure or invalid citation was observed in the run. The threat model uses trusted synthetic host snapshots and a read-only database in a disposable directory.

## Evidence and reproduction

- [Preregistration](canonical-fallback-protocol.md), [case/source hashes](../../scripts/canonical_fallback_freeze.json) and [public issue record](https://github.com/baileyrd/Adaptive-Autonomous-Memory-Subsystem/issues/124#issuecomment-7147104973). Design and labels were published at `17881e2`; the executable and tests were published at `794e637` before scoring. No protocol amendment or held-out tuning was made.
- [First-run aggregate, environment, timing, and family counts](canonical-fallback-results.json) and [all 252 decision traces](canonical-fallback-decisions.jsonl). A second fresh run reproduced every trace, split score and file-manifest digest. The preparer and all three read-only readers agreed on the hashes of all 79 files across reopen. The six deliberately missing sidecars account for the difference between 84 episodes and 78 sidecars.
- Median decision times on the first run across both splits were 0.241 ms for checkpoint-only, 0.436 ms for fallback and 0.217 ms for direct canonical reads. These measurements exclude preparation and scoring. They describe this sequential fixture run.
- The [original #130 negative result](checkpoint-recovery-results.md) remains a separate frozen experiment: 12/48 checkpoint-only, 40/48 for the host-assisted journal, 44/48 for direct canonical heads. The new 56-case denominator and three arms do not revise those scores.

From the repository root on Linux with Python 3.11 or newer:

```sh
python scripts/evaluate_canonical_fallback.py > fallback.json
python -m unittest discover -s tests -p test_canonical_fallback.py -v
```

The first command reruns every arm from a fresh store and emits rows, summaries and timing. Compare its per-arm rows and split summaries to the archived evidence; timings vary by host. Review the evidence before considering a further comparison against direct canonical reads on representative workloads. Product persistence, host authentication, transactional revocation and deployment remain separate design questions.
