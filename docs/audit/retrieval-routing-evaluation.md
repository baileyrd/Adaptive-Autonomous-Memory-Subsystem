# v0.5 held-out retrieval routing

The fixed fixture has 26 synthetic records across four scopes and ten queries, distinct from the v0.4 corpus. Relevance labels cover paraphrases, a misleading shared term, an explicit counterexample, a copied origin, Spanish, a historical cutoff and private decoys. Eight queries use the live scope, one uses a stale archive and one simulates encoder unavailability. Workload opt-in is explicit and fixed in the fixture. It is independent of per-query outcomes.

## Reproduce

Run from the repository root using Python with the source on its import path. For the real local CPU encoder, install spaCy 3.8.11 and the checksum-verified en_core_web_sm 3.8.0 wheel using the [v0.4 instructions](semantic-evaluation.md). Regular CI runs the offline comparator only.

```sh
PYTHONPATH=src python scripts/evaluate_routing.py lexical
PYTHONPATH=src python scripts/evaluate_routing.py hybrid --encoder fixture
PYTHONPATH=src python scripts/evaluate_routing.py routed --encoder fixture
PYTHONPATH=src python scripts/evaluate_routing.py hybrid --encoder neural
PYTHONPATH=src python scripts/evaluate_routing.py routed --encoder neural
```

Each process uses the same top-three result budget and ten-query workload, one warmup and 20 timed repetitions. The always-opted-in hybrid comparator requests semantic ranking on each query and still uses existing safety fallback. The routed profile adds the workload's explicit opt-in and derives scoped compatibility/freshness from the native service. Recall@3 and nDCG@3 macro-average the nine positively labeled queries. A task is covered when all its required IDs appear.

A false route is actual hybrid use on a query whose host policy requires lexical or whose scoped provider/index is unusable. The rate uses all ten queries as denominator. Separately, the script counts hybrid queries whose nDCG was lower than lexical on the same query. Quality regression measures a different outcome from policy violation.

## Observed on Linux x86-64, Python 3.12.14

| Mode | Recall@3 | nDCG@3 | Tasks | False routes | Hybrid quality regressions | Median / p95 ms | Peak RSS KiB |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Lexical | 0.7778 | 0.7887 | 7/9 | 0/10 | 0 | 0.886 / 1.336 | 15,744 |
| Hybrid byte buckets fixture | 0.7778 | 0.7614 | 6/9 | 3/10 | 1 | 1.885 / 2.511 | 16,128 |
| Routed byte buckets fixture | 0.7778 | 0.7614 | 6/9 | 0/10 | 1 | 1.543 / 2.387 | 16,128 |
| Hybrid pretrained spaCy | 0.7778 | 0.8226 | 7/9 | 3/10 | 0 | 3.672 / 5.729 | 119,248 |
| Routed pretrained spaCy | 0.7778 | 0.8226 | 7/9 | 0/10 | 0 | 2.599 / 4.483 | 119,612 |

All five profiles retrieved both sides of the labeled contradiction and exposed zero private or post-cutoff evidence. The four encoder profiles fell back for stale and unavailable inputs. Routed use removed three unrequested hybrid routes and lowered median latency against always-opted-in hybrid. The real encoder increased nDCG on this fixture, with unchanged recall/task coverage, higher latency and higher process memory than lexical. The earlier corpus found a quality regression. The fixture encoder is not neural evidence. Keep lexical as default and require larger independent evaluation before interpreting these results as general benefit.
