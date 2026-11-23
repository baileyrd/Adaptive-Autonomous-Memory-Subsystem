# AAMS v0.3 governed learning acceptance

The [v0.3 goal](https://github.com/baileyrd/Adaptive-Autonomous-Memory-Subsystem/issues/23) adds a model-neutral, staged learning workflow. The native API and fixture cover proposal, validation, review and disposition. Approved proposals remain staged. The workflow does not write canonical beliefs, alter evidence, or expose new MCP tools.

## Reproduce

Install the project and pinned MCP extra with the [README setup](../../README.md). From the repository root, run:

```sh
PYTHONPATH=src python scripts/evaluate_learning.py --repetitions 30
PYTHONPATH=src python -m unittest discover -s tests -v
python -m aams.demo
```

The evaluation uses 11 fixed synthetic records across two scopes. It compares scoped lexical recall with two result slots per query against the same recall augmented by the proposal's linked evidence. A task counts as covered when the result contains every fixture-labeled evidence ID, including any required counterexample. This measures evidence coverage for reviewer tasks. It does not measure end-user decisions or model learning.

| Measure | Observed |
| --- | --- |
| Proposal precision and recall | 2/4 and 2/3. A useful singleton was missed and two repetitive adversarial groups reached review. |
| Approval | 1 of 4 proposals was approved by a distinct fixture reviewer. The copied-origin, proposer-produced and contradicted groups were rejected. |
| False approvals and canonical promotions | Zero on the final fixture. An earlier run exposed one false approval from proposer-produced evidence with separate source labels. The regression now excludes such records. |
| Scope and restart | A new process verified candidate state, versions 1 and 2, lineage groups and the gauge refutation. It found zero candidates in the unrelated scope and zero corresponding beliefs. |
| Reviewer task coverage | Baseline 2/3, augmented 3/3. The augmented packet returned six evidence links across the tasks, compared with five in the baseline. |
| Median native time | Baseline 1.937 ms, augmented 2.421 ms and proposal scan alone 0.371 ms over 30 timed repetitions on Linux with Python 3.12.14. These are small fixture timings without MCP, model or network cost. |
| Feedback and calibration | Unit tests preserve predicted versus measured scores, revisions, replay, scoped linkage and isolation from candidate disposition. |

## Verification and limits

| Slice | Tested head | CI |
| --- | --- | --- |
| Candidate contracts | `c3070ff089012f536be7e3a5d2347c5c9fd5cae2` | [Python 3.11 and 3.12](https://github.com/baileyrd/Adaptive-Autonomous-Memory-Subsystem/actions/runs/45163180157) |
| Scoped candidate store and dispositions | `23569c4bc3316be757cb4d9585760c43b2a12ce4` | [Python 3.11 and 3.12](https://github.com/baileyrd/Adaptive-Autonomous-Memory-Subsystem/actions/runs/45164259101) |
| Proposal preview | `c957d602de4266e91f268743480bb2b49f392e7b` | [Python 3.11 and 3.12](https://github.com/baileyrd/Adaptive-Autonomous-Memory-Subsystem/actions/runs/45164536109) |
| Outcome feedback | `4832a661714b29610dcc2410d03f3038b5e1dff5` | [Python 3.11 and 3.12](https://github.com/baileyrd/Adaptive-Autonomous-Memory-Subsystem/actions/runs/45164875167) |

The coordination issue records the combined acceptance PR, tested head and final main run. The earlier [operational limits](MVP-v0.2.md) still apply. Source labels and collector identity come from the trusted local boundary. The grouping rule cannot prove external source independence or detect all disguised copies. Literal text matches and explicit counterexample markers are the only proposal signals. Larger corpora, multilingual semantics, human review agreement and real task utility remain unevaluated.

For optional neural experiments, establish a larger labeled corpus and a blinded comparison with this deterministic baseline first. Keep neural results as disposable ranking or proposal signals and repeat scope and false-approval checks before expanding use.
