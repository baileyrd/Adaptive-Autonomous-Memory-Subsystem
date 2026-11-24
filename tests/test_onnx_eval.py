"""Eval-only ONNX encoder and fusion arms (#83/#84). Runs without onnxruntime or numpy."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from evaluate_retrieval import evaluate_groups, versus_baseline  # noqa: E402
from evaluate_semantic import seed, timestamp  # noqa: E402
from fusion import (  # noqa: E402
    InvalidRun,
    check_validity,
    dense_list,
    lexical_list,
    open_encoder,
    rrf,
)
from offline_experiment import SPLITS, load_groups, replay  # noqa: E402
from onnx_encoder import (  # noqa: E402
    DIMENSIONS,
    MAX_TOKENS,
    MODEL_FILE,
    TOKENIZER_FILE,
    OnnxSentenceEncoder,
    Pins,
    Variant,
    l2_normalize,
    probe,
    verify,
)

from aams.contracts import (  # noqa: E402
    EpistemicState,
    Evidence,
    EvidenceStatus,
    MemoryFormation,
    MemoryKind,
)
from aams.ranking import LexicalRanking  # noqa: E402
from aams.recall import CognitiveMemory, CognitiveNeed  # noqa: E402
from aams.representations import DeterministicFixtureProvider, RepresentationSpec  # noqa: E402
from aams.storage import AccessContext, SQLiteMemoryStore  # noqa: E402
from aams.vector_index import RepresentationIndex  # noqa: E402

GOLDEN = Path(__file__).resolve().parent / "fixtures/offline_policy_v06_baseline.json"
GOLDEN_KEYS = (
    "mode",
    "status",
    "packet_digest",
    "satisfied",
    "recall",
    "ndcg",
    "scope_leaks",
    "time_leaks",
)


class FakeTokenizer:
    def __init__(self):
        self.truncation = None

    def enable_truncation(self, length):
        self.truncation = length

    def encode(self, text):
        words = text.split()
        kept = words[: self.truncation]
        return SimpleNamespace(
            ids=list(range(len(kept))),
            attention_mask=[1] * len(kept),
            type_ids=[0] * len(kept),
            overflowing=[object()] if len(words) > len(kept) else [],
        )


class FakeSession:
    """Token 0 (CLS) carries a distinct vector, so pooling errors are visible."""

    def __init__(self, inputs=("input_ids", "attention_mask")):
        self.inputs = inputs
        self.feeds = None

    def get_inputs(self):
        return [SimpleNamespace(name=name) for name in self.inputs]

    def run(self, _outputs, feeds):
        self.feeds = feeds
        cls = [3.0, 4.0] + [0.0] * (DIMENSIONS - 2)
        other = [0.0, 0.0, 9.0] + [0.0] * (DIMENSIONS - 3)
        return [[[cls] + [other] * (len(feeds["input_ids"][0]) - 1)]]


class Float32:
    """Stands in for a numpy scalar: float()-convertible but not a float."""

    def __init__(self, value):
        self.value = value

    def __float__(self):
        return float(self.value)


def pinned_directory(directory: Path) -> Pins:
    files = {MODEL_FILE: b"model-bytes", TOKENIZER_FILE: b"{}"}
    for name, payload in files.items():
        (directory / name).parent.mkdir(parents=True, exist_ok=True)
        (directory / name).write_bytes(payload)
    return Pins("rev1", {name: sha256(payload).hexdigest() for name, payload in files.items()})


def fake_encoder(directory: Path, session=None) -> OnnxSentenceEncoder:
    pins = pinned_directory(directory)
    return OnnxSentenceEncoder(
        directory, pins=pins, session=session or FakeSession(), tokenizer=FakeTokenizer()
    )


class FixtureEncoder(DeterministicFixtureProvider):
    """Encoder-shaped fixture: distinct spec, call log and token-window flag."""

    def __init__(self):
        super().__init__(DIMENSIONS)
        self._spec = RepresentationSpec("onnx-test", "fixture", "1", DIMENSIONS)
        self.encode_ns: list[int] = []
        self.down = False

    def encode(self, text):
        if self.down:
            raise RuntimeError("encoder down")
        self.encode_ns.append(1)
        return super().encode(text)

    def truncated(self, text):
        return False


def ingest(store, identifier, scope, formed_day, recorded_day, text):
    access = AccessContext("collector", scope, True)
    payload = text.encode()
    evidence = Evidence(
        identifier,
        scope,
        "station",
        "fixture:" + identifier,
        access.principal,
        timestamp(recorded_day),
        timestamp(recorded_day),
        EvidenceStatus.RECORDED,
        payload,
        "sha256:" + sha256(payload).hexdigest(),
    )
    formation = MemoryFormation(
        "f-" + identifier,
        scope,
        MemoryKind.EXPERIENCE,
        (identifier,),
        access.principal,
        timestamp(formed_day),
        EpistemicState.OBSERVED,
    )
    store.ingest(access, identifier, formation, (evidence,))


class EncoderTest(unittest.TestCase):
    def test_variant_metadata_is_strict_and_names_an_independent_space(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            pins = pinned_directory(path)
            recipe = dict(
                model="Xenova/example",
                revision="a" * 40,
                source_file="onnx/model_quantized.onnx",
                dimensions=DIMENSIONS,
                files=pins.files,
            )
            reference = fake_encoder(path)
            variant = OnnxSentenceEncoder(
                path,
                variant=Variant(pooling="cls", **recipe),
                session=FakeSession(),
                tokenizer=FakeTokenizer(),
            )
            self.assertEqual(reference.encode("same text"), variant.encode("same text"))
            self.assertNotEqual(reference.spec, variant.spec)
            with self.assertRaises(ValueError):
                Variant(pooling="unknown", **recipe)
            with self.assertRaises(ValueError):
                Variant(pooling="cls", **{**recipe, "revision": "main"})
            with self.assertRaises(ValueError):
                Variant(
                    pooling="cls",
                    **{
                        **recipe,
                        "files": {MODEL_FILE: "z" * 64, TOKENIZER_FILE: pins.files[TOKENIZER_FILE]},
                    },
                )

    def test_l2_normalize_returns_plain_unit_floats(self):
        values = l2_normalize([Float32(3.0), Float32(4.0)])
        self.assertEqual(values, (0.6, 0.8))
        self.assertTrue(all(type(value) is float for value in values))
        for bad in ([], [0.0, 0.0], [float("nan")]):
            with self.assertRaises(ValueError):
                l2_normalize(bad)

    def test_pins_are_verified_before_loading(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pins = pinned_directory(root)
            version = verify(root, pins)
            self.assertEqual(version, verify(root, pins))
            (root / MODEL_FILE).write_bytes(b"tampered")
            with self.assertRaisesRegex(ValueError, "checksum mismatch"):
                OnnxSentenceEncoder(root, pins=pins, session=FakeSession())
        with self.assertRaises(ValueError):
            Pins("rev1", {MODEL_FILE: "0" * 64})

    def test_cls_pooling_truncation_and_spec(self):
        with tempfile.TemporaryDirectory() as directory:
            session = FakeSession()
            encoder = fake_encoder(Path(directory), session)
            values = encoder.encode("one two three")
            self.assertEqual(values[:3], (0.6, 0.8, 0.0))
            self.assertEqual(set(session.feeds), {"input_ids", "attention_mask"})
            self.assertEqual(encoder._tokenizer.truncation, MAX_TOKENS)
            self.assertTrue(encoder.truncated("w " * (MAX_TOKENS + 1)))
            self.assertFalse(encoder.truncated("short"))
            self.assertEqual(len(encoder.encode_ns), 1)
            self.assertEqual(encoder.spec.provider_id, "onnx")
            self.assertTrue(encoder.spec.model_id.endswith("@rev1"))
            self.assertEqual(encoder.spec.dimensions, DIMENSIONS)
            probe(encoder)


class FusionTest(unittest.TestCase):
    def test_rrf_ranks_missing_ranks_and_ties(self):
        self.assertEqual(rrf([["a", "b", "c"], ["b", "c"]]), ["b", "c", "a"])
        self.assertEqual(rrf([["y"], ["x"]]), ["x", "y"])

    def test_validity_is_route_aware(self):
        def row(opt_in, arm, mode, status, calls=0):
            measured = {"mode": mode, "status": status, "encoder_calls": calls}
            return {"task": "t", "features": {"opt_in": opt_in}, "measurements": {arm: measured}}

        valid = [
            row(False, "bm25_guarded_onnx", "lexical", "default_lexical"),
            row(True, "bm25_guarded_onnx", "hybrid", "fresh", 1),
            row(True, "rrf_onnx", "fused", "no_match", 1),
        ]
        self.assertEqual(check_validity(valid), [])
        invalid = [
            row(False, "bm25_guarded_onnx", "lexical", "default_lexical", calls=1),
            row(True, "bm25_guarded_onnx", "lexical", "provider_unavailable"),
            row(True, "onnx", "dense", "stale"),
            row(False, "rrf_onnx", "fused", "default_lexical"),
        ]
        self.assertEqual(len(check_validity(invalid)), 4)

    def test_dense_list_uses_only_time_visible_scoped_citations(self):
        with tempfile.TemporaryDirectory() as directory:
            store = SQLiteMemoryStore(Path(directory) / "s.sqlite3")
            text = "orbital mechanics of the comet"
            seed(store, "visible", "lab", 1, text)
            seed(store, "future", "lab", 3, text)
            seed(store, "private", "other", 1, text)
            ingest(store, "late", "lab", 1, 3, text)  # Backdated formation, later evidence.
            encoder = FixtureEncoder()
            RepresentationIndex(store).rebuild(AccessContext("indexer", "lab", True), encoder)
            memory = CognitiveMemory(store)
            access = AccessContext("reader", "lab")
            need = CognitiveNeed(query=text, recorded_as_of=timestamp(2))
            ranked, status = dense_list(memory, encoder, access, need)
            self.assertEqual(status, "fresh")
            self.assertEqual([source for source, _ in ranked], ["visible"])
            fused = rrf([lexical_list(memory, access, need), [s for s, _ in ranked]])
            self.assertEqual(fused, ["visible"])
            later = CognitiveNeed(query=text, recorded_as_of=timestamp(3))
            ranked, _ = dense_list(memory, encoder, access, later)
            self.assertEqual({source for source, _ in ranked}, {"visible", "future", "late"})

    def test_lexical_list_depth_truncation_is_not_a_byte_cap(self):
        with tempfile.TemporaryDirectory() as directory:
            store = SQLiteMemoryStore(Path(directory) / "s.sqlite3")
            for index in range(25):
                seed(store, f"r{index:02d}", "lab", 1, f"shared term record {index}")
            memory = CognitiveMemory(store)
            ids = lexical_list(memory, AccessContext("reader", "lab"), CognitiveNeed("shared"))
            self.assertEqual(len(ids), 20)

    def test_backdated_formations_cannot_take_lexical_slots(self):
        with tempfile.TemporaryDirectory() as directory:
            store = SQLiteMemoryStore(Path(directory) / "s.sqlite3")
            for index in range(3):
                seed(store, f"visible-{index}", "lab", 1, "comet " * (index + 1) + "tail")
            memory = CognitiveMemory(store)
            access = AccessContext("reader", "lab")
            need = CognitiveNeed("comet", recorded_as_of=timestamp(2))
            before = lexical_list(memory, access, need)
            for index in range(25):  # IDs match the query; their evidence is recorded later.
                ingest(store, f"comet-{index}", "lab", 1, 3, "unrelated text")
            self.assertEqual(lexical_list(memory, access, need), before)
            self.assertEqual(set(before), {"visible-0", "visible-1", "visible-2"})


class GateTest(unittest.TestCase):
    def test_ndcg_delta_is_not_rounded_away(self):
        rows = [
            {"measurements": {"bm25_guarded": {"satisfied": True, "ndcg": 1.0}}}
            for _ in range(4000)
        ]
        for row in rows:
            row["measurements"]["arm"] = dict(row["measurements"]["bm25_guarded"])
        rows[0]["measurements"]["arm"]["ndcg"] = 0.87  # One rank 2 -> 3 style loss.
        details = [{"article": f"a{i % 10}"} for i in range(len(rows))]
        profiles = {name: {"ndcg_at_3": 1.0, "p95_ms": 1.0} for name in ("arm", "bm25_guarded")}
        self.assertLess(versus_baseline(rows, details, "arm", profiles)["ndcg_delta"], 0)


class ReplayTest(unittest.TestCase):
    def test_default_replay_matches_committed_v06_baseline(self):
        golden = json.loads(GOLDEN.read_text())["splits"]
        for split in SPLITS:
            groups = [group for group in load_groups() if group["split"] == split]
            with tempfile.TemporaryDirectory() as directory:
                rows = replay(
                    Path(directory) / "g.sqlite3", groups, 1, rankings=(LexicalRanking.BM25,)
                )
            actual = [
                {
                    "task": row["task"],
                    "arms": {
                        arm: {key: measured[key] for key in GOLDEN_KEYS}
                        for arm, measured in sorted(row["measurements"].items())
                    },
                }
                for row in rows
            ]
            self.assertEqual(actual, golden[split], split)

    def test_encoder_arms_validate_and_failures_invalidate_the_run(self):
        groups = [group for group in load_groups() if group["split"] == "test_a"]
        details = [
            {"article": group["domain"], "split": "heldout", "answer_beyond_preview": False}
            for group in groups
            for _ in group["tasks"]
        ]
        with tempfile.TemporaryDirectory() as directory:
            rows = replay(
                Path(directory) / "a.sqlite3",
                groups,
                1,
                rankings=(LexicalRanking.BM25,),
                encoder=FixtureEncoder(),
            )
        self.assertEqual(check_validity(rows), [])
        guarded = [row["measurements"]["bm25_guarded_onnx"] for row in rows]
        self.assertTrue(any(m["status"] == "default_lexical" for m in guarded))
        for measured in guarded:
            if measured["status"] == "default_lexical":
                self.assertEqual(measured["encoder_calls"], 0)
        for row in rows:
            self.assertEqual(row["measurements"]["rrf_onnx"]["scope_leaks"], 0)
            self.assertEqual(row["measurements"]["rrf_onnx"]["time_leaks"], 0)

        broken = FixtureEncoder()
        rebuild = RepresentationIndex.rebuild

        def rebuild_then_fail(index, access, provider):  # Index builds; every query fails.
            provider.down = False
            built = rebuild(index, access, provider)
            provider.down = True
            return built

        with mock.patch.object(RepresentationIndex, "rebuild", rebuild_then_fail):
            with self.assertRaises(InvalidRun):
                evaluate_groups(groups, details, 1, (LexicalRanking.BM25,), encoder=broken)

        def stale_for_encoder(index, access, provider):
            if isinstance(provider, FixtureEncoder):
                return SimpleNamespace(status="stale")
            return rebuild(index, access, provider)

        with mock.patch.object(RepresentationIndex, "rebuild", stale_for_encoder):
            with self.assertRaisesRegex(InvalidRun, "stale"):
                evaluate_groups(
                    groups, details, 1, (LexicalRanking.BM25,), encoder=FixtureEncoder()
                )

        class FailsDuringBuild(FixtureEncoder):
            def encode(self, text):
                raise RuntimeError("model crashed")

        with self.assertRaisesRegex(InvalidRun, "rebuild failed"):
            evaluate_groups(groups, details, 1, (LexicalRanking.BM25,), encoder=FailsDuringBuild())
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(InvalidRun, "load or probe"):
                open_encoder(Path(directory))  # No pinned files: refused, not a traceback.
        with self.assertRaisesRegex(ValueError, "BM25"):
            replay(Path("unused"), groups, 1, encoder=FixtureEncoder())


class MemoryProbeTest(unittest.TestCase):
    def test_baseline_phases_run_without_onnxruntime(self):
        context = "Comets orbit the sun. " * 4
        qa = {"question": "What do comets orbit?", "answers": [{"text": "sun", "answer_start": 17}]}
        data = {"data": [{"title": "Comet", "paragraphs": [{"context": context, "qas": [qa]}]}]}
        raw = json.dumps(data).encode()
        check = (
            "import runpy, sys; sys.argv = sys.argv[1:];"
            "runpy.run_path(sys.argv[0], run_name='__main__');"
            "assert 'onnxruntime' not in sys.modules and 'numpy' not in sys.modules"
        )
        env = {**os.environ, "PYTHONPATH": str(SCRIPTS.parent / "src")}
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "squad.json"
            source.write_bytes(raw)
            for phase in ("build", "serve"):
                args = ["--workload", "squad", "--arm", "baseline", "--phase", phase]
                args += ["--db", str(Path(directory) / "m.db"), "--data", str(source)]
                args += ["--expected-sha256", sha256(raw).hexdigest()]
                result = subprocess.run(
                    [sys.executable, "-c", check, str(SCRIPTS / "memory_probe.py"), *args],
                    capture_output=True,
                    text=True,
                    env=env,
                    check=False,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertGreater(json.loads(result.stdout)["peak_rss_kib"], 0)


if __name__ == "__main__":
    unittest.main()
