"""Offline-only ONNX phase profiling; mock inference needs no optional dependencies."""

import tempfile
import unittest
from hashlib import sha256
from pathlib import Path

from scripts.onnx_encoder import (
    DIMENSIONS,
    MODEL_FILE,
    TOKENIZER_FILE,
    EncodePhaseTiming,
    OnnxSentenceEncoder,
    Pins,
)


class _Encoded:
    ids = [101, 102]
    attention_mask = [1, 1]
    type_ids = [0, 0]


class _Tokenizer:
    def enable_truncation(self, maximum):
        self.maximum = maximum

    def encode(self, text):
        if text == "raise":
            raise RuntimeError("tokenization failed")
        return _Encoded()


class _Input:
    def __init__(self, name):
        self.name = name


class _Session:
    def __init__(self):
        self.feeds = None

    def get_inputs(self):
        return [_Input("input_ids"), _Input("attention_mask")]

    def run(self, outputs, feeds):
        self.feeds = feeds
        vector = [0.0] * DIMENSIONS
        vector[0] = 1.0
        return [[[vector]]]


class OnnxPhaseTimingTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.directory = Path(folder.name)
        (self.directory / MODEL_FILE).parent.mkdir()
        (self.directory / MODEL_FILE).write_bytes(b"fake model")
        (self.directory / TOKENIZER_FILE).write_bytes(b"fake tokenizer")
        self.pins = Pins(
            "test-revision",
            {
                name: sha256((self.directory / name).read_bytes()).hexdigest()
                for name in (MODEL_FILE, TOKENIZER_FILE)
            },
        )

    def make_encoder(self, record_phases=False):
        return OnnxSentenceEncoder(
            self.directory,
            pins=self.pins,
            session=_Session(),
            tokenizer=_Tokenizer(),
            as_array=lambda rows: rows,
            record_phases=record_phases,
        )

    def test_opt_in_measurement_does_not_change_output(self):
        default = self.make_encoder()
        tracked = self.make_encoder(record_phases=True)
        self.assertEqual(
            default.encode("sensitive query text"), tracked.encode("sensitive query text")
        )
        self.assertEqual(len(default.encode_ns), 1)
        self.assertEqual(default.phase_timings_ns, [])
        self.assertEqual(len(tracked.phase_timings_ns), 1)
        sample = tracked.phase_timings_ns[0]
        self.assertEqual(
            sample.total_ns,
            sample.tokenize_ns + sample.prepare_ns + sample.inference_ns + sample.normalize_ns,
        )
        self.assertGreaterEqual(sample.total_ns, 0)
        self.assertEqual(
            tracked._session.feeds, {"input_ids": [[101, 102]], "attention_mask": [[1, 1]]}
        )
        self.assertNotIn("sensitive query text", str(sample))
        self.assertEqual(tracked.encode_ns[0] >= sample.total_ns, True)

    def test_failed_encode_never_records_partial_measurement(self):
        tracked = self.make_encoder(record_phases=True)
        with self.assertRaisesRegex(RuntimeError, "tokenization failed"):
            tracked.encode("raise")
        self.assertEqual(tracked.phase_timings_ns, [])
        self.assertEqual(tracked.encode_ns, [])

    def test_phase_contract_rejects_negative_and_inconsistent_values(self):
        self.assertEqual(EncodePhaseTiming(1, 2, 3, 4, 10).total_ns, 10)
        for args in ((-1, 2, 3, 4, 8), (1, 2, 3, 4, 9), (True, 2, 3, 4, 10)):
            with self.subTest(args=args), self.assertRaises(ValueError):
                EncodePhaseTiming(*args)
        with self.assertRaises(ValueError):
            self.make_encoder(record_phases=1)


if __name__ == "__main__":
    unittest.main()
