# Two-inspection shipment release results

The directed candidate eliminated all 12 unnecessary holds on 32 held-out histories. Both selectors made zero unsafe releases, so there were zero unsafe releases corrected and zero introduced. Correct decisions rose from 20/32 to 32/32. The candidate passed both frozen gates on this synthetic mix. Production behavior was untouched.

| Shipment outcome | Merged #135 selector | Directed candidate |
| --- | ---: | ---: |
| Exact decisions correct | 20/32 | 32/32 |
| Unsafe releases | 0 | 0 |
| Unnecessary holds | 12 | 0 |
| All abstentions | 32 | 20 |
| Explicit stops | 0 | 0 |
| Correct-to-incorrect transitions | | 0 |

The paired correctness change was **+37.5 percentage points**, with a family-bootstrap 95% interval of **[+12.5, +75] pp**. The unnecessary hold change was **−37.5 pp [−75, −12.5]**. The observed unsafe release difference was **0 pp [0, 0]**. Resampling these histories cannot estimate the chance of an unsafe release outside this fixture mix.

## What the selectors preserved

Each family has four histories. Every decision in each family followed the pattern shown.

| History | Expected | A → B | Originals retained, A → B |
| --- | --- | --- | --- |
| Two originals cited together | Proceed | Abstain → proceed | 2 → 8 of 8 |
| Copies of a two-original report | Proceed | Abstain → proceed | 2 → 8 of 8 |
| Overlapping pairs of originals | Proceed | Abstain → proceed | 0 → 12 of 12 |
| Copies of one inspection | Abstain | Abstain → abstain | 2 → 4 of 4 |
| Conflicting observations | Abstain | Abstain → abstain | 2 → 8 of 8 |
| Missing links | Abstain | Abstain → abstain | 4 → 4 of 4 |
| Partial links | Abstain | Abstain → abstain | 2 → 4 of 4 |
| Unknown originals | Abstain | Abstain → abstain | 0 → 0 |

In the 12 release-eligible histories the candidate retained all 28 original citations. In each single-inspection history it retained exactly one row, the original. The merged selector also reduced those copy sets to one row, selecting a copy in two report-first histories. Both arms flagged all four same-time conflicts. Missing, partial and unknown provenance never supplied additional quorum credit. These cases use explicitly granted original receipts from a simulated registry. They do not measure acquisition or verification of those receipts. The fixture families contain no gold explicit-stop decisions. A toy unit test verifies that an unambiguous newer blocking assertion triggers an explicit stop.

Every one of the 24 unavailable overlays matched the absent-link public response in each arm, including all four denied-grant checks. Equality covers the entire selected context, decision and cited original slots. The visible overlays changed the response in both arms, so the control could distinguish a link that reached the selector. The common pool was complete and both selectors retained native order. The logical ledger digest was identical before and after evaluation.

## Replay

[Per-case outcomes and control response hashes](quorum-lineage-replay.json) include expected actions, common candidate order, selected IDs, latest receipt slots and original retention. The [protocol](quorum-lineage-protocol.md) and fixture semantics were frozen in `0b92ea631a3f76366b1dbbe89e5fddc221a2737b`. The evaluator and toy tests were frozen in `a5fd86c407c1e2a36679c63d00f0e91c41fdc6af` before the first score. Both runs on Python 3.12.14 and SQLite 3.53.1 produced JSON SHA-256 `be55d0877e08d18ff02aa50f0bd94a2df49ca1707b71533fd0969b196c1f3032`.

Run from the repository root on the PR branch:

```sh
python -m venv /tmp/aams-quorum-venv
. /tmp/aams-quorum-venv/bin/activate
python -m pip install '.[mcp]' ruff==0.14.6
PYTHONPATH=src python scripts/evaluate_quorum_lineage.py > /tmp/aams-quorum-replay.json
cmp docs/audit/quorum-lineage-replay.json /tmp/aams-quorum-replay.json
sha256sum /tmp/aams-quorum-replay.json
ruff format --check src tests scripts
ruff check src tests scripts
python -m compileall -q src tests scripts
PYTHONPATH=src python -m unittest discover -s tests -v
python -m aams.demo
```

**Next action:** Freeze and run a fresh stress test in which copies can crowd out a newer blocking observation or one of the original receipts at the final citation budget.
