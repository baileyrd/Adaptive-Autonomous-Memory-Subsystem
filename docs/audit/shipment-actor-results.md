# Shipment actor qualification result (#125)

**Qualification failed. The #137 versus #138 model comparison was not run.** Qwen2.5-3B-Instruct Q4_K_M produced **4/18 supported correct decisions** on the full-evidence diagnostic against a frozen **18/18** threshold. It chose the right action on 5/18 trials. No history passed all three action legends. The gate stopped before constructing held-out packets. This leaves the model-level effect of #138 unmeasured.

| Full-evidence action required | Trials | Correct action | Supported correct | Observed errors |
| --- | ---: | ---: | ---: | --- |
| Release | 6 | 2 | 2 | Four unnecessary holds |
| Explicit stop | 6 | 1 | 1 | Five missed stops, including two unsafe releases |
| Conflict abstention | 6 | 2 | 1 | Two unsafe releases, two stops, and one abstention citing only clear evidence |
| Total | 18 | 5 | 4 | Four unsafe releases, all unsupported by the packet |

The model emitted raw C on 16/18 trials and raw A on the other two. C meant abstain, release or stop depending on the legend. All 14 failures of supported correctness had sufficient evidence in the packet. In one conflict trial the model correctly abstained but cited two clear records and omitted the current blocked record. There are no paired selector gains, regressions or intervals because the comparison was gated off.

The [qualification archive](shipment-actor-replay.json) contains all rendered prompts and hashes, legends, packets, verbatim stdout, decoded actions, citations, scores and error attribution. The protocol and input hashes were frozen in `030351dd2eee7ee85fa61ce1eb5cd733d74965b3` and the runner in `9e678574ac1ddb27e8110de1af684e1440fa45ce`.

## Output capture incident

The initial runner used `--log-disable`. In llama.cpp b6500, generated tokens are printed through the same logger, so stdout was empty on all 18 trials. That diagnostic is preserved as [the transport failure archive](shipment-actor-transport-failure.json), SHA-256 `40299275b1727eb39a77c7215b5fb9a13153e197487673cd2c9ac03ccf679626`. It yielded no usable model actions. The interrupted repeat of that capture produced no completed archive. The repair in `c1ddc3b1a9d171a8461a2f8ba4668fb518de364f) enabled output and stripped only the runtime end marker before JSON parsing. It left the model, prompt, grammar, sampling, cases, scoring and threshold unchanged. The measured result above uses the repaired capture. [Pinned runtime token logging](https://github.com/ggml-org/llama.cpp/blob/b6500/tools/main/main.cpp#L734-L752)

The two completed qualification runs matched byte for byte. The archive SHA-256 is `6579f1f598006d709a7806a46a93e2279410299c75be23a6abfdade8b807e9d7`. This is a bounded result for one synthetic full-evidence diagnostic and one frozen actor configuration. The deterministic selector findings in #137 and #138 remain separate.
## Exact replay

Acquire the public GGUF and Linux CPU release once. No inference requires network access. The weights are external to the repository and to default CI. From the repository root:

```sh
mkdir -p /tmp/aams-actor-artifacts
gh release download b6500 --repo ggml-org/llama.cpp \
  --pattern llama-b6500-bin-ubuntu-x64.zip --dir /tmp/aams-actor-artifacts
cd /tmp/aams-actor-artifacts
echo '716803084e565fe779bc2d01ea576c418be141f8fabac97509bc6d7c3cd786b2  llama-b6500-bin-ubuntu-x64.zip' | sha256sum -c -
unzip -q llama-b6500-bin-ubuntu-x64.zip
python - <<'PY'
import hashlib
import json
import shutil
import urllib.request

repo = "ai/qwen2.5"
pin = "48f4925de3417c3e259c5b460024ec9907458c52c9a7aab81269a4befd473e5e"
token_url = "https://auth.docker.io/token?service=registry.docker.io&scope=repository:"
with urllib.request.urlopen(token_url + repo + ":pull") as response:
    public_token = json.load(response)["token"]
url = f"https://registry-1.docker.io/v2/{repo}/blobs/sha256:{pin}"
request = urllib.request.Request(url, headers={"Authorization": f"Bearer {public_token}"})
with urllib.request.urlopen(request) as response, open("model.gguf", "wb") as output:
    shutil.copyfileobj(response, output)
with open("model.gguf", "rb") as model:
    assert hashlib.file_digest(model, "sha256").hexdigest() == pin
PY
cd -
PYTHONPATH=src python scripts/evaluate_shipment_actor.py \
  --cli /tmp/aams-actor-artifacts/build/bin/llama-cli \
  --model /tmp/aams-actor-artifacts/model.gguf > /tmp/aams-shipment-actor-replay.json
cmp docs/audit/shipment-actor-replay.json /tmp/aams-shipment-actor-replay.json
sha256sum /tmp/aams-shipment-actor-replay.json
```

Local validation used Python 3.12.14 on x86-64 Intel Xeon Platinum 8370C. Format, lint, compilation, all 233 unit tests, and the MCP demo passed. The four new tests use no model download and cover release citation sufficiency, conflict citations, packet-gap attribution the qualification stop gate, and stdout framing.

```sh
python -m pip install '.[mcp]' ruff==0.14.6
ruff format --check src scripts tests
ruff check src scripts tests
python -m compileall -q src scripts tests
PYTHONPATH=src python -m unittest discover -s tests -v
python -m aams.demo
```

**Next action:** Independently replay the full-evidence qualification and verify the 14 failures against the raw responses before selecting any new actor.
