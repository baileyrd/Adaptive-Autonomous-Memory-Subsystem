# AAMS v0.4 optional neural association acceptance

The [v0.4 engineering goal](https://github.com/baileyrd/Adaptive-Autonomous-Memory-Subsystem/issues/34) adds a replaceable provider, disposable scoped index and opt-in hybrid retrieval. Canonical evidence remains the source for every citation. The index cannot create evidence, revise beliefs, or alter governed candidate dispositions.

| Requirement | Observed status |
| --- | --- |
| Provider substitution and scope isolation | **PASS.** Versioned provider keys include model and dimensions. The representation tests exercised different dimensions, provider errors and canonical reauthorization. |
| Index migration, recovery and replay | **PASS.** Tests cover schema 4 to 5, restart, idempotent rebuild, interruption during replacement, stale watermarks, invalidation and corrupt-vector recovery. Empty batches also require valid generation metadata. |
| Deterministic lexical fallback | **PASS.** Exact lookup and default lexical ranking use canonical paths. Missing, stale, corrupt and unusable derived data fell back without provider error details. Temporal and scope checks apply before any result is returned. |
| Canonical authority and existing behavior | **PASS.** The test suite preserves immutable evidence, belief and candidate histories, MCP restart and the v0.3 approval safeguards. Hybrid recall is a native opt-in path. |
| Real encoder execution | **PASS locally.** spaCy 3.8.11, en_core_web_sm 3.8.0 and 96-dimensional CPU tok2vec mean pooling ran against the same fixture as the lexical and byte-bucket modes. |
| Neural quality improvement | **FAIL for the tested encoder and corpus.** Recall@3 was 0.6250 versus 0.6875 lexical and nDCG@3 was 0.6369 versus 0.7211. Task coverage was 5/8 for both. No scope or historical disclosure was observed on any mode. |
| Real-world and long-running operating limits | **NOT TESTED.** Production-scale rebuilds, live write contention, multilingual performance beyond the fixture and changes in provider artifacts are unverified. |

The real encoder raised median latency from 0.907 ms to 3.758 ms and process peak RSS from 16,000 to 118,568 KiB in the fixed experiment. It recovered one paraphrase at the cost of lower aggregate quality. Lexical remains the default. The [evaluation](../audit/semantic-evaluation.md) includes exact install and benchmark commands, model checksum, corpus, p95, CPU, memory, storage and contradiction results.

## Evidence and operations

| Slice | Tested head | CI |
| --- | --- | --- |
| Provider contracts | `356e0dfc3341c11152296a1c16e9bdcf2f1eb33c` | [Python 3.11 and 3.12](https://github.com/baileyrd/Adaptive-Autonomous-Memory-Subsystem/actions/runs/45166470523) |
| Scoped representation index | `e6c9840d291fb1aeea084a64570f6e79ce2b5d72` | [Python 3.11 and 3.12](https://github.com/baileyrd/Adaptive-Autonomous-Memory-Subsystem/actions/runs/45167644084) |
| Opt-in hybrid recall | `2ebf9477eb5d4195a39285e6eeb44fb3b1e757a3` | [Python 3.11 and 3.12](https://github.com/baileyrd/Adaptive-Autonomous-Memory-Subsystem/actions/runs/45168004069) |
| Evaluation | `a91b71f1c3d35a23b614003cc887d25ed131cdee` | [Python 3.11 and 3.12](https://github.com/baileyrd/Adaptive-Autonomous-Memory-Subsystem/actions/runs/45168432002) |

The coordination issue records the final integration SHA and CI. Regular CI covers the offline lexical and fixture modes. The pretrained neural run was executed separately with optional dependencies. Use the [index and recovery instructions](../vector-index.md) for rebuild, corruption, outage and scope behavior, and the [README](../../README.md) for backup, restore, demo and test commands.

## Adaptation research

Before optimizing ranking from recorded outcomes, define a larger held-out relevance and counterexample corpus. Require repeated quality improvement against lexical under matched budgets, calibrated task proxies, zero observed scope or historical disclosures, and contradiction retention before testing any feedback-driven ranking. Keep all feedback and neural scores separate from authority decisions.
