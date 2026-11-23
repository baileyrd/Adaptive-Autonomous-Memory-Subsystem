# AAMS v0.9 encoder feasibility research

The [v0.9 goal](https://github.com/baileyrd/Adaptive-Autonomous-Memory-Subsystem/issues/94) measured whether CPU-only ONNX encoding can fit the resource budget for a full retrieval-quality evaluation. Production native and MCP recall keep scoped BM25 with guarded routing. The optional research tooling has no serving activation path.

| Requirement | Observed result |
| --- | --- |
| Phase instrumentation and output invariance | **PASS.** Nanosecond phase timings record durations only. Offline tests check timing consistency, failure behavior and unchanged output. |
| Bounded same-model sessions | **PASS experiment.** Float BGE one/two/four-thread and extended graph arms produced identical vectors and top-three rankings on the sampled train and dev groups. The fastest option used two threads and added 10.039/9.884 ms p95. No profile qualified. |
| Versioned, isolated quantized encoders | **PASS experiment.** Separate BGE q8 and MiniLM L3 q8 Model and tokenizer hashes were verified at exact revisions. The CPU variants retain their own pooling and versioned index spaces. A fresh process and separate scoped index were used for each arm. |
| End-to-end latency gate | **PASS for the quantized profiles on both resource samples.** MiniLM L3 one-thread added 2.014/2.111 ms p95. All float BGE profiles exceeded 5 ms. |
| Peak RSS gate | **FAIL for all profiles.** The closest quantized recipe used about 5.3× guarded RSS. The limit remains 2×. |
| Held-out retrieval quality and routing comparisons | **NOT MEASURED.** The full quality stage is conditional on passing both resource gates. Rank parity within an export is an invariance check and does not establish quality across models. |
| Production traffic or canary | **NOT TESTED.** The experiments use bounded public SQuAD subsets in a hosted Linux evaluation job. No neural policy was activated. |

Inference dominated float BGE phase costs. In the dev sample, two threads cut inference p95 from 12.914 to 7.620 ms, while full-request added p95 still exceeded the budget. Four threads used more CPU and did not improve the two-thread result. Reducing graph optimization did not qualify. Quantized variants reduced added latency but their loaded runtime and retrieval process remained too large. The [quality gate report](../audit/onnx-quality-gate.md) lists every measured arm with dev/train results. Complete phase, latency, CPU and RSS data are available in the linked run annotations.

## Reproduce

The [CPU protocol](../audit/onnx-cpu.md) defines the workload, tolerance, phases, model sourcing and warmup. Use Python 3.12 on Linux. Install optional runtime packages only in the evaluation environment.

```sh
python -m pip install . onnxruntime==1.32.0 tokenizers==0.23.3 numpy==2.5.3
python scripts/prepare_onnx_variant.py minilm-l3-q8 model
python scripts/benchmark_onnx_cpu.py --model model --variant model/manifest.json --data dev.json --partition dev
python scripts/benchmark_onnx_cpu.py --model model --variant model/manifest.json --data train.json --partition train
```

The hosted workflows contain exact SQuAD source URLs and dataset hash verification. Float BGE artifact hashes are listed in [the original pins](../../scripts/onnx_pins.json), and the exact tokenizer, export hashes, revisions and pooling recipes for the two alternatives are in [the quantized pins](../../scripts/onnx_variant_pins.json). Artifacts remain outside the repository and subject to their upstream terms. The measured float runs used AMD EPYC 7763 and the committed quantized reruns used Intel Xeon 6975P-C, both with Python 3.12.16. Each candidate and its guarded comparator ran on the same host. Compare normalized results within the job.

| Evidence | Exact tested head | Run |
| --- | --- | --- |
| Phase instrumentation | `7a64843c09d728a992987f8fed58486b52e712e9` | [Python CI](https://github.com/baileyrd/Adaptive-Autonomous-Memory-Subsystem/actions/runs/45286809645) |
| Float CPU options | `65e0ae7875984828f1ea6fa79855e1e6bde76420` | [Python CI](https://github.com/baileyrd/Adaptive-Autonomous-Memory-Subsystem/actions/runs/45288978825) · [Cost](https://github.com/baileyrd/Adaptive-Autonomous-Memory-Subsystem/actions/runs/45288978823) |
| Pinned quantized variants | `2a10b6f69f68b9a9290fabf5b437281ff345dbc7` | [Python CI](https://github.com/baileyrd/Adaptive-Autonomous-Memory-Subsystem/actions/runs/45289712254) · [Cost](https://github.com/baileyrd/Adaptive-Autonomous-Memory-Subsystem/actions/runs/45289712325) |

Use the coordination issue for integration status and final main CI. See [v0.8](MVP-v0.8.md) for the evidence supporting the BM25 default. Stop an experiment by removing its optional model cache and using guarded BM25. The existing overlap fallback is available via `LexicalRanking.OVERLAP`; no storage migration is needed to switch ranking. Further work would need to reduce runtime memory before the held-out quality gate becomes relevant. Any production canary would require separate authorization and independently verified cost, quality and scope safety.
