# v0.8 retrieval optimization experiments

Tracking: goal #79. This document covers the experiments that followed the [root-cause audit](retrieval-root-cause.md). Each experiment records its hypothesis, the comparison against every baseline on identical inputs, and the decision taken.

## E1: Scoped BM25 over full payloads (#81)

**Hypothesis.** Most of the gap comes from ranking, not routing. Keep guarded routing unchanged and swap only the lexical ranker for scoped BM25 over the full payload ([ADR-0009](../adr/0009-scoped-lexical-ranking.md)). This should beat guarded by at least 5 pp of tasks on held-out articles, with a positive lower bound on the interval, no nDCG loss, no disclosures, no contradiction regressions, and within the latency and memory budgets. The gate was registered in #79 before any measurement at five questions per paragraph. An exploratory one-question-per-paragraph run had shown +5.8 pp before registration.

**Arms.** `bm25` is BM25 used lexically. `bm25_hybrid` always asks for hybrid. `bm25_guarded` keeps guarded's routing rule (hybrid only with opt-in) and is the candidate. The other arms are unchanged.

```sh
PYTHONPATH=src python scripts/evaluate_retrieval.py --squad squad-dev-v1.1.json --ranking bm25
curl -fL https://raw.githubusercontent.com/rajpurkar/SQuAD-explorer/eee5fdbf62f8613a7812b03419e6b29617b74fd1/dataset/train-v1.1.json -o squad-train-v1.1.json
PYTHONPATH=src python scripts/evaluate_retrieval.py --squad squad-train-v1.1.json \
  --expected-sha256 3527663986b8295af4f7fcdff1ba1ff3f72d07d61a20f487cb238a6ef92fd955 \
  --max-articles 48 --ranking bm25
for mode in lexical fixture; do for r in overlap bm25; do
  PYTHONPATH=src python scripts/evaluate_semantic.py $mode --ranking $r; done; done
```

The second workload is the first 48 articles of the SQuAD v1.1 *training* set. None of them share a title with the development set, and none were looked at during design. Environment: Linux x86-64, Python 3.13.18, 4 vCPU, byte-bucket fixture provider. Both SQuAD runs ran at the same time in one container. Latency is one timed call per task and arm after a warmup.

### Primary: development held-out articles (18 articles, 3,646 tasks)

| Arm | Satisfied | Recall@3 | nDCG@3 | Median / p95 ms | Δ tasks vs guarded [95% CI] | Wins / losses |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| lexical | 2,716 | 0.7449 | 0.6888 | 4.39 / 7.91 | −2.11 pp [−2.95, −1.29] | 78 / 155 |
| hybrid | 2,793 | 0.7660 | 0.7085 | 6.94 / 12.48 | 0 | — |
| guarded | 2,793 | 0.7660 | 0.7085 | 6.94 / 12.59 | — | — |
| staged v0.6 | 2,718 | 0.7455 | 0.6898 | 4.40 / 8.55 | −2.06 pp [−2.86, −1.23] | 72 / 147 |
| bm25 | 3,345 | 0.9174 | 0.8704 | 5.41 / 10.28 | +15.14 pp [12.54, 17.48] | 621 / 69 |
| **bm25_guarded** | **3,354** | **0.9199** | **0.8726** | 7.96 / 14.51 | **+15.39 pp [12.77, 17.75]** | 622 / 61 |

The design partition (30 articles, 5,782 tasks) gave +15.03 pp [13.25, 16.68], with nDCG rising from 0.6880 to 0.8471.

### Generalization: SQuAD training articles (48 articles, 10,054 tasks)

| Partition | Guarded satisfied / nDCG | bm25_guarded satisfied / nDCG | Δ tasks [95% CI] | Added p95 |
| --- | ---: | ---: | ---: | ---: |
| hash-heldout (22 articles, 4,712 tasks) | 3,405 / 0.6642 | 4,064 / 0.8112 | +13.99 pp [12.24, 15.64] | +2.19 ms |
| hash-design (26 articles, 5,342 tasks) | 3,743 / 0.6336 | 4,608 / 0.7995 | +16.19 pp [13.91, 18.39] | +2.18 ms |

### Correctness, security and cost

- **Disclosures.** Every arm had zero scope and zero time disclosures across 19,482 tasks, each with private and future decoys. A unit test shows that BM25 packets are byte-identical whether or not same-vocabulary private or future records exist. Scores therefore cannot act as an existence oracle.
- **Contradictions and paraphrases.** On the v0.4 semantic fixture, BM25 gave the same results as overlap in both lexical and byte-bucket hybrid modes: 5/8 and 6/8 tasks, with the contradiction retained 1/1 and zero disclosures. On the v0.6 controlled fixture, BM25 also matched overlap per split. Its guarded arm equals guarded, with 11/12 tasks and the contradiction tasks preserved. **BM25 does not fix vocabulary mismatch.** On the paraphrase fixture, lexical BM25 alone solves 6/12 tasks while guarded solves 11/12. So the candidate keeps guarded routing rather than replacing it.
- **Regressions.** bm25_guarded lost 61 held-out tasks that guarded satisfied (1.7%), against 622 gains. The losses are left in the totals, not filtered out.
- **Latency.** Added p95 over guarded was +1.92 ms on the primary workload and +2.19 ms on the second, within the 5 ms budget. Lexical BM25 on its own is faster than guarded.
- **Memory.** In separate processes with the whole development set loaded, hybrid recall over all 9,428 questions peaked at 46,076 KiB with overlap and 46,408 KiB with BM25 (+0.7%). There is no new persisted state, dependency or network use.

### Ablation (prototype, outside the store)

Run outside the store on all 48 development articles at five questions per paragraph, so the numbers come from a prototype script, not the in-repo replay. Tasks satisfied: overlap on the preview 73.5%, overlap on the full text 81.8%, BM25 on the preview 81.4%, BM25 on the full text 90.5%. Full-payload matching and term weighting each contribute about 8 pp, and they add up.

### Decision

**Kept, as opt-in host configuration.** The candidate passed every pre-registered criterion on both the held-out development articles and the separate training-article workload. Overlap stays the default. Switching the default changes the meaning of `relevance.score` for consumers and is a separate, explicitly authorized decision (#85).

## E2: Lexical-confidence router on top of BM25 (#82)

**Hypothesis.** Request-local lexical confidence can tell when hybrid beats lexical BM25.

**Ceiling measured first.** A per-task oracle choosing between `bm25` and `bm25_hybrid` reached 3,356 held-out tasks. bm25_guarded already reached 3,354, so the ceiling is +0.05 pp. On the training workload it was 4,077 against 4,064 (+0.28 pp). Both are far below the 5 pp gate.

**Decision: rejected without building a router.** With the byte-bucket provider, no router can qualify. Routing work only becomes worthwhile again if a real semantic provider (#84) raises the two-arm ceiling. Rank fusion (#83) is deferred for the same reason.

## E3: Low-overlap, cross-domain check on SciFact (follow-up to #79)

**Why.** Both SQuAD workloads favor lexical matching. Before any default change, the owner asked for validation on queries that were not written while reading their evidence.

**Workload.** SciFact (Wadden et al., 2020; [data](https://scifact.s3-us-west-2.amazonaws.com/release/latest/data.tar.gz), SHA-256 `11c62128…76be`, CC BY-NC 2.0) consists of expert-written biomedical claims and 5,183 abstracts. The labeled train and dev claims are used. Every evidence abstract is relevant and required. A SHA-256 hash of `doc_id` splits the corpus into 16 shards, each one scope with about 324 abstracts, plus a private twin and a future decoy. Of the claims, 647 have evidence inside one shard; 46 whose evidence spans shards are excluded and counted. Nothing in v0.8 was designed on this data. 98.9% of abstracts are longer than the preview.

```sh
PYTHONPATH=src python scripts/evaluate_scifact.py --scifact data.tar.gz
```

| Arm (647 claims, 16 scopes) | Satisfied | nDCG@3 | Δ tasks vs guarded [95% CI] | Wins / losses | Median / p95 ms |
| --- | ---: | ---: | ---: | ---: | ---: |
| lexical | 478 | 0.6875 | −1.85 pp [−3.95, 0.49] | 15 / 27 | 24.0 / 37.3 |
| guarded (= hybrid) | 490 | 0.7062 | — | — | 38.5 / 61.8 |
| staged v0.6 | 480 | 0.6890 | −1.55 pp [−3.35, 0.70] | 15 / 25 | 23.9 / 37.6 |
| oracle lexical/hybrid router | 505 | 0.7321 | +2.32 pp | — | — |
| bm25 | 621 | 0.9402 | +20.25 pp [16.29, 24.11] | 136 / 5 | 25.2 / 42.1 |
| **bm25_guarded** | **620** | **0.9378** | **+20.09 pp [16.22, 23.95]** | 135 / 5 | 39.2 / 62.8 |

There were zero scope or time disclosures. The gain is larger than on SQuAD, so the SQuAD result was not an artifact of lexical overlap between questions and passages. As on SQuAD, a router on top of BM25 has no headroom: the oracle reached 622 tasks against 620.

**Latency finding and fix.** The first SciFact run, before caching, met the quality gate but **failed the latency budget**: bm25_guarded p95 was 84.8 ms against guarded's 54.2 ms (+30.6 ms). Profiling showed that per-request tokenization of full payloads dominated. Evidence is immutable, so `CognitiveMemory` now keeps a bounded LRU (4,096 entries) of payload term counts. It is keyed by `(scope, evidence_id, digest)` and filled only from records an authorized scan already returned. The results above are with the cache. Added p95 is +1.0 ms on SciFact, and on SQuAD dev held-out it is −1.4 ms (12.14 against 13.56 ms). A test checks that cached, fresh and size-1-bounded caches produce identical packets.

**Memory.** In separate processes loading all of SciFact and running hybrid recall without per-query warmup, peak RSS was 50,948 KiB with overlap and 80,852 KiB with BM25 (1.59×, under the 2× budget). p95 was 61.6 against 64.1 ms, and the slowest cold call was 83.4 against 107.6 ms. The cache is per `CognitiveMemory` instance. Its worst-case size grows with payload vocabulary, up to 4,096 records.

## Limitations

- SQuAD questions were written while looking at the passage, which favors lexical methods. SciFact (E3) covers a second domain with expert-written claims, but it is still English-only. The only vocabulary-mismatch measurement comes from the small synthetic fixtures, where BM25 neither helps nor hurts.
- The environment could not reach Hugging Face or BEIR mirrors, so no real sentence embedder could be evaluated (#84).
- Latency comes from a shared container. Production traffic, concurrency and large stores (the scan is linear) were not tested.
