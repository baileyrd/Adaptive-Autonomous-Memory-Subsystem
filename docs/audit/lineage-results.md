# Can explicit report ancestry change a release decision?

**Visible links corrected eight unsafe releases in 32 paired shipment histories.** The link-aware arm retained all 18 genuine independent observations across the four corroboration controls, all of which had no lineage links. Correct decisions rose from 16/32 to 24/32. No previously correct action regressed, 24 actions tied, and eight unsafe releases remained. The gain was confined to fully linked aliases and multi-hop copies. The preregistered overall-benefit criterion was **not met**: the eight-family paired bootstrap interval for correctness was **[0, +62.5] percentage points**, with an observed difference of +25 points. The unsafe-rate difference was −25 points, interval [−62.5, 0]. These intervals describe the constructed family mix.

| Held-out family (four histories each) | Correct A → B | Unsafe A → B | Source groups A → B, summed | What reached the decision |
|---|---:|---:|---:|---|
| Aliased copies | 0 → 4 | 4 → 0 | 32 → 8 | One clear representative and the newer blocked inspection |
| Multi-hop copies | 0 → 4 | 4 → 0 | 32 → 8 | Authorized chains also freed a slot for the blocker |
| Independent agreement (unlinked) | 4 → 4 | 0 → 0 | 18 → 18 | Both arms kept 3, 4, 5 and 6 distinct simulator acquisitions |
| Unknown origins | 4 → 4 | 0 → 0 | 32 → 32 | Both proceeded on clear evidence; independence was unverified |
| Same-origin dispute | 4 → 4 | 0 → 0 | 22 → 4 | Both retained clear and blocked assertions and abstained |
| Partial links | 0 → 0 | 4 → 4 | 32 → 32 | Enough unlinked copies remained to exclude the blocker |
| Missing links | 0 → 0 | 4 → 4 | 32 → 32 | Same original selection and unsafe release |
| Revoked grant | 4 → 4 | 0 → 0 | 0 → 0 | Empty candidate pool and context; abstained |

**How the decision changed.** For task `63af315752cc32`, native recall returned 11 candidates in both arms. The frozen #122 D selector used all eight slots for `a00` through `a07`, each reporting clear on day 2, and the rule chose proceed. With the explicit links, the selector delivered `a00` and `z`. The latter was a separate, day-5 blocked inspection. The same latest-observation rule chose stop. The agent never saw the links or voted on source counts. The dispute family illustrates the opposite result: grouping reduced the source proxy, but the correct abstention stayed the same. [Full candidate order, delivered citations, actions and oracle scores](lineage-rows.jsonl)

**Source independence.** The summed group proxy fell from 200 to 134. On fully attributed contexts the excess above simulator origins fell from 130 to 56. Both arms made **zero unsupported independence assertions**: neither interface certifies an independent pair. Each arm returned 32 unknown-origin rows, excluded from the proxy-excess calculation. The 18/18 retention result covers unlinked independent acquisitions only. The sidecars were explicitly supplied and accurate in these fixtures. They do not establish the accuracy or authority of real-world lineage, and false links between genuinely independent observations were outside this protocol.

**Authorization.** The common experiment host withheld the individually revoked record before staging the disposable DB. Whole-request revocation stopped recall. Traversal checked each link’s reader, grant, scope and both dates before admitting the edge, then required canonical, eligible, in-pool endpoints. On the four missing-family histories the visible overlay changed all four proceeds to stops. Nine unavailable overlays per history produced the same full public response as absent links on **36/36** comparisons, including evidence bytes, counts, independence status and decision. The unavailable variants covered private/foreign/late/premature links and paths through foreign, late, premature, revoked and nonexistent endpoints. Endpoint and link permission checks were also exercised independently in toy tests. These overlays are repeated controls, outside the 32 paired histories. This is a disposable host grant and sidecar experiment, with no new product authority. [Matched responses](lineage-controls.jsonl) · [Family scorecards](lineage-scorecards.json)

## Baseline and reproduction

The source baseline was main `8a834f375fd4e20fa5ec2d8238185b47e834e270`. The #122 selector, candidate pool, rule and factorial harness matched the #122 merge. The historical replay matched all 480 archived rows after excluding elapsed time. Both the alias and derived families retained eight unsafe actions out of twelve, with excess groups of 84 in each. The independent family had 12/12 correct. Arm D used the native structured window of 100 citations / 65536 bytes, deduplicated by declared actor, locator, digest and observation time, and delivered at most eight citations / 8192 bytes. The new paired experiment preserved native ranking and those budgets. Baseline parity was checked per case. No model ran and #124's failed qualification and stop remain historical results.

The [design and fixture registration](https://github.com/baileyrd/Adaptive-Autonomous-Memory-Subsystem/issues/125#issuecomment-7172487915) preceded the [executable/test freeze](https://github.com/baileyrd/Adaptive-Autonomous-Memory-Subsystem/issues/125#issuecomment-7172535069). The [protocol](lineage-protocol.md) contains the historical source pins, fixture/key hashes, pass rule and analysis. Frozen SHA-256 values for the new sources:

| Source | SHA-256 |
|---|---|
| lineage_cases.py | `47d6567b7802dc1e96c3ef1e0b98dad08aa49f7a65f21c39e9525333302f6b05` |
| lineage_selector.py | `9f6d3c1d625024e727d99a4e20cf3d76cc669a9f873d0980ecd6042078defad7` |
| evaluate_lineage.py | `6c145802af1788faa01c2b736a3988aa672229ff6726d7b9e6b1c6a57dbf30e3` |
| test_lineage.py | `c1c4f96f03b2d940cc2fb38d510a252852cfd9a341c9de4d6cf39c43b0018034` |

Runs used Python 3.12.14, SQLite 3.53.1, Fedora WSL2. The ledger SQL dump digest before/after was `8cbf5f1d09e4e1799613471bfadf05248fcb10c32dabc91d1e158fcee29a0306`. The first two runs matched byte-for-byte; WSL temporary storage disappeared before archiving them. Two further runs from the unchanged freeze matched byte-for-byte in durable storage, with the same reported family outcomes and database digest. The published evidence is from that second pair. The complete deterministic stdout SHA-256 is `03b120cd5d24342c852e2bd528fad0c48023c5c31908ef0adcb84f204c9913a9`. The evidence test reassembles this output from the two JSONL files and scorecard, checks its hash, and independently recounts transitions and disclosure controls.

From the evidence PR checkout in Linux, with Git and Python available:

```bash
set -eu
repo=$(pwd)
scratch=$(mktemp -d)
git worktree add --detach "$scratch/freeze" 57182be18807ad8fb6dd047f9f8e8b4342876e61
cd "$scratch/freeze"
export PYTHONPATH=src:scripts
PY=/home/baileyrd/.cache/aams-124-q4-runtime/bin/python
"$PY" scripts/evaluate_selection_factorial.py > "$scratch/historical.json"
"$PY" scripts/lineage_cases.py
"$PY" -m unittest discover -s tests -p test_lineage.py -v
"$PY" scripts/evaluate_lineage.py > "$scratch/one.json"
"$PY" scripts/evaluate_lineage.py > "$scratch/two.json"
cmp "$scratch/one.json" "$scratch/two.json"
sha256sum "$scratch/one.json"
cd "$repo"
"$PY" -m unittest discover -s tests -p test_lineage_evidence.py -v
```

One next action is independent review of the frozen traces, especially the four partial-link failures and protected-path controls, before considering any separate authority or serving decision.

## Unscored multi-parent probe added after review

Two independent inspections record identical clear payloads at the same observation time. A third report cites both and repeats that payload. Both supplied links accurately describe the report. With no links the frozen selector returns the two inspections and the report (three source groups). With both links visible it joins all three into one connected component, returns only the first inspection and reports one group. Thus independent inspections retained fall from two to one. Both arms still choose proceed.

Connectivity through a shared child does not establish that its parents share an origin. Using a component as a single origin requires a single-origin assumption; accurate links alone do not supply it. The original 32 histories, 36 unavailable-overlay checks, scorecards and interval exclude this post-review case.

Run the [unscored probe](../../tests/test_lineage_multi_parent.py) from the repository root on Linux:

```sh
PYTHONPATH=src:scripts python -m unittest discover -s tests -p test_lineage_multi_parent.py -v
```
