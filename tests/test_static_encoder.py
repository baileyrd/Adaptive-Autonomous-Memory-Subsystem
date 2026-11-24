"""Eval-only static encoder, its preparation and the BM25 rerank arm (#105). Stdlib only."""

import json
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from benchmark_onnx_cpu import STATIC_ARM, measure  # noqa: E402
from evaluate_semantic import seed, timestamp  # noqa: E402
from fusion import InvalidRun, check_validity, lexical_list, open_encoder, rerank_arm  # noqa: E402
from offline_experiment import load_groups, replay  # noqa: E402
from prepare_static_embedder import convert, embedding_rows, wordpiece_vocab  # noqa: E402
from static_encoder import (  # noqa: E402
    EMBEDDINGS_FILE,
    MANIFEST,
    MAX_TOKENS,
    StaticEmbeddingEncoder,
    WordPiece,
)

from aams.ranking import LexicalRanking  # noqa: E402
from aams.recall import CognitiveMemory, CognitiveNeed  # noqa: E402
from aams.storage import AccessContext, SQLiteMemoryStore  # noqa: E402
from aams.vector_index import RepresentationIndex  # noqa: E402

VOCAB = [
    "[UNK]",
    "comet",
    "tail",
    "ice",
    "sun",
    "orbit",
    "##s",
    "what",
    "the",
    "cafe",
    ",",
    "!",
    "probe",
]
# Two topics: comet/tail/ice share axis 0, sun/orbit share axis 1, function words axis 2.
ROWS = {
    "comet": [1.0, 0.0, 0.0, 0.1],
    "tail": [0.9, 0.0, 0.0, 0.0],
    "ice": [0.8, 0.1, 0.0, 0.0],
    "sun": [0.0, 1.0, 0.0, 0.0],
    "orbit": [0.0, 0.9, 0.0, 0.1],
}


def tokenizer_json(vocab=VOCAB, **overrides) -> bytes:
    config = {
        "model": {
            "type": "WordPiece",
            "unk_token": "[UNK]",
            "continuing_subword_prefix": "##",
            "max_input_chars_per_word": 100,
            "vocab": {token: index for index, token in enumerate(vocab)},
        },
        "normalizer": {
            "type": "BertNormalizer",
            "lowercase": True,
            "clean_text": True,
            "handle_chinese_chars": True,
            "strip_accents": None,
        },
        "pre_tokenizer": {"type": "BertPreTokenizer"},
    }
    config.update(overrides)
    return json.dumps(config).encode()


def safetensors(rows: list[list[float]], dtype: str = "F32", extra: bool = False) -> bytes:
    code = {"F32": "<f", "F16": "<e"}[dtype]
    data = b"".join(struct.pack(code, value) for row in rows for value in row)
    header = {
        "__metadata__": {"format": "pt"},
        "embeddings": {
            "dtype": dtype,
            "shape": [len(rows), len(rows[0])],
            "data_offsets": [0, len(data)],
        },
    }
    if extra:
        header["weights"] = {"dtype": dtype, "shape": [1], "data_offsets": [0, 4]}
    encoded = json.dumps(header).encode()
    return struct.pack("<Q", len(encoded)) + encoded + data


def table(vocab=VOCAB) -> list[list[float]]:
    return [ROWS.get(token, [0.0, 0.0, 0.3, 0.0]) for token in vocab]


def prepared(directory: Path, dtype: str = "F32") -> StaticEmbeddingEncoder:
    sources = {"model.safetensors": safetensors(table(), dtype), "tokenizer.json": tokenizer_json()}
    convert("test/static", "a" * 40, sources, directory)
    return StaticEmbeddingEncoder(directory)


def cosine(left, right) -> float:
    return sum(a * b for a, b in zip(left, right))


class WordPieceTest(unittest.TestCase):
    def setUp(self):
        self.tokenizer = WordPiece(VOCAB)

    def test_bert_normalization_punctuation_and_subwords(self):
        ids = self.tokenizer.ids("The  Comets,\tCAFÉ!")
        self.assertEqual([VOCAB[i] for i in ids], ["the", "comet", "##s", ",", "cafe", "!"])

    def test_unknown_and_overlong_words_become_one_unknown(self):
        self.assertEqual(self.tokenizer.ids("cometx"), [0])
        self.assertEqual(WordPiece(VOCAB, max_chars=4).ids("comet"), [0])

    def test_control_characters_dropped_and_cjk_isolated(self):
        self.assertEqual(self.tokenizer.ids("com\x00et\u200b"), [1])  # Control, format dropped.
        self.assertEqual([VOCAB[i] for i in self.tokenizer.ids("sun\x07")], ["sun"])
        self.assertEqual(self.tokenizer.ids("sun中ice"), [4, 0, 3])

    def test_vocabulary_must_be_unique_with_unknown(self):
        with self.assertRaises(ValueError):
            WordPiece(["a", "a", "[UNK]"])
        with self.assertRaises(ValueError):
            WordPiece(["a"])


class PrepareTest(unittest.TestCase):
    def test_refuses_tokenizers_and_tensors_it_cannot_reproduce(self):
        self.assertEqual(wordpiece_vocab(tokenizer_json()), VOCAB)
        with self.assertRaisesRegex(ValueError, "WordPiece"):
            wordpiece_vocab(tokenizer_json(model={"type": "Unigram"}))
        with self.assertRaisesRegex(ValueError, "uncased BERT"):
            wordpiece_vocab(tokenizer_json(pre_tokenizer={"type": "Whitespace"}))
        with self.assertRaisesRegex(ValueError, "exactly one"):
            embedding_rows(safetensors(table(), extra=True))
        rows, width, _, _ = embedding_rows(safetensors(table()))
        self.assertEqual((rows, width), (len(VOCAB), 4))

    def test_conversion_is_deterministic_and_rows_must_match_vocab(self):
        with tempfile.TemporaryDirectory() as one, tempfile.TemporaryDirectory() as two:
            first, second = prepared(Path(one)), prepared(Path(two))
            self.assertEqual(first.spec, second.spec)
            self.assertEqual(first.spec.dimensions, 4)
            self.assertEqual(first.spec.provider_id, "static")
            sources = {
                "model.safetensors": safetensors(table()[:-1]),
                "tokenizer.json": tokenizer_json(),
            }
            with self.assertRaisesRegex(ValueError, "vocabulary"):
                convert("test/static", "a" * 40, sources, Path(one) / "bad")


class StaticEncoderTest(unittest.TestCase):
    def test_encoding_is_unit_sum_pooled_and_drops_unknown_tokens(self):
        with tempfile.TemporaryDirectory() as directory:
            encoder = prepared(Path(directory))
            comet = encoder.encode("comet")
            self.assertAlmostEqual(cosine(comet, comet), 1.0, places=9)
            self.assertTrue(all(type(value) is float for value in comet))
            self.assertEqual(encoder.encode("comet zzz"), comet)  # Unknown token dropped.
            self.assertGreater(cosine(encoder.encode("ice tail"), comet), 0.95)
            self.assertLess(cosine(encoder.encode("sun orbit"), comet), 0.2)
            self.assertEqual(encoder.encode("zzz"), (0.0,) * 4)
            self.assertEqual(len(encoder.encode_ns), 5)

    def test_float16_sources_match_float32_within_quantization(self):
        with tempfile.TemporaryDirectory() as one, tempfile.TemporaryDirectory() as two:
            full, half = prepared(Path(one)), prepared(Path(two), "F16")
            self.assertGreater(cosine(full.encode("comet sun"), half.encode("comet sun")), 0.999)

    def test_truncation_window_counts_known_tokens(self):
        with tempfile.TemporaryDirectory() as directory:
            encoder = prepared(Path(directory))
            self.assertFalse(encoder.truncated("comet " * MAX_TOKENS + "zzz"))
            self.assertTrue(encoder.truncated("comet " * (MAX_TOKENS + 1)))
            self.assertEqual(encoder.encode("sun " * MAX_TOKENS + "comet"), encoder.encode("sun"))

    def test_tampered_or_mislabelled_files_are_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            prepared(Path(directory))
            path = Path(directory) / EMBEDDINGS_FILE
            path.write_bytes(path.read_bytes()[:-1] + b"\x01")
            with self.assertRaisesRegex(ValueError, "checksum"):
                StaticEmbeddingEncoder(Path(directory))
            manifest = json.loads((Path(directory) / MANIFEST).read_text())
            manifest["recipe"] = "other"
            (Path(directory) / MANIFEST).write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError, "recipe"):
                StaticEmbeddingEncoder(Path(directory))

    def test_open_encoder_dispatches_on_the_static_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            prepared(Path(directory))
            self.assertIsInstance(open_encoder(Path(directory)), StaticEmbeddingEncoder)


class RerankArmTest(unittest.TestCase):
    def build(self, directory: Path):
        store = SQLiteMemoryStore(directory / "s.sqlite3")
        seed(store, "lexical", "lab", 1, "what the comet xylem the the")
        seed(store, "semantic", "lab", 1, "what ice tail")
        seed(store, "future", "lab", 3, "what comet ice tail")
        seed(store, "private", "other", 1, "what comet ice tail")
        encoder = prepared(directory / "model")
        RepresentationIndex(store).rebuild(AccessContext("indexer", "lab", True), encoder)
        return store, encoder

    def test_rerank_reorders_only_visible_lexical_candidates(self):
        with tempfile.TemporaryDirectory() as directory:
            store, encoder = self.build(Path(directory))
            memory = CognitiveMemory(store, lexical_ranking=LexicalRanking.BM25)
            access = AccessContext("reader", "lab")
            need = CognitiveNeed("what comet", recorded_as_of=timestamp(2))
            self.assertEqual(lexical_list(memory, access, need), ["lexical", "semantic"])
            built = len(encoder.encode_ns)
            result = rerank_arm(memory, encoder, access, need, 3)
            found = [item["citations"][0]["evidence_id"] for item in result["items"]]
            self.assertEqual(result["retrieval"], {"mode": "fused", "status": "fresh"})
            self.assertEqual(set(found), {"lexical", "semantic"})  # No future or private.
            self.assertEqual(len(encoder.encode_ns) - built, 1)  # Only the query is encoded.

    def test_stale_index_and_unknown_queries_keep_lexical_order(self):
        with tempfile.TemporaryDirectory() as directory:
            store, encoder = self.build(Path(directory))
            memory = CognitiveMemory(store, lexical_ranking=LexicalRanking.BM25)
            access = AccessContext("reader", "lab")
            unknown = rerank_arm(memory, encoder, access, CognitiveNeed("xylem"), 3)
            self.assertEqual(unknown["retrieval"]["status"], "no_match")
            seed(store, "added", "lab", 1, "what comet")
            stale = rerank_arm(memory, encoder, access, CognitiveNeed("what comet"), 3)
            self.assertEqual(stale["retrieval"]["status"], "stale")

    def test_encoder_failure_invalidates_the_run(self):
        with tempfile.TemporaryDirectory() as directory:
            store, encoder = self.build(Path(directory))
            memory = CognitiveMemory(store, lexical_ranking=LexicalRanking.BM25)
            encoder.encode = lambda text: (_ for _ in ()).throw(RuntimeError("down"))
            with self.assertRaisesRegex(InvalidRun, "rerank"):
                rerank_arm(memory, encoder, AccessContext("r", "lab"), CognitiveNeed("comet"), 3)

    def test_replay_measures_rerank_without_leaks(self):
        groups = [group for group in load_groups() if group["split"] == "test_a"]
        with tempfile.TemporaryDirectory() as directory:
            encoder = prepared(Path(directory) / "model")
            rows = replay(
                Path(directory) / "a.sqlite3",
                groups,
                1,
                rankings=(LexicalRanking.BM25,),
                encoder=encoder,
            )
        self.assertEqual(check_validity(rows), [])
        for row in rows:
            measured = row["measurements"]["bm25_rerank"]
            self.assertEqual((measured["scope_leaks"], measured["time_leaks"]), (0, 0))
            self.assertLessEqual(measured["encoder_calls"], 1)


class StaticBenchmarkTest(unittest.TestCase):
    def test_static_arm_measures_rerank_serving(self):
        context = "The comet has an ice tail."
        groups = [
            {
                "domain": "article-0",
                "records": [["a0p0", "article-0", 15, context, "a0p0"]],
                "tasks": [{"query": "What is the comet tail?", "day": 15}],
            }
        ]
        with tempfile.TemporaryDirectory() as directory:
            prepared(Path(directory) / "model")
            path = Path(directory) / "groups.json"
            path.write_text(json.dumps(groups))
            args = SimpleNamespace(
                arm=STATIC_ARM,
                model=Path(directory) / "model",
                groups=path,
                vectors=Path(directory) / "vectors.json",
                repetitions=1,
                variant=None,
            )
            fields = measure(args)
            vectors = json.loads(args.vectors.read_text())
        self.assertEqual(vectors["rankings"], [["a0p0"]])
        self.assertEqual(fields["requests"], 1)
        self.assertIn("inference", fields["phase_ms"])

    def test_prepare_helper_imports_with_the_standard_library_only(self):
        result = subprocess.run(
            [sys.executable, str(SCRIPTS / "prepare_static_embedder.py"), "--help"],
            capture_output=True,
            text=True,
            check=False,
            env={"PYTHONPATH": str(SCRIPTS.parent / "src")},
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("potion-base-8m", result.stdout)


if __name__ == "__main__":
    unittest.main()
