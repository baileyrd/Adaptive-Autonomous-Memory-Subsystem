"""Hosted evaluation helper for two published quantized ONNX exports."""

import argparse
import json
from dataclasses import asdict
from hashlib import sha256
from pathlib import Path
from urllib.request import urlopen

from onnx_encoder import MODEL_FILE, TOKENIZER_FILE, Pins, Variant, verify

_VARIANTS = ("bge-q8", "minilm-l3-q8")
_ARTIFACTS = "https://huggingface.co"
_PINS = Path(__file__).with_name("onnx_variant_pins.json")


def read_remote(path):
    with urlopen(_ARTIFACTS + "/" + path, timeout=60) as response:
        content = response.read(128 * 1024 * 1024 + 1)
    if len(content) > 128 * 1024 * 1024:
        raise ValueError("Hosted artifact exceeds experiment budget")
    return content


def prepare(name, model_dir):
    manifest = Variant(**json.loads(_PINS.read_text())[name])
    for source, local in ((manifest.source_file, MODEL_FILE), (TOKENIZER_FILE, TOKENIZER_FILE)):
        payload = read_remote(f"{manifest.model}/resolve/{manifest.revision}/{source}")
        if sha256(payload).hexdigest() != manifest.files[local]:
            raise ValueError("Downloaded bytes do not match the committed pin")
        target = model_dir / local
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
    verify(model_dir, Pins(manifest.revision, manifest.files))
    manifest_path = model_dir / "manifest.json"
    manifest_path.write_text(json.dumps(asdict(manifest), indent=2) + "\n")
    print(
        f"::notice title=Variant {name} manifest::{json.dumps(asdict(manifest), separators=(',', ':'))}"
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("variant", choices=_VARIANTS)
    parser.add_argument("model_dir", type=Path)
    args = parser.parse_args()
    prepare(args.variant, args.model_dir)


if __name__ == "__main__":
    main()
