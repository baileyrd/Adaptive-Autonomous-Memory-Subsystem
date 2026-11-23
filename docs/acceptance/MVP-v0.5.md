# AAMS v0.5 retrieval routing acceptance

The [v0.5 engineering goal](https://github.com/baileyrd/Adaptive-Autonomous-Memory-Subsystem/issues/45) introduces deterministic guarded mode selection, explicit outcome telemetry, and a held-out comparison. Lexical stays the default and exact lookup remains canonical. Hybrid recall is native, local and opt-in.

| Requirement | Verified result |
| --- | --- |
| Lexical default and transparent routing | **PASS.** Explicit lexical and exact reads skip the provider. The versioned decision is based on caller opt-in and the scoped index/provider state. An explicit request reports the actual selected mode and fallback status. |
| Scope, time and contradiction | **PASS.** The held-out workload exposed zero private or post-cutoff evidence and retained both labeled sides of the contradiction in all five profiles. Existing tests also verify kind and exact lookup rules. |
| Provider/index failure and rollback | **PASS.** Tests cover missing, incompatible, stale and corrupted index entries, provider failure and interrupted replacement. Invalidate a derived batch or omit the provider to roll back to lexical; no canonical migration rollback is needed to change retrieval mode. |
| Bounded, privacy-safe feedback | **PASS.** Explicit native host grant, replay conflict, fixed labels, policy version, 30-day window, per-principal bounded rows and live deletion. The schema stores no free-form query, evidence or model feedback. |
| Evidence and approval boundaries | **PASS.** The integrated test confirms that hybrid retrieval, favorable telemetry and rollback preserve actual evidence, belief revisions and candidate history. |
| Hosted or production-scale performance and feedback-driven rankings | **NOT TESTED.** The test corpus is small and synthetic. Telemetry has no training or online policy update path. |
| General neural benefit | **NOT ESTABLISHED.** The real encoder improved nDCG on this workload, matched lexical recall and tasks, and regressed on the v0.4 corpus. It still uses more time and memory than lexical. |

## Reproduce and operate

```sh
python -m pip install '.[mcp]' ruff==0.14.6
ruff format --check src tests scripts
ruff check src tests scripts
python -m compileall -q src tests scripts
PYTHONPATH=src python -m unittest discover -s tests -v
python -m aams.demo
PYTHONPATH=src python scripts/evaluate_routing.py routed --encoder fixture
```

Use the [held-out evaluation](../audit/retrieval-routing-evaluation.md) for all five run commands and measured recall, nDCG, safety, p95 latency and RSS. The optional real CPU encoder was spaCy 3.8.11 with en_core_web_sm 3.8.0; v0.4 commands and wheel checksum are preserved in the [earlier comparison](../audit/semantic-evaluation.md). CI runs offline comparators without neural dependencies. Use the [index recovery instructions](../vector-index.md) for outages and corrupt batches and the [telemetry instructions](../retrieval-telemetry.md) for grants, retention, opaque IDs and backup limitations.

| Slice | Tested head | CI |
| --- | --- | --- |
| Routing contracts | `b19224e4849298da9a50ed03d3991c3a9fde3a77` | [Python 3.11 and 3.12](https://github.com/baileyrd/Adaptive-Autonomous-Memory-Subsystem/actions/runs/45170038683) |
| Guarded recall integration | `128e69b76c0dfdedaf30430e8351a82b69d0e30a` | [Python 3.11 and 3.12](https://github.com/baileyrd/Adaptive-Autonomous-Memory-Subsystem/actions/runs/45170747561) |
| Outcome telemetry | `29e9e38bb535a9193682d8fa270c9443bf29dd49` | [Python 3.11 and 3.12](https://github.com/baileyrd/Adaptive-Autonomous-Memory-Subsystem/actions/runs/45171090944) |
| Held-out evaluation | `7267eaecc7766b1cc78e694582240b24406713e4` | [Python 3.11 and 3.12](https://github.com/baileyrd/Adaptive-Autonomous-Memory-Subsystem/actions/runs/45171513410) |

The coordination issue records the integrated acceptance head and main CI. The held-out results support explicit opt-in gating and further offline comparisons. They do not justify autonomous weight updates. Require a larger independent corpus, improved task coverage at matched budgets, retained contradiction evidence and zero observed scope violations before changing default policy.
