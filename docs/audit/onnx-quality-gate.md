# v0.9 neural quality gate disposition

The held-out SQuAD, SciFact, and paraphrase/contradiction quality runs are **NOT MEASURED** for this milestone. The pre-registered gate requires at most 5 ms added p95 and 2× guarded peak RSS on both matched resource samples. No measured profile passed both limits. Retrieval quality remains unknown for these variants.

| Exact evaluated recipe/profile | Dev / train added p95 | Dev / train RSS ratio | Resource gate |
| --- | --- | --- | --- |
| Float BGE, one thread | 16.010 / 14.888 ms | 12.169× / 11.919× | Fail latency and RSS |
| Float BGE, two threads | 10.039 / 9.884 ms | 11.814× / 11.742× | Fail latency and RSS |
| Float BGE, four threads | 12.658 / 12.148 ms | 11.832× / 11.666× | Fail latency and RSS |
| Float BGE, extended graph | 15.004 / 14.601 ms | 12.089× / 11.828× | Fail latency and RSS |
| Quantized BGE, one thread | 3.731 / 3.608 ms | 6.652× / 6.469× | Fail RSS |
| Quantized BGE, two threads | 3.917 / 3.915 ms | 6.662× / 6.515× | Fail RSS |
| Quantized MiniLM L3, one thread | 2.014 / 2.111 ms | 5.379× / 5.290× | Fail RSS |
| Quantized MiniLM L3, two threads | 2.110 / 2.107 ms | 5.341× / 5.298× | Fail RSS |

Float BGE was evaluated at `65e0ae7875984828f1ea6fa79855e1e6bde76420` in [45288978823](https://github.com/baileyrd/Adaptive-Autonomous-Memory-Subsystem/actions/runs/45288978823). The checksum-pinned quantized rerun tested `2a10b6f69f68b9a9290fabf5b437281ff345dbc7` in [45289712325](https://github.com/baileyrd/Adaptive-Autonomous-Memory-Subsystem/actions/runs/45289712325). Results compare each candidate with guarded on its own runner, not absolute timings across CPU models. The rank-parity check compares CPU settings within the same export. It says nothing about quality differences between exports or gain over guarded.

If a future recipe clears both costs under the same protocol, preregister and run the full independent workload set, including low-overlap SciFact, adversarial scope/time and contradiction coverage, and article/group-resampled intervals. Include the guarded BM25, explicit hybrid, dense/fusion and route oracle arms. The existing BM25 default remains authorized. The feasibility runs do not authorize any runtime change.
