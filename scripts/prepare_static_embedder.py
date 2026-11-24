"""Hosted evaluation helper: fetch a pinned static model and write its int8 table (#105).

Stdlib only. With complete pins in `static_embedder_pins.json`, downloads the exact revision,
verifies every source byte, converts the float table to per-row int8 and writes the files
`static_encoder.py` reads plus their manifest. With an empty revision it only identifies:
it resolves the current revision, hashes the source files, prints proposed pins and exits 2,
so nothing unpinned is ever converted or measured.
"""

import argparse
import json
import struct
import sys
from array import array
from dataclasses import asdict
from hashlib import sha256
from pathlib import Path
from urllib.request import urlopen

from static_encoder import (
    EMBEDDINGS_FILE,
    MANIFEST,
    SCALES_FILE,
    VOCAB_FILE,
    StaticManifest,
    WordPiece,
)

HUB = "https://huggingface.co"
PINS = Path(__file__).with_name("static_embedder_pins.json")
SOURCE_FILES = ("model.safetensors", "tokenizer.json")
TENSOR = "embeddings"
FORMATS = {"F32": ("<f", 4), "F16": ("<e", 2)}
LIMIT = 512 * 1024 * 1024
REFERENCE_TOKENIZER = "source-tokenizer.json"


def read_remote(path: str) -> bytes:
    with urlopen(f"{HUB}/{path}", timeout=120) as response:
        content = response.read(LIMIT + 1)
    if len(content) > LIMIT:
        raise ValueError("Hosted artifact exceeds experiment budget")
    return content


def wordpiece_vocab(tokenizer_json: bytes) -> list[str]:
    """Vocabulary by id; refuses any tokenizer the stdlib WordPiece does not reproduce."""
    config = json.loads(tokenizer_json)
    model, normalizer = config.get("model") or {}, config.get("normalizer") or {}
    expected_model = {
        "type": "WordPiece",
        "unk_token": "[UNK]",
        "continuing_subword_prefix": "##",
        "max_input_chars_per_word": 100,
    }
    if any(model.get(key) != value for key, value in expected_model.items()):
        raise ValueError("Tokenizer model is not standard BERT WordPiece")
    if (
        normalizer.get("type") != "BertNormalizer"
        or normalizer.get("lowercase") is not True
        or normalizer.get("clean_text") is not True
        or normalizer.get("handle_chinese_chars") is not True
        or normalizer.get("strip_accents") not in (None, True)
        or (config.get("pre_tokenizer") or {}).get("type") != "BertPreTokenizer"
    ):
        raise ValueError("Tokenizer normalization is not uncased BERT")
    ids = model["vocab"]
    if sorted(ids.values()) != list(range(len(ids))):
        raise ValueError("Tokenizer ids are not contiguous")
    vocab = [""] * len(ids)
    for token, index in ids.items():
        if "\n" in token:
            raise ValueError("Tokenizer token contains a newline")
        vocab[index] = token
    WordPiece(vocab)  # Validates uniqueness and the unknown token.
    return vocab


def embedding_rows(safetensors: bytes) -> tuple[int, int, str, memoryview]:
    """(rows, width, struct format, raw bytes) of the single 2-D `embeddings` tensor."""
    (length,) = struct.unpack("<Q", safetensors[:8])
    header = json.loads(safetensors[8 : 8 + length])
    tensors = {name: spec for name, spec in header.items() if name != "__metadata__"}
    if set(tensors) != {TENSOR}:
        raise ValueError(f"Expected exactly one '{TENSOR}' tensor, found {sorted(tensors)}")
    spec = tensors[TENSOR]
    if spec["dtype"] not in FORMATS or len(spec["shape"]) != 2:
        raise ValueError("Embeddings must be a 2-D F32 or F16 tensor")
    rows, width = spec["shape"]
    code, size = FORMATS[spec["dtype"]]
    begin, end = (8 + length + offset for offset in spec["data_offsets"])
    if end - begin != rows * width * size or end > len(safetensors):
        raise ValueError("Embeddings byte range disagrees with its shape")
    return rows, width, code, memoryview(safetensors)[begin:end]


def quantize(rows: int, width: int, code: str, raw: memoryview) -> tuple[bytes, bytes]:
    """Per-row symmetric int8 values and float32 scales; deterministic for the same bytes."""
    size = struct.calcsize(code)
    table, scales = array("b"), array("f")
    for row in range(rows):
        chunk = raw[row * width * size : (row + 1) * width * size]
        values = [value for (value,) in struct.iter_unpack(code, chunk)]
        peak = max(map(abs, values))
        scale = peak / 127 if peak else 0.0
        table.extend(max(-127, min(127, round(v / scale))) if scale else 0 for v in values)
        scales.append(scale)
    return table.tobytes(), scales.tobytes()


def convert(name: str, revision: str, sources: dict[str, bytes], target: Path) -> StaticManifest:
    vocab = wordpiece_vocab(sources["tokenizer.json"])
    rows, width, code, raw = embedding_rows(sources["model.safetensors"])
    if rows != len(vocab):
        raise ValueError("Embedding rows do not match the vocabulary")
    table, scales = quantize(rows, width, code, raw)
    target.mkdir(parents=True, exist_ok=True)
    derived = {VOCAB_FILE: "\n".join(vocab).encode(), EMBEDDINGS_FILE: table, SCALES_FILE: scales}
    for file, payload in derived.items():
        (target / file).write_bytes(payload)
    manifest = StaticManifest(
        model=name,
        revision=revision,
        dimensions=width,
        vocab_size=rows,
        source_files={file: sha256(payload).hexdigest() for file, payload in sources.items()},
        files={file: sha256(payload).hexdigest() for file, payload in derived.items()},
    )
    (target / MANIFEST).write_text(json.dumps(asdict(manifest), indent=2) + "\n")
    # Kept for the tokenizer parity check only; the encoder never reads it.
    (target / REFERENCE_TOKENIZER).write_bytes(sources["tokenizer.json"])
    return manifest


def fetch(model: str, revision: str) -> dict[str, bytes]:
    return {file: read_remote(f"{model}/resolve/{revision}/{file}") for file in SOURCE_FILES}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("variant", choices=tuple(json.loads(PINS.read_text())))
    parser.add_argument("target", type=Path)
    args = parser.parse_args()
    if sys.byteorder != "little":
        parser.error("Static model files are little-endian")
    pin = json.loads(PINS.read_text())[args.variant]
    if not pin["revision"]:
        info = json.loads(read_remote(f"api/models/{pin['model']}"))
        sources = fetch(pin["model"], info["sha"])
        proposal = {
            **pin,
            "revision": info["sha"],
            "files": {file: sha256(data).hexdigest() for file, data in sources.items()},
        }
        print(f"::notice title=Proposed pins {args.variant}::{json.dumps(proposal)}")
        sys.exit(2)
    sources = fetch(pin["model"], pin["revision"])
    for file, payload in sources.items():
        if sha256(payload).hexdigest() != pin["files"][file]:
            raise SystemExit(f"Downloaded {file} does not match the committed pin")
    manifest = convert(pin["model"], pin["revision"], sources, args.target)
    print(f"::notice title=Static manifest {args.variant}::{json.dumps(asdict(manifest))}")


if __name__ == "__main__":
    main()
