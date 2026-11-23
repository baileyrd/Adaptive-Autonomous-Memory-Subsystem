# Offline retrieval experiment protocol

The checked-in v0.6 fixture has six independent domains. Training and two held-out partitions each contain two domains and four measured tasks. The loader rejects shared domains, observation days, recorded origins, evidence identities or normalized payload copies across groups. Copies within a group stay together. Each group includes private decoys, a later observation, and a task with an explicit opt-in. Two groups contain a labeled counterexample. The data is synthetic and intentionally small.

Run a controlled replay using `PYTHONPATH=src python scripts/offline_experiment.py --split test_a --repetitions 20`. Repeat on `test_b` after fixing the candidate and the thresholds. Each invocation creates a temporary SQLite database and has no production database option.

## Pre-registered measures

Use a top-three result limit, one warmup and 20 timed repetitions on the same fixture for lexical, explicit hybrid and guarded policies. Count tasks satisfied only when all required evidence IDs are returned. Report recall@3, nDCG@3, median and p95 wall latency, and peak RSS of the complete replay process. The provider is deterministic byte buckets and has no neural interpretation.

For a candidate to clear the research gate, require strictly more satisfied tasks than lexical on both held-out partitions and no fewer than guarded, no nDCG loss versus lexical, zero scope and historical disclosures, and preservation of required contradiction evidence where lexical retained it. The registered risk budget for each partition is at most 15 ms mean per-task median and at most 50% unsatisfied tasks. Satisfying this small fixture would justify further offline study only.

Both modes are actually executed. Pairing through the controlled-outcome contract excludes tasks that took the same actual mode. The all-task report retains those cases. Outcome observations from production telemetry cannot establish the unobserved alternative outcome.

## Staged candidate

Run `PYTHONPATH=src python scripts/train_offline_candidate.py --repetitions 20` to export the staged JSON to stdout. Training uses only matched controlled outcomes from the fixed training partition. The versioned feature contract uses a short-query flag and explicit opt-in. There are two bins and at most one conservative vote per independent group. A bin needs at least two winning groups and no losses. Unknown or weak bins abstain to lexical, as does a request without opt-in. The manifest checksum covers ordered task/group identities, permitted features and measured labels. Timing is excluded from training and the checksum. No randomness or seed selection is involved.

The artifact contains no source text, authority decision or live activation path. The displayed gain probability is a Laplace-smoothed group win rate. It is a small-sample estimate for calibration, not a guarantee or a runtime gate.

## Held-out results

Run `PYTHONPATH=src python scripts/evaluate_offline_candidate.py --repetitions 20`. The evaluator trains once using the registered training partition, replays four strategies per held-out partition and repeats a simulated provider outage. No threshold changed after measurement.

| Partition / strategy | Satisfied | Recall@3 | nDCG@3 | Median / p95 ms |
| --- | ---: | ---: | ---: | ---: |
| A / lexical | 2/4 | 0.5000 | 0.4599 | 0.444 / 0.801 |
| A / hybrid | 4/4 | 1.0000 | 0.9197 | 1.032 / 1.338 |
| A / guarded | 4/4 | 1.0000 | 0.9197 | 0.790 / 1.289 |
| A / staged | 4/4 | 1.0000 | 0.9197 | 0.796 / 1.198 |
| B / lexical | 2/4 | 0.5000 | 0.5365 | 0.455 / 0.692 |
| B / hybrid | 4/4 | 1.0000 | 0.9398 | 0.968 / 1.213 |
| B / guarded | 3/4 | 0.8750 | 0.8631 | 0.798 / 1.255 |
| B / staged | 3/4 | 0.8750 | 0.8631 | 0.812 / 1.164 |

Linux x86-64, Python 3.12.14. Peak RSS for the complete evaluator was 16,384 KiB. Each strategy was repeated 20 times on every task. The staged policy met the fixture research gate in both partitions and tied guarded on every task. The held-out observations give no evidence that learning improved over guarded routing. Neither partition showed a lexical task loss, lost required contradiction, or scope/time disclosure under the staged policy. Provider unavailability returned lexical quality for all eight tasks, with four explicit provider fallbacks.

The single populated calibration bin predicted 0.75 gain. Three of four actually paired opt-in tasks improved over lexical, giving a Brier score of 0.1875. One bin and four observations are insufficient to establish reliable probabilities under distribution shift. The two held-out partitions are independently grouped within one synthetic fixture. No real-world or neural benchmark was run for this offline learner.
