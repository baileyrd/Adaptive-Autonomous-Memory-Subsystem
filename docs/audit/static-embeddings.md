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
