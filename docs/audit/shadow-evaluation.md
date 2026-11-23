# v0.7 shadow replay protocol

The staged v0.6 artifact is fitted from its unchanged synthetic training split. Compare it against guarded serving in separate executed replay calls, using the same recorded cutoff, scope, index and top-three budget. Exercise guarded recall both with and without the native observer and compare complete responses. Observation work is excluded from the separate staged-policy arm. Missing and observational labels cannot stand in for a measured alternate mode.

Use the eight synthetic held-out tasks and 24 public human-authored SQuAD v1.1 development questions. For the public subset, take the first two questions from each of the first three paragraphs of Apollo program, Oxygen, Packet switching and Warsaw. Each question's associated paragraph is its relevant retrieval target. Add one synthetic future record and private twin per topic. Scope and observation days are artificial replay coordinates. The public benchmark tests real questions and passages, without access to any production workload.

Define useful gain as at least five percentage points of paired task satisfaction over guarded, with a strictly positive lower bound in a 2,000-resample group-bootstrap 95% interval (seed 202607). Operational fixture thresholds are identical serving packets, zero observed scope/time leaks, added p95 serving latency at most 5 ms, and at most 10% unsuccessful completed worker observations. Report skipped or pending work separately. Aggregate performance only after 20 repetitions, using one warmup. Group-bootstrap inference is descriptive on such a small corpus. Group windows, replies and training data remain separate.

## Reproduce and interpret

```sh
PYTHONPATH=src python scripts/evaluate_shadow.py --repetitions 20
curl -fL https://raw.githubusercontent.com/rajpurkar/SQuAD-explorer/eee5fdbf62f8613a7812b03419e6b29617b74fd1/dataset/dev-v1.1.json -o squad-dev-v1.1.json
PYTHONPATH=src python scripts/evaluate_shadow.py --squad squad-dev-v1.1.json --repetitions 20
```

The evaluator validates dataset SHA-256 `95aa6a52d5d6a735563366753ca50492a658031da74f301ac5238b03966972c9` before processing and uses temporary SQLite state only. Public workload attribution: Pranav Rajpurkar, Jian Zhang, Konstantin Lopyrev and Percy Liang, *SQuAD: 100,000+ Questions for Machine Comprehension of Text* (2016). The development set derives from Wikipedia passages and is distributed under CC BY-SA 4.0. [Dataset](https://rajpurkar.github.io/SQuAD-explorer/) · [License](https://creativecommons.org/licenses/by-sa/4.0/)

Observed on Linux x86-64 with Python 3.12.14, byte-bucket fixture encoder and training manifest `9c7a7099afba6a6fba18da939eff90e3754f4fd66efc1add7286cb485fdc0a10`.

| Workload | Tasks guarded / staged | nDCG guarded / staged | Recall@3 guarded / staged | Controlled alternate modes | Added serving p95 | Peak RSS |
| --- | --- | --- | --- | ---: | ---: | ---: |
| Synthetic | 7/8 / 7/8 | 0.8914 / 0.8914 | 0.9375 / 0.9375 | 0 | 0.026 ms | 17,280 KiB |
| Public SQuAD | 24/24 / 24/24 | 0.9692 / 0.9539 | 1.0000 / 1.0000 | 24 | 0.712 ms | 42,752 KiB |

Guarded versus guarded-with-observer p95 was 1.605 versus 1.631 ms on synthetic and 1.737 versus 2.449 ms on public. Complete serving packet digests matched in both workloads. Zero scope or time disclosures and zero required contradiction regressions were observed. The worker completed 168/168 and 504/504 offered observations with zero failures in this run. Injected errors, delayed output and capacity are tested separately.

Paired utility difference was zero on both workloads. The empirical group-bootstrap interval was [0, 0] in both cases because every observed binary pair tied. It does not establish equivalence beyond the fixture. Synthetic rows had no alternate-mode comparison. In the public workload all 24 staged recommendations took lexical while guarded took hybrid. The staged rule's useful-gain criterion failed on both workloads.

The fraction of opted-in short queries moved from 100% in training and synthetic holdout to 0% in the public replay. For matched lexical/hybrid actions, the synthetic gain bin predicted 0.75, observed 0.75 and had Brier 0.1875. The public unknown bin used the neutral 0.50 estimate, observed zero gain and had Brier 0.25. This is a contrast in workload composition and calibration, rather than proof about production drift. The public task measures paragraph retrieval at a top-three budget, not answer generation or live user outcomes.
