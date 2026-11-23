# AAMS v0.8 retrieval optimization acceptance

The [v0.8 goal](https://github.com/baileyrd/Adaptive-Autonomous-Memory-Subsystem/issues/79) set out to find why the offline-trained routing policy never beat guarded retrieval, and to improve on the strongest baseline using evidence. No learned policy, default change, live activation or autonomous adaptation is part of this milestone.

## Outcome

| Status level | Result |
| --- | --- |
| Engineering complete | **Yes.** The benchmark (#80) and the scoped BM25 ranker (#81) are merged with unit, security and benchmark tests. |
| Experiment complete | **Yes.** Lexical, hybrid, guarded, staged, the oracle router and BM25 arms were measured on identical inputs over two independent public workloads and the existing synthetic fixtures. The ONNX embedder (#84) and fusion (#83) arms stopped at the cost gates, before a quality run. |
| Performance improvement validated | **Yes, offline, for BM25 ranking under guarded routing**, within the measured scope. It passed every pre-registered #79 criterion on held-out development articles and on separate SQuAD training articles. No learned routing policy qualified. |
| Deployment ready | **Partially.** With owner approval, BM25 is now the default lexical ranker, with a migration note and overlap rollback. Production traffic, sustained concurrency and very large scopes remain untested, and no learned or neural policy is active. |

## Root causes (measured, [audit](../audit/retrieval-root-cause.md))

1. A perfect lexical/hybrid router would add only 2.14 pp over guarded on held-out articles, below the 5 pp gate. Routing was never the binding constraint.
2. The overlap ranker counts distinct matched terms with no weighting or length normalization.
3. Lexical matching sees only the 512-byte preview, which truncates 86% of the records. Lexical success falls from 82.9% to 43.4% when the answer lies beyond the preview.
4. Staged features are a subset of guarded's decision. On public data the staged rule was significantly *worse* than guarded (−2.06 pp [−2.86, −1.23]).
5. The v0.7 public replay was saturated: recall@3 was 1.0 by construction, and its bootstrap was degenerate.
6. The CI semantic provider is a byte histogram, not a semantic model.

## Side-by-side (held-out SQuAD dev articles, 3,646 tasks, [details](../audit/retrieval-optimization.md))

| Arm | Satisfied | nDCG@3 | Δ vs guarded [95% CI] | p95 ms |
| --- | ---: | ---: | ---: | ---: |
| lexical | 2,716 | 0.6888 | −2.11 pp [−2.95, −1.29] | 7.91 |
| guarded (= hybrid here) | 2,793 | 0.7085 | — | 12.59 |
| staged v0.6 | 2,718 | 0.6898 | −2.06 pp [−2.86, −1.23] | 8.55 |
| oracle lexical/hybrid router | 2,871 | 0.7357 | +2.14 pp | — |
| BM25 + guarded routing | **3,354** | **0.8726** | **+15.39 pp [12.77, 17.75]** | 14.51 |

On independent SQuAD training articles (hash-held-out half, 4,712 tasks), BM25 with guarded routing gained +13.99 pp [12.24, 15.64], and nDCG rose from 0.6642 to 0.8112. On the low-overlap, cross-domain **SciFact** check (647 expert-written biomedical claims, 16 scopes of about 324 abstracts), it gained **+20.09 pp [16.22, 23.95]**, with nDCG rising from 0.7062 to 0.9378 and 5 losses against 135 wins. There were zero scope or time disclosures across all 20,129 SQuAD and SciFact tasks. On the v0.4 and v0.6 synthetic fixtures (paraphrase, contradiction, history), the results matched the current default exactly. Before caching, SciFact's larger scopes broke the latency budget (+30.6 ms p95). A bounded LRU of evidence term counts, keyed by digest, brought the added p95 down to +1.0 ms on SciFact and −1.4 ms on SQuAD. Peak RSS was 1.59× overlap on SciFact, within the 2× budget.

## Rejected or deferred

- **Confidence router (#82): rejected.** The oracle over BM25 and BM25-hybrid adds only +0.05 pp, so no router was built.
- **Real sentence embedder (#84): not validated (cost); quality not measured.** An eval-only, sha256-pinned `BAAI/bge-small-en-v1.5` ONNX encoder (CLS pooling, onnxruntime + tokenizers, no torch) and its measurement arms are in `scripts/` (#91), with a manual Actions workflow, `embedder-eval.yml` (#92). On GitHub's `ubuntu-24.04` runner, encoding alone took 8.67 ms p95 per query (median 8.45, one thread), against a budget of 5 ms for *all* added latency. Process RSS after loading the model was about 283 MiB, against the 2× memory budget. A local probe also put the pure-Python 384-d scan at +13.2 ms p95. Both cost gates therefore fail whatever quality shows, so the owner stopped the multi-hour quality run. Vocabulary-mismatch queries, where BM25 does nothing (6/12 versus guarded's 11/12 on the paraphrase fixture), remain the open gap, which is why guarded routing is retained.
- **Rank fusion (#83): not validated (cost).** The eval-only k=60 RRF arm, built over recall's own time-visible citations, needs the same encoder on every query, so it inherits #84's cost failure. Following the plan's decision D7, a fusion scorer is only built together with an approved encoder promotion.

## Remaining limitations

SQuAD questions overlap lexically with their passages. SciFact supplies a second, lower-overlap domain, but all workloads are English, so multilingual generalization was not tested. Latency comes from a shared container with linear scans, and large stores and concurrency were not tested. No production traffic was used.

## Recommendation

Keep guarded routing. The owner kept BM25 opt-in until the low-overlap, cross-domain SciFact check passed, then approved it as the default on #79. It is now the default, with `LexicalRanking.OVERLAP` as rollback. A small local embedder, as measured, does not fit the latency or memory budget. Revisit #84 only with a materially cheaper path, such as a quantized or smaller encoder, cached query embeddings, or an ANN index instead of a linear scan. `embedder-eval.yml` with `stage=full` then gives the pre-registered quality answer without further code. Until then, routing headroom will not return, because the semantic arm is not actually semantic.

## Reproduce

```sh
python -m pip install '.[mcp]' ruff==0.14.6
PYTHONPATH=src python -m unittest discover -s tests -v
PYTHONPATH=src python scripts/evaluate_retrieval.py --squad squad-dev-v1.1.json --ranking bm25
```

See the audits for dataset URLs, checksums and the second-workload command.

| Slice | Exact tested head | CI |
| --- | --- | --- |
| Benchmark and root-cause audit (#80, PR #86) | `5a1d2151f5e3ce75de2aa4d5067fee3428388831` | [Python 3.11 and 3.12](https://github.com/baileyrd/Adaptive-Autonomous-Memory-Subsystem/actions/runs/45207898837) |
| Scoped BM25 ranking (#81, PR #87) | `79e6034862175290649f814fde5d24f123da0f88` | [Python 3.11 and 3.12](https://github.com/baileyrd/Adaptive-Autonomous-Memory-Subsystem/actions/runs/45212635824) |
