# Interrupted coding pilot with optional AAMS recall

**Result: tied failure. Recommend revising the handoff before integration.** The real Qwen2.5-3B-Instruct agent read the fixture file in both fresh sessions and then changed `return value` to `return value.capitalize()`. It never requested memory in either arm, even though the identical instruction asked it to read the file and request memory before editing. Both diffs and raw edit choices matched. The edit addressed capitalization instead of the pending ASCII edge-padding change.

| Frozen score | A, recall disabled | B, recall enabled |
| --- | --- | --- |
| Correct next step | No | No |
| Prior NBSP mistake avoided | Unobserved by the frozen probe evaluator | Unobserved by the frozen probe evaluator |
| Cited evidence supports the action | No. Cited the unavailable placeholder `evidence-id`. | No. Cited the unavailable placeholder `evidence-id`. |

The restricted evaluator intentionally interprets only the fixture's string-stripping expressions. It did not execute either model-written capitalization expression. Consequently the NBSP score remains unobserved under the frozen rule. The observed diff was enough to reject the edit as the next step.

No AAMS memory changed the observed outcome. The separate preparation check verified that native scoped recall returned the prior ASCII-only decision, the captured failed `strip()` probe, the independent NBSP requirement, and the unresolved CR/LF question. It also verified the approved lesson and both source links. That check was separate from the resumed sessions. The recall-enabled agent never saw any of those records. This pair measures a failure to invoke optional recall. The effect of the memory contents on an actual edit remains unmeasured.

## Trace and reproduction

The [protocol and executable freeze](interrupted-coding-pilot-protocol.md) was committed at `7634fdfb8ea8da274c72a4e2dce49ea1d7e3561e`. Both arms started from Git tree `03e1671913f470eff503848bfa31a13dec9b2914`. The [archive](interrupted-coding-pilot-traces.json) contains the concrete pre-interruption failed probe, every resumed prompt, raw output, tool call and result, Git statuses and diffs, and all three scores. Archive SHA-256 is `f792470ce7aad731efbac88bd9dea6047e2105d8c1ad58bef3a8695a39550c53`. The only resumed execution was the frozen pair.

The hosted Codex CLI preflight was blocked by the workspace's network policy. An unrelated tool-call preflight succeeded with the pinned local model. The pilot used that real model as the decision-maker with a small host tool loop. It did not use a model score proxy or the prior study's deterministic action selector.

The [pinned Qwen and llama.cpp acquisition procedure](shipment-actor-results.md#exact-replay) puts the external artifacts under `/tmp/aams-actor-artifacts`. In a clone that contains the pinned base commit, the command below reproduces the pilot setup and runs a new pair. The historical trace is preserved separately.

```sh
PYTHONPATH=src python scripts/evaluate_interrupted_coding.py \
  --cli /tmp/aams-actor-artifacts/build/bin/llama-cli \
  --model /tmp/aams-actor-artifacts/model.gguf > /tmp/aams-interrupted-pilot.json
```

All 252 local tests, the MCP demo, Ruff format and lint, and compilation of the pilot runner passed. The model artifacts are external to default CI.

**Recommendation — revise:** In a separately frozen pilot, have the host supply the scoped recall result at session start, with an empty result in the control. This would test what the agent does with the memory after removing the optional retrieval step that both sessions skipped.
