# Eight-citation shipment stress results (#125)

One extra copy pushed a newer blocking inspection or a second valid original out of the final context. The unchanged #136 selector went from 24/24 correct at low pressure to 0/24 at high pressure on the frozen primary pairs. All 24 action errors first lost decisive evidence at the final citation cap. The decisive row was still present after native retrieval, lineage projection and declared-copy filtering. No candidate correction was evaluated.

| Primary outcome | Low pressure | High pressure | Introduced / corrected | Paired change (95% interval), pp |
| --- | ---: | ---: | ---: | ---: |
| Unsafe releases | 0/24 | 16/24 | 16 / 0 | +66.7 [+33.3, +100] |
| Missed explicit stops | 0/24 | 8/24 | 8 / 0 | +33.3 [0, +66.7] |
| Unnecessary holds | 0/24 | 8/24 | 8 / 0 | +33.3 [0, +66.7] |
| Correct decisions | 24/24 | 0/24 | 24 lost / 0 gained | −100 [−100, −100] |

The primary denominator is the same 24 pairs for each rate. Eight histories required stop, eight required abstention for conflict, and eight allowed release. The eight missed stops are included in the 16 unsafe releases. The other eight unsafe releases followed loss of the concurrent conflicting report. All unnecessary holds were abstentions after losing the second original receipt.

| Decisive evidence | Link condition | Low → high action | Native rank, low → high | Final rank, low → high |
| --- | --- | --- | --- | --- |
| Newer blocked original | Unlinked | Stop → proceed, 4/4 | 8 → 9 | 8 → omitted |
| Newer blocked original | Partial | Stop → proceed, 4/4 | 9 → 10 | 8 → omitted |
| Second clear original | Unlinked | Proceed → abstain, 4/4 | 8 → 9 | 8 → omitted |
| Second clear original | Partial | Proceed → abstain, 4/4 | 9 → 10 | 8 → omitted |
| Concurrent blocked original | Unlinked | Abstain → proceed, 4/4 | 8 → 9 | 8 → omitted |
| Concurrent blocked original | Partial | Abstain → proceed, 4/4 | 9 → 10 | 8 → omitted |

The intervals resample six constructed families. The degenerate correctness interval reflects failure in every high-pressure family by design of this boundary stress mix. These rates describe a mechanism and give no estimate of how frequently the mechanism occurs in practice.

## Controls and frozen criteria

- **Baseline gate failed.** The decisive row had post-filter rank 8 at low pressure and 9 at high pressure. Nine eligible rows took at most 4,628 bytes, below 8,192 bytes. The two surviving clear receipts could still satisfy the unchanged quorum when newer or conflicting blocking evidence was omitted.
- **Fully linked controls passed.** Both arms were correct on all 12 matched pairs. The selector removed the resolved copies and moved the decisive row to rank two or three.
- **Inaccessible controls passed.** All 48 inaccessible comparisons matched the full absent-evidence output, including decision, context and receipt slots. Foreign, late-recorded and future-effective evidence was staged and excluded by native recall. Individual withholding models a host grant by omitting the row at staging, as in #135. It tests the host/evaluator boundary.
- Every ledger remained immutable and every final context matched the authorized native order after filtering. Two complete runs matched byte for byte.

## Exact replay and tests

[Per-case traces](citation-pressure-replay.json) record raw native order, post-lineage order, post-declared-copy order, final context, decisive ranks, decision citations and first loss for every wrong action. They also include the fully linked pairs and matched control traces. [Protocol and histories](citation-pressure-protocol.md) were frozen at `edbfd96e5c4465e79b68bc9a47af62a27b1a40bb`. The instrumented harness and two toy tests were frozen at `b810d19949ef7f0bac525b1c4cccb03a32edb8f2` before scoring. The harness delegates selection to the merged functions and verifies their source hashes.

Run from the repository root on the PR branch:

```sh
python -m venv /tmp/aams-pressure-venv
. /tmp/aams-pressure-venv/bin/activate
python -m pip install '.[mcp]' ruff==0.14.6
PYTHONPATH=src python scripts/evaluate_citation_pressure.py > /tmp/aams-pressure-replay.json
cmp docs/audit/citation-pressure-replay.json /tmp/aams-pressure-replay.json
sha256sum /tmp/aams-pressure-replay.json
ruff format --check src tests scripts
ruff check src tests scripts
python -m compileall -q src tests scripts
PYTHONPATH=src python -m unittest discover -s tests -v
python -m aams.demo
```

Replay SHA-256 is `d38730ec2596805cf4c1a688819218284b495797313fdb58df410497a132ec7e` on Python 3.12.14 and SQLite 3.53.1. Local format, lint, compile and the two focused tests passed.

**Next action:** Preregister one bounded citation-selection correction that reserves evidence for the shipment decision, then compare it with this baseline on fresh held-out histories at the same limits.
