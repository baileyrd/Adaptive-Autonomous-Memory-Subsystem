# Literal YES/NO inspection recognition with Gemma (#125, #105)

Base is main `dcd91eb33c509c0c84d571b289d514fc458e1348`, the merge of #143. In #143 the model always selected raw B under rotated letter legends. This diagnostic uses literal answers and tests wording and evidence sensitivity separately.

## Frozen design

Use #143's Gemma 3 4B IT Q4_K_M text weights (SHA-256 `04a43a22e8d2003deda5acc262f68ec1005fa76c735a9962a8c77042a74a7d19`) and llama.cpp b6500 CPU CLI (SHA-256 `b411ede792661c7098a7bd8965ec92b062952010fecd816fd5f77b76b450631c`). Reuse the decoding flags exactly: four CPU threads, zero GPU layers, context 2,048, output cap 64, greedy temperature zero, seed 42, no conversation or warm-up. Each trial is a fresh process.

Four fresh pairs comprise eight nonempty sets of current observations. Fixture digest `de449300bf3e966d19c0b26e5c75d62bf992c79f0c6ed30b0a58a8190bc79651`. Within each matched pair, flip one checked current row from blocked to clear and preserve its time, slot, original ID, other rows and row order. Verified facts describe all current states and original slots and retain the ordered rows. Cross-check hand-checked current IDs with source timestamps before inference. Two changes create all-clear singleton sets, and two create mixed sets. Stale records are excluded from both prompts.

Ask A, “Are all current inspections blocked?” and B, “Is at least one current inspection clear?” on every observation set. The only prompt difference within a set is the question. Reply with the literal text YES or NO. Prompt SHA-256 `4a9b49083dabe79adca5433aa91c6b7ee0a40607b1258848805231e5fa74bba6`, literal grammar SHA-256 `76c38b9536d0334b07585a12295d7e4980f4ac1a1a4e239e1d8cf0afa53a1327`. Each wording has four YES and four NO keys. Counterbalance wording order within each evidence polarity and which evidence variant runs first. The prompts contain no keys or other trial outputs.

## Frozen scores and interpretation

- **Accuracy by wording.** Compare each literal answer to the truth from the verified current rows. Record other text as invalid and incorrect.
- **Wording reversal.** Count sets where two valid answers differ (out of eight). Also count cases where both are correct.
- **Evidence sensitivity.** For each wording count pairs where two valid answers differ (out of four). Also count pairs with the correct answer on both variants, separating evidence sensitivity from wrong-direction changes.

Report four evidence-blind baselines on the exact design. Always YES and always NO each have 4/8 correct per wording, 0/8 wording reversals and 0/4 evidence flips per wording. The two wording-only strategies (A always YES and B always NO, or the reverse) each have 4/8 correct per wording, 8/8 wording reversals and 0/4 evidence flips. Always answering differently to the questions can be explained by wording alone. Evidence discrimination requires correct changes to the same wording when the decisive observation flips. Report the paired results and any invalid outputs. These constructed recognition cases neither qualify Gemma nor open #137/#138 or affect production.
