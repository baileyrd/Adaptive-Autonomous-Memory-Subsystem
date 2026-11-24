# Model-driven decisions on paired work histories

A local Qwen2.5-0.5B-Instruct agent selected one of three actions on 14 unseen histories. Each family had the same question twice and opposite world outcomes. Gold actions were fixed separately from prompts. All five arms used the same model, instruction and final budgets. The published JSON records each actual action, delivered IDs, decisive-evidence presence, neural-only IDs, prompt tokens and latency.

**Cognitive utility — failed the preregistered positive criterion.** Every no-memory, copy-aware and neural decision was an abstention. Raw and structured each got two actions right but also issued one false yes. For neither did the lower correctness bound exceed zero. Each arm failed at least one member of every counterfactual pair. This pilot supplies no evidence of improved learning or restored task continuity. Why this model abstained so consistently is inconclusive.

**Retrieval — verified within the histories.** The decisive entry reached the model on 8/14 structured tasks, 13/14 copy-aware tasks and all 14 neural tasks. On all 14 neural decisions the failure occurred after relevant evidence was presented. This isolates the stage, while leaving open whether the instruction, model capacity, representation of the journal or forced-choice policy caused the behavior. Zero correct actions lacked the designated decisive entry; its presence alone cannot establish justified reasoning.

**Memory correctness and safety — verified for the evaluated paths.** Authorized citation checks covered source identity, payload preview, digest and both time bounds. Database content digests matched after every arm. False yes measures an incorrect model decision and occurred despite valid citations. Model resistance to instruction injection, authenticated source independence, governed deletion and open-ended tool use were not measured.

**Operating cost — measured on this host.** Total input tokens include the journal framing and question. Subtract the paired no-memory total (1,390) to obtain incremental context tokens: 7,855 for raw and structured, 1,950 for copy-aware and 2,028 for neural. Each inference generated one constrained token. Medians include retrieval and inference, exclude loading, and use a shared-process single pass. Per-arm RSS, cold start, sustained throughput and deployment qualification were not measured.

| Arm | Correct / 14 | False yes | Wrong no | Abstained | Decisive entry surfaced | Correct without decisive entry | Input tokens | Median ms |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| no_memory | 0 | 0 | 0 | 14 | 0 | 0 | 1390 | 937 |
| raw_search | 2 | 1 | 0 | 11 | 8 | 0 | 9245 | 6687 |
| structured | 2 | 1 | 0 | 11 | 8 | 0 | 9245 | 6558 |
| copy_diverse | 0 | 0 | 0 | 14 | 13 | 0 | 3340 | 2306 |
| neural | 0 | 0 | 0 | 14 | 14 | 0 | 3418 | 2911 |

| Arm | Correctness change vs no memory, pp [95% interval] | Change vs structured, pp [95% interval] |
|---|---:|---:|
| no_memory | +0.00 [+0.00, +0.00] | -14.29 [-28.57, +0.00] |
| raw_search | +14.29 [+0.00, +28.57] | +0.00 [+0.00, +0.00] |
| structured | +14.29 [+0.00, +28.57] | +0.00 [+0.00, +0.00] |
| copy_diverse | +0.00 [+0.00, +0.00] | -14.29 [-28.57, +0.00] |
| neural | +0.00 [+0.00, +0.00] | -14.29 [-28.57, +0.00] |

| Family | No memory | Raw | Structured | Copy-aware | Neural |
|---|---:|---:|---:|---:|---:|
| prior_failure | 0/2 | 0/2 | 0/2 | 0/2 | 0/2 |
| lesson_transfer | 0/2 | 0/2 | 0/2 | 0/2 | 0/2 |
| interruption | 0/2 | 0/2 | 0/2 | 0/2 | 0/2 |
| belief_update | 0/2 | 0/2 | 0/2 | 0/2 | 0/2 |
| common_origin | 0/2 | 1/2 | 1/2 | 0/2 | 0/2 |
| repeat_mistake | 0/2 | 1/2 | 1/2 | 0/2 | 0/2 |
| recency_counterexample | 0/2 | 0/2 | 0/2 | 0/2 | 0/2 |

SQLite fixture size 401,408 bytes. The neural arm surfaced one decisive entry absent from the lexical top 20: the single-origin archive counterexample. The model abstained. Structured recall produced a false yes on the journal conversion with a known unresolved defect. Neither result establishes real-world source attestation.

## Reproduction

The task set and protocol were frozen at 03bd52785f04cfa3b1329a6feacf2f305436da76. Execution source was frozen at f366e7835184a3d9bd5a5dd41a62ea1f4a9ebb89. Run on Linux x86-64, AMD EPYC 9V45, CPython 3.12.14, NumPy 2.5.5. Install the project and the optional llama-cpp-python==0.3.16 in an isolated research environment. This run built the library with GCC/G++, GGML_NATIVE=OFF and GGML_OPENMP=OFF. No default CI job installs this dependency or downloads weights.

The official model file is qwen2.5-0.5b-instruct-q4_k_m.gguf. This execution used only the binary model from the weights-v1 GitHub release of rtynbirf/singulyar-llm. Joining the six ordered parts yields the required SHA-256. The runner verifies that identity before inference.

```sh
gh release download weights-v1 -R rtynbirf/singulyar-llm -D parts -p '*.bin'
cat parts/qwen2.5-0.5b-instruct-q4_k_m.part-*-of-06.bin > qwen.gguf
python scripts/evaluate_model_decisions.py qwen.gguf > replay.json
```

The seven-family intervals are descriptive. Fixed-choice decisions cannot establish open-ended reasoning, durable task learning, or autonomous belief revision. The fixtures and answer keys were frozen by the same experiment author; independent scoring means the outcome key is outside the model and retrieval code. The synthetic source names expose family and variant identifiers. A replication should blind those identifiers. Neural-vector cosine ordering is over authorized visible text only; source-private and future decoys are included in each history. The checkpoint task supplies a journal entry rather than a persistent checkpoint. Model weights, derived vectors and decisions were never stored in authoritative memory.
