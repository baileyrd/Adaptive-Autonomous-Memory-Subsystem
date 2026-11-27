# Staged evidence requests versus abstention (#128)

Base `a1fbb6fcceede72accf64dccfec12712d1c22ecc`. FR-016 / M09. This offline study uses a deterministic rule and a synthetic reviewer. It measures bounded task completion and reviewer work.

## Frozen cases and inputs

Twenty histories, four each of five mechanisms, distributed across balance, photometer, timer and caliper tasks. The decision is whether to enable an instrument for bench work in the current verification round. A matching accuracy reading of pass supports `enable`, fail supports `withhold`, and insufficient evidence requires `abstain`. The oracle action describes the synthetic instrument's current state. An abstention without evidence is safe but leaves the decision incomplete.

- Visible reading with a matching search alias.
- Missing reading with a separately supplied current meter receipt.
- Overlooked scoped reading whose record ID is known but whose lexical alias is absent.
- Missing reading with no independent receipt.
- Missing current reading with a stale independent receipt.

The source, task and inbox fixture digest is `6f98ac17738f0baf33f03d003166ec1fcd70b712ff6872af81e3502ab56f82e3`. Separate evaluator key digest is `8536fb0e0da3ba5d36dc6ca6dce9a9b3b9d17f18b3f92e23cf0dc44f2281f113`. The key and mechanism are never passed to the actor or reviewer. It records both the expected initial action and the independent substantive outcome. Inbox readings are supplied by the fixture meter before decisions and kept out of canonical evidence.

## Frozen arms and reviewer

Both arms begin with the same task and the same scoped native BM25 packet, limited to two items and 4,096 bytes. It contains an authorized task manifest specifying the exact reading ID and round. Match readings on ID, instrument, round, kind and meter producer. Baseline A takes a supported action or abstains.

When the initial action is abstain and the manifest identifies the missing observation, B also abstains and stages at most one local request. The request names the exact observation and the manifest's authorized evidence ID and digest. It describes what remains unknown and maps pass and fail to the two possible changed decisions. No request suggests a foreign source. The fixed reviewer processes each staged ticket once. Recheck its exact manifest basis in the same scope, then look up exactly the requested scoped evidence ID. If the current reading is found, hand it to the same rule as an existing local reference. Otherwise inspect the independent synthetic inbox once. Hand over only a matching current, authorized meter reading. A stale or absent receipt closes the ticket without a handoff. Review does not contact anyone, acquire data, write a belief or ingest feedback. The temporary ledger must be unchanged.

## Frozen scores and stopping rule

Report one paired decision per history after the optional review. A substantive action is correct only when it matches the external key and has a valid supporting receipt. Count incomplete abstentions and incorrect substantive actions separately. Gains are A incomplete or wrong and B supported correct. Regressions are the reverse. Report unchanged actions and any unsupported actions. Count uncertainty resolved when a valid scoped reading becomes available for an initially abstaining task. Separate newly supplied receipts from recovered overlooked ones.

A request is unnecessary if its requested current reading was already available via authorized exact lookup. Report also requests with no useful handoff and their reasons. Report reviewer workload as tickets handled, manifest checks, exact observation lookups and inbox checks, with no time or monetary assumptions. A useful novel result requires resolution from a current independent receipt and improved action. An overlooked reading may improve the task while the request itself remains unnecessary.

For each of the eight missing-delivered and missing-unavailable histories, replay the same task, scoped inputs and inbox in a separate ledger with the exact observation ID present only in another scope. Compare the complete caller-visible initial and final response for each arm and the remembered authorized packet. Verify scoped lookup misses and that the foreign record really exists under its own grant. Keep shadow runs outside primary counts. Invalidate the trial on disclosure, ledger change, a frozen-key/input mismatch, or an unsupported substantive action. Report the result including negative or mixed findings, repeat for exact replay, and stop. No production behavior, canonical promotions, autonomous experiments or external messages.
