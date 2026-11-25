# Checkpoint assistance and the model’s first action after interruption

Checkpoint assistance and existing structured BM25 each produced **2/12 supported correct first actions** on the same held-out histories. The model chose **C, resolve consent, on all 78 decisions**, including every denial, conflict and no-memory prompt. There were zero paired gains and zero regressions. The separate all-evidence diagnostic scored **1/6**, below its frozen 6/6 gate. Added checkpoint benefit failed the preregistered criterion. The tie leaves efficacy inconclusive for a model capable of the task. It does not reproduce #132’s rule-agent performance of 16/16 in both arms.

## What the model saw and did

A preparer wrote the simulated histories and checkpoints, then exited. Every decision started a fresh isolated interpreter with the same Qwen weights and no inference history. Both assisted arms used #132’s original code. The checkpoint arm reauthorized source references, added newer executor evidence and used ordinary retrieval after rejection. The scorer required the correct action and all decisive evidence in the packet. The two supported correct choices happened to match the model’s invariant answer; they establish no evidence use by the model.

| Outcome | No memory | Bounded transcript | Structured BM25 | Checkpoint-assisted |
|---|---:|---:|---:|---:|
| Design supported correct / 6 | 0 | 0 | 1 | 1 |
| Held-out action matched key / 12 | 2 | 2 | 2 | 2 |
| Held-out supported correct resumptions / 8 operational cases | 0 | 0 | 2 | 2 |
| Required access denials / 2 | 0 | 0 | 0 | 0 |
| Required conflict abstentions / 2 | 0 | 0 | 0 | 0 |
| Incorrect abstentions | 0 | 0 | 0 | 0 |
| Unsupported actions / 12 | 12 | 12 | 10 | 10 |
| Complete decisive evidence / 10 authorized histories | 0 | 0 | 10 | 10 |
| Simulated unsafe actions / 12 | 4 | 4 | 4 | 4 |

Each held-out arm had four unsafe choices (both conflicts and both revoked grants), six wasted steps and two actions that would advance the simulator. For no memory and transcript, both advances were unsupported guesses. The host withheld all protected content after revocation, even when the model requested an operational action. No arm disclosed a protected or time-ineligible citation. Counts of implied invented progress, repeated completed work, repeated failed verification and bypassed active constraints were each zero across all four arms. The narrow action vocabulary makes these action-implied errors observable; the experiment elicited no free-text progress claims.

| Held-out family (two histories each) | No memory | Transcript | BM25 | Checkpoint |
|---|---:|---:|---:|---:|
| Changed consent requirement | 0 | 0 | 1 | 1 |
| Failed prior verification | 0 | 0 | 0 | 0 |
| Stale pre-interruption state | 0 | 0 | 0 | 0 |
| Equally current conflicting certificates | 0 | 0 | 0 | 0 |
| Revoked grant | 0 | 0 | 0 | 0 |
| Expired checkpoint | 0 | 0 | 1 | 1 |

The checkpoint-minus-BM25 difference was 0 percentage points in each family. The descriptive six-family bootstrap interval was [0, 0] pp. This interval resamples the six observed families, all tied; it does not bound effects on other prompts, models, or tasks. The diagnostic included five granted cases with complete evidence and one explicit denied grant. Only the changed-consent case was correct. Shared synthetic grammar, six author-visible families, one action-to-letter mapping and one small quantized model limit interpretation. The study cannot distinguish preference for the letter C from preference for its associated action.

## Retrieval, integrity and cost

On held-out histories, no memory left ten decisive evidence sets unavailable. Transcript recency excluded all ten from the final packet. Structured and checkpoint delivered all ten, including both sides of each conflict. The two arms still had eight wrong answers on granted cases and two wrong answers with the explicit denied grant. In the checkpoint arm eight requests restored pre-interruption sources, two expired cases used canonical fallback, and two revoked requests returned empty. The success on one expired history came through fallback.

Each reopen matched all 26 physical file hashes and the logical SQLite digest `5efa7e5b401c8d28eb580a77e0fec7d6e470a610c2b92a4f5cbe5d9c54b994bf`. SQLite was 3.53.1. Total prepared database, registry and sidecars occupied 493,799 bytes. The [event stream](q4-resume-events.jsonl) contains the exact prompt, raw output, decoded action, simulated consequence, candidates, canonical citations, per-file manifests and resource measurements. Its SHA-256 is `2b16c77aca888e99ea621667030a8367e3ac1827e12022de9bf9594183ade6f7`. The [scorecards](q4-resume-scorecards.json) include every split, family and held-out paired effect.

| Held-out cost | No memory | Transcript | BM25 | Checkpoint |
|---|---:|---:|---:|---:|
| Median elapsed ms | 3434 | 6310 | 5919 | 5914 |
| Median actor CPU ms | 1869 | 5439 | 5854 | 5839 |
| Largest actor peak RSS KiB | 648140 | 679932 | 680268 | 680168 |
| Maximum prompt tokens | 132 | 508 | 580 | 580 |

Every completion used one token. Elapsed time includes retrieval and fresh process/model startup. CPU measures the actor from before llama import through completion. First-run measurements overlapped local validation and part of a separate replay. Fixed arm order, OS caching and shared-host load preclude a latency ranking. This is disposable, same-model fresh-process recovery. Model replacement, durable checkpoint authority and real-world action execution remain unmeasured.

One next action is independent review of the frozen packets and model decoding, especially the invariant C response on the diagnostic, before using this actor to interpret memory efficacy.

## Replay

The preregistration and evaluator freeze were public before scoring. Design commit `09d54e9fac624b625c30a7ffc7fd363ca0794362` pins the cases, labels and rules. Executable commit `95bcfe65b9b50b5b813fe837119b4e0464574002` pins prompts, retrieval, decoding, scoring and tests. Base `395118e4de5b13a0767ea441bbf98b58c2121810` contains #132 and the original #129–#131 evidence. [Design registration](https://github.com/baileyrd/Adaptive-Autonomous-Memory-Subsystem/issues/124#issuecomment-7167032089) · [Executable freeze](https://github.com/baileyrd/Adaptive-Autonomous-Memory-Subsystem/issues/124#issuecomment-7167072956)

Inside the WSL distribution registered as `FedoraLinux-43`, the installed userspace reported Fedora release 44. The host exposed four logical CPUs on an AMD Ryzen 9 7900X3D. Kernel, SQLite, interpreter build and GGUF hash are in the first event. The pinned interpreter contained llama-cpp-python 0.3.16, diskcache 5.6.3, Jinja2 3.1.6, MarkupSafe 3.0.4, NumPy 2.5.5 and typing-extensions 4.16.0. Loaded package library file hashes for replay:

| Runtime file | SHA-256 |
|---|---|
| libllama.so | fb22835b334a81bc045fc6f2e131a7418d39cef0c243eea3b337ce945ad323a7 |
| libggml-base.so | 1686a8a487cf43a3cdd2ed4e689ff2ba7812797e7e4284ae6ea5be3e999e0acd |
| libggml-cpu.so | e7d06482836b03afeab7c6d1b642685ab5536787188e6edd2be97aafdfbaa238 |
| libggml.so | 159c05940335ea95265223cb8e2d07c2c5ad3f88b57cd4bc3b476d0e93998367 |
| libmtmd.so | cf21470c213bddedad151b378d981c0b91626ed1c9e830072b76ec99c7e1d84f |

From a Linux checkout of this evidence PR, run the following in Bash. The new output filename must be unused. The runtime checks the GGUF SHA-256 and versions before opening the disposable database.

```bash
PY=/home/baileyrd/.cache/aams-124-q4-runtime/bin/python
GGUF=/mnt/c/Users/baileyrd/OneDrive/Documents/ChatGPT/AAMS/model-cache/qwen2.5-0.5b-instruct-q4_k_m.gguf
scratch=$(mktemp -d)
git worktree add --detach "$scratch/freeze" 95bcfe65b9b50b5b813fe837119b4e0464574002
"$PY" "$scratch/freeze/scripts/q4_resume_cases.py"
"$PY" "$scratch/freeze/scripts/evaluate_q4_resume.py" "$GGUF" "$scratch/replay.jsonl"
"$PY" scripts/audit_q4_resume.py "$scratch/replay.jsonl" > "$scratch/replay-scorecards.json"
"$PY" scripts/audit_q4_resume.py docs/audit/q4-resume-events.jsonl > "$scratch/published-scorecards.json"
diff "$scratch/published-scorecards.json" docs/audit/q4-resume-scorecards.json
```

Compare `semantic_sha256` and `logical_sha256` between the two generated scorecards. The semantic hash covers every ordered decision, exact prompt, candidate list, citation, raw choices, token counts and consequence. It omits elapsed time, CPU, RSS, PID and the raw completion's generated ID, timestamp and model path. Each run must also pass its own physical file checks. The actor receives only the prompt on standard input and the GGUF path as an argument. Model outputs are simulated first actions with no tools.

For the repository checks in a separate environment:

```bash
uv venv --python 3.12 .venv
uv pip install '.[mcp]' ruff==0.14.6
.venv/bin/ruff format --check src tests scripts
.venv/bin/ruff check src tests scripts
.venv/bin/python -m compileall -q src tests scripts
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m aams.demo
```
