# Shipment witness selection results (#125)

The candidate passed the frozen criteria. At the same eight-citation and 8,192-byte limits, reserving the latest decision evidence improved correctness from **28/48 to 48/48**. It corrected **12 unsafe releases**, including four missed explicit stops, and **eight unnecessary holds**. It introduced zero unsafe releases and lost zero correct decisions. These were constructed one-seal histories.

| Metric | Merged #137 baseline | Witness selection | Corrected / introduced | Paired change, pp (95% family interval) |
| --- | ---: | ---: | ---: | --- |
| Unsafe releases | 12 | 0 | 12 / 0 | −25.0 [−41.7, −8.3] |
| Missed explicit stops | 4 | 0 | 4 / 0 | −8.3 [−25.0, 0] |
| Unnecessary holds | 8 | 0 | 8 / 0 | −16.7 [−33.3, 0] |
| Exact decisions correct | 28 | 48 | 20 gained / 0 lost | +41.7 [+25.0, +50.0] |

Both arms were correct on all 24 low-pressure histories. Under high pressure correctness rose from 4/24 to 24/24, a paired change of +83.3 pp [50.0, 100]. Both arms stopped on all four high-pressure early-block histories, where the baseline already retained the decisive record. The intervals resample six constructed mechanisms and give no estimate of field prevalence.

## What changed

The table covers all 20 action changes. Each row represents four high-pressure histories. In each change, the citations displaced by the reserved rows were copies without receipt slots.

| Mechanism | Baseline → candidate | Evidence that entered and its effect |
| --- | --- | --- |
| Newer block | Proceed → stop | Newer blocked claim became the latest state, superseding two older clear receipts. |
| Concurrent conflict | Proceed → abstain | Blocked claim joined same-time clear claims, making the conflict visible. |
| Clear quorum | Abstain → proceed | Second current original added a distinct receipt slot. |
| Superseded block | Stop → proceed | Two newer clear receipts supplied a quorum. The older blocked claim stayed in the packet and was superseded by timestamp. |
| Stale receipt | Proceed → abstain | Newer clear receipt made the two older slots stale, leaving only one latest slot. |

[Per-case evidence](shipment-witness-replay.json) records the authorized native and post-lineage order, expected actions, receipt attestations, both packets and rule outputs, and every entered or departed citation for changed actions with its state, time and slot. Both selectors consumed the same ordered post-lineage input and preserved native relative order in the final packets. All final contexts stayed within eight citations. The largest was 4,120 bytes, so the main experiment exercised citation pressure. The focused tests include a tighter byte limit.

All 48 inaccessible-versus-absent comparisons matched the entire public response within each arm, for 96 arm comparisons. Individual withholding is modeled at staging. The other controls used out-of-scope or temporally ineligible observations. Both replays were byte identical, and ledgers remained unchanged. No production files changed.

## Exact replay

The [protocol](shipment-witness-protocol.md), candidate and fixtures were frozen at `20eb7debbd90f7f3af46913073c0faca28831101`. The harness and tests were frozen at `2784ffee8730bfbfb7565107465096c1354594f9` before scoring. The historical #137 archive reproduced with SHA-256 `d38730ec2596805cf4c1a688819218284b495797313fdb58df410497a132ec7e`. The new archive reproduced twice with SHA-256 `1dfbdc8561912c442bbaec1056863bf564c8f8f50c80d75fb1990967b4aa9cd4` on Python 3.12.14 and SQLite 3.53.1.

```sh
python -m venv /tmp/aams-witness-venv
. /tmp/aams-witness-venv/bin/activate
python -m pip install '.[mcp]' ruff==0.14.6
PYTHONPATH=src python scripts/evaluate_citation_pressure.py > /tmp/aams-witness-baseline.json
cmp docs/audit/citation-pressure-replay.json /tmp/aams-witness-baseline.json
sha256sum /tmp/aams-witness-baseline.json
PYTHONPATH=src python scripts/evaluate_shipment_witnesses.py > /tmp/aams-witness-first.json
PYTHONPATH=src python scripts/evaluate_shipment_witnesses.py > /tmp/aams-witness-repeat.json
cmp docs/audit/shipment-witness-replay.json /tmp/aams-witness-first.json
cmp /tmp/aams-witness-first.json /tmp/aams-witness-repeat.json
sha256sum /tmp/aams-witness-first.json
ruff format --check src scripts tests
ruff check src scripts tests
python -m compileall -q src scripts tests
PYTHONPATH=src python -m unittest discover -s tests -v
python -m aams.demo
```

**Next action:** Independently review the frozen result and replay the 20 changed decisions against the source observations and receipt slots.
