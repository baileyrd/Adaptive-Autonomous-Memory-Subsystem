# Fresh-process checkpoint-assisted rule-agent control

**Neutral checkpoint result:** checkpoint assistance and existing structured AAMS recall both produced 16/16 correct held-out decisions, comprising **14 supported next actions and two required access denials**. There is no observed checkpoint advantage over structured recall. This is a deterministic rule-agent control, **not a language-model recovery result**.

The [protocol](agent-restart-protocol.md) and executable were [preregistered on #124](https://github.com/baileyrd/Adaptive-Autonomous-Memory-Subsystem/issues/124#issuecomment-7151469826) at `7f27df140f07f195339dcdb3f2f00f3f3d11bb66`, before scoring. [Input, separate label and source pins](../../scripts/restart_agent_freeze.json) cover 36 histories: four independent calibration tasks, 16 design and 16 held-out. The first pre-scoring unit run caught a missing source-level effective-time filter in the new transcript adapter; it was corrected before the execution freeze, without changing cases or action keys. Both subsequent benchmark runs used the frozen executable. No held-out tuning or scored-run failures occurred.

[Aggregate evidence](agent-restart-results.json) includes the exact tested SHA, environment, per-reader file manifests, logical database fingerprint, pair counts and costs. [All 132 task traces](agent-restart-decisions.jsonl) include full packets, actual agent outputs, interpreted states, oracle actions, simulated consequences, evidence stages and process identities. JSONL SHA-256: `ddb45bb6f75711f1b7406fb8bdadf7858f71bf83ed3e3f8f510a9062eb5e6a20`.

## Memory correctness and safety

**Verified for the evaluated fixture paths:** every delivered citation matched scoped canonical bytes/digest/provenance and both requested time bounds. No unauthorized, cross-scope or time-ineligible source was delivered; no expired or rejected checkpoint interpretation became evidence. All rejections were empty and independently authorized structured fallback supplied source bytes. No file mutation, invalid citation, partial restore or budget overflow was observed.

Across two complete fresh runs, all **38 physical files** (36 checkpoint sidecars, registry and database) had identical preparer/reader hashes. The portable logical database digest was `126bc7b2ab745e524ff2b5674cb65f09daebe2793ccdb483e3b40fa7afe977b1`. All per-file maps and SQLite version are retained, following #131's integrity correction. Cross-SQLite physical byte reproducibility is not claimed. The state certificates, grants and registry remain trusted synthetic fixtures; real authentication, transactionally concurrent revocation and persistent authority remain unimplemented here.

Additional tests deny access before sidecar/source probes, reject a host-recognized but fabricated progress interpretation, exercise expired/foreign rejection and fresh canonical fallback, exclude both temporal decoys, verify failed-attempt counterfactual behavior and enforce SQLite read-only mode. An actor's first action runs in a different interpreter for every decision: **132 distinct actor PIDs per run**, separate from the preparer and five reader processes.

## Cognitive task outcomes

The separate full-evidence diagnostic passed **4/4 supported correct actions** (verify, publish, repair, verify). All decisive certificates were visible. This establishes capability only for the authored rule agent on its shared synthetic grammar. It does not establish that #129's model can interpret the same histories.

| Held-out outcome (16 tasks per arm) | No memory | Transcript | Structured BM25 | Checkpoint-assisted |
| --- | ---: | ---: | ---: | ---: |
| Correct decisions | 2 | 2 | 16 | 16 |
| Correct supported next actions | 0 | 0 | 14 | 14 |
| Correct required denials | 2 | 2 | 2 | 2 |
| Both variants correct (8 pairs, including denial pair) | 1 | 1 | 8 | 8 |
| Incorrect abstentions / stalled consequences | 14 | 14 | 0 | 0 |
| Invented progress / repeated failed attempts / repeated completed work | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 |
| Lost active constraints in returned state | 0 | 0 | 0 | 0 |
| No returned state despite active constraints | 2 | 2 | 0 | 0 |
| Unsupported correct guesses / unsupported non-abstaining actions | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 |

Design totals were identical to held-out totals. The seven action-changing pairs test progress, failure and constraint changes; the eighth pair requires access denial in both variants. The rule agent repaired an unresolved failed verification instead of repeating it, and resolved active approval constraints before publication. Consequences are simulator-classified first steps, not executed real-world actions or completed multi-step tasks.

Checkpoint-minus-structured correctness was **0 percentage points, descriptive eight-family interval [0,0]**, with **zero gains and zero regressions**. Structured and checkpoint each gained 14 decisions over no memory, with zero regressions: +87.5 pp, family-bootstrap interval [+62.5,+100] pp. Transcript-minus-no-memory was 0 [0,0]. There were 2,000 equally weighted whole-family draws, seed 0; both members stayed together. Eight author-visible mechanisms and a deliberate distraction-heavy case mix cannot establish generalization or real interruption rates. The preregistered checkpoint-benefit criterion **failed**: no positive lower bound over structured recall.

## Retrieval effectiveness and error attribution

| Required evidence (14 authorized tasks; denials excluded) | No memory | Transcript | Structured BM25 | Checkpoint-assisted |
| --- | ---: | ---: | ---: | ---: |
| Decisive certificate delivered | 0/14 | 0/14 | 14/14 | 14/14 |
| Errors: unavailable to arm | 14 | 0 | 0 | 0 |
| Errors: missed by retrieval | 0 | 0 | 0 | 0 |
| Errors: excluded from final context | 0 | 14 | 0 | 0 |
| Errors: presented but misinterpreted | 0 | 0 | 0 | 0 |

Transcript replay's recent journal chatter exhausted its citation cap and excluded the decisive state certificates. This is a bounded recency-replay comparator, not an optimized transcript reasoner or raw search. Structured recall and checkpoint assistance share the existing lexical candidate pool; a checkpoint supplies verified pre-interruption source references plus later executor observations, and rejects to structured fallback. The 10 ready checkpoint cases, two expired cases, two foreign-envelope cases and two denied cases are recorded separately. Successful fallback after expired rejection is not successful cache reuse. No evidence here shows an advantage over a direct canonical reader or over representative natural-language retrieval.

The source-support metric conservatively requires the latest designated certificate, even if an older identical certificate could justify the same action. All actor-returned state and citations remain in the trace for inspection. #129 is unchanged: its 14 neural tasks had decisive evidence presented and were all abstentions, a different failure stage from this rule-control transcript result.

## Operating cost

Python 3.12.14 / Linux / SQLite 3.53.1, sequential processes on the same host. The first run overlapped local validation; its original timings remain in the traces. Costs below come from a third complete run with no concurrent test/install command, which matched every semantic decision and file hash. Costs include context preparation and starting a new Python actor for each decision; eight citations / 8,192 context bytes and 12,288 total packet bytes were enforced for all arms. Byte budgets do not measure model tokens.

| Held-out cost | No memory | Transcript | Structured BM25 | Checkpoint-assisted |
| --- | ---: | ---: | ---: | ---: |
| Median decision ms | 30.28 | 30.75 | 35.11 | 37.90 |
| p95 decision ms (nearest rank, n=16) | 44.46 | 35.99 | 40.24 | 54.24 |
| Worker peak RSS KiB | 25,164 | 25,292 | 25,548 | 25,932 |
| Maximum individual actor RSS KiB | 23,828 | 24,600 | 24,728 | 24,728 |
| Actor-child CPU seconds (32 design + held-out decisions) | 0.964 | 0.925 | 0.942 | 0.964 |

The matched regenerated preparation had the same physical hashes as the scored preparation: database **856,064 bytes**, 36 sidecars **33,616 bytes**, registry **3,312 bytes**. Worker CPU per decision and full packets are also recorded. RSS figures are separate process maxima, not an aggregate simultaneous peak. Timing changed between replays, as expected. Cost-run per-task timings and process metrics are retained separately in the aggregate JSON; shared-host background contention remains uncontrolled. No resource deployment gate, concurrency/cold model load, inference/token cost or production traffic claim follows from these tiny stdlib rule processes.

## Reproduction and disposition

From a clean checkout on Linux:

```sh
python -m pip install '.[mcp]' ruff==0.14.6
python scripts/evaluate_agent_restart.py > restart.json
PYTHONPATH=src python -m unittest discover -s tests -p test_agent_restart.py -v
ruff format --check src tests scripts
ruff check src tests scripts
python -m compileall -q src tests scripts
PYTHONPATH=src python -m unittest discover -s tests -v
python -m aams.demo
```

The two full executions matched **all 132 semantic trace objects**, summaries and paired intervals. Compare `traces` from a fresh output with JSONL in file order, omitting only `agent_pid`, `elapsed_ns` and `worker_cpu_ns`; all decisions, packets, stages and consequences must match. The canonical compact sorted-key JSON encoding of that semantic list has SHA-256 `62dfa89a0965630eefb0bfe930bf3efdbdc8a23fda60cd43eaa291335d0a3716`. Compare physical file maps within each run and logical digests across runtimes. All **206 local tests**, pinned format/lint/compile and MCP demo passed. Head-specific GitHub CI and merge evidence are recorded on the PR and coordination issues.

**Verified:** disposable fresh-process rule actions, bounded safety checks, calibration and replay. **Failed:** the criterion for added checkpoint benefit over structured recall. **Inconclusive:** utility outside the eight synthetic mechanisms. **Unmeasured / not run:** language-model recovery or replacement, genuine task execution, persistent checkpoint authority and production efficacy. The pinned Qwen artifact could not be downloaded under this environment's published network configuration; the optional runtime build also failed. No simulated model output is substituted. #118, #120, #122, #129, #130 and #131 artifacts and production BM25/native/MCP behavior remain unchanged.

One next action: obtain an approved, checksum-pinned executable model/runtime and preregister a separate model-driven calibration/comparison using new histories before making any model continuity claim. No deployment or persistent authority is authorized by this control.
