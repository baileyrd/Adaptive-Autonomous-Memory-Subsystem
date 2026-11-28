# #109 held-out retrieval evidence

## What was reused

| Prior work | Reproducible result | Use in #109 |
| --- | --- | --- |
| [#112](https://github.com/baileyrd/Adaptive-Autonomous-Memory-Subsystem/pull/112) | Potion 8M dense, guarded hybrid, full-list RRF, top-20 rerank and top-20 score fusion on SQuAD and SciFact. v0.6 contradiction checks and matched cost. | Verified SHA-256 of the [round 2 artifacts](https://github.com/baileyrd/Adaptive-Autonomous-Memory-Subsystem/actions/runs/45332012602) and reused the aggregate paired comparisons. Potion 32M had cost only. Potion 8M had no result on the new synthetic families. |
| [#113](https://github.com/baileyrd/Adaptive-Autonomous-Memory-Subsystem/pull/113) | A perfect judge inside the BM25 candidate list could add only 2.32 pp on SciFact at depth 10 and 2.78 pp at depth 20 or 50. | Ceiling and negative control. No Laya inference ran. |
| [#114](https://github.com/baileyrd/Adaptive-Autonomous-Memory-Subsystem/pull/114) and [v0.9](onnx-quality-gate.md) | Pinned ONNX resource tests, including isolated MiniLM model, build and serve stages. No held-out quality test passed through the old cost gate. | Reused as cost evidence. |
| [#115](https://github.com/baileyrd/Adaptive-Autonomous-Memory-Subsystem/issues/115) and [#116](https://github.com/baileyrd/Adaptive-Autonomous-Memory-Subsystem/pull/116) | Approval to measure offline quality independently of cost and a bounded evaluation plan. | Governs this run. |

Potion 8M used the full historical public workloads and other candidates used bounded public subsets. All candidate-versus-baseline pairs used identical questions within their comparison. The historical artifacts lack individual packets and direct paired counts against plain lexical BM25. Their published comparator is `bm25_guarded`, the evaluator's BM25 arm with the deterministic fixture provider on explicit opt-in queries. Plain `bm25` is lexical only. Do not use the two sample sizes for a head-to-head model comparison. The new comparisons include both baselines, and all five encoders share the same new synthetic queries.

## Frozen measurements

Main was `52dac70` at branching. The evaluator, model matrix, selection rules, synthetic cases and scoring were committed at [`8fe8bc1`](https://github.com/baileyrd/Adaptive-Autonomous-Memory-Subsystem/commit/8fe8bc1b47b3a4d89cb7bd198fbd83db8d64393d) before the [hosted run](https://github.com/baileyrd/Adaptive-Autonomous-Memory-Subsystem/actions/runs/46105695762). It used the existing offline replay and ranking arms. Local artifact downloads were blocked by HTTP 403, so only baseline and test checks ran locally. The hosted run used one encoder and disposable store per job, a 30-minute comparison command limit and a 35-minute job limit. It used isolated Linux runners with no enforced 2 GiB process address-space ceiling.

- SQuAD uses the first ten eligible questions from different paragraphs per article, in the first 12 dev articles and train articles 48–59. SciFact uses the first 128 eligible labeled claims sorted by stable ID from the existing train/dev archive, with 16 scope shards. The published corpora and these article ranges have prior exposure. The new public measurements are exploratory replications, and pretraining exposure is unknown.
- Six fresh synthetic families include vocabulary mismatch, contradictory observations, future records, a same-ID foreign-scope decoy and a copied report. The copy cannot substitute for the independently labeled original. Required IDs stay outside the encoder input. There are two contradiction queries, each requiring both sides.
- A win means the candidate packet contains **every** required source within its top three and the baseline packet does not. A loss reverses that comparison. Individual required IDs gained or lost count even when neither packet is complete. On public questions the labels identify the passage or abstract; the packet preview may omit the actual answer. These results measure retrieval, with no reasoning or model-decision outcome scored.
- For the new comparisons, the 95% interval resamples 2,000 paired groups with seed 0: SQuAD articles, SciFact shards containing the eligible evidence clusters, or synthetic families. Repeat timings do not increase the sample size. An interval of `[0, 0]` is an observed tie on these groups. The many comparisons and small group counts limit interpretation.
- The machine-readable [scorecards](heldout-evidence-scorecards.json) retain both baselines, all routes, individual-ID counts, intervals, input/model hashes and costs. The [paired packets](heldout-evidence-packets.jsonl) give the ordered evidence and decisive IDs for each new comparison. Artifact digests and the scored packet counts were independently recounted; repeated baseline packets and selection hashes were checked across models on each workload.

## Reused Potion 8M results

Top-20 score fusion against guarded BM25, from the verified #112 artifacts. Intervals are on net completion-rate change, in percentage points. The #112 SQuAD evaluator used 2,000 paired article resamples with seed 202607. Its published aggregates preserve the counts and interval, with no per-query outcomes for an independent recount.

| Workload and partition | Queries | Recoveries | Losses | Net pp [95% CI] |
| --- | ---: | ---: | ---: | ---: |
| Train 48–95, primary held-out | 4,198 | 120 | 52 | +1.62 [+1.01, +2.23] |
| Train 48–95, design partition | 5,237 | 115 | 36 | +1.51 [+0.99, +2.00] |
| Dev, held-out reuse | 3,646 | 83 | 34 | +1.34 [+0.41, +2.40] |
| Train 0–47, held-out reuse | 4,712 | 141 | 53 | +1.87 [+1.10, +2.71] |
| SciFact, reuse | 647 | 12 | 1 | +1.70 [+0.71, +2.86] |

The alternate Potion 8M routes behaved differently. On the primary held-out partition, dense had 210 wins and 694 losses, RRF 168 and 220, and top-20 RRF rerank 157 and 160. Full-scan guarded fusion had 122 wins and 52 losses on that partition.

## Where retrieval changed

For example, on SQuAD dev, BGE float RRF recovered the passage about the original meaning of “Norman” (`article-2/2`, `a2p2`) and lost the passage naming the duke at Hastings (`article-2/1`, `a2p1`) against guarded BM25. On train, BGE q8 rerank recovered the Epic Records creation-year passage (`article-50/4`, `a50p4`). Potion 32M dense recovered that same source and lost the history-of-pubs passage (`article-48/1`, `a48p1`).

All five dense encoders found the synthetic rail observation (`rail-0`) that lexical BM25 missed. Guarded BM25 already found it, so this yields zero dense recoveries against the guarded comparator. Both top-20 arms for every encoder lost `rail-0` against guarded BM25 because their lexical candidate pool excluded it. Full-scan hybrid and full-list RRF retained it for this query. The synthetic groups produced zero contradiction misses for the compared arms. Six families leave substantial uncertainty about generalization.
## New paired comparisons

Cells give complete-packet recoveries/losses and the 95% interval for the net change in percentage points against guarded BM25. The scorecards also contain the direct plain-BM25 comparison for every row.

| Model | Workload | Queries (groups) | Dense | Full-scan hybrid | Full-list RRF | Top-20 RRF | Top-20 score fusion |
| --- | --- | ---: | --- | --- | --- | --- | --- |
| bge-float | dev | 120 (12) | 15/10 [-3.3, +12.5] | 3/1 [+0.0, +4.2] | 10/2 [+1.7, +12.5] | 8/1 [+2.5, +9.2] | 3/1 [+0.0, +4.2] |
| bge-float | scifact | 128 (16) | 5/0 [+0.0, +9.1] | 3/0 [+0.0, +6.9] | 3/0 [+0.0, +6.5] | 2/0 [+0.0, +4.2] | 3/0 [+0.0, +6.9] |
| bge-float | semantic | 6 (6) | 0/0 [+0.0, +0.0] | 0/0 [+0.0, +0.0] | 0/0 [+0.0, +0.0] | 0/1 [-50.0, +0.0] | 0/1 [-50.0, +0.0] |
| bge-float | train | 120 (12) | 12/9 [-4.2, +9.2] | 3/0 [+0.0, +5.8] | 7/3 [-1.7, +9.2] | 7/1 [+0.8, +9.2] | 3/0 [+0.0, +5.8] |
| bge-q8 | dev | 120 (12) | 14/9 [-2.5, +12.5] | 3/1 [+0.0, +4.2] | 10/3 [+0.0, +11.7] | 8/1 [+1.7, +10.0] | 3/1 [+0.0, +4.2] |
| bge-q8 | scifact | 128 (16) | 5/0 [+0.0, +9.1] | 3/0 [+0.0, +6.9] | 3/0 [+0.0, +6.5] | 2/0 [+0.0, +4.2] | 3/0 [+0.0, +6.9] |
| bge-q8 | semantic | 6 (6) | 0/0 [+0.0, +0.0] | 0/0 [+0.0, +0.0] | 0/0 [+0.0, +0.0] | 0/1 [-50.0, +0.0] | 0/1 [-50.0, +0.0] |
| bge-q8 | train | 120 (12) | 14/8 [-0.8, +10.8] | 3/0 [+0.0, +5.8] | 9/2 [+1.7, +10.8] | 7/0 [+2.5, +9.2] | 3/0 [+0.0, +5.8] |
| minilm-l3-q8 | dev | 120 (12) | 14/18 [-13.3, +5.8] | 6/1 [+0.8, +8.3] | 7/5 [-3.3, +6.7] | 4/3 [-2.5, +5.0] | 6/1 [+0.8, +8.3] |
| minilm-l3-q8 | scifact | 128 (16) | 5/1 [-0.9, +8.5] | 7/0 [+1.4, +11.5] | 2/0 [+0.0, +4.2] | 2/0 [+0.0, +4.2] | 5/0 [+0.0, +9.6] |
| minilm-l3-q8 | semantic | 6 (6) | 0/0 [+0.0, +0.0] | 0/1 [-50.0, +0.0] | 0/0 [+0.0, +0.0] | 0/1 [-50.0, +0.0] | 0/1 [-50.0, +0.0] |
| minilm-l3-q8 | train | 120 (12) | 11/12 [-10.8, +9.2] | 4/1 [+0.0, +6.7] | 6/3 [-3.3, +7.5] | 5/1 [+0.0, +6.7] | 4/1 [+0.0, +6.7] |
| potion-base-8m | semantic | 6 (6) | 0/0 [+0.0, +0.0] | 0/1 [-50.0, +0.0] | 0/0 [+0.0, +0.0] | 0/1 [-50.0, +0.0] | 0/1 [-50.0, +0.0] |
| potion-retrieval-32m | dev | 120 (12) | 6/21 [-20.0, -5.8] | 2/0 [+0.0, +4.2] | 3/8 [-9.2, +0.0] | 2/5 [-6.7, +0.8] | 2/0 [+0.0, +4.2] |
| potion-retrieval-32m | scifact | 128 (16) | 5/2 [-2.4, +7.9] | 5/0 [+0.0, +9.6] | 3/0 [+0.0, +6.5] | 2/0 [+0.0, +4.2] | 5/0 [+0.0, +9.6] |
| potion-retrieval-32m | semantic | 6 (6) | 0/0 [+0.0, +0.0] | 0/1 [-50.0, +0.0] | 0/0 [+0.0, +0.0] | 0/1 [-50.0, +0.0] | 0/1 [-50.0, +0.0] |
| potion-retrieval-32m | train | 120 (12) | 8/21 [-22.5, -0.8] | 4/2 [-1.7, +5.8] | 6/7 [-5.8, +5.0] | 6/5 [-5.0, +6.7] | 4/2 [-1.7, +5.8] |

## Operating costs

This is warm replay p95 on the same job, with one timed repeat per query after the identical first packet. Whole-process peak RSS includes the interpreter, corpus parsing and all arms on that job. This is no substitute for isolated serving RSS. Costs are reported separately from evidence quality.

| Model | Workload | Guarded p95 ms | Dense p95 ms | Full-scan hybrid p95 ms | Top-20 fusion p95 ms | Whole-process peak MiB |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| bge-float | dev | 11.11 | 22.80 | 35.11 | 19.67 | 351.4 |
| bge-float | scifact | 34.38 | 49.30 | 86.80 | 38.43 | 420.2 |
| bge-float | semantic | 0.94 | 7.55 | 8.67 | 7.25 | 295.1 |
| bge-float | train | 9.06 | 20.77 | 31.73 | 18.97 | 303.0 |
| bge-q8 | dev | 16.04 | 22.87 | 37.77 | 17.71 | 202.8 |
| bge-q8 | scifact | 62.66 | 74.71 | 130.38 | 55.09 | 274.6 |
| bge-q8 | semantic | 1.14 | 4.04 | 4.70 | 4.04 | 150.3 |
| bge-q8 | train | 14.06 | 21.53 | 33.60 | 17.01 | 199.4 |
| minilm-l3-q8 | dev | 17.10 | 21.68 | 36.71 | 15.60 | 170.3 |
| minilm-l3-q8 | scifact | 34.59 | 37.44 | 74.69 | 25.75 | 252.5 |
| minilm-l3-q8 | semantic | 0.90 | 1.66 | 2.42 | 1.68 | 118.6 |
| minilm-l3-q8 | train | 8.07 | 10.57 | 18.56 | 7.62 | 169.9 |
| potion-base-8m | semantic | 1.35 | 1.62 | 2.65 | 1.02 | 45.7 |
| potion-retrieval-32m | dev | 8.65 | 11.53 | 23.00 | 7.69 | 101.0 |
| potion-retrieval-32m | scifact | 33.45 | 41.39 | 87.03 | 24.51 | 140.3 |
| potion-retrieval-32m | semantic | 1.58 | 2.11 | 3.52 | 2.76 | 98.0 |
| potion-retrieval-32m | train | 7.70 | 10.76 | 20.87 | 7.19 | 141.9 |

The matched historical cost gates were ≤5 ms added p95 and ≤2× peak RSS. Potion 8M top-20 score fusion added +0.412/+0.320 ms on dev/train and used 1.660×/1.649× RSS. Potion 32M rerank added +0.803/+0.748 ms but used 3.702×/3.673× RSS. Quantized BGE one-thread added +3.731/+3.608 ms at 6.652×/6.469× RSS. Float BGE one-thread added +16.010/+14.888 ms at 12.169×/11.919×. One-thread MiniLM added +2.014/+2.111 ms at 5.379×/5.290×. The separate [#114 artifact](https://github.com/baileyrd/Adaptive-Autonomous-Memory-Subsystem/actions/runs/45316528563/artifacts/14885279331) reports process-cold first requests and isolated model/build/serve peaks for MiniLM. These are within-run comparisons on distinct historical hosts. Do not subtract RSS across hosts or infer deployment costs from the current replay.

## Scope, time and provenance

All 17 hosted jobs completed. Across 1,502 candidate-query pairs and 10,514 audited packets, the evaluator recorded zero scope, time, or provenance violations. Every new scored packet was checked against the fixture’s independently constructed in-scope evidence set at the recorded-time cutoff. Native provenance fields include the payload digest, source actor, source locator, producer, and both timestamps. Dense, full-list RRF, and both top-20 arms emit ID-only citations. Their ranks use the existing scope/version-specific vector index and source-digest join to eligible canonical citations. The frozen evaluator compared any native provenance fields present and rejected partial citations, but an ID-only native citation could bypass the completeness check. The corrected evaluator requires full provenance explicitly for every native arm. The archived rank lists contain IDs, so they cannot independently establish native field completeness. The paired audit checked the research arms’ IDs against the independent allowlist. It could not compare wire provenance fields those packets do not carry. The synthetic same-ID cross-scope decoy has a different source and payload, and future rows are scored as invalid if returned. The harness uses disposable stores and has no model actor, tool execution, or canonical promotion path. Model-level instruction following, separate valid-time coverage and statistical bounds on leakage remain unmeasured here.

#112 reported no scope/time leaks on its public workloads and no contradiction regressions on v0.6. Its published aggregates cannot establish the newer per-citation provenance check. Scope and time checks in this PR describe the tested paths and decoys only.

## Replay

The pinned artifact preparation and dataset URLs are in [the workflow](../../.github/workflows/heldout-evidence.yml). The evidence run used the historical trigger at the frozen SHA. The workflow now requires manual dispatch so a report edit will not rerun the comparisons. To replay one cell locally, fetch the pinned inputs first, then run a command such as:

```sh
export PYTHONPATH=src
export PYTHONHASHSEED=0
python -m pip install onnxruntime==1.32.0 tokenizers==0.23.3 numpy==2.5.3
python scripts/prepare_onnx_variant.py bge-q8 /tmp/aams-bge-q8
python scripts/evaluate_heldout.py train bge-q8 --dataset /path/to/train-v1.1.json --model /tmp/aams-bge-q8
python scripts/evaluate_heldout.py semantic baseline
python -m unittest discover -s tests -p test_heldout_evidence.py -v
```

The exact result JSON hashes identify the archived bytes. Replay latency, RSS and runner metadata vary with hardware and process state. Compare selection hashes, ranked evidence IDs, counts and intervals when replaying quality. The local SQuAD train and synthetic baseline packets also matched the hosted BM25 and guarded BM25 packets exactly. Local verification passed 260 tests, the MCP acceptance demo, format, lint, compile and whitespace checks.
## Recommendation

Prioritize one **offline model-level trial of Potion 8M top-20 score fusion** against guarded BM25 on fresh decision tasks. Its archived net gains recur across public workloads, and it passed the matched cost gate. The synthetic rail loss makes it important to include cases where guarded BM25 already finds decisive evidence. Freeze the actor and task protocol, and score whether its decisions are correct and supported by the delivered sources.

Keep the ONNX candidates and Potion 32M at the retrieval-research stage. Preserve their recovered cases and regressions for future study. The live default remains BM25. The startup-recall study remains parked.
