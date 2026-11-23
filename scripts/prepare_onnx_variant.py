"""Hosted evaluation helper for two published quantized ONNX exports."""

import argparse
import json
from dataclasses import asdict
from hashlib import sha1, sha256
from pathlib import Path
from urllib.request import urlopen

from onnx_encoder import DIMENSIONS, MODEL_FILE, TOKENIZER_FILE, Variant, verify

_REPOSITORIES = {
    "bge-q8": ("Xenova/bge-small-en-v1.5", "cls"),
    "minilm-l3-q8": ("Xenova/paraphrase-MiniLM-L3-v2", "mean"),
}
_ARTIFACTS = "https://huggingface.co"
_QUANTIZED = "onnx/model_quantized.onnx"
_PINS = Path(__file__).with_name("onnx_variant_pins.json")


def read_remote(path):
    with urlopen(_ARTIFACTS + "/" + path, timeout=60) as response:
        content = response.read(128 * 1024 * 1024 + 1)
    if len(content) > 128 * 1024 * 1024:
        raise ValueError("Hosted artifact exceeds experiment budget")
    return content


def prepare(name, model_dir):
    repository, pooling = _REPOSITORIES[name]
    pins = json.loads(_PINS.read_text()) if _PINS.exists() else {}
    pinned = Variant(**pins[name]) if name in pins else None
    revision = (
        pinned.revision if pinned else json.loads(read_remote(f"api/models/{repository}"))["sha"]
    )
    files = {}
    metadata = {}
    for directory in ("", "onnx"):
        entries = json.loads(read_remote(f"api/models/{repository}/tree/{revision}/{directory}"))
        metadata.update({entry["path"]: entry for entry in entries})
    for source, local in ((_QUANTIZED, MODEL_FILE), (TOKENIZER_FILE, TOKENIZER_FILE)):
        payload = read_remote(f"{repository}/resolve/{revision}/{source}")
        entry = metadata[source]
        digest = sha256(payload).hexdigest()
        upstream = entry["lfs"]["oid"] if entry.get("lfs") else entry["oid"]
        received = (
            digest if entry.get("lfs") else sha1(b"blob %d\0" % len(payload) + payload).hexdigest()
        )
        if upstream != received:
            raise ValueError("Downloaded bytes do not match upstream object ID")
        if pinned and pinned.files[local] != digest:
            raise ValueError("Downloaded bytes do not match the committed pin")
        target = model_dir / local
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
        files[local] = digest
    manifest = Variant(repository, revision, _QUANTIZED, pooling, DIMENSIONS, files)
    if pinned and pinned != manifest:
        raise ValueError("Pinned recipe differs from the verified artifact")
    from onnx_encoder import Pins

    verify(model_dir, Pins(manifest.revision, manifest.files))
    manifest_path = model_dir / "manifest.json"
    manifest_path.write_text(json.dumps(asdict(manifest), indent=2) + "\n")
    print(
        f"::notice title=Variant {name} manifest::{json.dumps(asdict(manifest), separators=(',', ':'))}"
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("variant", choices=tuple(_REPOSITORIES))
    parser.add_argument("model_dir", type=Path)
    args = parser.parse_args()
    prepare(args.variant, args.model_dir)


if __name__ == "__main__":
    main()
