# Recall scaling on synthetic local data

Baseline source is commit `e76bcbe` (#15). Compare it with the single-snapshot change in the #17 PR. Both use the same benchmark script in this revision. To reproduce, extract baseline `src` into a temporary directory with `git archive e76bcbe src | tar -x -C "$baseline"` after creating that directory. Run the following twice per corpus. Set `PYTHONPATH` to the extracted baseline's `src` for baseline runs and to this checkout's `src` for optimized runs.

```sh
PYTHONPATH=src python scripts/benchmark.py --records 256 --scopes 4 --beliefs 8 --samples 30 --warmup 8
PYTHONPATH=src python scripts/benchmark.py --records 1024 --scopes 4 --beliefs 32 --samples 30 --warmup 8
PYTHONPATH=src python scripts/benchmark.py --records 4096 --scopes 8 --beliefs 128 --samples 30 --warmup 8
```

Linux 6.18.57 x86-64, Python 3.12.14, SQLite 3.53.1 and SDK 2.3.0. Seed 1081 produces repeated payloads and two revisions per synthetic belief, including refuting evidence. Each run has eight ingest and read warmups and 30 timed samples per read mode.

| Formations incl. warmup | Scopes | Revisions | Exact p50 / p95 before (ms) | Exact p50 / p95 after (ms) | Contextual p50 / p95 before (ms) | Contextual p50 / p95 after (ms) |
| ---: | ---: | ---: | --- | --- | --- | --- |
| 264 | 4 | 16 | 0.259–0.264 / 0.327–0.413 | 0.286–0.287 / 0.389–0.784 | 18.331–18.670 / 19.769–20.064 | 2.186–2.321 / 2.567–2.728 |
| 1032 | 4 | 64 | 0.283–0.324 / 0.382–0.506 | 0.266–0.294 / 0.365–0.503 | 74.329–82.435 / 101.817–103.224 | 7.826–8.194 / 8.540–10.594 |
| 4104 | 8 | 256 | 0.270–0.303 / 0.403–0.542 | 0.269–0.271 / 0.365 | 155.257–156.012 / 173.736–219.392 | 15.203–16.860 / 15.589–22.787 |

| Formations | Ingest before / after (records/s) | Contextual peak Python allocations before / after (bytes) | SQLite bytes in both |
| ---: | --- | --- | ---: |
| 264 | 3668–4096 / 3755–3785 | 70,238–70,488 / 76,294–76,544 | 237,568 |
| 1032 | 3329–3825 / 3182–3447 | 286,209–288,259 / 277,696–278,611 | 737,280 |
| 4104 | 3478–3794 / 3790–3797 | 530,301–532,251 / 491,411–493,240 | 2,744,320 |

Ranked recall now reads each candidate and its evidence through one scoped snapshot. It uses the same canonical decoders and ranking rules as before. Tests verify stable ties, scope filtering, historic revisions, contradiction links and use of one connection. Exact recall continues to use the canonical identity lookup. No schema change, background index or alternate retrieval policy is needed.

The scan still grows with the eligible corpus. The snapshot can hold a read transaction while ranking, and the benchmark did not measure concurrent write contention, MCP latency or process RSS. Small exact-read and ingest differences varied between runs. The contextual improvement was consistent across all three corpora.
