# Offline retrieval experiment protocol

The checked-in v0.6 fixture has six independent domains. Training and two held-out partitions each contain two domains and four measured tasks. The loader rejects shared domains, observation days, recorded origins, evidence identities or normalized payload copies across groups. Copies within a group stay together. Each group includes private decoys, a later observation, and a task with an explicit opt-in. Two groups contain a labeled counterexample. The data is synthetic and intentionally small.

Run a controlled replay using `PYTHONPATH=src python scripts/offline_experiment.py --split test_a --repetitions 20`. Repeat on `test_b` after fixing the candidate and the thresholds. Each invocation creates a temporary SQLite database and has no production database option.

## Pre-registered measures

Use a top-three result limit, one warmup and 20 timed repetitions on the same fixture for lexical, explicit hybrid and guarded policies. Count tasks satisfied only when all required evidence IDs are returned. Report recall@3, nDCG@3, median and p95 wall latency, and peak RSS of the complete replay process. The provider is deterministic byte buckets and has no neural interpretation.

For a candidate to clear the research gate, require strictly more satisfied tasks than lexical on both held-out partitions and no fewer than guarded, no nDCG loss versus lexical, zero scope and historical disclosures, and preservation of required contradiction evidence where lexical retained it. The registered risk budget for each partition is at most 15 ms mean per-task median and at most 50% unsatisfied tasks. Satisfying this small fixture would justify further offline study only.

Both modes are actually executed. Pairing through the controlled-outcome contract excludes tasks that took the same actual mode. The all-task report retains those cases. Outcome observations from production telemetry cannot establish the unobserved alternative outcome.
