# E1: Laya as an offline relevance judge (pre-run ceiling)

**Hypothesis (tagged, research only):** a local decision model judging query–passage relevance can rerank `bm25_guarded`'s candidates enough to matter. Laya, Unsloth's decision model, is far outside the serving budgets (sub-second CPU requests, 4–5 GB RAM against ≤5 ms added p95 and ≤2× RSS). So it was scoped only as an offline judge measuring reranking headroom for [#105](https://github.com/baileyrd/Adaptive-Autonomous-Memory-Subsystem/issues/105). No serving, write-path or default change is involved.

## Pre-registered gates

The arm reorders the top 10 of `bm25_guarded` by Laya's yes probability and keeps the top 3. All of these were required:

- satisfied@3 rises by ≥ +5 pp with a 95% grouped-bootstrap lower bound above 0, separately on 300 seeded held-out SQuAD dev tasks and on all 647 SciFact claims
- pooled public AUC ≥ 0.85 and ECE ≤ 0.05
- no regression and zero contradiction regressions on the v0.6 fixture
- zero scope or time disclosures

## Result: the gates are unreachable, so Laya was not run

Before any model call, `ceiling` scored a perfect judge, which puts every gold passage first within the same candidate lists. The baselines reproduce v0.8 (SciFact nDCG@3 0.9378; SQuAD sample 0.8717).

| Workload | Tasks | `bm25_guarded` satisfied | Perfect judge | Δ [95% CI] |
| --- | ---: | ---: | ---: | ---: |
| SQuAD held-out sample | 300 | 276 | 292 | +5.33 pp [1.91, 9.09] |
| SciFact | 647 | 620 | 635 | +2.32 pp [1.32, 3.28] |
| v0.6 fixture | 12 | 11 | 11 | 0 |

A depth of 20 or 50 instead of 10 gives the same SQuAD ceiling and 638 on SciFact (+2.78 pp). BM25 returns only records that share a term with the query, about 12 per SQuAD task. The remaining failures are candidate-generation misses, which no reranker can recover. As with the v0.8 router oracle (+2.14 pp), the headroom is in candidate generation, not ordering. A judge over whole scopes would need about 324 calls per SciFact query, which is far too costly on CPU.

**Decision input:** neural reranking of BM25 candidates is not worth pursuing under the current gates. Any further neural work for #105 must widen candidate generation, such as a dense or expansion stage, before ordering can matter.

## Reproduce

Datasets are verified against the pinned SQuAD and SciFact hashes in `evaluate_retrieval.py` and `evaluate_scifact.py`.

```sh
PYTHONPATH=src:scripts python scripts/evaluate_laya_rerank.py prepare \
  --squad dev-v1.1.json --scifact data.tar.gz --out e1
PYTHONPATH=src:scripts python scripts/evaluate_laya_rerank.py ceiling e1/tasks.json
```

To measure Laya itself, copy `e1/pairs.jsonl`, which holds no gold labels, to a machine running the Unsloth Decision API. Run `python laya_judge.py pairs.jsonl judgments.jsonl` there; it needs only the standard library, resumes when interrupted, and reads an optional `LAYA_API_KEY`. Then run `score e1/tasks.json judgments.jsonl`. Laya's licence terms are unpublished, and the owner approved evaluation use only. Record the Unsloth and llama.cpp versions with any run.
