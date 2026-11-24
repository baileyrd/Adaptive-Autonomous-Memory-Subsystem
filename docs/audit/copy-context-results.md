# #119: copied reports, missing contrary outcomes and an offline correction

**Completed source-held-out synthetic experiment; no serving change or cognitive-learning claim.** Tracking [#119](https://github.com/baileyrd/Adaptive-Autonomous-Memory-Subsystem/issues/119), [#105](https://github.com/baileyrd/Adaptive-Autonomous-Memory-Subsystem/issues/105). Evidence: [protocol](copy-context-protocol.md), [historical reproduction](copy-context-reproduction.json), [fresh aggregate results](copy-context-results.json), [420 fresh decision traces](copy-context-decisions.jsonl), [data preregistration](../../scripts/copy_context_preregistration.json), [execution pins](../../scripts/copy_context_execution.json).

## Reproduced failure and classification

All **144 historical #118 decisions matched exactly**, including the same three unsafe copied-report episodes for each of raw search and structured AAMS. The frozen historical sources, recipe, trace and labels are unchanged. For each episode:

| Diagnostic | Raw search | Structured BM25 |
| --- | --- | --- |
| Later failure exists in canonical authorized/time-visible history | Yes, 3/3 | Yes, 3/3 |
| Later failure is delivered under the original eight-citation cap | No, 0/3 | No, 0/3 |
| Original fixed agent on bounded context | Unsafe proceed, 3/3 | Unsafe proceed, 3/3 |
| Same agent after compacting only the already-truncated context | Still proceed, 3/3 | Still proceed, 3/3 |
| Same agent with full visible pool (diagnostic only) | Correct stop, 3/3 | Correct stop, 3/3 |

Root cause: known copied reports consume the selection window and contrary evidence is lost **before** the agent receives context. The agent can interpret the later failure when delivered. Merely counting copies differently downstream cannot recover an absent report; the original policy already does not majority-vote repeated copies. Canonical provenance fidelity does not prove a report's truth or ensure the right evidence is delivered.

The full-pool probe exceeds the original agent budget and is **not** used as a quality arm. The committed reproduction artifact preserves original record chronology, delivered/full IDs and actual decisions for the six arm/episode combinations. No original failure was relabeled or tuned away.

## Targeted correction and preregistration

The only tested intervention is an **offline** known-copy selector ahead of the final context cap. It retains the existing structured BM25 order while keeping one citation per `(source_actor, source_locator, digest, observed_at)` group. Different sources remain separate even with identical payloads; same-origin opposing reports have different digests and both survive. This recognizes exact declared copies, not independent evidence, semantic paraphrases or hidden shared origins. Neither the agent nor the oracle changes, and no adverse-outcome labels enter selection.

Fresh data/protocol were committed before implementation or measurement at **`bcb6eb5643b5bbd3c4d14d4b0d99d63ab87d3386`**. Execution sources/tests were frozen before the first aggregate run at **`d4b45bd034d701c757cb373bce5ebb9350c64666`**. Both commits and their role were recorded on #119. No intervention, case, agent, oracle or execution source was changed after the fresh outcomes were inspected.

Seven registered mechanism categories have separate source-disjoint design/held-out variants: copied positives plus a later failure, copied positives without failure, distinct declared support, current/historical changed states, same-time conflict, relabelled origins, and recovery after older negatives. Fourteen design episodes yield 28 decisions; 56 held-out episodes yield 112 decisions **per arm**. IDs, scopes and source origins were explicitly checked disjoint across splits and against #118. Held-out copy counts and chronology vary from design; categories and grammar are shared, author-visible controls. This is source-held-out evaluation, not novel real-world reasoning families.

The intervention inspects a larger bounded internal structured packet (100 citations / 65,536 bytes), validates it, then groups before delivering the same eight-citation / 8,192-byte context as the baselines. Costs include that extra inspection. This evaluates the **pre-cap selection bundle**; it does not isolate grouping from internal candidate-window/packet-budget effects with a fourth budget-only arm. That ablation remains necessary before attributing every difference solely to deduplication.

## Actual outcomes on fresh held-out data

| Measure | Raw source BM25 | Current structured AAMS | Offline known-copy selector |
| --- | ---: | ---: | ---: |
| Correct decisions | 64/112 | 72/112 | **96/112** |
| Unsafe proceed | 40/112 | 32/112 | **8/112** |
| Abstentions | 0/112 | 0/112 | 8/112 |
| Time-visible later reports delivered | 0/40 | 8/40 | **40/40** |
| Same-time conflicts detected and abstained | 0/8 | 0/8 | **8/8** |
| Benign/recovery losses | 8/40 | 8/40 | **0/40** |
| Benign/recovery abstentions | 0/40 | 0/40 | **0/40** |
| Wrong stops on safe tasks | 8 | 8 | **0** |
| Historical state/decision correctness | 8/8 | 8/8 | 8/8 |
| Canonical citation fidelity | 1.0 | 1.0 | 1.0 |
| Canonical writes during replay | 0 | 0 | 0 |

Relative to current structured recall, the selector improves completion by **24/112 (+21.43 pp)** and reduces unsafe proceed by **24/112 (−21.43 pp)**. Paired whole-family bootstrap 95% intervals are **[+7.14,+35.71] pp** for success and **[−42.86,−7.14] pp** for unsafe proceed, with seven family units and 2,000 resamples/seed 0. These are descriptive synthetic intervals, not population-level cognition evidence; 112 decisions and repeated timings are not 112 independent mechanisms. Design outcomes were 16/28 raw, 18/28 structured and 24/28 control, with 10/8/2 unsafe proceeds respectively. No tuning followed either result.

The extra eight abstentions occur on genuinely unresolved same-time report conflicts, not clean/recovery tasks. They reduce unsafe action but do not count as completed tasks. Remaining eight unsafe control decisions are the early same-time-conflict snapshots: the simulator state is blocked but only an incorrect positive report is available then. The selector cannot invent later evidence or attest source truth. All other control errors are honest abstentions on the later conflict snapshots; this is not complete safety or truth adjudication.

Recovery succeeds with the same policy, so the result is not achieved by blindly preferring negative reports. The independent-clean sources remain distinct. The relabelled-copy family **does not show a control advantage**: structured BM25 already retrieved the later failure there. Source-locator/identity tokens affect BM25 document lengths/order, and these alias names happened to favor the later record over the copies. Raw source-only ranking still failed. Do not present this as successful hidden-copy detection or retune alias strings after seeing held-out results; a stronger independent alias/adversarial corpus remains a limitation.

## Safety, fidelity and cost are separate

Every inspected control candidate and every delivered context passed canonical scope, valid/recorded time, digest, preview, source actor/locator, producer and status validation before grouping or decision scoring. Private/future decoys never enter the selection groups. All three arms run in fresh decision processes after their own identical source preparation, and every canonical database digest is unchanged after replay. Rule-parser handling of instruction-like text is inert; model prompt-injection resistance is unmeasured. Valid citations can still support a physically wrong decision, as the residual eight failures show.

The latent simulator supplies labels independently of reported claims; the selector receives only canonical citation metadata, not `world`, `later_ids`, hidden origin labels or expected actions. Actual used IDs, context hashes, declared-group hashes, actions and errors are in the trace. Aggregate/trace hashes are cross-checked. Six new tests exercise exact-copy-only grouping, opposing-origin/content/time preservation, neutral rank order, source-disjoint pins, historical filtering, candidate tampering, fresh processes and the unchanged historical failures. Tests impose no minimum gain, so negative outcomes remain publishable.

Local Linux / Python 3.12.14, same host and workload per arm; 1,671,168-byte databases:

| Arm | Request p50 | Request p95 | Median CPU | Peak RSS |
| --- | ---: | ---: | ---: | ---: |
| Raw search | 0.461 ms | 0.704 ms | 0.461 ms | 28,040 KiB |
| Structured AAMS | 0.622 ms | 0.873 ms | 0.622 ms | 29,148 KiB |
| Offline selector | 2.030 ms | 3.986 ms | 2.030 ms | 29,064 KiB |

The selector includes candidate validation in the timed acquisition path; common final validation/scoring is outside it. Five passes include a first request. No candidate windows truncated in this small corpus. These costs do not establish a deployment SLO, cold-start tail, concurrency/scaling behavior or ONNX resource qualification; cost failure would not suppress task outcomes.

## Reproduce and recommendation

```sh
python -m pip install -e '.[mcp]' ruff==0.14.6
python scripts/evaluate_cognitive_tasks.py > historical.json
python scripts/evaluate_copy_context.py > fresh.json
python -m unittest discover -s tests -p test_copy_context.py -v
ruff format --check src tests scripts
ruff check src tests scripts
python -m compileall -q src tests scripts
python -m unittest discover -s tests -v
python -m aams.demo
```

The first command reproduces the old frozen pipeline; the new experiment also performs its own 144-decision comparison before fresh scoring. New source/data/historical pins fail closed; execution errors exit 3 with explicit invalid status. All **181 tests**, formatting, lint, compilation and MCP demo passed locally at the pinned execution source. Current PR-head CI links and exact SHAs are recorded in the PR/#119/#105 handoff. The locally tested execution SHA is in the aggregate JSON; report-only commits do not change source bytes.

Recommend retaining this as an offline positive result for **pre-cap declared-copy diversity**, with an explicit candidate-budget-only ablation, stronger hidden-origin/long-document adversaries and model-agent decision tests before a serving proposal. No production recall code, BM25/guarded default, authority, neural activation or independent-source policy changes here. A serving-path change requires a separate bounded PR and review. Real-world cognitive learning, checkpoints, richer transfer and model reasoning remain unmeasured.
