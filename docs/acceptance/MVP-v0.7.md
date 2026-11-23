# AAMS v0.7 shadow-mode acceptance

The [v0.7 goal](https://github.com/baileyrd/Adaptive-Autonomous-Memory-Subsystem/issues/67) adds optional native, read-only observation of a staged routing suggestion, a scoped pairing ledger, and a controlled replay. Serving decisions, evidence, and memory authority remain independent of observation and analysis.

| Requirement | Observed status |
| --- | --- |
| Default-off and scoped feature gates | **PASS.** Observation requires explicit host configuration, a scoped principal grant and a visible canonical result. Only two Boolean features and opaque tokens are passed to the fixed evaluator. |
| Failure, deadline and rollback | **PASS.** Tests cover busy workers, exceptions, late successful suggestions, revoked grants and observer removal. Serving packets stay equal and observed work adds no database writes. The deadline discards a late result and does not preempt the thread. |
| Immutable matched observations | **PASS.** Per-scope and per-principal bounds, deduplication, explicit missing labels, half-open time windows and rejection of conflicting replays. Observational or same-mode pairs cannot support alternate-mode inference. |
| Serving invariance and privacy on replay | **PASS.** Guarded serving packet digests matched with and without observation across 32 tasks. Zero private or post-cutoff disclosures and no required contradiction regressions were observed. The measured runs met the local overhead and failure budgets. |
| Staged utility gain over guarded | **FAIL on both measured workloads.** The candidate tied guarded at 7/8 synthetic tasks and 24/24 public tasks. Public nDCG fell from 0.9692 to 0.9539. The staged policy stays offline. |
| Drift, calibration and uncertainty | **MEASURED.** The opted-in short-query fraction moved from 100% on synthetic to 0% on public SQuAD. Brier was 0.1875 and 0.25 respectively, with one populated bin per workload. The degenerate bootstrap intervals reflect all observed binary ties; they do not establish equivalence. |
| Production traffic and service-level guarantees | **NOT TESTED.** Public SQuAD uses human-authored questions and a temporary scoped replay. Live workload utility, sustained concurrency, and privacy or performance on arbitrary inputs remain unverified. |

## Reproduce and operate

```sh
python -m pip install '.[mcp]' ruff==0.14.6
ruff format --check src tests scripts
ruff check src tests scripts
python -m compileall -q src tests scripts
PYTHONPATH=src python -m unittest discover -s tests -v
python -m aams.demo
PYTHONPATH=src python scripts/evaluate_shadow.py --repetitions 20
```

The [shadow evaluation](../audit/shadow-evaluation.md) gives public data attribution, exact download checksum, thresholds, commands and timing. It used Linux x86-64 and Python 3.12.14. The regular CI matrix uses Python 3.11 and 3.12 and the pinned MCP SDK 2.3.0. Offline replay uses the byte-bucket fixture provider. No neural runtime or external download is needed in CI. The [operator notes](../shadow.md) describe disable, scope, isolation, storage lifetime and recovery.

| Slice | Exact tested head | CI |
| --- | --- | --- |
| Shadow contracts | `744c99ff2864d3147b759c1a688a3aef05f5ab6f` | [Python 3.11 and 3.12](https://github.com/baileyrd/Adaptive-Autonomous-Memory-Subsystem/actions/runs/45183139913) |
| Read-only observer | `24b37db8edc8444a1ef63eea5231b23290735fa5` | [Python 3.11 and 3.12](https://github.com/baileyrd/Adaptive-Autonomous-Memory-Subsystem/actions/runs/45193816589) |
| Paired measurements | `84aee3f0c951215e5eb048ff98d027455b468046` | [Python 3.11 and 3.12](https://github.com/baileyrd/Adaptive-Autonomous-Memory-Subsystem/actions/runs/45194253319) |
| Shadow evaluation | `091c21dc9336e175d30ff50d607ab2b64558acf3` | [Python 3.11 and 3.12](https://github.com/baileyrd/Adaptive-Autonomous-Memory-Subsystem/actions/runs/45194848167) |

The coordination issue records the integrated commit and CI. A future canary requires its own design and explicit authorization, independently measured gain over guarded, scope and latency budgets, bounded exposure and a tested kill switch. v0.7 supplies no canary or staged policy activation path. Memory authority continues to require its own existing policy.
