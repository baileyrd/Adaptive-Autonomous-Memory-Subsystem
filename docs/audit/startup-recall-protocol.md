# Frozen startup-recall follow-up to #150

From main `e044b66ad305b03069d70ce20bd6a0b74935b9d6`. #150 tested optional recall. Both agents skipped it, changed the formatter to capitalization, and cited an unavailable placeholder. This follow-up changes delivery only and preserves #150's protocol, executable and archive.

## Paired inputs and stopping rule

Reuse the exact [#150 checkout, handoff, tools and scoring](interrupted-coding-pilot-protocol.md). Restore Git tree `03e1671913f470eff503848bfa31a13dec9b2914` in two clean disposable copies. Prepare and scope the same AAMS memory using the native source, candidate and review interfaces. Run A then B in fresh model sessions with up to four turns each. Stop at the first edit attempt, stop call, unparseable response or budget exhaustion. Run one pair, with no retries for agent behavior and no post-result prompt changes.

Both arms use the same Qwen2.5-3B-Instruct Q4_K_M weights, llama.cpp b6500 CLI, decoding flags, grammar and original instructions. The host provides a packet in the initial user turn directly after “Resume the pending edit.” A receives `{"items":[]}`, and B receives the exact result of #150's verified scoped recall. That initial turn stays in the session history. The optional recall tool remains available under the same arm-specific grants as #150. The evaluator and other workspace files are outside the bounded tool interface.

## Delivery gate

Before either model call, confirm the pinned original trace and runner, the shared clean tree and failed NBSP probe, and the exact authorized source bytes, IDs and digests. Verify the approved lesson with its two source links and check that a foreign scope cannot read the sources or candidate. Verify the complete first-input token arrays with the pinned model tokenizer (SHA-256 `b250c7af88c58c2f8b225139d5661dbdc431dd0ffd7f427e755e8bdc0b60aeca`), including an escape-preserving transport check. Use unchanged CLI flags. Require input length plus the 160-token allowance to fit 4,096 tokens. Save both first inputs, CLI arguments, packets, packet hashes and input/token hashes before inference. Confirm that the actual first call uses the verified argument and that the runtime reports the expected prompt evaluation length. Keep A isolated from the ledger and verify that the ledger did not change. Any delivery, scope or isolation failure prevents scoring.

## Outcome and interpretation

Use the frozen #150 scorer unchanged. For cite availability include records in the verified startup packet as well as any later recall output. Score correct next edit, avoidance of the documented NBSP mistake, and evidence support separately. Avoidance is unobserved when the edit does not exercise the relevant behavior in the frozen evaluator. Preserve each actual tool call, observed edit and diff.

If B alone makes the correct evidence-backed edit, recommend a limited startup-recall pilot. If both make the correct edit, report that the common handoff was sufficient for the edit in this pair and score their citations separately. If B still fails the edit or evidence gate, recommend parking this workflow. The result concerns one model, task and response contract.
