"""Eval-only static embedding encoder for the v1.0 resource study (#105). Not part of the product.

A static model is a table with one vector per WordPiece token. A text is encoded by taking its
token vectors, summing them and L2-normalizing the result, with no neural runtime. The table is
stored as per-row symmetric int8 with one float32 scale per row, and read with the standard
library only, so numpy, tokenizers and onnxruntime are never imported.

Recipe: BERT normalization and pre-tokenization, greedy longest-match WordPiece, unknown tokens
dropped, first 512 remaining tokens kept, sum pooling, L2 normalization. Files are produced by
`prepare_static_embedder.py` and verified against the hashes in their manifest before use.
"""

import json
import sys
import unicodedata
from array import array
from collections import Counter
from dataclasses import dataclass
from hashlib import sha256
from math import fsum, sqrt
from pathlib import Path
from re import fullmatch
from time import perf_counter_ns

from onnx_encoder import EncodePhaseTiming, file_sha256

from aams.representations import RepresentationSpec

MANIFEST = "static_manifest.json"
VOCAB_FILE = "vocab.txt"
EMBEDDINGS_FILE = "embeddings.i8"
SCALES_FILE = "scales.f32"
DERIVED_FILES = (VOCAB_FILE, EMBEDDINGS_FILE, SCALES_FILE)
MAX_TOKENS = 512
RECIPE = "bert-wordpiece/drop-unk/first-512/sum/l2/int8-row-symmetric"


def _is_punctuation(char: str) -> bool:
    code = ord(char)
    if 33 <= code <= 47 or 58 <= code <= 64 or 91 <= code <= 96 or 123 <= code <= 126:
        return True
    return unicodedata.category(char).startswith("P")


def _is_cjk(code: int) -> bool:
    return (
        0x4E00 <= code <= 0x9FFF
        or 0x3400 <= code <= 0x4DBF
        or 0x20000 <= code <= 0x2A6DF
        or 0x2A700 <= code <= 0x2B73F
        or 0x2B740 <= code <= 0x2B81F
        or 0x2B820 <= code <= 0x2CEAF
        or 0xF900 <= code <= 0xFAFF
        or 0x2F800 <= code <= 0x2FA1F
    )


def _normalize(text: str) -> str:
    """BertNormalizer: clean text, isolate CJK, strip accents, lowercase (in that order)."""
    out = []
    for char in text:
        code = ord(char)
        if code == 0 or code == 0xFFFD:
            continue
        if char in "\t\n\r" or unicodedata.category(char) == "Zs":
            out.append(" ")
        elif unicodedata.category(char).startswith("C"):
            continue
        elif _is_cjk(code):
            out.append(f" {char} ")
        else:
            out.append(char)
    decomposed = unicodedata.normalize("NFD", "".join(out))
    return "".join(c for c in decomposed if unicodedata.category(c) != "Mn").lower()


def _pre_tokenize(text: str) -> list[str]:
    """BertPreTokenizer: split on whitespace and isolate every punctuation character."""
    words: list[str] = []
    for chunk in text.split():
        current = ""
        for char in chunk:
            if _is_punctuation(char):
                if current:
                    words.append(current)
                words.append(char)
                current = ""
            else:
                current += char
        if current:
            words.append(current)
    return words


class WordPiece:
    """Stdlib BERT WordPiece. Parity with `tokenizers` is checked in the evaluation job."""

    def __init__(
        self,
        vocab: list[str],
        *,
        unk_token: str = "[UNK]",
        prefix: str = "##",
        max_chars: int = 100,
    ) -> None:
        if len(set(vocab)) != len(vocab) or unk_token not in vocab:
            raise ValueError("Vocabulary must be unique and contain the unknown token")
        self._ids = {token: index for index, token in enumerate(vocab)}
        self.unk_id = self._ids[unk_token]
        self._prefix = prefix
        self._max_chars = max_chars

    def _word(self, word: str) -> list[int]:
        if len(word) > self._max_chars:
            return [self.unk_id]
        pieces, start = [], 0
        while start < len(word):
            end = len(word)
            while end > start:
                piece = word[start:end] if start == 0 else self._prefix + word[start:end]
                if piece in self._ids:
                    pieces.append(self._ids[piece])
                    break
                end -= 1
            if end == start:
                return [self.unk_id]
            start = end
        return pieces

    def ids(self, text: str) -> list[int]:
        """Token ids without special tokens, as `encode(text, add_special_tokens=False)`."""
        return [i for word in _pre_tokenize(_normalize(text)) for i in self._word(word)]


@dataclass(frozen=True, slots=True)
class StaticManifest:
    """Source pins, derived-file hashes and shape of one prepared static model."""

    model: str
    revision: str
    dimensions: int
    vocab_size: int
    source_files: dict[str, str]
    files: dict[str, str]
    recipe: str = RECIPE

    def __post_init__(self) -> None:
        if not fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", self.model):
            raise ValueError("Manifest requires an exact model repository")
        if not fullmatch(r"[0-9a-f]{40}", self.revision):
            raise ValueError("Manifest requires a full commit revision")
        if self.recipe != RECIPE or set(self.files) != set(DERIVED_FILES):
            raise ValueError("Unknown static recipe or file set")
        if not (1 <= self.dimensions <= 4096 and 1 <= self.vocab_size <= 1_000_000):
            raise ValueError("Static model shape out of bounds")
        hashes = (*self.files.values(), *self.source_files.values())
        if not self.source_files or any(not fullmatch(r"[0-9a-f]{64}", h) for h in hashes):
            raise ValueError("Manifest hashes must be hex sha256 digests")

    def version(self) -> str:
        identity = json.dumps(
            [self.model, self.revision, self.recipe, self.source_files, self.files],
            sort_keys=True,
        )
        return sha256(identity.encode()).hexdigest()[:12]


def load_manifest(directory: Path) -> StaticManifest:
    return StaticManifest(**json.loads((directory / MANIFEST).read_text()))


def _read_array(typecode: str, path: Path) -> array:
    """Read a file straight into a typed array, without an intermediate bytes copy."""
    values = array(typecode)
    size = path.stat().st_size
    if size % values.itemsize:
        raise ValueError(f"{path.name} is not a whole number of items")
    with path.open("rb") as handle:
        values.fromfile(handle, size // values.itemsize)
    return values


class StaticEmbeddingEncoder:
    """`RepresentationProvider` over a verified int8 static table. Records encode time."""

    def __init__(self, directory: Path, *, record_phases: bool = False) -> None:
        if sys.byteorder != "little":
            raise ValueError("Static model files are little-endian")
        manifest = load_manifest(directory)
        for name, expected in sorted(manifest.files.items()):
            if file_sha256(directory / name) != expected:
                raise ValueError(f"Static model checksum mismatch for {name}")
        vocab = (directory / VOCAB_FILE).read_text(encoding="utf-8").split("\n")
        self._tokenizer = WordPiece(vocab)
        width = manifest.dimensions
        self._table = _read_array("b", directory / EMBEDDINGS_FILE)
        self._scales = _read_array("f", directory / SCALES_FILE)
        shape = (len(vocab), len(self._scales), len(self._table))
        if shape != (manifest.vocab_size, manifest.vocab_size, manifest.vocab_size * width):
            raise ValueError("Static model files disagree on shape")
        self._width = width
        self._spec = RepresentationSpec(
            "static", f"{manifest.model}@{manifest.revision}", manifest.version(), width
        )
        self.encode_ns: list[int] = []
        self._record_phases = record_phases
        self.phase_timings_ns: list[EncodePhaseTiming] = []

    @property
    def spec(self) -> RepresentationSpec:
        return self._spec

    def _token_ids(self, text: str) -> list[int]:
        unk = self._tokenizer.unk_id
        return [i for i in self._tokenizer.ids(text) if i != unk]

    def truncated(self, text: str) -> bool:
        """Whether `text` has more than 512 known tokens (its tail is not encoded)."""
        return len(self._token_ids(text)) > MAX_TOKENS

    def encode(self, text: str) -> tuple[float, ...]:
        """Unit vector of the summed token rows; all zeros when no token is known."""
        if type(text) is not str:
            raise ValueError("Expected text input")
        start = perf_counter_ns()
        counts = Counter(self._token_ids(text)[:MAX_TOKENS])
        tokenized = perf_counter_ns()
        width, table, total = self._width, self._table, [0.0] * self._width
        for token, count in counts.items():
            weight = self._scales[token] * count
            row = table[token * width : (token + 1) * width]
            total = [acc + weight * value for acc, value in zip(total, row)]
        pooled = perf_counter_ns()
        norm = sqrt(fsum(value * value for value in total))
        values = tuple(value / norm for value in total) if norm else tuple(total)
        finished = perf_counter_ns()
        self.encode_ns.append(finished - start)
        if self._record_phases and len(self.phase_timings_ns) < 4096:
            self.phase_timings_ns.append(
                EncodePhaseTiming(
                    tokenized - start, 0, pooled - tokenized, finished - pooled, finished - start
                )
            )
        return values
