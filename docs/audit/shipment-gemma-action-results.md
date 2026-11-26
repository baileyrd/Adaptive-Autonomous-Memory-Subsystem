# Removing citations from Gemma's shipment response (#125, #105)

**Removing the citation request changed 0/6 actions.** Gemma abstained on every case in both arms. Each arm scored **2/6 exact correct**, with zero paired gains, zero regressions and zero unsafe releases. Each abstained on both required stops and both eligible releases. All 12 outputs were valid JSON of the required shape. There were no malformed or incomplete outputs.

| Case | Required action | A action only | B action and citations | B citations cover required evidence |
| --- | --- | --- | --- | --- |
| p01 | Release | Abstain (C) | Abstain (C), R2 | No. Missing the second original. |
| p02 | Stop | Abstain (A) | Abstain (A), R2 and R3 | Yes. Both are current blocked rows. |
| p03 | Conflict abstention | Abstain (B) | Abstain (B), R2 | No. Missing the blocked side. |
| p04 | Release | Abstain (B) | Abstain (B), R3 | No. Missing a distinct clear original. |
| p05 | Stop | Abstain (C) | Abstain (C), R3 | Yes. The cited current row is blocked. |
| p06 | Conflict abstention | Abstain (A) | Abstain (A), R3 and R4 | Yes. One blocked and one clear current row. |

B's citations covered the evidence required for the expected action on **3/6** cases. Only **1/6** B responses were supported correct because B abstained even when its cited evidence supported stopping. A has no citation score. All raw labels also matched within pairs. The label varied across cases with the rotated mapping.

The two-current-block case reproduced #141's action failure even when the response consisted solely of an action. For these verified packets, the joint action-and-citation response requirement was unnecessary for the abstention pattern to occur. The experiment leaves open whether Gemma misclassifies the decision predicate or maps a correctly understood predicate to abstention. Results apply to six constructed pairs under the frozen model, prompts and decoding.

**Next action:** Freeze a minimal verified-facts probe that asks whether the current observations are unanimously blocked, then compare that answer with the action on the same facts. This tests whether the unanimity check fails before action selection.

## Evidence

The [protocol, fixtures, action-only prompt and grammar](shipment-gemma-action-protocol.md) were frozen at `2f42ecbcb7f20c348f7368834b131b358fceabd7`. The runner and tests were frozen at `298fbfa79d98c287753ab8f9aa704a12c4f3cdff` before inference. The [archive](shipment-gemma-action-replay.json) preserves source rows, verified facts, displayed legends, prompts, raw stdout and scores for all 12 trials. Its SHA-256 is `59f9f0e5a55ca33562e3b12379b79ff28dd2db54bb67db2c6b59b41e8983a375`.

An independent recount recomputed the current facts from source timestamps, checked identical displayed facts and legends per pair, decoded raw responses from those legends, and rederived action and citation scores. All 239 unit tests and the MCP demo passed locally, along with format, lint and compile checks on Python 3.12.14. This experiment did not qualify Gemma or open the #137/#138 packet comparison. Production code is unchanged.

## Exact replay and checks

Use the same external text GGUF and CPU runtime as #141. The [pinned acquisition commands](https://github.com/baileyrd/Adaptive-Autonomous-Memory-Subsystem/blob/0380e2ba868ecec7f8cedf44b386135146b3714a/docs/audit/shipment-gemma-results.md#exact-replay) place them in `/tmp/aams-gemma-artifacts`. Run this from the repository root after acquisition. The runner verifies artifact hashes and inference uses no network.

```sh
PYTHONPATH=src python scripts/evaluate_gemma_action_only.py \
  --cli /tmp/aams-gemma-artifacts/build/bin/llama-cli \
  --model /tmp/aams-gemma-artifacts/model.gguf > /tmp/aams-gemma-action-replay.json
cmp docs/audit/shipment-gemma-action-replay.json /tmp/aams-gemma-action-replay.json
sha256sum /tmp/aams-gemma-action-replay.json
```

```sh
python -m pip install '.[mcp]' ruff==0.14.6
ruff format --check src scripts tests
ruff check src scripts tests
python -m compileall -q src scripts tests
PYTHONPATH=src python -m unittest discover -s tests -v
python -m aams.demo
```
