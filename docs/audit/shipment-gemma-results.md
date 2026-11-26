# Gemma 3 shipment qualification result (#125, #105)

**Gemma 3 4B IT Q4_K_M failed the frozen 18/18 gate.** It made the right action on 6/18 trials and supplied sufficient citations on 0/18. The runner stopped before constructing held-out histories or packets. The effect of #138 versus #137 on this model remains unmeasured.

| Required action | Trials | Emitted action | Correct action | Supported correct |
| --- | ---: | --- | ---: | ---: |
| Explicit stop | 6 | Abstain on all six | 0 | 0 |
| Release | 6 | Abstain on all six | 0 | 0 |
| Conflict abstention | 6 | Abstain on all six | 6 | 0 |

There were six missed explicit stops, six unnecessary holds, and zero unsafe or unsupported releases. Each trial contained the decisive evidence. In all six stop trials the cited row actually showed a current block. In all six release trials the model cited only one current original even though another distinct current slot was visible. In all six conflict trials the model cited one side of the visible conflict. Each history kept the same cited row across all three rotations.

The dominant pattern was **semantic abstention with a single citation**. The model emitted each of A, B and C six times, always choosing whichever letter meant abstain. This differs from #139's repeated choice of one raw letter. The trial outputs establish consistent abstention for this configuration. They leave open whether the model assembled an incomplete picture from the records or assembled the evidence and still defaulted to abstention under the action prompt.

**Next action:** Run a paired evidence-extraction diagnostic on the same frozen actor before trying another model. Ask it to list the latest states and original slots without choosing an action, then give it an independently verified list and ask for the rotated action and citations. The first stage tests whether it combines the visible records. The second tests its decision and citation behavior when the combination is supplied.

The [frozen protocol](shipment-gemma-protocol.md) and fixtures were committed at `376acc0349d8c98b76891d6c2147a9e3ce949a23` and the runner at `370362f947f22a1dfd2f1d0a83681e4febf39014` before inference. The runner reuses #139's transport, flags, response grammar and scorer. The [archive](shipment-gemma-replay.json) preserves all 18 rendered prompts, visible records, raw stdout, labels, citations and scores. An independent recount from the rendered prompts and raw responses agreed with the stored scores. Archive SHA-256 is `4b76100fb60a59703ff004d8c3fc8761937ef79b2cb7be1ecff972efbba76571`.

Validation on Python 3.12.14 and Linux x86-64 passed format, lint, compilation, all 235 tests and the MCP demo. The two new tests verify balanced full-evidence fixtures, all three rotations and stopping even with a 17/18 score. No production behavior changed.
## Exact replay

Download the text GGUF and CPU runtime once, then run qualification offline from the repository root. The pinned runtime can also be reused from #139. Weights remain external to the repository.

```sh
mkdir -p /tmp/aams-gemma-artifacts
gh release download b6500 --repo ggml-org/llama.cpp \
  --pattern llama-b6500-bin-ubuntu-x64.zip --dir /tmp/aams-gemma-artifacts
cd /tmp/aams-gemma-artifacts
echo '716803084e565fe779bc2d01ea576c418be141f8fabac97509bc6d7c3cd786b2  llama-b6500-bin-ubuntu-x64.zip' | sha256sum -c -
unzip -q llama-b6500-bin-ubuntu-x64.zip
python - <<'PY'
import hashlib
import json
import shutil
import urllib.request

repo = "ai/gemma3"
pin = "04a43a22e8d2003deda5acc262f68ec1005fa76c735a9962a8c77042a74a7d19"
auth = "https://auth.docker.io/token?service=registry.docker.io&scope=repository:"
with urllib.request.urlopen(auth + repo + ":pull") as response:
    token = json.load(response)["token"]
url = f"https://registry-1.docker.io/v2/{repo}/blobs/sha256:{pin}"
request = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
with urllib.request.urlopen(request) as response, open("model.gguf", "wb") as output:
    shutil.copyfileobj(response, output)
with open("model.gguf", "rb") as model:
    assert hashlib.file_digest(model, "sha256").hexdigest() == pin
PY
cd -
PYTHONPATH=src python scripts/evaluate_shipment_gemma.py \
  --cli /tmp/aams-gemma-artifacts/build/bin/llama-cli \
  --model /tmp/aams-gemma-artifacts/model.gguf > /tmp/aams-gemma-replay.json
cmp docs/audit/shipment-gemma-replay.json /tmp/aams-gemma-replay.json
sha256sum /tmp/aams-gemma-replay.json
```

```sh
python -m pip install '.[mcp]' ruff==0.14.6
ruff format --check src scripts tests
ruff check src scripts tests
python -m compileall -q src scripts tests
PYTHONPATH=src python -m unittest discover -s tests -v
python -m aams.demo
```
