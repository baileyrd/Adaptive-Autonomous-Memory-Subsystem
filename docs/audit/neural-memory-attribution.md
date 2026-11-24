# v1.0 — neural dependency RSS attribution protocol

Tracking: [goal #105](https://github.com/baileyrd/Adaptive-Autonomous-Memory-Subsystem/issues/105), [slice #106](https://github.com/baileyrd/Adaptive-Autonomous-Memory-Subsystem/issues/106).

## Known v0.9 facts

The fastest quantized ONNX candidate added about 2 ms p95 on two bounded SQuAD samples but required about 5.3× guarded process memory; the gate was ≤2×. Neural retrieval quality was **NOT MEASURED**, and production BM25/guarded recall must not change.

## Stage probe

`scripts/profile_neural_memory.py` executes each stage in a **separate** Python process with `-I` isolation and a 90-second timeout. It reports `ru_maxrss` (peak), Linux `VmRSS` (current; null elsewhere), elapsed time, stage, Python and platform. These are **process footprints**—not additive allocations or a causal component breakdown. Differences between stages include shared libraries, lazy initialization, allocator behavior, and Python runtime overhead. Do not sum or subtract peak figures as if they isolated components. The utility captures no user queries, retrieved content, vectors, or persisted memories.

Stages: stdlib baseline, NumPy import, tokenizers import, checksum-verified tokenizer load, ONNX Runtime import, and checksum-verified ONNX session load. Model-dependent stages require both `--model-dir` and `--pins` containing exactly `onnx/model.onnx` and `tokenizer.json` SHA-256 digests. No network access, package install, or index mutation is attempted. Execute only inside an optional, pinned-model evaluation environment:

```sh
python scripts/profile_neural_memory.py --stages baseline
python scripts/profile_neural_memory.py --model-dir /path/to/pinned/model --pins /path/to/pins.json
```

The tests run a real baseline subprocess, check strict payload contracts, reject duplicate/unknown stages, and verify checksum rejection before any optional import. They do **not** establish actual ONNX memory consumption in CI.

### Next attribution work

Build a second isolated measurement path for **representation index creation and serving with the same pinned model**, comparing model-only RSS and full scoped-index/recall process RSS. Preserve controlled workloads, equal article/scope sizes, warm/cold behavior, and split out cache lifetime. Only then investigate on-demand loading, a persistent isolated worker, compact index representations, and smaller/native model runtimes. Explicitly record model and dataset hashes, process counts, cold-start tail latency and no-leak regression evidence.

No live model enablement, adaptive policy, or default-retrieval change is authorized by these experiments.
