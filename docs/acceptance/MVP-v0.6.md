# AAMS v0.6 offline policy research acceptance

The [v0.6 goal](https://github.com/baileyrd/Adaptive-Autonomous-Memory-Subsystem/issues/56) delivers a reproducible offline workflow using controlled retrieval outcomes. The live v0.5 router and lexical default retain their semantics. This milestone adds no runtime activation, telemetry-to-evidence path, or canonical promotion.

| Requirement | Observed status |
| --- | --- |
| Matched outcomes and risk budgets | **PASS.** The contract rejects mismatched tasks, copied task IDs, and observational logs as counterfactual evidence. The comparison includes only actually executed distinct modes. |
| Independent grouped replay | **PASS.** Synthetic shipping and facilities train the artifact. Botany and weather form held-out A, with transport and archives in held-out B. The replay loader rejects overlapping domains, time windows, origins, IDs and normalized evidence copies across groups. |
| Bounded candidate and abstention | **PASS.** The staged artifact uses two Boolean features, at most one vote per independent group and a two-winning-group/no-loss gate. Copied groups, observational labels, stale policy versions and counterexamples are covered. No live consumer loads the artifact. |
| Quality and pre-registered limits | **PASS on the fixed fixture.** Candidate task coverage was 4/4 and 3/4 on A and B, respectively, versus 2/4 and 2/4 lexical. The fixed research budgets passed. |
| Incremental benefit over guarded | **FAIL to outperform on this fixture.** The staged candidate took the same route as guarded on all held-out tasks. Both achieved 7/8 across the partitions. The result supports existing guarded retrieval on this fixture and establishes no incremental learning benefit. |
| Scope, time, contradictions and outage | **PASS on the fixed fixture.** No scope or time disclosures, lexical task losses or required contradiction regressions were observed for the candidate. In the simulated outage all eight tasks matched lexical quality, with four explicit provider fallbacks. |
| Calibration | **MEASURED.** One bin had a predicted gain of 0.75 and observed gain of 3/4, with Brier score 0.1875. Larger calibration and distribution shift are **NOT TESTED**. |
| Runtime and cost | **MEASURED.** Candidate median/p95 were 0.796/1.198 ms on A and 0.812/1.164 ms on B. Linux x86-64 complete replay peak RSS was 16,384 KiB. Model, network and production-scale costs are **NOT TESTED**. |

## Reproduce

Use Python 3.11 or 3.12 and the repository source. Replay and training use the Python standard library and the byte-bucket fixture provider. No model is downloaded. The existing MCP smoke test uses the pinned SDK 2.3.0.

```sh
python -m pip install '.[mcp]' ruff==0.14.6
PYTHONPATH=src python scripts/offline_experiment.py --split test_a --repetitions 20
PYTHONPATH=src python scripts/train_offline_candidate.py --repetitions 20
PYTHONPATH=src python scripts/evaluate_offline_candidate.py --repetitions 20
PYTHONPATH=src python -m unittest discover -s tests -v
python -m aams.demo
```

The [synthetic corpus](../../tests/fixtures/offline_policy_v06.json) has SHA-256 `b993e9f2d98681a39d97cb1a8372ce85a7358ab956309bedbd921d06178973e9`. The ordered training manifest checksum is `sha256:9c7a7099afba6a6fba18da939eff90e3754f4fd66efc1add7286cb485fdc0a10` under model `group-votes-v1`, feature contract `short-query-and-opt-in-v1` and routing policy `1`. The [protocol and results](../audit/offline-experiments.md) document partition provenance, frozen thresholds, all comparators and calibration limits. The CLI uses temporary databases and never reads application telemetry.

| Slice | Exact tested head | CI |
| --- | --- | --- |
| Outcome contracts | `ca0b641215ce97687c4f22f2bab5dceb16974275` | [Python 3.11 and 3.12](https://github.com/baileyrd/Adaptive-Autonomous-Memory-Subsystem/actions/runs/45173805463) |
| Grouped replay | `a3c586ec9868e52cd8cf6130f412fe19c4db1e01` | [Python 3.11 and 3.12](https://github.com/baileyrd/Adaptive-Autonomous-Memory-Subsystem/actions/runs/45179006523) |
| Staged training | `fd2668116c2b4450942a9f48f0387cbdf93cc467` | [Python 3.11 and 3.12](https://github.com/baileyrd/Adaptive-Autonomous-Memory-Subsystem/actions/runs/45179337397) |
| Held-out comparison | `865449067a0b700c61640ebf00156c46267c7423` | [Python 3.11 and 3.12](https://github.com/baileyrd/Adaptive-Autonomous-Memory-Subsystem/actions/runs/45179720196) |

The coordination issue records exact integrated CI. The [v0.5 acceptance](MVP-v0.5.md) remains authoritative for live scope, telemetry, fallback and authority behavior.

## Conditions for a future shadow-mode study

A separate v0.7 study could compare shadow recommendations against guarded routing with opt-in workloads, independent outcome labels, an explicit budget and expiry, and a kill switch. The current tie provides no basis to enable a live policy. Require independently repeated gains over guarded at matched budgets and zero observed boundary violations before a human considers manual promotion of a routing policy. Routing promotion changes retrieval configuration only. Candidate evidence and belief authority remain governed by their own contracts. Keep background learning and automatic activation disabled.
