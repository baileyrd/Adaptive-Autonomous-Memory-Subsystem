# Host-delivered AAMS recall on the frozen coding task

**Startup delivery worked. The model still failed the task. Recommend parking this workflow for this model and task.** The control attempted to replace the identity return with itself. The AAMS arm wrote `return value.strip(chr(160))`, which targets NBSP instead of ASCII space and tab.

| Frozen score | A, empty startup packet | B, authorized startup packet |
| --- | --- | --- |
| Resume the intended edit | No. No resulting diff. | No. The diff strips NBSP instead of ASCII edge padding. |
| Avoid the documented NBSP mistake | Unobserved. No changed expression. | Unobserved by the frozen evaluator, which cannot interpret a nested `chr` call. |
| Cite received evidence that supports the action | No. Cited the placeholder `evidence-id`. | No. Cited real `trial-strip` and `decision-ascii` records but acted contrary to both. It did not cite the open question. |

**Separate behavioral check:** An independently typed equivalent of the B expression applied to the prior input `'\u00a0Oak\u00a0'` returned `'Oak'` rather than preserving the input. This checks the observed edit without executing model-written code or changing the frozen score. The treatment improved citation identity and changed the edit, but did not improve any frozen endpoint. Its cited evidence specifically says to preserve NBSP and trim ASCII space and tab.

Both agents invoked optional recall in this follow-up. A received the same empty result and B received the same authorized packet again. Because B saw the memory at startup and again on demand, the pair cannot separate the effect of startup presentation from repeated availability. It does establish that the relevant memory reached B before any action. No additional pair ran.

## Delivery, isolation and evidence

The [pre-inference delivery record](startup-recall-delivery.json) preserves the exact first inputs, CLI prompt arguments, packet content, IDs, and input, packet and token-array hashes. Its SHA-256 is `c8762169424fa4ba01c5426c4b3dd2c0870d17eb93ac07108076738daeeb33b5`. The pinned tokenizer and runtime both counted **217 A tokens** and **689 B tokens** on the first input. The startup payload is the only difference between the paired first inputs. A received an empty packet and had no ledger capability. B received scoped `decision-ascii`, `trial-strip`, `display-contract`, and `open-linebreak` plus approved `lesson-strip`. Canonical source bytes and digests matched and a foreign grant could read neither the evidence nor the lesson. The ledger remained unchanged.

The [raw trace](startup-recall-traces.json) preserves every tool call, actual CLI prompt, runtime token count and resulting diff, including the empty control diff. SHA-256 is `64a2ec050b77a31b06b8f288f08e21fa8036d3f7f7e08314f8cddf5a1d8cce2f`. An archive check independently confirmed that the first prompt differed only by packet, the supplied packet matched the recorded bytes, actual evaluation lengths matched tokenizer counts, and raw outputs matched the parsed tool calls. Both arms used #150's identical interrupted Git tree. The [frozen protocol](startup-recall-protocol.md) and runner were committed at `3273347` before inference. The original #150 protocol, runner and archive are unchanged.

All 252 local unit tests and the MCP demo passed, along with format and lint checks and compilation of the follow-up runner. No production behavior changed.

## Reproduce the setup

Use the [pinned Qwen and llama.cpp artifacts](shipment-actor-results.md#exact-replay) in a clone containing the original base commit. The tokenizer is included in the same llama.cpp ZIP. The command below runs a new pair. The historical traces are preserved separately.

```sh
PYTHONPATH=src python scripts/evaluate_startup_recall.py \
  --cli /tmp/aams-actor-artifacts/build/bin/llama-cli \
  --tokenizer /tmp/aams-actor-artifacts/build/bin/llama-tokenize \
  --model /tmp/aams-actor-artifacts/model.gguf \
  --delivery-out /tmp/aams-startup-delivery.json > /tmp/aams-startup-followup.json
```
