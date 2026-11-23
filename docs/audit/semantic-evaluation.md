# v0.4 semantic recall evaluation

The fixed synthetic corpus contains 25 records across two scopes and nine queries. It includes paraphrases, a copied origin, a contradictory pair, a historical cutoff, Spanish and English reports, irrelevant distractors and private decoys. Graded relevance and required task evidence are checked in with the fixture. Recall@3 and nDCG@3 average the eight queries with relevant records. A task is covered only when every required evidence ID appears. The private-only query contributes to the disclosure check.

## Reproduction

Run from the repository root on Linux. Separate processes isolate peak RSS per mode. Every mode performs one warmup pass and 20 measured repetitions of the same nine queries.

```sh
PYTHONPATH=src python scripts/evaluate_semantic.py lexical
PYTHONPATH=src python scripts/evaluate_semantic.py fixture
```

The optional neural run uses CPU inference from spaCy's pretrained English `tok2vec` component. It mean-pools 96-dimensional contextual token outputs. The encoder was trained for token-level tasks and is not a dedicated sentence embedder. Download and verify the official wheel before installing. The regular CI suite requires neither spaCy nor model artifacts.

```sh
wheel=en_core_web_sm-3.8.0-py3-none-any.whl
curl -fsSLo "$wheel" "https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.8.0/$wheel"
printf '%s  %s\n' 1932429db727d4bff3deed6b34cfc05df17794f4a52eeb26cf8928f7c1a0fb85 "$wheel" | sha256sum -c -
python -m pip install spacy==3.8.11 "./$wheel"
PYTHONPATH=src python scripts/evaluate_semantic.py neural
```

## Observed on Linux x86-64, Python 3.12.14

| Method | Recall@3 | nDCG@3 | Task coverage | Contradiction | Scope / historic disclosures |
| --- | ---: | ---: | ---: | ---: | ---: |
| Lexical | 0.6875 | 0.7211 | 5/8 | 1/1 | 0 / 0 |
| Byte buckets fixture | 0.7500 | 0.7976 | 6/8 | 1/1 | 0 / 0 |
| spaCy tok2vec hybrid | 0.6250 | 0.6369 | 5/8 | 1/1 | 0 / 0 |

| Method | Median / p95 wall (ms) | Median CPU (ms) | Peak RSS (KiB) | SQLite growth (bytes) | Index build (ms) |
| --- | ---: | ---: | ---: | ---: | ---: |
| Lexical | 0.907 / 1.134 | 0.906 | 16,000 | 0 | — |
| Byte buckets fixture | 1.960 / 2.364 | 1.958 | 16,512 | 8,192 | 1.649 |
| spaCy tok2vec hybrid | 3.758 / 4.323 | 3.739 | 118,568 | 24,576 | 32.412 |

The real encoder recovered an automobile paraphrase missed by lexical retrieval, but reduced aggregate quality and increased median native latency and memory on this corpus. Both encoders preserved the labeled contradiction, exposed zero private and post-cutoff records, and fell back after a new scoped record made the batch stale. Both also returned unrelated authorized results for the private-only query, demonstrating noisy similarity. The fixture encoder is a deterministic test baseline. Its small-corpus gain is not evidence of neural benefit. Retain lexical as the default. These measurements do not establish general task utility or multilingual quality.
