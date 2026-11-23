# v0.9 ONNX profiling contract (first slice)

Tracking: [#94](https://github.com/baileyrd/Adaptive-Autonomous-Memory-Subsystem/issues/94) / [#95](https://github.com/baileyrd/Adaptive-Autonomous-Memory-Subsystem/issues/95).

The pinned BAAI/bge-small-en-v1.5 eval-only encoder exceeded resource gates in v0.8: encode p95 8.67 ms versus a ≤5 ms *added end-to-end* budget, and approximately 283 MiB loaded RSS versus ≤2× baseline. Its retrieval quality was **not** fully measured; neither semantic nor RRF is enabled in product.

## Inert measurement

`OnnxSentenceEncoder(..., record_phases=True)` records a capped list (4,096) of immutable `EncodePhaseTiming` records, each containing **only** nanosecond durations: tokenization, feed preparation, ONNX session inference, vector normalization, and sum. It does not store text, token IDs, memory sources, or embeddings. Failed encodes do not append partial measurements. The default `record_phases=False` retains the old output, call shape, and `encode_ns` interface and does not enable profiling or network access.

The phase timings include Python clock overhead and are diagnostics, not a low-overhead production profiler. Timing one call cannot establish warm-state p95 or total retrieval impact; measure repeated matched requests on the same host, separately from model initialization and memory peak, with a controlled baseline and sample sizes.

## Planned attribution experiment

Record cold load and warm query phase distributions separately, then test session/thread and representation options one at a time. Predeclare RSS and end-to-end p95 gates before quality comparisons. Do not optimize based on mock encoder timings; the offline tests only prove shape and invariants. The default BM25 ranker, guarded routing, scope/time checks and authoritative memory state must stay unchanged.

No real model was executed as part of this slice. Exact real ONNX numbers and cost improvements remain **NOT MEASURED** until the optional pinned model is run.
