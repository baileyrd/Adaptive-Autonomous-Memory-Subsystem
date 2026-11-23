# v0.8 retrieval root-cause investigation

Tracking: goal #79, issue #80. This document explains why the v0.6/v0.7 staged policy could not beat guarded retrieval. Each item is marked as either **measured** or **hypothesis**.

## Reproduced v0.7 baseline

On main `2d4e867`, `scripts/evaluate_shadow.py` reproduces the published numbers exactly. Synthetic: guarded and staged 7/8, nDCG 0.8914 for both. Public 24-task SQuAD: both 24/24, nDCG 0.9692 guarded and 0.9539 staged.

## Benchmark with headroom

`scripts/evaluate_retrieval.py` turns every SQuAD v1.1 development article into one scope. All of the article's paragraphs compete, so the scopes hold 21–98 records instead of 3. The question's own paragraph is the only relevant and required record. Each scope also gets a private-scope twin and a later-dated decoy, both of which repeat the article's first question verbatim. The SHA-256 of the article title assigns 30 articles to `design` and 18 to `heldout`, so no article informs both partitions. Up to five questions per paragraph give 5,782 design and 3,646 held-out tasks. The staged arm is the unchanged v0.6 artifact (`sha256:9c7a7099…0a10`). Quality is deterministic. Latency is one warmup plus one timed call per task and strategy.

```sh
curl -fL https://raw.githubusercontent.com/rajpurkar/SQuAD-explorer/eee5fdbf62f8613a7812b03419e6b29617b74fd1/dataset/dev-v1.1.json -o squad-dev-v1.1.json
PYTHONPATH=src python scripts/evaluate_retrieval.py --squad squad-dev-v1.1.json
```

Observed on Linux x86-64, Python 3.13.18, 4 vCPU, byte-bucket fixture provider. The run took 7 min 05 s with peak RSS 80,700 KiB.

| Held-out (18 articles, 3,646 tasks) | Satisfied | Recall@3 | nDCG@3 | Median / p95 ms | Δ tasks vs guarded [95% CI] |
| --- | ---: | ---: | ---: | ---: | ---: |
| lexical | 2,716 | 0.7449 | 0.6888 | 3.99 / 7.99 | −2.11 pp [−2.95, −1.29] |
| hybrid | 2,793 | 0.7660 | 0.7085 | 6.57 / 13.30 | 0 |
| guarded | 2,793 | 0.7660 | 0.7085 | 6.56 / 13.57 | — |
| staged v0.6 | 2,718 | 0.7455 | 0.6898 | 4.01 / 8.75 | −2.06 pp [−2.86, −1.23] |
| oracle lexical/hybrid router | 2,871 | — | 0.7357 | — | +2.14 pp |

The design partition (30 articles, 5,782 tasks) shows the same ordering. Guarded is at 4,319, staged at −2.18 pp [−2.82, −1.51], and the oracle at +2.37 pp. Intervals come from 2,000 article-grouped bootstrap resamples (seed 202607). All strategies had zero scope and zero time disclosures.

## Root causes

1. **Routing has a ceiling below the gate (measured).** A perfect per-task choice between lexical and hybrid improves on guarded by only 2.14 pp of held-out tasks, and 2.37 pp on design. The registered useful-gain threshold is 5 pp. So no router over the existing two arms, learned or not, can qualify. Learning to route was not the binding constraint.
2. **The lexical ranker is weak (measured in #81).** Its score is the count of distinct matched query terms, with no term weighting, no length normalization and ties broken by ID. Hybrid beat lexical on 364 held-out tasks by nDCG and lost on 230. Part of the "semantic" benefit is a byte-histogram tie-breaker among records with equal overlap counts.
3. **Lexical matching sees only the 512-byte preview (measured).** 86.1% of records are longer than the preview. Lexical recall finds the paragraph for 82.9% of held-out questions whose answer starts inside the preview, but only 43.4% when it starts beyond it. The representation index encodes the full payload, so hybrid partly compensates for a truncation artifact rather than adding semantic association.
4. **The staged features can't express the decision (measured).** `opt_in` is exactly the guarded decision, so the staged rule can only pick a subset of guarded's hybrid routes. It can never beat guarded unless hybrid hurts on opted-in tasks. Its only other feature, `short_query`, is true for 2.9% of held-out queries. On this workload the artifact abstains to lexical and is significantly *worse* than guarded. In the v0.6 fixture, opt-in and query wording are confounded by construction, with one opted-in short query per group.
5. **The v0.7 public evaluation was saturated (measured).** Each scope had three visible paragraphs at a top-three budget, so recall@3 was 1.0 by construction. 24 tasks in 4 groups produced a degenerate [0, 0] interval. Taking the first questions of each paragraph also favors answers near the passage opening: for first questions alone, preview truncation barely mattered, but with five questions per paragraph it dominates.
6. **The semantic arm isn't semantic (measured in v0.4, hypothesis here).** The CI provider is a byte histogram. The only real encoder tested, spaCy tok2vec, isn't a sentence embedder and lowered quality in v0.4. Whether a dedicated local sentence embedder helps is untested (#84).

## Implications

Optimize what is retrieved before optimizing when to use semantic association. The next slice (#81) tests scoped BM25 over full payloads against all of these baselines. Confidence-based routing (#82) only makes sense if a stronger pair of arms raises the oracle ceiling above the gate. Report that ceiling before building a router.

## Limitations

SQuAD questions were written while reading the passage, so they overlap lexically with their passages more than natural queries would. This favors lexical methods. It is one domain (Wikipedia) in English. Scope and time coordinates are artificial. Answer position is a proxy for where matching terms appear. Latency comes from a shared 4-vCPU container with one timed call per task. No production traffic was used.
