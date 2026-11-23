"""Eval-only ONNX sentence encoder for the #84 experiment. Not part of the product.

`BAAI/bge-small-en-v1.5`: CLS pooling, no query prefix, 512-token truncation, L2 normalized.
Model files are passed in by path and verified against `onnx_pins.json`. This module has no
network code. onnxruntime, tokenizers and numpy are imported lazily, so default CI can test the
pure-Python parts without them.
"""

import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from hashlib import sha256
from math import fsum, isfinite, sqrt
from pathlib import Path
from time import perf_counter_ns
from typing import Any

from aams.representations import RepresentationSpec

MODEL = "BAAI/bge-small-en-v1.5"
PINS = Path(__file__).with_name("onnx_pins.json")
MODEL_FILE = "onnx/model.onnx"
TOKENIZER_FILE = "tokenizer.json"
POOLING = "cls"
MAX_TOKENS = 512
DIMENSIONS = 384


@dataclass(frozen=True, slots=True)
class Pins:
    """A pinned model revision and the sha256 of every file the encoder loads."""

    revision: str
    files: dict[str, str]

    def __post_init__(self) -> None:
        if not self.revision or set(self.files) != {MODEL_FILE, TOKENIZER_FILE}:
            raise ValueError(
                f"Pins must name a revision and exactly {MODEL_FILE}, {TOKENIZER_FILE}"
            )
        if any(len(value) != 64 for value in self.files.values()):
            raise ValueError("Pinned hashes must be hex sha256 digests")


def load_pins(path: Path = PINS) -> Pins:
    data = json.loads(path.read_text())
    return Pins(data["revision"], dict(data["files"]))


def file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def verify(directory: Path, pins: Pins) -> str:
    """Refuse unpinned bytes; return the representation version for this model + pooling."""
    for name, expected in sorted(pins.files.items()):
        if file_sha256(directory / name) != expected:
            raise ValueError(f"Pinned checksum mismatch for {name}")
    identity = pins.files[MODEL_FILE] + pins.files[TOKENIZER_FILE] + POOLING
    return sha256(identity.encode()).hexdigest()[:12]


def l2_normalize(values: Sequence[Any]) -> tuple[float, ...]:
    """Plain-float unit vector; `DerivedVector` and recall reject numpy scalars."""
    floats = tuple(float(value) for value in values)
    if not floats or not all(isfinite(value) for value in floats):
        raise ValueError("Encoder produced an empty or non-finite vector")
    norm = sqrt(fsum(value * value for value in floats))
    if norm == 0:
        raise ValueError("Encoder produced a zero vector")
    return tuple(value / norm for value in floats)


def probe(encoder: "OnnxSentenceEncoder") -> None:
    """Fail fast unless one query encodes to a finite, unit-norm, 384-d tuple of floats."""
    values = encoder.encode("validity probe")
    if len(values) != DIMENSIONS or any(type(value) is not float for value in values):
        raise ValueError("Probe vector has the wrong shape or element type")
    if abs(fsum(value * value for value in values) - 1.0) > 1e-6:
        raise ValueError("Probe vector is not unit norm")


class OnnxSentenceEncoder:
    """`RepresentationProvider` over a pinned ONNX export. Records per-call encode time."""

    def __init__(
        self,
        directory: Path,
        *,
        pins: Pins | None = None,
        session: Any = None,
        tokenizer: Any = None,
        as_array: Callable[[list[list[int]]], Any] | None = None,
    ) -> None:
        pins = pins or load_pins()
        version = verify(directory, pins)
        if session is None:
            import numpy
            import onnxruntime

            options = onnxruntime.SessionOptions()
            options.intra_op_num_threads = 1
            session = onnxruntime.InferenceSession(
                str(directory / MODEL_FILE), options, providers=["CPUExecutionProvider"]
            )
            as_array = as_array or (lambda rows: numpy.array(rows, dtype=numpy.int64))
        if tokenizer is None:
            from tokenizers import Tokenizer

            tokenizer = Tokenizer.from_file(str(directory / TOKENIZER_FILE))
            tokenizer.no_padding()
        tokenizer.enable_truncation(MAX_TOKENS)
        self._session = session
        self._tokenizer = tokenizer
        self._as_array = as_array or (lambda rows: rows)
        self._inputs = frozenset(item.name for item in session.get_inputs())
        self._spec = RepresentationSpec("onnx", f"{MODEL}@{pins.revision}", version, DIMENSIONS)
        self.encode_ns: list[int] = []

    @property
    def spec(self) -> RepresentationSpec:
        return self._spec

    def truncated(self, text: str) -> bool:
        """Whether `text` exceeds the 512-token window (its tail is not encoded)."""
        return bool(self._tokenizer.encode(text).overflowing)

    def encode(self, text: str) -> tuple[float, ...]:
        if type(text) is not str:
            raise ValueError("Expected text input")
        start = perf_counter_ns()
        encoding = self._tokenizer.encode(text)
        feeds = {
            "input_ids": encoding.ids,
            "attention_mask": encoding.attention_mask,
            "token_type_ids": encoding.type_ids,
        }
        hidden = self._session.run(
            None,
            {name: self._as_array([row]) for name, row in feeds.items() if name in self._inputs},
        )[0]
        values = l2_normalize(hidden[0][0])  # CLS: batch 0, token 0.
        if len(values) != DIMENSIONS:
            raise ValueError("Unexpected encoder dimensions")
        self.encode_ns.append(perf_counter_ns() - start)
        return values
