# Gemma shipment action-only diagnostic (#125, #105)

Base is main `ace688b`, the merge of #141. That diagnostic found Gemma abstained even when supplied verified current facts and, in one case, when it cited two current blocked observations. Test whether the requirement to return citations changes the chosen action on equally informative verified packets.

## Frozen contrast

Use #141's Gemma 3 4B IT Q4_K_M text weights (SHA-256 `04a43a22e8d2003deda5acc262f68ec1005fa76c735a9962a8c77042a74a7d19`) and llama.cpp b6500 CLI (SHA-256 `b411ede792661c7098a7bd8965ec92b062952010fecd816fd5f77b76b450631c`). Keep the same fresh-process four-thread CPU decoding, 2,048 context, 64 output tokens, temperature zero and seed 42. Both arms use the same verified states, distinct original slots, every current row in source order, shipment decision rule, and displayed action legend. Neither receives the expected action or any derived action field.

- A asks only for an action label in a JSON object. Prompt SHA-256 `5446d87cb8a6a9bd5c1e564246030537e18c482e5eda308d20f8d59897f6e3cf`, grammar SHA-256 `2afca47e0beb0c28828b01225650b5ff9a60521b1f9bc96b08280d334d390f63`.
- B uses #141's verified-facts action and citation prompt and grammar unchanged. SHA-256 `ef92bac19c129dbbfdb4b8bd9b4e23875ca5f6cbcf005ed81221947e7ca0e33f` and `36ca434bf5406e4e89d5de0a9903d235569a7a82eaff3461b8f8badbcaf6e57f`. A removes the citation instructions and field. The decision bullets retain the same conditions for release, stop and abstain.

Six new cases with two required releases, two stops and two conflict abstentions. Source fixture SHA-256 `c9b5e610351f466a126d1fa34b927330f34406f54dbea39ed006bfcf695caac0`. Derive current facts using the manually checked latest IDs, cross-checked against actual timestamps. Distinct current clear receipts allow release, current unanimous block requires stop, and current disagreement requires abstention. Cases include stale records, duplicates, unreceipted reports and two current blocked observations. Rotate the action legend across the cases, with each correct action letter used twice. Alternate arm order so each action has one A-first and one B-first case. Run each case once per arm in isolated processes.

## Frozen analysis

Primary outcome is exact semantic action correctness, paired within case. Report every changed label and action, A-over-B gains and regressions, unsafe releases, and abstentions on required stops and releases. Distinguish malformed outcomes and incomplete JSON without a runtime end marker from valid but wrong actions. Failed formatting counts as incorrect for exact correctness. In B separately report whether the cited rows cover the required evidence and whether the emitted action is supported by those citations. Coverage uses #139 citation rules applied to the required action, including unique current rows, two distinct slots for release, a blocked observation for stop and both sides for conflict.

A gain supports an effect of the citation request and its required format within these pairs. Any change without correctness gain is reported alongside harm or no net improvement. If both arms abstain on a stop or release, record persistence despite action-only output. This bounded diagnostic cannot distinguish the citation instruction from the output format itself or establish a unique internal cause. No change to serving and no qualification or #137/#138 comparison.
