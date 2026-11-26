# Why Gemma abstained in the shipment diagnostic (#125, #105)

**Verified current facts did not rescue a single action or supported decision.** The unchanged #140 Gemma configuration abstained in all six full-evidence trials and all six verified-facts trials. Each arm scored **2/6 correct actions and 0/6 supported correct**, with two missed explicit stops, two unnecessary holds, and zero unsafe releases. Both exact actions were conflict abstentions that cited one side only.

| Case | Required | A full evidence | B extraction | C verified facts |
| --- | --- | --- | --- | --- |
| d01 | Release | Abstain, R2 | Dropped current unreceipted R3 | Abstain, R4. Cited only one of two distinct clear originals. |
| d02 | Stop | Abstain, R2 | Dropped current unreceipted R2 | Abstain, R2 and R4. Both citations actually show current blocks. |
| d03 | Conflict abstention | Abstain, R2 | Incomplete JSON | Abstain, R2. Omitted the current clear side. |
| d04 | Release | Abstain, R1 | Exact, including the repeated receipt slot | Abstain, R3. Cited only one of two distinct clear originals. |
| d05 | Stop | Abstain, R3 | Included a stale clear state and two stale slots | Abstain, R3. The cited record actually shows a current block. |
| d06 | Conflict abstention | Abstain, R3 | Incomplete JSON | Abstain, R3. Omitted the current blocked side. |

In B, **1/6** extractions were exact and **4/6** were valid JSON of the requested shape. Among the four valid outputs, missing entries were **0 states, 0 slots and 2 row tuples**. Invented entries were **1 state, 2 slots and 0 row tuples**. The invented values were stale facts copied into the current summary. There were no duplicate output items. Two conflict extractions ended mid-JSON under the frozen 64-token cap. Each visibly included a stale slot before truncation. Those partial values are visible in the archive and excluded from the valid-output counts. This diagnostic cannot separate extraction errors from the output cap in those two cases.

There were **zero aggregation rescues** and **four persistent abstentions on cases requiring a stop or release**, including d04, where extraction alone was already exact. The C results establish that the action and citation failures persist when aggregation is supplied for these inputs. The model declined to stop even when citing current blocks. It also failed to cite both sides of either conflict, though both were visible. The data do not uniquely separate a default action policy from difficulty coordinating action and citations in one response. Presentation and aggregation changed together, and the six cases are constructed.

**Next action:** Freeze a paired action-only diagnostic using the same verified facts and rotated legends, compared with action plus citations. This checks whether abstention persists when the model has only the action to produce.

## Evidence

The [protocol, fixtures and prompts](shipment-gemma-diagnostic-protocol.md) were frozen in `10c9f3f26abd72a1821159d908a09a24aaf6bb4a`. The runner and tests were frozen in `183a0ee215b0c81563960198d33947a63bb3d042` before inference. The [per-case archive](shipment-gemma-diagnostic-replay.json) contains the full prompts, verified facts, rotated legends, raw stdout and scores. I independently reconstructed the latest facts from A and B's displayed observations, checked their equality to the facts displayed in C, decoded the raw actions from their displayed legends, and recounted the citation and extraction scores. The archive SHA-256 is `34f1305cb2fbed42c1aa44c5a9abe6dee69a39e7fc8c4316a4ce4c6002275e8b`.

All 237 unit tests passed, including focused checks for extraction deltas and keeping both conflict sides in C. The MCP demo, format, lint and compile checks passed on Python 3.12.14. The diagnostic does not qualify the actor or open the #137/#138 comparison. Production code is unchanged.

## Replay and tests

Use the exact CPU runtime and text weights from #140. The [artifact acquisition commands](https://github.com/baileyrd/Adaptive-Autonomous-Memory-Subsystem/blob/0380e2ba868ecec7f8cedf44b386135146b3714a/docs/audit/shipment-gemma-results.md#exact-replay) place them in `/tmp/aams-gemma-artifacts`. The runner checks their hashes along with the frozen prompts and grammars. Run the following from the repository root after acquisition. Inference uses no network.

```sh
PYTHONPATH=src python scripts/evaluate_gemma_evidence_diagnostic.py \
  --cli /tmp/aams-gemma-artifacts/build/bin/llama-cli \
  --model /tmp/aams-gemma-artifacts/model.gguf > /tmp/aams-gemma-diagnostic-replay.json
cmp docs/audit/shipment-gemma-diagnostic-replay.json /tmp/aams-gemma-diagnostic-replay.json
sha256sum /tmp/aams-gemma-diagnostic-replay.json
```

```sh
python -m pip install '.[mcp]' ruff==0.14.6
ruff format --check src scripts tests
ruff check src scripts tests
python -m compileall -q src scripts tests
PYTHONPATH=src python -m unittest discover -s tests -v
python -m aams.demo
```
