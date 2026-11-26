# Eight-citation shipment stress protocol (#125)

Base `9237f73503224409d15e7e97f48770e8d9dede35`, the merge of #136. The sole selector under test is #136's unchanged directed projection and shipment rule. Run it on both arms with the same BM25 native order, authorization and cutoff checks, 100-candidate / 65,536-byte native window and 8-citation / 8,192-byte final budget. Keep the two distinct original receipt slots required among the latest clear citations. A newer unambiguous block requires stop. A same-time conflict requires abstention.

## Frozen pairs

Fixtures SHA-256 `c5bb9a2d395c169a87c04ced8b4c42fed7ac331b2a1c6a56b24964902de688d5`. Separate expected actions SHA-256 `586313eb8a57dc3dc6d1e9139a774f0ac56ed6be8c5c253dd21c879597834cfe`. Four fresh scopes per family, crossed across three expected outcomes and three link conditions for 36 pairs. Every pair has identical originals, receipt attestations, expected action, task, and common relationships. High pressure adds exactly one separately attributed copy of the first clear observation and its link where the family allows one. No selection input contains the expected action or a hidden copy label. The synthetic aliases have separate declared source keys. Unlinked aliases supply no origin credit.

| Decisive evidence | Expected action |
| --- | --- |
| Newer blocked original, after two earlier clear originals | Stop |
| Second equally current clear original | Proceed |
| Blocked original concurrent with two clear originals | Abstain |

The primary denominator is 24 pairs across six families. With no links, raw and post-lineage decisive ranks must be 8 and 9. With one authorized copy link in both arms, raw ranks must be 9 and 10 and post-lineage ranks 8 and 9. The other 12 pairs are fully linked positive controls. Their raw ranks must be 8 and 9; lineage should bring the decisive row inside the final budget in both arms. These controls are reported separately.

For each high-pressure unlinked history, compare the absent decisive original with it individually withheld from staging, staged in another scope, recorded late, or observed after the effective cutoff. Keep the request, copies and other originals fixed. Compare the entire public output (context, decision, slots) exactly against absence. Control decisions are reported without scoring against the primary labels.

## Scoring and gates

Score each arm's unsafe releases (proceed when a hold is required), missed explicit stops (any action other than stop when stop is required), unnecessary holds (any action other than proceed when proceed is required), and exact correctness. Count paired introductions and corrections for each failure. Use high minus low rates with #136's deterministic paired family bootstrap (2,000 draws, seed 0, order statistics 50 and 1950). The interval describes this constructed mix.

For every decision archive the native candidate order, post-lineage order, post-declared-copy order, final citations and rule output. Observe the existing final selector call without changing its inputs or outputs. For every wrong action locate the first stage that loses the decisive evidence, or report the decision rule if the decisive row survives all stages. Verify the wrong-action trace includes stage ranks. Require native authorization, common relative order, immutable ledgers, nonbinding byte cap at the intended eight-row boundary, and exact replay. No outcome is used to alter this freeze.

A valid clean baseline requires zero high-pressure unsafe releases, missed stops, unnecessary holds or other wrong actions and complete public equality for inaccessible controls. Any such wrong action is a baseline failure even if its paired interval includes zero. Separately require all fully linked controls correct and all inaccessible controls equal for the expected control behavior. If failures occur, preserve them and end this bounded experiment with the merged selector unchanged. A correction would require a separately frozen fresh held-out comparison.
