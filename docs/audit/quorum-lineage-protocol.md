# Two-inspection shipment release under #125

Base `38377317cdc6e868cbca175670e4bd53547fc5fb`, the merge of #135. Its final review at `0ca4ec4` reproduced a two-parent collapse in an unscored probe. The old rule allowed release with a single clear seal observation. This follow-up gives both arms the same quorum rule.

## Frozen protocol

- Compare A, the exact merged `lineage_selector.components` and `respond` context selection, with B, directed projection with explicit original-observation receipts. A's prior one-inspection decision is discarded. Baseline module SHA-256 is `9f6d3c1d625024e727d99a4e20cf3d76cc669a9f873d0980ecd6042078defad7`.
- Use the same SQLite ledger, native BM25 candidate order, 100 candidates / 65,536 bytes and final 8 citations / 8,192 bytes. Both use the existing exact-declared-copy selector. B supplies an ordered subsequence and cannot fetch or add rows. Use the merged relation and endpoint authorization checks before any traversal, including scope, principal, grant and both time axes. Protocol validity requires candidate window completeness for these fixtures, authorized output and ledger immutability.
- Simulate a trusted inspector registry using request-scoped original receipts that explicitly attest distinct inspection slots. Both arms have the same receipts, intersected with the authorized pool. These are evaluator inputs, separate from gold actions. An arbitrary evidence identifier, locator or link conveys no inspection credit. A derived report can never stand in for an original.
- In B, original receipts terminate directed ancestry. Non-receipted rows with no visible path to an original, a visible unresolved parent, or a cyclic dependency have unknown ancestry. Unavailable edges have no effect, including on any completeness inference. The projection describes visible ancestry only. Preserve every original. Suppress a derived row when every resolved original has the identical payload digest and observation time. Otherwise deduplicate derived rows only on the same nonempty resolved root set, digest and observation time. Preserve conflicting assertions and unknown rows before the shared declared-copy filter.
- Run the existing latest-observation decision function on each selected context. Conflicting latest assertions abstain. A latest unambiguous blocked assertion stops. Proceed requires a clear latest seal and original receipts from at least two distinct inspection slots among the latest citations. Otherwise abstain. Count either stop or abstain as a hold and report them separately where applicable.

## Held-out set and analysis

Four fresh histories per family, 32 paired decisions. Fixture SHA-256 `0b3a698fcca98108cc406a7a7347ddf4a3237a437a07601cbed61d818cc1314c`. Separate labels SHA-256 `8075e22aa5c560463bd73d7bae69fddb14fcb90bf76e8164bd76261783ab4f52`. The cases vary report order and, where relevant, copy depth/count. The original receipt list evaluates retention after selection. Source IDs/scopes must be disjoint from #135.

| Family | Condition | Expected |
| --- | --- | --- |
| dual | One report cites two originals | proceed |
| nested | Copies descend from a two-original report | proceed |
| overlap | Two reports cite overlapping pairs of three originals | proceed |
| single | Many separately named copies cite one original | abstain |
| conflict | Two originals and an incompatible same-time linked assertion | abstain |
| missing | One original and unlinked copies | abstain |
| partial | One original, one traversable link and one missing endpoint | abstain |
| unknown | Clear rows without original receipts or lineage | abstain |

Primary metrics are paired action correctness, unsafe releases (proceed against hold), their corrections (unsafe to expected) and introductions, and unnecessary holds (hold against proceed). Report correct-to-incorrect transitions, then original retention and conflict/known-copy behavior. Reuse #135's paired bootstrap, 2,000 draws of whole families with replacement, seed 0, percentile indices 50 and 1950, B minus A for correctness, unsafe release and unnecessary hold rates. Intervals describe these constructed families.

Mechanism success requires B to release all 12 valid multi-parent histories with every original retained, hold all four single-origin histories with one selected original and no redundant copies, preserve the contradictory assertion and abstain in all four conflict histories, and withhold release in all missing, partial and unknown cases. The overall decision gate additionally requires fewer unnecessary holds, zero unsafe introductions or correct-to-incorrect transitions, and a strictly positive lower paired correctness bound. A zero observed unsafe rate is descriptive.

For each dual history run matched visible, absent, denied-grant, other-reader, other-scope, future-recorded, future-effective and missing-endpoint relation overlays. For each arm compare the entire public response of each unavailable variant against that arm's absent response. Every unavailable comparison must match. These repeated controls are outside primary denominators. No model, serving, schema, or authority changes.
