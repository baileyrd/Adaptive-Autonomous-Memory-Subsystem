# v1.0 — static embeddings with BM25 rerank (pre-registration)

Tracking: [goal #105](https://github.com/baileyrd/Adaptive-Autonomous-Memory-Subsystem/issues/105), architecture alternatives (#107). Eval-only: no runtime dependency, no product default, no neural activation.

## Why this alternative

v0.9 solved latency (quantized MiniLM L3 added about 2 ms p95) but every ONNX profile failed the ≤2× guarded peak RSS gate (best 5.3×). Fresh-process imports alone account for most of it: bare Python 10 MiB, NumPy + tokenizers + onnxruntime 66 MiB (Linux, Python 3.12, `ru_maxrss`) before any model loads. A smaller transformer cannot remove that floor. A separate worker moves it, but does not remove it.

A static model is a table holding one vector per WordPiece token. Encoding is a lookup and a sum. [`scripts/static_encoder.py`](../../scripts/static_encoder.py) reads a per-row int8 table with the standard library only. It imports neither NumPy, tokenizers nor onnxruntime.

## Recipe (fixed before measurement)

- **Models:** `minishlab/potion-base-8M` and `minishlab/potion-retrieval-32M`. Each revision and source hash is pinned in [`static_embedder_pins.json`](../../scripts/static_embedder_pins.json). An empty revision only prints proposed pins.
- **Conversion:** the single `embeddings` tensor becomes per-row symmetric int8 with one float32 scale per row. The derived files are hashed into the manifest and the representation version.
- **Encoding:**
  - Tokenization: uncased BERT normalization and pre-tokenization, then greedy WordPiece.
  - Unknown tokens are dropped, and the first 512 remaining tokens are kept.
  - Vectors are sum-pooled and L2-normalized. A text with no known token encodes to all zeros.
- **Tokenizer validity:** token ids must equal `tokenizers==0.23.3` (no special tokens) on every SQuAD dev context and question and every SciFact abstract and claim. Any mismatch fails the run.
- **`bm25_rerank` arm:**
  - Takes BM25 guarded's first 20 cited evidence IDs (the existing `lexical_list`).
  - Reads only those IDs' stored vectors, under the index's freshness, checksum and cited-digest rules.
  - Encodes only the query, then returns RRF (k = 60) of the lexical rank and the cosine rank, with ties broken by ID.
  - A zero query vector keeps the lexical order and reports `no_match`.
- The existing `bm25_guarded_onnx`, `onnx` (dense) and `rrf_onnx` arms run unchanged with the static encoder for comparison.

## Order and gates

1. **Cost.** The [v0.9 CPU protocol](onnx-cpu.md) is unchanged: bounded SQuAD dev and train samples, fresh processes, the same guarded comparator, one warmup and ten repetitions. The `static_rerank` arm serves through `bm25_rerank`. It must add ≤5 ms p95 **and** stay within ≤2× guarded peak RSS on both samples.
2. **Quality**, only for a variant that passed cost:
   - Workloads: SQuAD dev, SQuAD train (48 articles), SciFact (16 shards) and the v0.6 fixture with contradiction tasks, with 5 repetitions each.
   - Comparison: paired task success and nDCG@3 against `bm25_guarded`, with article/shard-grouped bootstrap intervals and zero scope and time leaks.
   - A variant that fails cost is reported as quality **NOT MEASURED**.

The workflow is [`static-embedder-eval.yml`](../../.github/workflows/static-embedder-eval.yml). It installs AAMS only for the cost and quality jobs, and tokenizers only for the parity step.

**Local preflight.** This is not evidence: synthetic random tables of the same shape on SQuAD dev, Python 3.13.

| Table | Added p95 | RSS ratio |
| --- | --- | --- |
| 29,528 × 256 | +0.35 to 0.77 ms | 1.67× |
| 63,091 × 512 | Within noise | 3.84× (fails) |

With random vectors, `bm25_rerank` lost about 15 pp against `bm25_guarded`. The harness can therefore show harm, and real vectors must recover that loss before they can show any gain.

## Results

Run [45314502181](https://github.com/baileyrd/Adaptive-Autonomous-Memory-Subsystem/actions/runs/45314502181) at head `6d63be6`. Hosted Linux, Python 3.12.16. Tokenizer parity: 18,929/18,929 texts were identical for both models.

**Cost gate** (static_rerank vs guarded, same runner):

| Model | Dev added p95 / RSS | Train added p95 / RSS | Gate |
| --- | --- | --- | --- |
| potion-base-8M | +0.371 ms / 1.660× | +0.367 ms / 1.668× | **PASS** |
| potion-retrieval-32M | Within budget / over 2× | +0.748 ms / 3.673× | **FAIL** (RSS); quality NOT MEASURED |

The 8M encoder adds 0.32 ms p95 itself. This is the first encoder to pass both v0.9 gates.

**Quality, potion-base-8M** (held-out splits; paired task-success delta vs `bm25_guarded`, 95% grouped CI):

| Workload | `bm25_rerank` (pre-registered) | nDCG@3 Δ | `bm25_guarded_onnx` (full-scan score fusion, comparison only) | nDCG@3 Δ | Its added p95 |
| --- | --- | --- | --- | --- | --- |
| SQuAD dev | −0.88 pp [−2.04, +0.41] | −0.032 | **+1.34 pp [+0.41, +2.40]** | +0.012 | +7.3 ms |
| SQuAD train (48) | +0.30 pp [−0.55, +1.42] | −0.017 | **+1.87 pp [+1.10, +2.71]** | +0.018 | +11.2 ms |
| SciFact | +0.77 pp [−0.15, +1.72] | −0.006 | **+1.70 pp [+0.71, +2.86]** | +0.017 | +24.4 ms |

Every arm had zero scope leaks, zero time leaks and zero contradiction regressions on the v0.6 fixture. The dense-only arm lost 5 to 13 pp, and `rrf_onnx` lost up to 2.3 pp.

## Disposition

- **`bm25_rerank`: no-go.** It gives no significant task gain on any workload, and nDCG@3 is slightly negative on all three.
- **The static encoder: cost go.** It passes both resource gates without NumPy or onnxruntime, and its vectors carry real signal.
- **Score fusion.** The existing score-averaging fusion (`bm25_guarded_onnx`) improves every workload significantly. It fails latency only because the full-scan snapshot path reads and verifies every vector in the scope on each query; encoding is not the cause.
- **Hypothesis for the next pre-registration (post hoc, untested here):** the same score fusion, restricted to BM25 guarded's top 20 cited vectors, keeps the gain at rerank cost. It must be tested on fresh partitions or under a stated reuse caveat, because it was chosen after seeing these results.
- No runtime or default change is authorized by these results.

## Follow-up pre-registration: top-20 score fusion (`bm25_fusion`)

This section was committed before the run. It was chosen after seeing the results above, so it is a follow-up hypothesis, not a confirmation of them.

- **Arm.** Take BM25 guarded's first 20 cited evidence IDs and their BM25 scores (the best score of any item citing each one). Read only those IDs' stored vectors, under the same rules as `bm25_rerank`, and encode only the query. Score each candidate as (BM25 / list peak + cosine, counted only if ≥ 0.35) / 2. This is recall's hybrid rule, restricted to the lexical candidates. Sort descending, with ties broken by ID. A zero query vector keeps the lexical order and reports `no_match`.
- **Model.** potion-base-8M only, at the same pins and recipe.
- **Cost gate.** The v0.9 protocol is unchanged. The `static_fusion` serving arm must add ≤5 ms p95 and stay within ≤2× guarded RSS on both samples.
- **Primary workload.** SQuAD train articles 48–95 (`--first-article 48 --max-articles 48`), never evaluated by any earlier run. Both hash partitions count, reported separately and pooled by the article-grouped bootstrap.
- **Secondary workloads, with a reuse caveat.** SQuAD dev, SQuAD train 0–47, SciFact and the v0.6 contradiction fixture.
- **Go criterion for proposing a canary.** All of the following must hold:
  - Primary paired task-success Δ vs `bm25_guarded` has a 95% CI lower bound > 0, and nDCG@3 Δ ≥ 0.
  - No secondary workload shows a significant loss.
  - Zero scope and time leaks, and zero contradiction regressions.
  - The cost gate passes.
- Meeting the criterion authorizes only a separate proposal. The default stays BM25.

### Results: `bm25_fusion`

Run [45332012602](https://github.com/baileyrd/Adaptive-Autonomous-Memory-Subsystem/actions/runs/45332012602) at head `853c5b0`. Hosted Linux, Python 3.12.16. Tokenizer parity: 18,929/18,929.

**Cost gate** (vs guarded, same runner): `static_fusion` added +0.412 ms p95 / 1.660× RSS on dev and +0.320 ms / 1.649× on train. `static_rerank` added +0.397 / 1.654× and +0.363 / 1.647×. **PASS.**

**Quality** (paired task-success Δ vs `bm25_guarded`, 95% grouped CI):

| Workload | Partition | `bm25_fusion` Δ | nDCG@3 Δ | Wins / losses |
| --- | --- | --- | --- | --- |
| **SQuAD train 48–95 (primary)** | design | **+1.51 pp [+0.99, +2.00]** | +0.018 | 115 / 36 |
| **SQuAD train 48–95 (primary)** | heldout | **+1.62 pp [+1.01, +2.23]** | +0.016 | 120 / 52 |
| SQuAD dev (reuse) | heldout | +1.34 pp [+0.41, +2.40] | +0.012 | |
| SQuAD train 0–47 (reuse) | heldout | +1.87 pp [+1.10, +2.71] | +0.018 | |
| SciFact (reuse) | heldout | +1.70 pp [+0.71, +2.86] | +0.017 | 12 / 1 |

On the reused workloads `bm25_fusion` matched the full-scan `bm25_guarded_onnx` exactly, so restricting to the top 20 lost nothing; full scan still added +9 to +24 ms p95. `bm25_rerank` stayed null on the primary heldout split (−0.07 pp [−1.04, +0.89]). Every arm had zero scope and time leaks and zero contradiction regressions on the v0.6 fixture.

### Disposition: `bm25_fusion`

- **Go criterion met.** The primary CI lower bound is above zero on both partitions, nDCG@3 Δ is positive, no secondary workload loses, leaks and contradiction regressions are zero, and the cost gate passes with about 12× headroom on latency.
- This authorizes **only a separate canary proposal**. The default stays BM25. A runtime change would make the static encoder an optional extra, and it needs explicit approval before any dependency or default change.
- Caveats: the gain is about +1.5 pp of task success, measured on SQuAD and SciFact; the v0.6 fixture showed no regression but is too small to show gain. The secondary workloads informed the hypothesis, so only the primary partition is confirmatory.
