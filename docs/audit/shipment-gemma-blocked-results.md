# Gemma's unanimous-blocking answers and shipment actions (#125, #105)

**Gemma emitted raw B in all eight predicate sessions and abstained in all eight action sessions.** The rotated legends mapped B to YES four times and NO four times. The predicate was correct on **4/8 cases**. Its responses matched a fixed-letter strategy in every case, so the correct blocked-case answers do not establish that Gemma recognized unanimous blocking.

| Case | Current observations | Session order | Required predicate | Decoded predicate (raw B) | Required action | Chosen action |
| --- | --- | --- | --- | --- | --- | --- |
| u01 | Blocked | Predicate first | YES | NO | Stop | Abstain |
| u02 | Clear, two distinct receipts | Action first | NO | NO | Release | Abstain |
| u03 | Blocked | Action first | YES | YES | Stop | Abstain |
| u04 | Mixed | Action first | NO | YES | Abstain | Abstain |
| u05 | Blocked, repeated receipt | Action first | YES | NO | Stop | Abstain |
| u06 | Clear, duplicate plus distinct receipt | Predicate first | NO | YES | Release | Abstain |
| u07 | Blocked | Predicate first | YES | YES | Stop | Abstain |
| u08 | Mixed | Predicate first | NO | NO | Abstain | Abstain |

On the four blocked cases, **two returned a correct YES and still failed to stop**, and **two returned NO and failed to stop**. Zero stopped. The first count records observable paired answers. Given the identical raw letter across all cases, it cannot distinguish genuine recognition from agreement by the rotated mapping. Each control type produced one correct NO and one incorrect YES. The actor showed neither an always-YES nor an always-NO semantic response. It showed an always-B response.

The action arm scored **2/8 correct** because it abstained on both mixed cases. It missed all four explicit stops, held both eligible releases and made zero unsafe releases. All 16 responses were valid. The experiment does not isolate a downstream failure after verified recognition, because the direct predicate itself showed no discrimination beyond the fixed label. Results apply to this prompt, output format, configuration and eight constructed pairs.

**Next action:** Freeze a direct predicate probe that permits literal `YES` and `NO` answers, with balanced question polarity and the same verified-facts construction. Test whether answers track the facts once the letter mapping is removed.

## Evidence and checks

The [protocol and inputs](shipment-gemma-blocked-protocol.md) were committed at `0c0c858e121d543eb652925cbc809fa672726f69`. A pre-inference test identified an order-by-label imbalance in the initial schedule. Two control orders were corrected and the final fixtures, runner and tests were frozen at `8dca3dd63e3ed159b4f929681c2bda3db5de1511` before any inference.

The [archive](shipment-gemma-blocked-replay.json) preserves all 16 prompts and raw outputs, source observations, verified facts, shown legends and per-case scores. SHA-256 is `ac60f00bd5c80772ba466004e830258ec82d9f778773625d97f249fe80ec85b4`. An independent recount reconstructed each current observation from its source timestamp, checked that both sessions showed the same rows in the same order, decoded the raw label using each displayed legend, and agreed with all archived results.

All 241 unit tests and the MCP demo passed locally, along with format, lint and compile checks on Python 3.12.14. This diagnostic did not qualify Gemma or run the #137/#138 packet comparison. Production code is unchanged.

## Exact replay

Reuse the [pinned text model and CPU runtime acquisition commands](https://github.com/baileyrd/Adaptive-Autonomous-Memory-Subsystem/blob/0380e2ba868ecec7f8cedf44b386135146b3714a/docs/audit/shipment-gemma-results.md#exact-replay) from #140. They place the local artifacts in `/tmp/aams-gemma-artifacts`. Run from the repository root. The runner checks the hashes and runs inference offline.

```sh
PYTHONPATH=src python scripts/evaluate_gemma_blocked.py \
  --cli /tmp/aams-gemma-artifacts/build/bin/llama-cli \
  --model /tmp/aams-gemma-artifacts/model.gguf > /tmp/aams-gemma-blocked-replay.json
cmp docs/audit/shipment-gemma-blocked-replay.json /tmp/aams-gemma-blocked-replay.json
sha256sum /tmp/aams-gemma-blocked-replay.json
```

```sh
python -m pip install '.[mcp]' ruff==0.14.6
ruff format --check src scripts tests
ruff check src scripts tests
python -m compileall -q src scripts tests
PYTHONPATH=src python -m unittest discover -s tests -v
python -m aams.demo
```
