# #117 cognitive decision pilot: outcome and limits

Tracking: [#117](https://github.com/baileyrd/Adaptive-Autonomous-Memory-Subsystem/issues/117), [#105](https://github.com/baileyrd/Adaptive-Autonomous-Memory-Subsystem/issues/105). **Completed synthetic rule-agent pilot; model-agent cognitive utility NOT MEASURED.** The [preregistered protocol](cognitive-task-pilot-protocol.md), [source/input pins](../../scripts/cognitive_task_preregistration.json), [aggregate results](cognitive-task-pilot-results.json) and [144 decision traces](cognitive-task-pilot-decisions.jsonl) distinguish task outcomes from retrieval coverage and deployment cost.

## Finding

Structured AAMS completed **18/24 held-out decisions**, versus **16/24** for raw source search; design results were **17/24 for both**. The held-out paired delta is **+8.33 percentage points**, with a descriptive family-bootstrap 95% interval of **[0, +25] pp**. Only four independent scenario families contribute to this interval; this is **inconclusive**, not validated learning or a general reasoning benefit. Two differences occur in the interrupted-constraints family, where AAMS's formation/belief retrieval retains prior training evidence that the bounded raw list misses. Do not infer a task-checkpoint implementation from this result.

The no-memory arm abstained on all 48 decisions because current requests contain no environmental facts. This is a deliberate information-absence control, not a competitive agent baseline or a useful intelligence-effect estimate. Citation correctness and decision correctness differ: both memory arms produced **three unsafe proceed decisions** in design despite valid canonical citations. Report those failures rather than averaging them away.

## Separate scorecards

### 1. Memory correctness and safety

All delivered citations were revalidated for scope, digest, source actor/locator, producer/status, preview and valid/recorded time. Private/future/instruction-like decoys were included; canonical memory digests were unchanged after all three decision-worker runs. Inferred/contested fixture beliefs were seeded by the simulated host, with a fixture-only recording clock in the preparer, not promoted by the agent. Eight targeted tests exercise oracle/report separation, missing evidence, conflict/repetition, injection-like text, tampering, grouping, real store history and fresh worker processes.

These checks establish this pilot's memory boundary, **not safe agent behavior**. The three unsafe decisions per memory arm remain failures. The rule parser treats instruction-like content as data; model prompt-injection following and real-world source authenticity are NOT MEASURED. Source labels in this simulator do not prove external independence. No agent writes canonical memory or performs external actions.

### 2. Task decisions (not retrieval labels)

Each split has 12 synthetic episodes and 24 decisions, grouped into four scenario families. Correctness is computed from hidden simulator state, not whether a relevant evidence ID was retrieved. Same rule policy and bounded contexts in every arm; the oracle and family/split/expected fields are excluded from agent requests.

| Measure | No memory | Raw source search | Structured AAMS |
| --- | ---: | ---: | ---: |
| Design task success | 0/24 | 17/24 | 17/24 |
| Held-out task success | 0/24 | 16/24 | 18/24 |
| Held-out abstentions | 24/24 | 8/24 | 6/24 |
| Held-out wrong non-abstaining decisions | 0/24 | 0/24 | 0/24 |
| Design unsafe proceed decisions | 0/24 | **3/24** | **3/24** |
| Historical decisions and exact retrospective state | 0/3 | 3/3 | 3/3 |
| Contradictory-source cases explicitly detected/abstained | 0/6 | 6/6 | 6/6 |
| Later attempts repeating a known failed action | 0/3 | 0/3 | 0/3 |
| Held-out action changed versus empty-context ablation | 0/24 | 16/24 | 18/24 |
| Unsupported actions relative to their delivered citations | 0 | 0 | 0 |
| Canonical citation fidelity precision | null (no citations) | 1.0 | 1.0 |

Abstaining is safe but does not finish an otherwise decidable task. Thus conflict handling can succeed while task completion fails. Conversely a report can support an action that is wrong in the environment: zero unsupported assertions does not mean zero factual errors. Citation precision here checks canonical source fidelity, not source truth or relevance. Known-failure repeat rate is a bounded simulated decision measure; no-memory's zero repeats arise from never acting. It does not establish long-term error reduction, adaptation or transfer.

### 3. Retrieval effectiveness

**NOT SCORED** in this task pilot: no recall/nDCG labels are invented from decision successes. Actual used citation IDs, context hashes, actions, latent expected actions, errors and ablation sensitivity are retained in the decision traces. Neural/dense/static quality research remains #109; no new encoder duplicates #112 work. No costly candidate is excluded on a deployment budget here.

### 4. Operational efficiency

Local Linux / Python 3.12.14, single worker per arm, fresh interpreter after a separate ingestion process. Each arm has its own identical source workload and a 380,928-byte database; generated revision IDs differ but canonical contents remain unchanged within each replay. Eight citations and 8,192 serialized bytes bound the delivered context. Five timings per task are not additional quality samples.

| Arm | Request median | Request p95 | Median CPU | Peak process RSS |
| --- | ---: | ---: | ---: | ---: |
| No memory | 0.0006 ms | 0.0008 ms | 0.0006 ms | 23,156 KiB |
| Raw source search | 0.297 ms | 0.554 ms | 0.297 ms | 23,404 KiB |
| Structured AAMS | 0.397 ms | 0.769 ms | 0.397 ms | 23,536 KiB |

These include a first request and exclude validation/scoring; they are tiny rule-agent measurements, not model inference, cold-start tails, sustained concurrency or production SLOs. No deployment gate or activation decision follows from them. Quality runs independently of cost.

## Negative cases to retain

- All three later **copied-report** design decisions proceed unsafely in both memory arms: repeated older positives fill the bounded selection and the later failure is absent from the agent context. The agent does not majority-vote copies, but it cannot reason from evidence it never sees. This is an evidence-selection/budget failure; do not patch the frozen agent or tune ranking against this pilot.
- Four missing-check design decisions in each memory arm abstain rather than assume an unreported condition. In two other missing-check decisions an independently blocked visible condition is sufficient to stop correctly. The task's true simulator outcome is separate from the available information.
- All six conflicting-source held-out decisions abstain; the simulator knows which action would be physically correct, but the agent cannot adjudicate two opposing reports. Honest uncertainty is not scored as task completion.
- Raw search additionally abstains in two interrupted-constraint decisions; structured AAMS happens to keep the missing prerequisite report. This one-family difference cannot support a transfer claim.

## Preregistration and validation amendment

The initial source/recipe/case protocol was committed and posted to #117 **before aggregate execution**, at `e093c283398107dd8cb04f25aa2c0c9a2c75a53b`. Review then added explicit producer/status validation, tampering regressions and an unsafe-proceed counter, refrozen before rerun at **`5176214976318bf40006461b1ece8c39b7e829cc`**. The agent, instruction, generator, cases and oracle did not change; every one of the 144 arm/task decisions matched the initial execution. Both source-hash sets are recorded in the aggregate report. Generated case SHA-256: `4661ada750b0b9d1c2af3bf40cd58c55684a51e7b6a4cf5bfabce5de70770e2c`.

The rerun passed all **175 repository tests**, 8 targeted tests, formatting, lint, compilation and the MCP demo. Current PR-head CI/run links and any integration limitations are recorded on the PR and #117/#105, rather than treating earlier main CI as current-head proof. The committed JSON identifies the actual locally executed source SHA; documentation/results commits do not change executable bytes.

```sh
python -m pip install -e '.[mcp]' ruff==0.14.6
python scripts/evaluate_cognitive_tasks.py > pilot.json
python -m unittest discover -s tests -p test_cognitive_tasks.py -v
ruff format --check src tests scripts
ruff check src tests scripts
python -m compileall -q src tests scripts
python -m unittest discover -s tests -v
python -m aams.demo
```

The runner rejects modified preregistered recipe/source/case hashes and invalid citations, and exits 3 on an invalid/failed run. No model, optional runtime or network downloads are needed. Random revision IDs, PIDs and timings may differ across reruns; decisions, contexts and quality counts are the reproducibility targets, not identical wall-clock artifacts.

## What remains unmeasured

No LLM/model agent, probabilistic calibration, new independent real-world episodes, unseen grammar, learned adaptation, governed consolidation transfer, authorized sharing, task-checkpoint recovery or model replacement was evaluated. Four author-visible held-out mechanisms do not fulfill the broader plan's twelve distinct confirmation families. The fresh worker reopens a store seeded with prior events; it does not implement a resumable agent task checkpoint or replay an agent's self-maintained internal state.

Next: independently freeze a richer decision corpus and pinned model/host interface, use matched current information/context budgets with a nontrivial no-memory control, and test actual task-state resumption only after its explicit implementation. Review the copied-evidence counterexamples before proposing a separate ranking or selection change. Keep the product's native/MCP BM25/guarded default and authority unchanged.
