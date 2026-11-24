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

## Index build and reopened serving (slice B)

`scripts/profile_retrieval_memory.py` prepares the bounded workload in a disposable subprocess, then runs six fresh `python -I` measurement children: guarded and one-thread MiniLM, each with model-only, index-build, and serving stages. Full SQuAD parsing stays outside the controller and measured children, matching v0.9 and preventing dataset parsing peaks from inflating the guarded denominator. Each child rechecks the source dataset with bounded-buffer hashing and verifies the prepared workload digest. Each arm builds its own temporary scoped database; serving reopens that database in a separate process. Both arms use the existing v0.9 checksum-pinned, three-article/eight-paragraph SQuAD resource sample and its scope/time-filtered requests. The ONNX encoder verifies both artifact hashes before loading. No optional packages are imported by the guarded arm.

Snapshots report current Linux RSS and cumulative child peak after workload load, provider load, index build, first serving pass, and repeated serving. Reports contain aggregate counts, durations, process IDs, model/dataset hashes and host details. They contain no source text, query, citation, vector, or quality score. Temporary databases are deleted when the harness exits. Model-only includes workload preparation to keep the comparison matched. The first request and first pass are **process-cold**, after reopening storage and loading the provider; OS filesystem caches are uncontrolled. Subsequent passes retain that process's provider and caches. `spawn_to_exit_ms` includes interpreter startup, imports, execution and output; `startup_through_cold_pass_ms` begins after script imports and ends after the first pass. Neither is a deployment cold-start SLA.

```sh
python -m pip install . onnxruntime==1.32.0 tokenizers==0.23.3 numpy==2.5.3
python scripts/prepare_onnx_variant.py minilm-l3-q8 model
# Obtain dev/train inputs from the exact SQuAD revision in neural-memory-eval.yml.
python scripts/benchmark_onnx_cpu.py --model model --variant model/manifest.json --data dev.json --partition dev
python scripts/profile_retrieval_memory.py --model model --variant model/manifest.json --data dev.json --partition dev
# Repeat both commands with train.json / --partition train on the same host.
```

The optional `neural-memory-eval.yml` workflow runs the original cost benchmark before attribution on the same runner for each partition. It saves the tested checkout SHA, package versions, model manifest, dependency-stage footprints, and full reports as `neural-memory-attribution`. The base CI retains its dependency-free product contract tests without model downloads. This harness is Linux-only, sequential and single-worker, with 1–20 warm passes (default 10), and a 300-second limit per child. Concurrency and execution-placement experiments remain #107 work.

The diagnostic resource screen compares added warm p95 against ≤5 ms and the maximum observed per-process stage peak against ≤2× guarded; it does not add child peaks and does not authorize quality evaluation. Qualification still requires the existing benchmark to pass both gates. Tests exercise real scoped storage and reopened serving with a deterministic fixture provider, process orchestration/failure propagation, and checksum rejection. Fixture results establish harness behavior only.

### Measurement disposition

Actual MiniLM measurements must be linked from #106 and #105 before advancing #107. The local model fetch was blocked by the network proxy (HTTP 403); optional hosted evaluation is the route for real measurements. Do not infer that a smaller model, worker service, or compact index is sufficient from import footprints alone. Select one falsifiable memory-reduction hypothesis from the matched model-only/build/serve results; any quality experiment remains gated.

No live model enablement, adaptive policy, or default-retrieval change is authorized by these experiments.
